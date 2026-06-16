"""One-off: SP sustainability + breakout sweep over Ligers SPs + FA SPs with FP_L15d>20.

Window: 2026-05-22 .. 2026-06-05 inclusive.
Writes data/outputs/_l15d_sp_sustainability_sweep.csv.
"""
from __future__ import annotations

import sys
import unicodedata
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(r"c:/Users/Joshua/plv_clone")
sys.path.insert(0, str(ROOT))

from app.espn_connector import (
    get_my_roster_with_injuries,
    get_all_teams,
    get_free_agents,
)

CACHE = ROOT / "data/research/xfp_cache"
OUT = ROOT / "data/outputs"
STATCAST_2026 = CACHE / "statcast_2026.parquet"
SP_MULTIYR = CACHE / "sp_multiyr.csv"
RP3_CSV = OUT / "xfp_rp3_projections.csv"

WIN_START = "2026-05-22"
WIN_END = "2026-06-05"
FP_THRESHOLD = 20.0


def _norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    parts = re.findall(r"[a-z]+", s)
    return "".join(sorted(parts))


# -------------------- Step 1: cohort --------------------

def get_ligers_sp() -> pd.DataFrame:
    r = get_my_roster_with_injuries()
    sp = r[r["position"].astype(str).str.upper().str.contains("SP", na=False)].copy()
    sp["ownership_status"] = "LIGERS"
    return sp[["player_name", "player_id", "pro_team", "lineup_slot", "ownership_status"]]


def get_fa_sp() -> pd.DataFrame:
    # Connelly Early bug: must subtract truly-rostered players from FA pool
    all_t = get_all_teams()
    rostered = set(all_t["player_name"].dropna().astype(str).str.strip().str.lower())
    fas = get_free_agents(size=2000)
    fas = fas[fas["position"].astype(str).str.upper().str.contains("SP", na=False)]
    fas = fas[~fas["player_name"].astype(str).str.strip().str.lower().isin(rostered)].copy()
    fas["ownership_status"] = "FA"
    fas["player_id"] = np.nan
    fas["lineup_slot"] = ""
    return fas[["player_name", "player_id", "pro_team", "lineup_slot", "ownership_status"]]


# -------------------- Step 1b: FP_L15d from statcast --------------------

def compute_fp_l15d() -> pd.DataFrame:
    sql = f"""
    WITH starts AS (
      SELECT pitcher, game_date::DATE AS gd,
        COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
        SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
        SUM(CASE WHEN events IN ('walk','intent_walk') THEN 1 ELSE 0 END) AS bb,
        SUM(CASE WHEN events='hit_by_pitch' THEN 1 ELSE 0 END) AS hbp,
        SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
        -- outs: any out event contributes 1; sac_fly/sac_bunt sometimes 1, DP=2
        SUM(CASE
            WHEN events IN ('strikeout','field_out','force_out','grounded_into_double_play','sac_fly','sac_bunt','fielders_choice','fielders_choice_out','caught_stealing_2b','caught_stealing_3b','caught_stealing_home','other_out') THEN 1
            WHEN events = 'double_play' THEN 2
            WHEN events = 'triple_play' THEN 3
            ELSE 0 END) AS outs,
        -- runs allowed approximation: max(post_bat_score - pre... by inning)
        MAX(post_bat_score) - MIN(bat_score) AS runs_proxy
      FROM read_parquet('{STATCAST_2026.as_posix()}')
      WHERE game_date BETWEEN DATE '{WIN_START}' AND DATE '{WIN_END}'
      GROUP BY pitcher, game_date::DATE
      HAVING COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 10
    )
    SELECT pitcher,
      COUNT(*) AS starts_L15d,
      SUM(k) AS k_sum, SUM(bb) AS bb_sum, SUM(hbp) AS hbp_sum, SUM(h) AS h_sum,
      SUM(outs) AS outs_sum,
      SUM(GREATEST(runs_proxy,0)) AS er_sum
    FROM starts
    GROUP BY pitcher
    """
    df = duckdb.sql(sql).df()
    if df.empty:
        return df
    ip = df["outs_sum"] / 3.0
    df["FP_L15d"] = (
        df["k_sum"] + ip * 3.3 - df["h_sum"] - 2 * df["er_sum"] - df["bb_sum"] - df["hbp_sum"]
    )
    return df[["pitcher", "starts_L15d", "FP_L15d"]]


