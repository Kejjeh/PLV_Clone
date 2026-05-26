"""SP career form batch computation.

Pulls all starts (game appearances) for a list of pitcher MLBAM IDs from
statcast parquets (2018-2026), computes rolling-5-start k_rate and avg_velo
windows, surfaces career percentile for each metric, buckets current form,
and flags velocity drops > 1.0 mph.

Usage:
    from scripts.xfp.sp_career_form_batch import batch_sp_career_form, build_sp_id_map
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

PARQUET_YEARS = range(2018, 2027)
MIN_STARTS_FOR_PERCENTILE = 15
VELO_FLAG_THRESHOLD = 1.0  # mph


def _normalize(name: str) -> str:
    """Strip accents so 'Jesús' == 'Jesus', 'Ján' == 'Jan', etc."""
    import unicodedata
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")


def build_sp_id_map() -> dict[str, int]:
    """Return {player_name: pitcher_mlbam_id} from xfp_rp3_projections.csv.

    Keys include both the original "Last, First" format and a converted
    "First Last" format, each in both accented and ASCII-normalized forms
    so ESPN roster names (which use "First Last" without accents) resolve.
    """
    rp3_path = REPO / "data/outputs/xfp_rp3_projections.csv"
    df = pd.read_csv(rp3_path, usecols=["pitcher", "player_name"])
    result = {}
    for _, row in df.iterrows():
        if not isinstance(row["player_name"], str):
            continue
        pid = int(row["pitcher"])
        name_orig = row["player_name"]
        # Store original and accent-stripped versions of "Last, First"
        result[name_orig] = pid
        result[_normalize(name_orig)] = pid
        # Convert "Last, First" → "First Last" and store both accent forms
        if "," in name_orig:
            parts = [p.strip() for p in name_orig.split(",", 1)]
            first_last = f"{parts[1]} {parts[0]}"
            result[first_last] = pid
            result[_normalize(first_last)] = pid
    return result


def _form_bucket(percentile: float | None) -> str:
    if percentile is None or pd.isna(percentile):
        return "INSUFFICIENT"
    if percentile >= 0.90:
        return "PEAK"
    if percentile >= 0.80:
        return "HIGH"
    if percentile >= 0.60:
        return "ABOVE_MEDIAN"
    if percentile >= 0.40:
        return "TYPICAL"
    if percentile >= 0.20:
        return "BELOW_MEDIAN"
    return "SLUMPING"


def batch_sp_career_form(pitcher_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Compute career form metrics for a list of pitcher MLBAM IDs.

    Returns a dict keyed by pitcher_id with form metrics and recent starts.
    Pitchers with fewer than MIN_STARTS_FOR_PERCENTILE career starts will have
    None for percentile fields and 'INSUFFICIENT' for bucket fields.
    """
    if not pitcher_ids:
        return {}

    ids_csv = ",".join(str(i) for i in pitcher_ids)

    # Build UNION ALL across all years
    parquet_selects = []
    for y in PARQUET_YEARS:
        path = (REPO / f"data/research/xfp_cache/statcast_{y}.parquet").as_posix()
        parquet_selects.append(
            f"SELECT pitcher, game_date::DATE AS gd, events, pitch_type, release_speed "
            f"FROM read_parquet('{path}') "
            f"WHERE pitcher IN ({ids_csv})"
        )
    union_all = " UNION ALL ".join(parquet_selects)

    con = duckdb.connect()

    # Step 2: aggregate to per-start level (events-level rows for k/bb/hr,
    # all rows for velo). Filter to starts via bf >= 15.
    start_sql = f"""
    WITH raw AS ({union_all}),
    per_start AS (
      SELECT
        pitcher,
        gd,
        COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
        SUM(CASE WHEN events = 'strikeout' THEN 1 ELSE 0 END)           AS k,
        SUM(CASE WHEN events = 'walk'      THEN 1 ELSE 0 END)           AS bb,
        SUM(CASE WHEN events = 'home_run'  THEN 1 ELSE 0 END)           AS hr,
        AVG(CASE WHEN pitch_type IN ('FF','FT','SI') THEN release_speed END) AS avg_velo
      FROM raw
      GROUP BY pitcher, gd
    )
    SELECT *,
           bf  AS bf_all,   -- alias for clarity
           CAST(k  AS DOUBLE) / NULLIF(bf, 0) AS k_rate,
           CAST(bb AS DOUBLE) / NULLIF(bf, 0) AS bb_rate,
           CAST(hr AS DOUBLE) / NULLIF(bf, 0) AS hr_rate
    FROM per_start
    WHERE bf >= 15
    ORDER BY pitcher, gd
    """
    starts_df = con.execute(start_sql).df()
    con.close()

    results: dict[int, dict[str, Any]] = {}

    for pid in pitcher_ids:
        pdf = starts_df[starts_df["pitcher"] == pid].copy().reset_index(drop=True)

        if pdf.empty:
            results[pid] = {
                "total_starts": 0,
                "career_k_percentile": None,
                "career_velo_percentile": None,
                "current_l5_k_rate": None,
                "current_l5_velo": None,
                "k_form_bucket": "INSUFFICIENT",
                "velo_form_bucket": "INSUFFICIENT",
                "velo_l5": None,
                "velo_pre_l5": None,
                "velo_delta": None,
                "velo_flag": False,
                "recent_starts": [],
            }
            continue

        total_starts = len(pdf)

        # Step 3: rolling 5-start k_rate and velo
        pdf["roll5_k"] = pdf["k_rate"].rolling(5, min_periods=5).mean()
        pdf["roll5_velo"] = pdf["avg_velo"].rolling(5, min_periods=5).mean()

        # Career percentile: compare current (last valid) 5-start window
        # against ALL prior windows with valid roll5 values
        valid_k = pdf["roll5_k"].dropna()
        valid_v = pdf["roll5_velo"].dropna()

        current_l5_k = valid_k.iloc[-1] if len(valid_k) > 0 else None
        current_l5_velo = valid_v.iloc[-1] if len(valid_v) > 0 else None

        if total_starts >= MIN_STARTS_FOR_PERCENTILE and len(valid_k) > 0:
            career_k_pct = float((valid_k < current_l5_k).sum()) / len(valid_k)
        else:
            career_k_pct = None

        if total_starts >= MIN_STARTS_FOR_PERCENTILE and len(valid_v) > 0:
            career_velo_pct = float((valid_v < current_l5_velo).sum()) / len(valid_v)
        else:
            career_velo_pct = None

        # Step 5: velo trend — L5 vs L10-20 (pre-L5 baseline)
        l5_rows = pdf.tail(5)
        pre_l5_rows = pdf.iloc[-20:-5] if len(pdf) >= 20 else pdf.iloc[:-5]

        velo_l5 = float(l5_rows["avg_velo"].mean()) if not l5_rows["avg_velo"].isna().all() else None
        velo_pre_l5 = float(pre_l5_rows["avg_velo"].mean()) if (len(pre_l5_rows) > 0 and not pre_l5_rows["avg_velo"].isna().all()) else None

        if velo_l5 is not None and velo_pre_l5 is not None:
            velo_delta = round(velo_l5 - velo_pre_l5, 2)
            velo_flag = velo_delta < -VELO_FLAG_THRESHOLD
        else:
            velo_delta = None
            velo_flag = False

        # Step 4: recent 5 starts
        recent_rows = pdf.tail(5)
        recent_starts = [
            {
                "date": str(row["gd"]),
                "bf": int(row["bf"]),
                "k_rate": round(float(row["k_rate"]), 3) if pd.notna(row["k_rate"]) else None,
                "bb_rate": round(float(row["bb_rate"]), 3) if pd.notna(row["bb_rate"]) else None,
                "velo": round(float(row["avg_velo"]), 1) if pd.notna(row["avg_velo"]) else None,
            }
            for _, row in recent_rows.iterrows()
        ]

        results[pid] = {
            "total_starts": total_starts,
            "career_k_percentile": round(career_k_pct, 3) if career_k_pct is not None else None,
            "career_velo_percentile": round(career_velo_pct, 3) if career_velo_pct is not None else None,
            "current_l5_k_rate": round(float(current_l5_k), 3) if current_l5_k is not None else None,
            "current_l5_velo": round(float(current_l5_velo), 1) if current_l5_velo is not None else None,
            "k_form_bucket": _form_bucket(career_k_pct),
            "velo_form_bucket": _form_bucket(career_velo_pct),
            "velo_l5": round(velo_l5, 1) if velo_l5 is not None else None,
            "velo_pre_l5": round(velo_pre_l5, 1) if velo_pre_l5 is not None else None,
            "velo_delta": velo_delta,
            "velo_flag": velo_flag,
            "recent_starts": recent_starts,
        }

    return results


