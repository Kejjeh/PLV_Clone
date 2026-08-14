"""Build historical predictor-outcome panel for multi-year weight-optimization backtest.

Outputs (under data/research/historical_panel/):
  - actuals_by_year.parquet     one row per (mlbam_id, year, player_type)
  - predictor_panel.parquet     prior-year + same-year archetype predictors per (mlbam_id, year, player_type)
  - master_panel.parquet        join of the two, filtered for minimum exposure
  - coverage_report.md          per-year row counts, medians, missingness

Years: 2015-2025 (skip 2026 — partial season). 2020 retained but tagged covid_short=True.

Sources:
  - data/research/xfp_cache/hitters_multiyr_2015_2026.csv      : hitter season actuals (R/TB/RBI/BB/HBP/SB/K/PA + fp_total)
  - data/research/xfp_cache/pitcher_counting_stats_<year>.json : 2017-2026 pitcher season actuals (K/BB/H/ER/HBP/IP/GS/G/SV/HLD/TBF)
  - data/research/xfp_cache/statcast_<year>.parquet            : 2015-2016 pitcher event derivation (no SV/HLD)
  - data/research/hitter_ratings_master.csv
  - data/research/sp_ratings_master.csv
  - data/research/rp_ratings_master.csv

BrownU scoring:
  HIT  FP/g  = R + TB + RBI + BB + HBP + SB - K
  SP   FP/st = K + IP*3.3 - H - 2*ER - BB - HBP
  RP   FP/g  = K + IP*3.3 - H - 2*ER - BB - HBP + 5*SV + 3*HLD

Run:  python scripts/xfp/build_historical_panel.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.fantasy.scoring import pitcher_fp

ROOT = Path(r"c:/Users/Joshua/plv_clone")
CACHE = ROOT / "data" / "research" / "xfp_cache"
RES = ROOT / "data" / "research"
OUT = RES / "historical_panel"
OUT.mkdir(parents=True, exist_ok=True)

YEARS = list(range(2015, 2026))  # 2015-2025 inclusive; 2026 partial-season excluded from training
COVID_YEAR = 2020

HIT_PA_MIN = 100
PIT_IP_MIN = 30


# ---------------------------------------------------------------------------
# 1. HITTER ACTUALS
# ---------------------------------------------------------------------------
def build_hitter_actuals() -> pd.DataFrame:
    h = pd.read_csv(CACHE / "hitters_multiyr_2015_2026.csv")
    # required cols: batter, year, pa, r, tb, rbi, bb, hbp, sb, k, fp_total
    needed = ["batter", "year", "pa", "r", "tb", "rbi", "bb", "hbp", "sb", "k", "fp_total"]
    miss = [c for c in needed if c not in h.columns]
    if miss:
        raise RuntimeError(f"hitters_multiyr missing cols: {miss}")
    h = h[needed].copy()
    h = h[h["year"].isin(YEARS)]
    h["player_type"] = "H"
    h = h.rename(columns={"batter": "mlbam_id"})
    # Recompute FP from formula to ensure consistency
    h["fp_total_recalc"] = (
        h["r"].fillna(0) + h["tb"].fillna(0) + h["rbi"].fillna(0)
        + h["bb"].fillna(0) + h["hbp"].fillna(0) + h["sb"].fillna(0)
        - h["k"].fillna(0)
    )
    h["fp_per_pa"] = np.where(h["pa"] > 0, h["fp_total_recalc"] / h["pa"], np.nan)
    h["fp_per_game"] = h["fp_per_pa"] * 3.5  # league avg PA/g convention
    h["games_proxy"] = h["pa"] / 3.5
    h["covid_short"] = h["year"] == COVID_YEAR
    return h


# ---------------------------------------------------------------------------
# 2. PITCHER ACTUALS — JSON years (2017-2025) + statcast fallback (2015-2016)
# ---------------------------------------------------------------------------
def _ip_from_str(ip_val) -> float:
    """Convert IP like 12.2 (12 IP + 2 outs) -> 12.667"""
    if ip_val is None or pd.isna(ip_val):
        return 0.0
    try:
        f = float(ip_val)
        whole = int(f)
        frac = round((f - whole) * 10)  # 0, 1, or 2
        if frac >= 3:  # data anomaly
            return whole + 1.0
        return whole + frac / 3.0
    except Exception:
        return 0.0


def _pitcher_fp(K, IP, H, ER, BB, HBP, SV=0, HLD=0) -> float:
    return pitcher_fp(k=K, ip=IP, h=H, er=ER, bb=BB, hbp=HBP, sv=SV, hld=HLD)


def build_pitcher_actuals_json(year: int) -> pd.DataFrame:
    fp = CACHE / f"pitcher_counting_stats_{year}.json"
    if not fp.exists():
        return pd.DataFrame()
    with open(fp) as f:
        rows = json.load(f)
    df = pd.DataFrame(rows)
    df["ip_float"] = df["inningsPitched"].apply(_ip_from_str)
    df["fp_total"] = df.apply(
        lambda r: _pitcher_fp(
            r.get("strikeOuts", 0) or 0, r["ip_float"],
            r.get("hits", 0) or 0, r.get("earnedRuns", 0) or 0,
            r.get("baseOnBalls", 0) or 0, r.get("hitByPitch", 0) or 0,
            r.get("saves", 0) or 0, r.get("holds", 0) or 0,
        ), axis=1,
    )
    df["gs"] = df["gamesStarted"].fillna(0).astype(int)
    df["g"] = df["gamesPitched"].fillna(0).astype(int)
    df["sv_hld_missing"] = False
    # Classify: SP if gs/g >= 0.5 AND gs >= 5, else RP
    df["is_sp"] = (df["gs"] >= 5) & (df["gs"] / df["g"].clip(lower=1) >= 0.5)
    df["player_type"] = np.where(df["is_sp"], "SP", "RP")
    df["fp_per_start"] = np.where(df["gs"] > 0, df["fp_total"] / df["gs"], np.nan)
    df["fp_per_g"] = np.where(df["g"] > 0, df["fp_total"] / df["g"], np.nan)
    df = df.rename(columns={
        "pitcher": "mlbam_id", "season": "year",
        "strikeOuts": "k", "baseOnBalls": "bb", "hits": "h",
        "earnedRuns": "er", "hitByPitch": "hbp", "saves": "sv", "holds": "hld",
        "battersFaced": "tbf",
    })
    keep = ["mlbam_id", "year", "player_type", "g", "gs", "ip_float", "tbf",
            "k", "bb", "h", "er", "hbp", "sv", "hld",
            "fp_total", "fp_per_start", "fp_per_g", "sv_hld_missing"]
    df = df[keep]
    df["covid_short"] = year == COVID_YEAR
    return df


def build_pitcher_actuals_statcast(year: int) -> pd.DataFrame:
    """Derive pitcher actuals from statcast events for 2015-2016 where no JSON cache exists.

    Cannot recover SV/HLD from raw events — flag sv_hld_missing=True. ER approximated
    by post_bat_score deltas; acceptable for training-set use, RP rows for these years
    will be down-weighted by sv_hld_missing flag.
    """
    fp = CACHE / f"statcast_{year}.parquet"
    if not fp.exists():
        return pd.DataFrame()
    cols = ["pitcher", "game_pk", "events", "inning", "post_bat_score", "bat_score"]
    sc = pd.read_parquet(fp, columns=cols)
    sc = sc.dropna(subset=["pitcher", "events"])

    # Per (pitcher, game): count events, count outs by inning progression
    is_k = sc["events"].isin(["strikeout", "strikeout_double_play"])
    is_bb = sc["events"].isin(["walk"])  # intent_walk excluded — matches BrownU? include both safely
    is_ibb = sc["events"].isin(["intent_walk"])
    is_hbp = sc["events"].eq("hit_by_pitch")
    is_h = sc["events"].isin(["single", "double", "triple", "home_run"])
    # Out events for IP derivation
    out_events = {"field_out", "force_out", "grounded_into_double_play", "double_play",
                  "fielders_choice_out", "strikeout", "strikeout_double_play",
                  "sac_fly", "sac_bunt", "sac_fly_double_play", "triple_play"}
    sc["outs_made"] = sc["events"].isin(out_events).astype(int)
    # double_play / grounded_into_double_play actually 2 outs
    dp = sc["events"].isin(["grounded_into_double_play", "double_play", "strikeout_double_play",
                            "sac_fly_double_play"]).astype(int)
    sc["outs_made"] = sc["outs_made"] + dp  # +1 extra for dp
    tp = sc["events"].eq("triple_play").astype(int)
    sc["outs_made"] = sc["outs_made"] + 2 * tp
    # Earned runs proxy: post_bat_score - bat_score for scoring events
    sc["runs_on_play"] = (sc["post_bat_score"].fillna(0) - sc["bat_score"].fillna(0)).clip(lower=0)

    sc["k"] = is_k.astype(int)
    sc["bb"] = (is_bb | is_ibb).astype(int)
    sc["hbp"] = is_hbp.astype(int)
    sc["h"] = is_h.astype(int)

    pg = sc.groupby(["pitcher", "game_pk"]).agg(
        k=("k", "sum"), bb=("bb", "sum"), hbp=("hbp", "sum"), h=("h", "sum"),
        outs=("outs_made", "sum"), runs=("runs_on_play", "sum"),
    ).reset_index()
    # Approximate: GS = game where pitcher saw inning 1; G = any appearance
    first_inning = sc.groupby(["pitcher", "game_pk"])["inning"].min().reset_index()
    first_inning["is_start"] = first_inning["inning"] == 1
    pg = pg.merge(first_inning[["pitcher", "game_pk", "is_start"]], on=["pitcher", "game_pk"])

    season = pg.groupby("pitcher").agg(
        g=("game_pk", "nunique"),
        gs=("is_start", "sum"),
        k=("k", "sum"), bb=("bb", "sum"), hbp=("hbp", "sum"), h=("h", "sum"),
        outs=("outs", "sum"), er_proxy=("runs", "sum"),
    ).reset_index()
    season["ip_float"] = season["outs"] / 3.0
    # ER approx = 0.92 * total runs allowed (league avg unearned ~8%)
    season["er"] = (season["er_proxy"] * 0.92).round().astype(int)
    season["sv"] = 0
    season["hld"] = 0
    season["sv_hld_missing"] = True
    season["tbf"] = season["k"] + season["bb"] + season["hbp"] + season["h"] + (season["outs"] - season["k"])
    season["fp_total"] = season.apply(
        lambda r: _pitcher_fp(r["k"], r["ip_float"], r["h"], r["er"], r["bb"], r["hbp"], 0, 0), axis=1
    )
    season["is_sp"] = (season["gs"] >= 5) & (season["gs"] / season["g"].clip(lower=1) >= 0.5)
    season["player_type"] = np.where(season["is_sp"], "SP", "RP")
    season["fp_per_start"] = np.where(season["gs"] > 0, season["fp_total"] / season["gs"], np.nan)
    season["fp_per_g"] = np.where(season["g"] > 0, season["fp_total"] / season["g"], np.nan)
    season["year"] = year
    season["covid_short"] = False
    season = season.rename(columns={"pitcher": "mlbam_id"})
    keep = ["mlbam_id", "year", "player_type", "g", "gs", "ip_float", "tbf",
            "k", "bb", "h", "er", "hbp", "sv", "hld",
            "fp_total", "fp_per_start", "fp_per_g", "sv_hld_missing", "covid_short"]
    return season[keep]


def build_pitcher_actuals() -> pd.DataFrame:
    frames = []
    for y in YEARS:
        if y in (2015, 2016):
            df = build_pitcher_actuals_statcast(y)
        else:
            df = build_pitcher_actuals_json(y)
        if not df.empty:
            print(f"  pitcher actuals {y}: {len(df)} rows (SP={int((df.player_type=='SP').sum())}, RP={int((df.player_type=='RP').sum())})")
            frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 3. PREDICTOR PANEL
# ---------------------------------------------------------------------------
def load_ratings() -> dict:
    h = pd.read_csv(RES / "hitter_ratings_master.csv")
    sp = pd.read_csv(RES / "sp_ratings_master.csv")
    rp = pd.read_csv(RES / "rp_ratings_master.csv")
    return {"H": h, "SP": sp, "RP": rp}


def build_predictor_panel(actuals_h: pd.DataFrame, actuals_p: pd.DataFrame, ratings: dict) -> pd.DataFrame:
    out_rows = []

    # ---- Hitters ----
    h_ratings = ratings["H"][[
        "year", "batter", "OVERALL", "traj_flag", "OVERALL_career_pct", "age",
    ]].rename(columns={"batter": "mlbam_id"})
    h_ratings.columns = ["year", "mlbam_id", "arche_overall", "arche_traj", "arche_career_pct", "age"]

    # Build per-player time series for prior-year lookup
    hit_actuals_sorted = actuals_h[["mlbam_id", "year", "fp_per_pa", "fp_per_game", "pa"]].copy()
    hit_actuals_sorted = hit_actuals_sorted.sort_values(["mlbam_id", "year"])
    hit_actuals_sorted["prior_year_fp_per_game"] = hit_actuals_sorted.groupby("mlbam_id")["fp_per_game"].shift(1)
    hit_actuals_sorted["prior_year_pa"] = hit_actuals_sorted.groupby("mlbam_id")["pa"].shift(1)
    hit_actuals_sorted["prior_year_fp_per_pa"] = hit_actuals_sorted.groupby("mlbam_id")["fp_per_pa"].shift(1)

    # Prior-year archetype
    h_ratings_sorted = h_ratings.sort_values(["mlbam_id", "year"])
    for col in ["arche_overall", "arche_traj", "arche_career_pct"]:
        h_ratings_sorted[f"{col}_prior"] = h_ratings_sorted.groupby("mlbam_id")[col].shift(1)

    h_pred = hit_actuals_sorted[["mlbam_id", "year",
                                  "prior_year_fp_per_game", "prior_year_fp_per_pa", "prior_year_pa"]].merge(
        h_ratings_sorted, on=["mlbam_id", "year"], how="left",
    )
    h_pred["player_type"] = "H"
    out_rows.append(h_pred)

    # ---- SPs ----
    sp_ratings = ratings["SP"][[
        "year", "pitcher", "OVERALL", "traj_flag", "OVERALL_career_pct", "age",
    ]].rename(columns={"pitcher": "mlbam_id"})
    sp_ratings.columns = ["year", "mlbam_id", "arche_overall", "arche_traj", "arche_career_pct", "age"]

    sp_act = actuals_p[actuals_p["player_type"] == "SP"][["mlbam_id", "year", "fp_per_start", "gs"]].copy()
    sp_act = sp_act.sort_values(["mlbam_id", "year"])
    sp_act["prior_year_fp_per_start"] = sp_act.groupby("mlbam_id")["fp_per_start"].shift(1)
    sp_act["prior_year_gs"] = sp_act.groupby("mlbam_id")["gs"].shift(1)

    sp_ratings_sorted = sp_ratings.sort_values(["mlbam_id", "year"])
    for col in ["arche_overall", "arche_traj", "arche_career_pct"]:
        sp_ratings_sorted[f"{col}_prior"] = sp_ratings_sorted.groupby("mlbam_id")[col].shift(1)

    sp_pred = sp_act[["mlbam_id", "year", "prior_year_fp_per_start", "prior_year_gs"]].merge(
        sp_ratings_sorted, on=["mlbam_id", "year"], how="left",
    )
    sp_pred["player_type"] = "SP"
    out_rows.append(sp_pred)

    # ---- RPs ----
    rp_ratings = ratings["RP"][[
        "year", "pitcher", "OVERALL", "traj_flag", "OVERALL_career_pct", "age",
    ]].rename(columns={"pitcher": "mlbam_id"})
    rp_ratings.columns = ["year", "mlbam_id", "arche_overall", "arche_traj", "arche_career_pct", "age"]

    rp_act = actuals_p[actuals_p["player_type"] == "RP"][["mlbam_id", "year", "fp_per_g", "g"]].copy()
    rp_act = rp_act.sort_values(["mlbam_id", "year"])
    rp_act["prior_year_fp_per_g_rp"] = rp_act.groupby("mlbam_id")["fp_per_g"].shift(1)
    rp_act["prior_year_g_rp"] = rp_act.groupby("mlbam_id")["g"].shift(1)

    rp_ratings_sorted = rp_ratings.sort_values(["mlbam_id", "year"])
    for col in ["arche_overall", "arche_traj", "arche_career_pct"]:
        rp_ratings_sorted[f"{col}_prior"] = rp_ratings_sorted.groupby("mlbam_id")[col].shift(1)

    rp_pred = rp_act[["mlbam_id", "year", "prior_year_fp_per_g_rp", "prior_year_g_rp"]].merge(
        rp_ratings_sorted, on=["mlbam_id", "year"], how="left",
    )
    rp_pred["player_type"] = "RP"
    out_rows.append(rp_pred)

    # Stack — align columns
    all_cols = set()
    for df in out_rows:
        all_cols.update(df.columns)
    for i, df in enumerate(out_rows):
        for c in all_cols:
            if c not in df.columns:
                df[c] = np.nan
        out_rows[i] = df[sorted(all_cols)]
    return pd.concat(out_rows, ignore_index=True)


# ---------------------------------------------------------------------------
# 4. MASTER JOIN + COVERAGE
# ---------------------------------------------------------------------------
def build_master(actuals_h: pd.DataFrame, actuals_p: pd.DataFrame, predictors: pd.DataFrame) -> pd.DataFrame:
    # Build a unified actuals frame
    h = actuals_h.copy()
    h["player_type"] = "H"
    h_keep = ["mlbam_id", "year", "player_type", "pa", "fp_total_recalc", "fp_per_pa", "fp_per_game", "covid_short"]
    h = h[h_keep].rename(columns={"fp_total_recalc": "fp_total"})

    p = actuals_p.copy()
    p_keep = ["mlbam_id", "year", "player_type", "g", "gs", "ip_float", "tbf",
              "fp_total", "fp_per_start", "fp_per_g", "sv_hld_missing", "covid_short"]
    p = p[p_keep]

    actuals_all = pd.concat([h, p], ignore_index=True)

    master = actuals_all.merge(predictors, on=["mlbam_id", "year", "player_type"], how="left")

    # Exposure filter
    is_h = master["player_type"] == "H"
    is_p = master["player_type"].isin(["SP", "RP"])
    mask_keep = (is_h & (master["pa"] >= HIT_PA_MIN)) | (is_p & (master["ip_float"] >= PIT_IP_MIN))
    master = master[mask_keep].reset_index(drop=True)
    return master


def write_coverage(master: pd.DataFrame, predictors: pd.DataFrame, out_path: Path):
    lines = ["# Historical Panel Coverage Report", ""]
    lines.append(f"Years: {min(YEARS)}-{max(YEARS)} (2020 retained, tagged covid_short=True)")
    lines.append(f"Filters: hitter PA >= {HIT_PA_MIN}, pitcher IP >= {PIT_IP_MIN}")
    lines.append("")
    lines.append("## Per-year row counts (after exposure filter)")
    lines.append("")
    lines.append("| year | H | SP | RP | total |")
    lines.append("|------|---|----|----|-------|")
    for y in sorted(master["year"].unique()):
        sub = master[master["year"] == y]
        nh = int((sub["player_type"] == "H").sum())
        nsp = int((sub["player_type"] == "SP").sum())
        nrp = int((sub["player_type"] == "RP").sum())
        lines.append(f"| {y} | {nh} | {nsp} | {nrp} | {nh+nsp+nrp} |")

    lines.append("")
    lines.append("## Per-year median season FP totals (sanity check)")
    lines.append("")
    lines.append("| year | H median FP | SP median FP/start | RP median FP/g |")
    lines.append("|------|-------------|--------------------|--------------:|")
    for y in sorted(master["year"].unique()):
        sub = master[master["year"] == y]
        hm = sub.loc[sub["player_type"] == "H", "fp_per_game"].median()
        spm = sub.loc[sub["player_type"] == "SP", "fp_per_start"].median()
        rpm = sub.loc[sub["player_type"] == "RP", "fp_per_g"].median()
        lines.append(f"| {y} | {hm:.2f} | {spm:.2f} | {rpm:.2f} |")

    lines.append("")
    lines.append("## Predictor missingness (master panel)")
    lines.append("")
    pred_cols = [c for c in master.columns if c.startswith("prior_year_") or c.startswith("arche_")]
    lines.append("| predictor | missing % |")
    lines.append("|-----------|-----------|")
    for c in pred_cols:
        mp = master[c].isna().mean() * 100
        lines.append(f"| {c} | {mp:.1f}% |")

    lines.append("")
    lines.append("## Rookie handling")
    lines.append("")
    rookies = master["prior_year_fp_per_game"].isna() & master["prior_year_fp_per_start"].isna() & master["prior_year_fp_per_g_rp"].isna()
    n_rookie = int(rookies.sum())
    lines.append(f"Rows with no prior-year FP anchor (rookies / gap-year returns): **{n_rookie}** "
                 f"({100*n_rookie/len(master):.1f}% of panel).")
    lines.append("")
    lines.append("Suggested handling for the weight-fitter: **exclude from training** (anchor coefficient "
                 "is undefined). Hold them out as a separate evaluation set where archetype + age + career_pct "
                 "carry all the explanatory weight — those are exactly the cases where the archetype/historical-comp "
                 "lens is load-bearing rather than a tag layer on top of a strong prior-year anchor.")

    lines.append("")
    lines.append("## SV/HLD coverage")
    sv_missing = master[(master["player_type"] == "RP") & master["sv_hld_missing"]].shape[0]
    sv_total = (master["player_type"] == "RP").sum()
    lines.append(f"RP rows with sv_hld_missing=True (2015-2016, derived from statcast events): "
                 f"{sv_missing} / {sv_total}. Recommend down-weighting these in the RP weight fit, "
                 f"or restricting RP training to 2017+ only.")

    lines.append("")
    lines.append("## COVID-2020 handling")
    n_covid = int((master["year"] == COVID_YEAR).sum())
    lines.append(f"2020 rows retained ({n_covid} total) but tagged `covid_short=True`. "
                 f"Recommend either excluding 2020 from training or down-weighting season-totals by 162/60 ratio.")

    lines.append("")
    lines.append("## Effective N estimates for weight regression")
    n_h = ((master["player_type"] == "H") & ~rookies & (master["year"] != COVID_YEAR)).sum()
    n_sp = ((master["player_type"] == "SP") & ~rookies & (master["year"] != COVID_YEAR)).sum()
    sv_ok = master["sv_hld_missing"].fillna(True).astype(bool) == False
    n_rp = ((master["player_type"] == "RP") & ~rookies & (master["year"] != COVID_YEAR) & sv_ok).sum()
    lines.append(f"- Hitter weight regression: ~**{int(n_h)}** complete cases (excl. rookies + 2020)")
    lines.append(f"- SP weight regression: ~**{int(n_sp)}** complete cases (excl. rookies + 2020)")
    lines.append(f"- RP weight regression: ~**{int(n_rp)}** complete cases (excl. rookies + 2020 + sv_hld_missing)")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("[1/4] Building hitter actuals...")
    actuals_h = build_hitter_actuals()
    print(f"  hitters: {len(actuals_h)} player-years across {actuals_h['year'].nunique()} years")

    print("[2/4] Building pitcher actuals...")
    actuals_p = build_pitcher_actuals()
    print(f"  pitchers: {len(actuals_p)} player-years")

    actuals_combined = pd.concat([
        actuals_h.assign(player_type="H"),
        actuals_p,
    ], ignore_index=True, sort=False)
    actuals_combined.to_parquet(OUT / "actuals_by_year.parquet", index=False)
    print(f"  -> {OUT/'actuals_by_year.parquet'}")

    print("[3/4] Building predictor panel...")
    ratings = load_ratings()
    predictors = build_predictor_panel(actuals_h, actuals_p, ratings)
    predictors.to_parquet(OUT / "predictor_panel.parquet", index=False)
    print(f"  -> {OUT/'predictor_panel.parquet'} ({len(predictors)} rows)")

    print("[4/4] Building master panel + coverage report...")
    master = build_master(actuals_h, actuals_p, predictors)
    master.to_parquet(OUT / "master_panel.parquet", index=False)
    print(f"  -> {OUT/'master_panel.parquet'} ({len(master)} rows post-exposure filter)")

    write_coverage(master, predictors, OUT / "coverage_report.md")
    print(f"  -> {OUT/'coverage_report.md'}")
    print("\nDone.")


if __name__ == "__main__":
    main()