# -------------------- Step 1c: name -> mlbam --------------------

def name_to_mlbam_map() -> dict:
    """Build name->mlbam from sp_multiyr or rp3."""
    rp3 = pd.read_csv(RP3_CSV)
    m = {}
    for _, row in rp3.iterrows():
        m[_norm(row["player_name"])] = int(row["pitcher"])
    return m


# -------------------- Step 2: sustainability decomp --------------------

MARKERS = [
    ("avg_velo",      "+", "Velo",     0.5),
    ("swstr_pct",     "+", "SwStr",    0.010),
    ("c_plus_swstr",  "+", "CSW",      0.010),
    ("o_swing_pct",   "+", "Chase",    0.020),
    ("k_pct",         "+", "K%",       0.020),
    ("bb_pct",        "-", "BB%",      0.015),
    ("hard_hit_pct",  "-", "HH%",      0.030),
    ("barrel_pct",    "-", "Brl%",     0.015),
    ("xwoba_contact", "-", "xwOBAcon", 0.020),
]


def load_sp_multiyr() -> pd.DataFrame:
    if not SP_MULTIYR.exists():
        return pd.DataFrame()
    return pd.read_csv(SP_MULTIYR)


def sustainability_bucket(mlbam: int, sp_my: pd.DataFrame) -> dict:
    """Return bucket + favorable_markers + fp_delta + key_driver."""
    if sp_my.empty:
        return {"bucket": "NO_DATA", "favorable": 0, "fp_delta": np.nan, "driver": "no sp_multiyr"}
    pid_col = "pitcher" if "pitcher" in sp_my.columns else "mlbam"
    rows = sp_my[sp_my[pid_col] == mlbam].copy()
    if rows.empty:
        return {"bucket": "NO_BASELINE", "favorable": 0, "fp_delta": np.nan, "driver": "no career row"}
    rows = rows.sort_values("year")
    cur = rows[rows["year"] == 2026]
    prior = rows[rows["year"] < 2026]
    if cur.empty:
        return {"bucket": "NO_2026", "favorable": 0, "fp_delta": np.nan, "driver": "no 2026 row"}
    if prior.empty:
        return {"bucket": "NO_BASELINE", "favorable": 0, "fp_delta": np.nan, "driver": "rookie/no prior"}
    cur = cur.iloc[-1]
    prior = prior.iloc[-1]  # most recent prior year
    fp_col = "fp_per_start" if "fp_per_start" in rows.columns else None
    fp_delta = float(cur[fp_col] - prior[fp_col]) if fp_col else np.nan

    favorable = 0
    drivers = []
    for col, direction, label, thresh in MARKERS:
        if col not in rows.columns:
            continue
        try:
            d = float(cur[col]) - float(prior[col])
        except (TypeError, ValueError):
            continue
        if pd.isna(d):
            continue
        # favorable in direction + material
        if direction == "+" and d >= thresh:
            favorable += 1
            drivers.append(f"{label}+{d:.2f}")
        elif direction == "-" and d <= -thresh:
            favorable += 1
            drivers.append(f"{label}{d:.2f}")
        elif direction == "+" and d <= -thresh:
            drivers.append(f"{label}{d:.2f}")
        elif direction == "-" and d >= thresh:
            drivers.append(f"{label}+{d:.2f}")

    # bucket
    if pd.isna(fp_delta):
        bucket = "MIXED"
    elif fp_delta >= 2.0 and favorable >= 7:
        bucket = "LEGIT"
    elif fp_delta >= 2.0 and favorable >= 5:
        bucket = "IMPROVING"
    elif fp_delta >= 2.0 and favorable <= 3:
        bucket = "NOISE"
    elif abs(fp_delta) < 2.0:
        bucket = "STABLE"
    elif fp_delta <= -2.0 and favorable >= 4:
        bucket = "BAD_LUCK"
    elif fp_delta <= -2.0:
        bucket = "REGRESS"
    else:
        bucket = "MIXED"

    driver = ",".join(drivers[:3]) if drivers else "no material markers"
    return {"bucket": bucket, "favorable": favorable, "fp_delta": fp_delta, "driver": driver}