if __name__ == "__main__":
    import json

    # Load rp3 projections, take top 3 by rank
    rp3_path = REPO / "data/outputs/xfp_rp3_projections.csv"
    rp3 = pd.read_csv(rp3_path)
    top3 = rp3.sort_values("rank").head(3)

    print("Top 3 rp3 SPs:")
    for _, row in top3.iterrows():
        print(f"  rank={int(row['rank'])}  id={int(row['pitcher'])}  {row['player_name']}")

    pitcher_ids = top3["pitcher"].astype(int).tolist()
    id_to_name = {int(row["pitcher"]): row["player_name"] for _, row in top3.iterrows()}

    print("\nRunning batch_sp_career_form...")
    results = batch_sp_career_form(pitcher_ids)

    for pid, data in results.items():
        name = id_to_name.get(pid, str(pid))
        print(f"\n{'='*60}")
        print(f"{name}  (id={pid})")
        print(f"  total_starts       : {data['total_starts']}")
        print(f"  career_k_pct       : {data['career_k_percentile']}  -> {data['k_form_bucket']}")
        print(f"  career_velo_pct    : {data['career_velo_percentile']}  -> {data['velo_form_bucket']}")
        print(f"  current_l5_k_rate  : {data['current_l5_k_rate']}")
        print(f"  current_l5_velo    : {data['current_l5_velo']}")
        print(f"  velo_l5            : {data['velo_l5']}  pre_l5={data['velo_pre_l5']}  delta={data['velo_delta']}")
        print(f"  velo_flag          : {data['velo_flag']}")
        print(f"  recent_starts:")
        for s in data["recent_starts"]:
            print(f"    {s['date']}  bf={s['bf']}  k%={s['k_rate']}  bb%={s['bb_rate']}  velo={s['velo']}")
