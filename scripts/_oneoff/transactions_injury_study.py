"""
transactions_injury_study.py — Feasibility + validation study for richer
INJURY / TRANSACTION data in the BrownU fantasy model.

GOAL: do better than ESPN return-date guesses by measuring the *post-IL-return
ramp penalty* — does a starting pitcher underperform his own pre-IL baseline
in his first 1-3 starts back, and is velo suppressed early? If so, IL-return
stashes (Snell/Glasnow pattern) should be valued with a discount on their
first couple of starts.

DATA SOURCE (already collected by build_il_history.py):
  data/research/xfp_cache/il_transactions_{2023,2024,2025}.json
    each record: {date, pid, name, desc}
    desc carries the IL category (10/15/60-day) AND, frequently, the injury
    text ("Tommy John surgery", "right elbow ... repair", "... strain", etc).

PER-START ACTUALS:
  MLB Stats API pitching gameLog per pitcher-season. We compute BrownU SP FP:
    FP = K + IP*3.3 - H - 2*ER - BB - HBP

VELO:
  Joined from the rolling panel (rolling_pitchers_2018_2026.csv,
  avg_velo_last21 at weekly cutoffs) — the closest cutoff on each side of the
  return date. (gameLog has no velo; this is the cheapest velo signal we have
  without re-pulling pitch-level Statcast.)

METHODOLOGY / LEAKAGE:
  The ramp-penalty measure is a within-pitcher pre/post comparison, so each
  pitcher is his own control (no cross-pitcher leakage). "Pre-IL baseline" =
  mean FP over the start(s) BEFORE the placement in the same season (or the
  prior season's full-year mean if no in-season pre starts exist). "Post" =
  the first 1/2/3 starts strictly AFTER the activation date. We never use a
  post start to define the baseline. We report the raw delta and a
  pitcher-fixed-effect (paired) summary.

OUTPUT:
  data/research/xfp_cache/mlb_transactions_2023_2025.csv  (parsed stints)
  printed summary -> captured into the validation_runs markdown by the caller.

Run with:  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/_oneoff/transactions_injury_study.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
PANEL = CACHE / "rolling_pitchers_2018_2026.csv"
OUT_STINTS = CACHE / "mlb_transactions_2023_2025.csv"
GAMELOG_CACHE = CACHE / "_gamelog_cache_il_study.json"
YEARS = [2023, 2024, 2025]

MLB_TEAMS = [
    "Angels", "Astros", "Athletics", "Blue Jays", "Orioles", "Red Sox", "Rays",
    "Rangers", "Royals", "Guardians", "Twins", "White Sox", "Tigers", "Mariners",
    "Braves", "Marlins", "Mets", "Nationals", "Phillies", "Brewers", "Cardinals",
    "Cubs", "Pirates", "Reds", "D-backs", "Diamondbacks", "Dodgers", "Giants",
    "Padres", "Rockies", "Yankees",
]

RE_PLACED = re.compile(r"placed\s+(RHP|LHP)\s+(.+?)\s+on the (\d+)-day injured list", re.I)
RE_ACT = re.compile(r"(?:activated|reinstated)\s+(RHP|LHP)\s+(.+?)\s+from the (\d+)-day injured list", re.I)
RE_TRANSFER = re.compile(r"transferred\s+(RHP|LHP)\s+(.+?)\s+to the (\d+)-day injured list", re.I)


# ---------- injury-type classification from the description text ----------
def classify_injury(desc: str) -> str:
    """Bucket the injury from the free-text tail of the transaction description.

    NOTE: the feed only sometimes carries the injury text. When absent we
    return 'unspecified'. Exact surgery type is sparse — we capture what IS
    there (TJ/UCL, strains, fractures, etc.) and honestly flag the rest.
    """
    d = desc.lower()
    if "tommy john" in d or ("ucl" in d) or ("ulnar collateral" in d):
        return "elbow_ucl_tj"
    if "internal brace" in d:
        return "elbow_ucl_tj"
    if "elbow" in d:
        return "elbow_other"
    if "shoulder" in d or "rotator cuff" in d or "labrum" in d:
        return "shoulder"
    if "forearm" in d:
        return "forearm"
    if "lat " in d or "latissimus" in d:
        return "lat"
    if "oblique" in d:
        return "oblique"
    if "back" in d or "lumbar" in d:
        return "back"
    if "hamstring" in d or "quad" in d or "calf" in d or "groin" in d or "knee" in d or "ankle" in d or "hip" in d:
        return "lower_body"
    if "strain" in d:
        return "strain_unspec"
    if "fracture" in d or "broken" in d:
        return "fracture"
    if "blister" in d or "fingernail" in d or "finger" in d:
        return "finger_blister"
    if "covid" in d or "illness" in d or "personal" in d:
        return "illness_personal"
    # IL category present but no body part => description was just the bare move
    return "unspecified"


def is_mlb(desc: str) -> bool:
    head = desc
    for sep in (" placed ", " activated ", " reinstated ", " transferred "):
        if sep in desc:
            head = desc.split(sep)[0]
            break
    return any(t in head for t in MLB_TEAMS)


# ---------------------- parse transactions into stints ----------------------
def load_events() -> pd.DataFrame:
    rows = []
    for y in YEARS:
        data = json.load(open(CACHE / f"il_transactions_{y}.json", encoding="utf-8"))
        for r in data:
            desc = r["desc"]
            if not is_mlb(desc):
                continue
            kind = days = hand = name = None
            m = RE_PLACED.search(desc)
            if m:
                kind, hand, name, days = "place", m.group(1), m.group(2), int(m.group(3))
            else:
                m = RE_ACT.search(desc)
                if m:
                    kind, hand, name, days = "activate", m.group(1), m.group(2), int(m.group(3))
                else:
                    m = RE_TRANSFER.search(desc)
                    if m:
                        kind, hand, name, days = "transfer", m.group(1), m.group(2), int(m.group(3))
            if kind is None:
                continue
            rows.append({
                "date": r["date"], "pid": int(r["pid"]), "name": r["name"],
                "kind": kind, "il_days_cat": days, "hand": hand,
                "injury_class": classify_injury(desc), "season": y, "desc": desc,
            })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["pid", "date"]).reset_index(drop=True)


def build_stints(ev: pd.DataFrame) -> pd.DataFrame:
    """Greedy-pair placements with the next activation (same pid, same season)."""
    stints = []
    for (pid, season), g in ev.groupby(["pid", "season"]):
        g = g.sort_values("date")
        places = g[g.kind == "place"].to_dict("records")
        acts = g[g.kind == "activate"].sort_values("date").to_dict("records")
        used = [False] * len(acts)
        for p in places:
            match = None
            for i, a in enumerate(acts):
                if not used[i] and a["date"] >= p["date"]:
                    used[i] = True
                    match = a
                    break
            stint = {
                "pid": pid, "name": p["name"], "season": season,
                "place_date": p["date"], "il_days_cat": p["il_days_cat"],
                "hand": p["hand"], "injury_class": p["injury_class"],
                "activate_date": match["date"] if match else pd.NaT,
                "stint_days": (match["date"] - p["date"]).days if match else np.nan,
                "paired": match is not None,
            }
            stints.append(stint)
    return pd.DataFrame(stints)


# ----------------------- per-start FP via gameLog --------------------------
def ip_to_outs(ip_str: str) -> float:
    """'5.2' innings -> 17 outs -> 5.667 IP float."""
    try:
        whole, frac = (ip_str.split(".") + ["0"])[:2]
        return int(whole) + int(frac) / 3.0
    except Exception:
        return float(ip_str)


_gl_cache: dict | None = None


def load_gl_cache() -> dict:
    global _gl_cache
    if _gl_cache is None:
        _gl_cache = json.load(open(GAMELOG_CACHE, encoding="utf-8")) if GAMELOG_CACHE.exists() else {}
    return _gl_cache


def save_gl_cache():
    if _gl_cache is not None:
        GAMELOG_CACHE.write_text(json.dumps(_gl_cache))


def fetch_gamelog(pid: int, season: int) -> list[dict]:
    cache = load_gl_cache()
    key = f"{pid}_{season}"
    if key in cache:
        return cache[key]
    url = (f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
           f"?stats=gameLog&group=pitching&season={season}")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        splits = r.json()["stats"][0]["splits"]
    except Exception:
        splits = []
    out = []
    for s in splits:
        st = s["stat"]
        if int(st.get("gamesStarted", 0)) != 1:
            continue  # starts only
        ip = ip_to_outs(st.get("inningsPitched", "0.0"))
        k = int(st.get("strikeOuts", 0)); h = int(st.get("hits", 0))
        er = int(st.get("earnedRuns", 0)); bb = int(st.get("baseOnBalls", 0))
        hbp = int(st.get("hitByPitch", 0))
        fp = k + ip * 3.3 - h - 2 * er - bb - hbp
        out.append({"date": s["date"], "ip": ip, "fp": fp})
    cache[key] = out
    time.sleep(0.05)
    return out


# --------------------------- velo from the panel ---------------------------
def load_velo_panel() -> pd.DataFrame:
    p = pd.read_csv(PANEL, usecols=["pitcher", "year", "cutoff_date", "avg_velo_last21", "gs_last21"])
    p["cutoff_date"] = pd.to_datetime(p["cutoff_date"])
    return p


def velo_around(panel: pd.DataFrame, pid: int, season: int, place_date, activate_date):
    """avg_velo_last21 at the last cutoff before placement vs first cutoff after return."""
    g = panel[(panel.pitcher == pid) & (panel.year == season)].sort_values("cutoff_date")
    if g.empty:
        return (np.nan, np.nan)
    pre = g[g.cutoff_date <= place_date]
    post = g[(g.cutoff_date >= activate_date) & g.gs_last21.gt(0)] if pd.notna(activate_date) else g.iloc[0:0]
    velo_pre = pre.iloc[-1].avg_velo_last21 if len(pre) else np.nan
    velo_post = post.iloc[0].avg_velo_last21 if len(post) else np.nan
    return (velo_pre, velo_post)


# ------------------------------- main study --------------------------------
def main():
    print("=== transactions_injury_study ===", flush=True)
    ev = load_events()
    print(f"MLB pitcher IL events 2023-25: {len(ev)} "
          f"(place={int((ev.kind=='place').sum())}, "
          f"activate={int((ev.kind=='activate').sum())}, "
          f"transfer={int((ev.kind=='transfer').sum())})", flush=True)

    stints = build_stints(ev)
    stints.to_csv(OUT_STINTS, index=False)
    paired = stints[stints.paired & stints.stint_days.notna() & (stints.stint_days >= 0)]
    print(f"\nParsed stints: {len(stints)}  | paired place->activate: {len(paired)}", flush=True)
    print(f"Cached parsed stints -> {OUT_STINTS}", flush=True)

    # ---- coverage: injury-class & stint length ----
    print("\n--- injury_class distribution (paired stints) ---", flush=True)
    print(stints["injury_class"].value_counts().to_string(), flush=True)
    spec = (stints["injury_class"] != "unspecified").mean()
    print(f"\nshare of stints with ANY injury text (not 'unspecified'): {spec:.1%}", flush=True)

    print("\n--- stint length (days) by IL category ---", flush=True)
    print(paired.groupby("il_days_cat")["stint_days"].describe()[["count", "mean", "50%", "max"]].to_string(), flush=True)

    print("\n--- median stint length by injury_class (paired) ---", flush=True)
    by_cls = paired.groupby("injury_class")["stint_days"].agg(["count", "median", "mean"]).sort_values("count", ascending=False)
    print(by_cls.to_string(), flush=True)

    # ---- RAMP PENALTY: per-start FP pre vs post ----
    panel = load_velo_panel()
    recs = []
    cand = paired.copy()
    print(f"\nFetching gameLogs for {cand.pid.nunique()} returning pitchers...", flush=True)
    n = 0
    for _, s in cand.iterrows():
        pid, season = int(s["pid"]), int(s["season"])
        pname = s["name"]
        gl = fetch_gamelog(pid, season)
        n += 1
        if n % 50 == 0:
            print(f"  ...{n} stints processed", flush=True)
            save_gl_cache()
        if not gl:
            continue
        gdf = pd.DataFrame(gl)
        gdf["date"] = pd.to_datetime(gdf["date"])
        gdf = gdf.sort_values("date")
        place, act = s.place_date, s.activate_date
        pre = gdf[gdf.date < place]
        post = gdf[gdf.date > act] if pd.notna(act) else gdf.iloc[0:0]
        # need a real baseline + at least one post start
        if len(post) == 0:
            continue
        if len(pre) >= 2:
            base = pre.fp.mean()
            base_src = "in_season_pre"
        else:
            # fall back to prior-season full-year mean (leakage-safe: prior year)
            pg = pd.DataFrame(fetch_gamelog(pid, season - 1))
            if len(pg) >= 5:
                base = pg["fp"].mean()
                base_src = "prior_season"
            elif len(pre) == 1:
                base = pre.fp.mean()
                base_src = "single_pre"
            else:
                continue
        velo_pre, velo_post = velo_around(panel, pid, season, place, act)
        recs.append({
            "pid": pid, "name": pname, "season": season,
            "injury_class": s["injury_class"], "il_days_cat": s["il_days_cat"],
            "stint_days": s["stint_days"], "base_src": base_src, "baseline_fp": base,
            "post1": post.fp.iloc[0],
            "post2_mean": post.fp.iloc[:2].mean() if len(post) >= 2 else np.nan,
            "post3_mean": post.fp.iloc[:3].mean() if len(post) >= 3 else np.nan,
            "post4_6_mean": post.fp.iloc[3:6].mean() if len(post) >= 4 else np.nan,
            "n_post": len(post),
            "velo_pre": velo_pre, "velo_post": velo_post,
        })
    save_gl_cache()
    R = pd.DataFrame(recs)
    print(f"\n=== RAMP-PENALTY SAMPLE: {len(R)} returning-pitcher stints with usable baseline+post ===", flush=True)
    print(f"baseline source mix: {R.base_src.value_counts().to_dict()}", flush=True)

    def line(col, label):
        d = (R[col] - R["baseline_fp"]).dropna()
        if len(d) == 0:
            print(f"  {label}: n=0"); return
        # paired t-ish: mean delta, sd, n, and share worse than baseline
        se = d.std() / np.sqrt(len(d))
        print(f"  {label:>14}: ΔFP={d.mean():+.2f}  (sd {d.std():.2f}, n={len(d)}, "
              f"95%CI [{d.mean()-1.96*se:+.2f},{d.mean()+1.96*se:+.2f}], "
              f"P(<base)={ (d<0).mean():.0%})", flush=True)

    print("\n--- post-return FP minus own pre-IL baseline (paired) ---", flush=True)
    print(f"  league baseline mean FP/start (these pitchers): {R.baseline_fp.mean():.2f}", flush=True)
    line("post1", "1st start")
    line("post2_mean", "starts 1-2")
    line("post3_mean", "starts 1-3")
    line("post4_6_mean", "starts 4-6")

    # velo
    V = R.dropna(subset=["velo_pre", "velo_post"]).copy()
    V["velo_delta"] = V["velo_post"] - V["velo_pre"]
    if len(V):
        se = V.velo_delta.std() / np.sqrt(len(V))
        print(f"\n--- velo (avg_velo_last21 panel): post-return minus pre-IL ---", flush=True)
        print(f"  Δvelo = {V.velo_delta.mean():+.2f} mph (sd {V.velo_delta.std():.2f}, n={len(V)}, "
              f"95%CI [{V.velo_delta.mean()-1.96*se:+.2f},{V.velo_delta.mean()+1.96*se:+.2f}], "
              f"P(velo down)={ (V.velo_delta<0).mean():.0%})", flush=True)

    # by stint length: short (<=20d, IL15-ish) vs long (>=60d)
    print("\n--- 1st-start ΔFP by stint length bucket ---", flush=True)
    R["len_bucket"] = pd.cut(R["stint_days"], [-1, 20, 45, 90, 9999],
                             labels=["<=20d", "21-45d", "46-90d", ">90d"])
    g = R.assign(d1=R.post1 - R.baseline_fp).groupby("len_bucket", observed=True)["d1"].agg(["count", "mean", "median"])
    print(g.to_string(), flush=True)

    print("\n--- 1st-start ΔFP by injury_class (n>=15) ---", flush=True)
    Rc = R.assign(d1=R.post1 - R.baseline_fp)
    gc = Rc.groupby("injury_class")["d1"].agg(["count", "mean", "median"])
    print(gc[gc["count"] >= 15].sort_values("mean").to_string(), flush=True)

    # persist the ramp sample for inspection
    R.to_csv(CACHE / "_il_ramp_sample_2023_2025.csv", index=False)
    print(f"\nWrote ramp sample -> {CACHE / '_il_ramp_sample_2023_2025.csv'}", flush=True)


if __name__ == "__main__":
    main()