# -------------------- Step 3: breakout signal --------------------

def breakout_signal(mlbam: int) -> dict:
    """Rolling-window good-start signal (threshold fp_proxy_per_bf >= -0.0476)."""
    sql = f"""
    WITH raw AS (
      SELECT pitcher, game_date::DATE AS gd,
        COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
        SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
        SUM(CASE WHEN events IN ('walk','intent_walk') THEN 1 ELSE 0 END) AS bb,
        SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
        SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr
      FROM read_parquet('{STATCAST_2026.as_posix()}')
      WHERE pitcher = {mlbam}
      GROUP BY pitcher, game_date::DATE
      HAVING COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 10
    )
    SELECT *, ROUND((k-bb-h-hr)*1.0/NULLIF(bf,0),4) AS fp_proxy_per_bf
    FROM raw ORDER BY gd
    """
    df = duckdb.sql(sql).df()
    if df.empty:
        return {"signal": "NO_GS", "L4": "0/0", "L5": "0/0", "tier": "NO_DATA"}
    GOOD = -0.0476
    df["good"] = (df["fp_proxy_per_bf"] >= GOOD).astype(int)
    goods = df["good"].tolist()
    last5 = goods[-5:]
    last4 = goods[-4:]
    last3 = goods[-3:]
    L4 = f"{sum(last4)}/{len(last4)}"
    L5 = f"{sum(last5)}/{len(last5)}"
    L3 = f"{sum(last3)}/{len(last3)}"

    # tier from best window
    tier = "NOISE"
    k4, k5, k3 = sum(last4), sum(last5), sum(last3)
    if len(last5) >= 5 and k5 == 5:
        tier = "LOCK"
    elif len(last4) >= 4 and k4 == 4:
        tier = "LOCK"
    elif len(last5) >= 5 and k5 >= 4:
        tier = "STRONG"
    elif len(last3) >= 3 and k3 == 3:
        tier = "STRONG"
    elif len(last4) >= 4 and k4 >= 3:
        tier = "ACTIONABLE"
    elif len(last3) >= 3 and k3 >= 2:
        tier = "WATCH"
    elif sum(goods) == 0 and len(goods) >= 3:
        tier = "COLD"
    return {"signal": f"L3:{L3} L4:{L4} L5:{L5}", "L4": L4, "L5": L5, "tier": tier}


# -------------------- Main --------------------

