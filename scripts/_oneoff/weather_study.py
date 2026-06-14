"""weather_study.py  — Leakage-safe SP weather study (BrownU 8-team points)

TWO goals:
  (A) Does game-level WEATHER / TEMPERATURE predict SP start performance?
      cold -> lower velo / less offense ; hot / Coors -> more offense.
  (B) Can temperature DE-CONFOUND our in-season velo-drop flag?
      Cold April games depress velo readings -> the "vs early-season"
      warmup confound in the velo work. We residualize per-start velo on
      temp and check if the velo-drop -> bust signal strengthens/weakens.

DATA:
  - statcast_{2023..2025}.parquet : pitch-level (release_speed, pitcher,
    game_pk, game_date, events, inning, post_bat_score, bat_score).
  - MLB Stats API feed/live keyed on game_pk -> gameData.weather {condition,
    temp, wind}, gameData.venue.name.

OUTPUT:
  - data/research/xfp_cache/game_weather_sample.csv  (cached weather)
  - data/research/validation_runs/weather_2026-06-13.md  (written by hand-off)

Run:  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/_oneoff/weather_study.py [--collect] [--max-games N]

--collect      : fetch weather from the API (otherwise reuse cache only)
--max-games N  : cap on NEW game_pks fetched this run (rate-friendly)
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
WEATHER_CSV = CACHE / "game_weather_sample.csv"
YEARS = [2023, 2024, 2025]

# Coors / Chase domes etc not needed; venue captured for context.
HEADERS = {"User-Agent": "Mozilla/5.0 (weather-study)"}


# ----------------------------------------------------------------------------
# Per-start SP FP + velo from statcast (matches build_historical_panel grain)
# ----------------------------------------------------------------------------
def _pitcher_fp(K, IP, H, ER, BB, HBP):
    return K + IP * 3.3 - H - 2 * ER - BB - HBP


def build_per_start(year: int) -> pd.DataFrame:
    """One row per (pitcher, game_pk) that is a START (saw inning 1).
    Columns: pitcher, game_pk, game_date, temp-less; FP + mean release_speed.
    """
    fp = CACHE / f"statcast_{year}.parquet"
    cols = ["pitcher", "game_pk", "game_date", "events", "inning",
            "post_bat_score", "bat_score", "release_speed"]
    sc = pd.read_parquet(fp, columns=cols)
    # velo: mean release_speed over ALL pitches the pitcher threw in the game
    velo = (sc.dropna(subset=["pitcher", "release_speed"])
              .groupby(["pitcher", "game_pk"])["release_speed"]
              .mean().rename("velo_game").reset_index())

    ev = sc.dropna(subset=["pitcher", "events"]).copy()
    is_k = ev["events"].isin(["strikeout", "strikeout_double_play"])
    is_bb = ev["events"].isin(["walk"])
    is_ibb = ev["events"].isin(["intent_walk"])
    is_hbp = ev["events"].eq("hit_by_pitch")
    is_h = ev["events"].isin(["single", "double", "triple", "home_run"])
    out_events = {"field_out", "force_out", "grounded_into_double_play", "double_play",
                  "fielders_choice_out", "strikeout", "strikeout_double_play",
                  "sac_fly", "sac_bunt", "sac_fly_double_play", "triple_play"}
    ev["outs_made"] = ev["events"].isin(out_events).astype(int)
    dp = ev["events"].isin(["grounded_into_double_play", "double_play", "strikeout_double_play",
                            "sac_fly_double_play"]).astype(int)
    ev["outs_made"] = ev["outs_made"] + dp
    tp = ev["events"].eq("triple_play").astype(int)
    ev["outs_made"] = ev["outs_made"] + 2 * tp
    ev["runs_on_play"] = (ev["post_bat_score"].fillna(0) - ev["bat_score"].fillna(0)).clip(lower=0)
    ev["k"] = is_k.astype(int)
    ev["bb"] = (is_bb | is_ibb).astype(int)
    ev["hbp"] = is_hbp.astype(int)
    ev["h"] = is_h.astype(int)

    pg = ev.groupby(["pitcher", "game_pk"]).agg(
        k=("k", "sum"), bb=("bb", "sum"), hbp=("hbp", "sum"), h=("h", "sum"),
        outs=("outs_made", "sum"), runs=("runs_on_play", "sum"),
        game_date=("game_date", "first"),
    ).reset_index()
    first_inning = ev.groupby(["pitcher", "game_pk"])["inning"].min().reset_index()
    first_inning["is_start"] = first_inning["inning"] == 1
    pg = pg.merge(first_inning[["pitcher", "game_pk", "is_start"]], on=["pitcher", "game_pk"])
    pg = pg[pg["is_start"]].copy()  # STARTS only

    pg["ip"] = pg["outs"] / 3.0
    pg["er"] = (pg["runs"] * 0.92).round()  # league avg ~8% unearned
    pg["fp"] = _pitcher_fp(pg["k"], pg["ip"], pg["h"], pg["er"], pg["bb"], pg["hbp"])
    pg = pg.merge(velo, on=["pitcher", "game_pk"], how="left")
    pg["year"] = year
    # require a real start: at least ~9 outs (3 IP) to avoid openers/ejections noise
    pg = pg[pg["outs"] >= 9].copy()
    return pg[["pitcher", "game_pk", "game_date", "year", "fp", "ip", "k", "bb",
               "h", "er", "outs", "velo_game"]]


# ----------------------------------------------------------------------------
# Weather collection
# ----------------------------------------------------------------------------
def fetch_weather(game_pk: int):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    gd = d.get("gameData", {})
    w = gd.get("weather", {}) or {}
    v = gd.get("venue", {}) or {}
    return {
        "game_pk": game_pk,
        "condition": w.get("condition"),
        "temp": w.get("temp"),
        "wind": w.get("wind"),
        "venue": v.get("name"),
        "venue_id": v.get("id"),
    }


def collect_weather(game_pks, max_games=None, sleep=0.12):
    """Fetch weather for game_pks not already cached; append to WEATHER_CSV."""
    have = set()
    if WEATHER_CSV.exists():
        have = set(pd.read_csv(WEATHER_CSV)["game_pk"].astype(int).tolist())
    todo = [g for g in game_pks if int(g) not in have]
    if max_games:
        todo = todo[:max_games]
    print(f"[collect] cached={len(have)} todo_this_run={len(todo)}", flush=True)
    rows, ok, fail = [], 0, 0
    for i, g in enumerate(todo):
        try:
            rows.append(fetch_weather(int(g)))
            ok += 1
        except Exception as e:
            fail += 1
            rows.append({"game_pk": int(g), "condition": None, "temp": None,
                         "wind": None, "venue": None, "venue_id": None})
            if fail <= 5:
                print(f"  fail {g}: {e}", flush=True)
        time.sleep(sleep)
        if (i + 1) % 250 == 0:
            print(f"  ...{i+1}/{len(todo)} ok={ok} fail={fail}", flush=True)
            # incremental flush
            _append(rows)
            rows = []
    if rows:
        _append(rows)
    print(f"[collect] done ok={ok} fail={fail}", flush=True)


def _append(rows):
    df = pd.DataFrame(rows)
    if WEATHER_CSV.exists():
        df.to_csv(WEATHER_CSV, mode="a", header=False, index=False)
    else:
        df.to_csv(WEATHER_CSV, index=False)


def load_weather():
    if not WEATHER_CSV.exists():
        return pd.DataFrame()
    w = pd.read_csv(WEATHER_CSV)
    w = w.dropna(subset=["temp"])
    w["temp"] = pd.to_numeric(w["temp"], errors="coerce")
    w = w.dropna(subset=["temp"])
    w["game_pk"] = w["game_pk"].astype(int)
    # de-dup (in case of double-append)
    w = w.drop_duplicates(subset=["game_pk"])
    return w


# ----------------------------------------------------------------------------
# Analyses
# ----------------------------------------------------------------------------
def pearson(x, y):
    m = (~pd.isna(x)) & (~pd.isna(y))
    if m.sum() < 30:
        return np.nan, int(m.sum())
    return float(np.corrcoef(x[m], y[m])[0, 1]), int(m.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.12)
    args = ap.parse_args()

    # Build per-start panel across years
    print("[panel] building per-start SP panel from statcast ...", flush=True)
    panel = pd.concat([build_per_start(y) for y in YEARS], ignore_index=True)
    print(f"[panel] starts={len(panel)} pitchers={panel['pitcher'].nunique()}", flush=True)

    if args.collect:
        # collect weather for the game_pks that appear in our starts panel first
        gpks = panel["game_pk"].drop_duplicates().tolist()
        collect_weather(gpks, max_games=args.max_games, sleep=args.sleep)

    w = load_weather()
    print(f"[weather] usable rows w/ temp = {len(w)}", flush=True)
    if len(w) == 0:
        print("NO WEATHER COLLECTED — run with --collect")
        return

    df = panel.merge(w[["game_pk", "temp", "condition", "venue", "venue_id"]],
                     on="game_pk", how="inner")
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["month"] = df["game_date"].dt.month
    print(f"[merge] starts with weather = {len(df)} "
          f"({df['game_pk'].nunique()} games, {df['pitcher'].nunique()} pitchers)", flush=True)

    out = []
    out.append("## (A) Per-start weather effects\n")
    out.append(f"n_starts_with_weather = {len(df)}; "
               f"n_games = {df['game_pk'].nunique()}; "
               f"temp range {df['temp'].min():.0f}-{df['temp'].max():.0f}F, "
               f"mean {df['temp'].mean():.1f}F\n")

    r_fp, n_fp = pearson(df["temp"].values, df["fp"].values)
    r_velo, n_velo = pearson(df["temp"].values, df["velo_game"].values)
    r_k, _ = pearson(df["temp"].values, df["k"].values)
    r_h, _ = pearson(df["temp"].values, df["h"].values)
    r_er, _ = pearson(df["temp"].values, df["er"].values)
    out.append(f"temp <-> SP FP/start : r = {r_fp:+.4f}  (n={n_fp})")
    out.append(f"temp <-> mean velo   : r = {r_velo:+.4f}  (n={n_velo})")
    out.append(f"temp <-> K           : r = {r_k:+.4f}")
    out.append(f"temp <-> H allowed   : r = {r_h:+.4f}")
    out.append(f"temp <-> ER allowed  : r = {r_er:+.4f}\n")

    # cold vs warm buckets
    df["tbucket"] = pd.cut(df["temp"], [0, 50, 60, 70, 80, 200],
                           labels=["<50", "50-60", "60-70", "70-80", "80+"])
    g = df.groupby("tbucket", observed=True).agg(
        n=("fp", "size"), fp=("fp", "mean"), velo=("velo_game", "mean"),
        k=("k", "mean"), h=("h", "mean"), er=("er", "mean")).round(3)
    out.append("By temp bucket:\n" + g.to_string() + "\n")

    # Coors callout
    coors = df[df["venue"].astype(str).str.contains("Coors", na=False)]
    if len(coors):
        out.append(f"Coors Field: n={len(coors)} starts, mean FP={coors['fp'].mean():.2f} "
                   f"(vs non-Coors {df[~df.index.isin(coors.index)]['fp'].mean():.2f}), "
                   f"mean temp={coors['temp'].mean():.1f}F\n")

    # ------------------------------------------------------------------
    # (B) DE-CONFOUND velo-drop flag
    # ------------------------------------------------------------------
    out.append("\n## (B) De-confound: does temp explain early-season velo dip?\n")
    # per-pitcher-year season-mean velo (as-of-safe enough: we residualize the
    # RAW per-start velo against temp and compare velo-drop signals).
    df = df.dropna(subset=["velo_game"]).copy()
    df["py"] = df["pitcher"].astype(str) + "_" + df["year"].astype(str)
    # season mean velo per pitcher-year (full-season baseline = the "vs season baseline" anchor)
    season_mean = df.groupby("py")["velo_game"].transform("mean")
    df["velo_drop_raw"] = df["velo_game"] - season_mean  # negative = dip vs own season

    # Cold-game velo dip: regress velo on temp WITHIN pitcher-year (de-mean both)
    df["velo_dm"] = df["velo_game"] - df.groupby("py")["velo_game"].transform("mean")
    df["temp_dm"] = df["temp"] - df.groupby("py")["temp"].transform("mean")
    m = (~df["velo_dm"].isna()) & (~df["temp_dm"].isna())
    beta = np.polyfit(df.loc[m, "temp_dm"], df.loc[m, "velo_dm"], 1)[0]
    r_within, _ = pearson(df["temp_dm"].values, df["velo_dm"].values)
    out.append(f"Within-pitcher-year velo vs temp: slope = {beta:+.4f} mph/F, "
               f"r = {r_within:+.4f}")
    out.append(f"  => a 30F-colder game costs ~{abs(beta)*30:.2f} mph off the start's mean velo.\n")

    # Early-season confound: April starts velo vs rest-of-season
    apr = df[df["month"] == 4]
    rest = df[df["month"] != 4]
    out.append(f"April starts mean velo_drop_raw = {apr['velo_drop_raw'].mean():+.3f} mph "
               f"(n={len(apr)}); non-April = {rest['velo_drop_raw'].mean():+.3f} (n={len(rest)})")
    out.append(f"April mean temp = {apr['temp'].mean():.1f}F vs non-April {rest['temp'].mean():.1f}F\n")

    # Residualize velo_drop on temp -> temp-adjusted velo drop
    # velo_adj = velo_game - beta*(temp - season_temp_mean): removes the cold-game component
    season_temp = df.groupby("py")["temp"].transform("mean")
    df["velo_game_tempadj"] = df["velo_game"] - beta * (df["temp"] - season_temp)
    season_mean_adj = df.groupby("py")["velo_game_tempadj"].transform("mean")
    df["velo_drop_tempadj"] = df["velo_game_tempadj"] - season_mean_adj

    apr2 = df[df["month"] == 4]
    out.append(f"After temp-adjust, April velo_drop = {apr2['velo_drop_tempadj'].mean():+.3f} mph "
               f"(was {apr['velo_drop_raw'].mean():+.3f}).")
    frac = 0.0
    if apr["velo_drop_raw"].mean() != 0:
        frac = 1 - apr2["velo_drop_tempadj"].mean() / apr["velo_drop_raw"].mean()
    out.append(f"  => temp explains ~{frac*100:.0f}% of the April velo dip vs own season.\n")

    # Does the velo-drop -> bust signal change after temp adjustment?
    # bust = FP < 5 (BrownU replacement-ish). Compare correlation of velo_drop with FP,
    # and the bust-rate gap between biggest velo-drop quintile vs rest, raw vs temp-adj.
    df["bust"] = (df["fp"] < 5).astype(int)
    r_drop_fp_raw, _ = pearson(df["velo_drop_raw"].values, df["fp"].values)
    r_drop_fp_adj, _ = pearson(df["velo_drop_tempadj"].values, df["fp"].values)
    out.append(f"velo_drop_raw     <-> FP : r = {r_drop_fp_raw:+.4f}")
    out.append(f"velo_drop_tempadj <-> FP : r = {r_drop_fp_adj:+.4f}\n")

    def bust_gap(col):
        q = df[col].quantile(0.20)  # bottom 20% = biggest velo drops
        lo = df[df[col] <= q]["bust"].mean()
        hi = df[df[col] > q]["bust"].mean()
        return lo, hi, lo - hi

    lo_r, hi_r, gap_r = bust_gap("velo_drop_raw")
    lo_a, hi_a, gap_a = bust_gap("velo_drop_tempadj")
    out.append(f"Bust rate (FP<5): biggest velo-drop quintile vs rest")
    out.append(f"  RAW drop      : {lo_r:.3f} vs {hi_r:.3f}  (gap {gap_r:+.3f})")
    out.append(f"  TEMP-ADJ drop : {lo_a:.3f} vs {hi_a:.3f}  (gap {gap_a:+.3f})")
    strengthen = "STRENGTHENS" if abs(gap_a) > abs(gap_r) else "weakens/unchanged"
    out.append(f"  => after removing cold-game velo, the velo-drop->bust signal {strengthen}.\n")

    report = "\n".join(out)
    print("\n" + report)
    # stash for the markdown writer
    (CACHE / "_weather_study_report.txt").write_text(report, encoding="utf-8")
    return report


if __name__ == "__main__":
    main()