def main():
    print("[1/5] Building cohort (Ligers SP + FA SP)...")
    ligers = get_ligers_sp()
    print(f"  Ligers SPs: {len(ligers)}")
    fa = get_fa_sp()
    print(f"  FA SPs (FA-verified): {len(fa)}")

    print("[2/5] Computing FP_L15d from statcast 2026...")
    fp = compute_fp_l15d()
    nm = name_to_mlbam_map()

    # Resolve mlbam for all cohort members
    cohort = pd.concat([ligers, fa], ignore_index=True)
    cohort["norm"] = cohort["player_name"].map(_norm)
    cohort["mlbam"] = cohort["norm"].map(nm)

    cohort = cohort.merge(fp, left_on="mlbam", right_on="pitcher", how="left")
    cohort["FP_L15d"] = cohort["FP_L15d"].fillna(0.0)
    cohort["starts_L15d"] = cohort["starts_L15d"].fillna(0).astype(int)

    # Apply filter: Ligers always included; FA only if FP_L15d > 20
    keep = (cohort["ownership_status"] == "LIGERS") | (cohort["FP_L15d"] > FP_THRESHOLD)
    cohort = cohort[keep].copy()
    print(f"  Final cohort: {len(cohort)}")

    print("[3/5] Joining rp3...")
    rp3 = pd.read_csv(RP3_CSV)
    rp3_sub = rp3[["pitcher", "rank", "xfp_rp3_per_start", "data_quality_tag"]].rename(
        columns={"rank": "rp3_rank", "xfp_rp3_per_start": "rp3_per_start"}
    )
    cohort = cohort.merge(rp3_sub, left_on="mlbam", right_on="pitcher", how="left", suffixes=("", "_rp3"))

    print("[4/5] Running sustainability decomp + breakout signal...")
    sp_my = load_sp_multiyr()
    rows = []
    for _, c in cohort.iterrows():
        mlbam = c["mlbam"]
        if pd.isna(mlbam):
            sus = {"bucket": "NO_ID", "favorable": 0, "fp_delta": np.nan, "driver": "name unresolved"}
            br = {"signal": "NO_ID", "tier": "NO_DATA", "L4": "", "L5": ""}
        else:
            sus = sustainability_bucket(int(mlbam), sp_my)
            br = breakout_signal(int(mlbam))

        # divergence flag
        div_flag = ""
        try:
            if not pd.isna(c["rp3_per_start"]) and not pd.isna(sus["fp_delta"]):
                # bullish sus + rp3 hasn't caught up?
                if sus["bucket"] in ("LEGIT", "BAD_LUCK") and c["FP_L15d"] / max(c["starts_L15d"], 1) - c["rp3_per_start"] > 1.5:
                    div_flag = "BUY-LOW"
                elif sus["bucket"] in ("NOISE", "REGRESS"):
                    div_flag = "SELL-HIGH"
                elif sus["bucket"] == "IMPROVING":
                    div_flag = "CONFIRM"
        except Exception:
            pass

        rows.append({
            "player_name": c["player_name"],
            "team": c["pro_team"],
            "ownership_status": c["ownership_status"],
            "lineup_slot": c["lineup_slot"],
            "FP_L15d": round(float(c["FP_L15d"]), 1),
            "starts_L15d": int(c["starts_L15d"]),
            "rp3_per_start": round(float(c["rp3_per_start"]), 2) if not pd.isna(c["rp3_per_start"]) else np.nan,
            "rp3_rank": int(c["rp3_rank"]) if not pd.isna(c["rp3_rank"]) else np.nan,
            "data_quality": c.get("data_quality_tag", ""),
            "sustain_bucket": sus["bucket"],
            "sus_favorable": sus["favorable"],
            "sus_fp_delta": round(sus["fp_delta"], 2) if not pd.isna(sus["fp_delta"]) else np.nan,
            "divergence": div_flag,
            "breakout_signal": br["signal"],
            "breakout_tier": br["tier"],
            "key_driver": sus["driver"],
        })
    out = pd.DataFrame(rows)

    # sort: LIGERS first, then by sustain bucket priority then FP_L15d
    bucket_order = {
        "LEGIT": 0, "IMPROVING": 1, "BAD_LUCK": 2,
        "STABLE": 3, "MIXED": 4,
        "NO_BASELINE": 5, "NO_2026": 6, "NO_ID": 7, "NO_DATA": 8,
        "NOISE": 9, "REGRESS": 10,
    }
    own_order = {"LIGERS": 0, "FA": 1}
    out["__own"] = out["ownership_status"].map(own_order)
    out["__bk"] = out["sustain_bucket"].map(lambda x: bucket_order.get(x, 5))
    # BUY-LOW divergence float up within FA
    out["__div"] = (out["divergence"] == "BUY-LOW").map({True: -1, False: 0})
    out = out.sort_values(["__own", "__bk", "__div", "FP_L15d"], ascending=[True, True, True, False])
    out = out.drop(columns=["__own", "__bk", "__div"])

    print("[5/5] Writing CSV...")
    out_path = OUT / "_l15d_sp_sustainability_sweep.csv"
    out.to_csv(out_path, index=False)
    print(f"  Wrote {out_path} ({len(out)} rows)")

    # Print compact table for the report
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 30)
    cols = ["player_name", "team", "ownership_status", "FP_L15d", "starts_L15d",
            "rp3_per_start", "rp3_rank", "sustain_bucket", "divergence",
            "breakout_tier", "breakout_signal", "key_driver"]
    print("\n=== FULL COHORT TABLE ===")
    print(out[cols].to_string(index=False))


if __name__ == "__main__":
    main()
