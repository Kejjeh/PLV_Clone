"""Historical comp matcher for slumping/peak hitters.

For each target batter, finds all real historical players (2015-2025 statcast)
who were at a similar career-percentile position, similar career PA count, and
similar calendar month — then reports what actually happened next (30/60/90 PA
xwOBA outcomes).

Age is a matching dimension as of v2: |snap_age - current_age| <= age_window (default 3).
If age data is unavailable for a target batter the filter is skipped gracefully.

Usage:
    python scripts/xfp/historical_comp_matcher.py
    python scripts/xfp/historical_comp_matcher.py --batter-ids 665489 112526
    python scripts/xfp/historical_comp_matcher.py --rebuild
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

CACHE_PATH = REPO / "data" / "research" / "xfp_cache" / "historical_comp_snapshots.parquet"
NAME_RES_PATH = REPO / "data" / "research" / "xfp_cache" / "name_resolution_2026.csv"

# Years used to build the historical snapshot DB (never include 2026 targets)
HIST_YEARS = list(range(2015, 2026))
TARGET_YEARS = list(range(2015, 2027))  # include 2026 for computing target batter current state


# ---------------------------------------------------------------------------
# Build / load the historical snapshot database
# ---------------------------------------------------------------------------

def _union_sql(years: list[int], batter_filter: str = "", include_age: bool = False) -> str:
    """Build UNION ALL SQL for the given years, optionally filtering batter IDs."""
    where_extra = f" AND batter IN ({batter_filter})" if batter_filter else ""
    age_col = ", age_bat AS player_age" if include_age else ""
    parts = []
    for y in years:
        path = (REPO / f"data/research/xfp_cache/statcast_{y}.parquet").as_posix()
        parts.append(
            f"SELECT batter, game_date, estimated_woba_using_speedangle AS xwoba, "
            f"{y} AS year{age_col} "
            f"FROM read_parquet('{path}') "
            f"WHERE events IS NOT NULL AND events != '' "
            f"AND estimated_woba_using_speedangle IS NOT NULL"
            f"{where_extra}"
        )
    return " UNION ALL ".join(parts)


def _cache_has_snap_age() -> bool:
    """Return True if the cached snapshot parquet has a snap_age column."""
    if not CACHE_PATH.exists():
        return False
    try:
        con = duckdb.connect()
        cols = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{CACHE_PATH.as_posix()}')"
        ).df()["column_name"].tolist()
        con.close()
        return "snap_age" in cols
    except Exception:
        return False


def build_snapshot_db(con: duckdb.DuckDBPyConnection, force: bool = False) -> None:
    """Build the historical snapshot DB and cache it to parquet.

    Snapshots are taken at every 30-PA milestone (rn % 30 == 0, rn >= 150).
    For each snapshot we compute:
      - career percentile (fraction of prior rolling-150 windows below current)
      - snap_age: batter age at the milestone event (from age_bat column)
      - next 30/60/90 PA average xwOBA

    Cached to CACHE_PATH; reused on subsequent runs unless force=True or
    the cache is missing the snap_age column (auto-rebuild detected).
    """
    # Auto-rebuild if cache exists but lacks snap_age
    if CACHE_PATH.exists() and not force:
        if not _cache_has_snap_age():
            print("[snapshot-db] cache missing snap_age column — auto-rebuilding...")
            CACHE_PATH.unlink()
        else:
            print(f"[snapshot-db] loading cache from {CACHE_PATH.name}...")
            con.execute(
                f"CREATE TABLE hist_snapshots AS SELECT * FROM read_parquet('{CACHE_PATH.as_posix()}')"
            )
            print(
                f"[snapshot-db] {con.execute('SELECT COUNT(*) FROM hist_snapshots').fetchone()[0]:,} snapshots loaded"
            )
            return

    print(f"[snapshot-db] building from {HIST_YEARS[0]}-{HIST_YEARS[-1]} statcast data (may take 30-60s)...")
    t0 = time.time()

    union = _union_sql(HIST_YEARS, include_age=True)

    sql = f"""
    CREATE TABLE hist_snapshots AS
    WITH all_events AS (
        {union}
    ),
    ranked AS (
        SELECT batter, game_date, xwoba, player_age,
               EXTRACT(MONTH FROM CAST(game_date AS DATE)) AS month,
               ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date, xwoba) AS rn
        FROM all_events
    ),
    rolling AS (
        SELECT batter, rn, game_date, month, xwoba, player_age,
               AVG(xwoba) OVER (
                   PARTITION BY batter ORDER BY rn
                   ROWS BETWEEN 149 PRECEDING AND CURRENT ROW
               ) AS roll150,
               COUNT(*) OVER (PARTITION BY batter) AS total_career_pa
        FROM ranked
    ),
    -- Percentile rank: for each row, fraction of prior rolling windows (rn>=150)
    -- that are below the current roll150
    pct_base AS (
        SELECT batter, rn, roll150,
               PERCENT_RANK() OVER (
                   PARTITION BY batter ORDER BY roll150
               ) AS pct_rank_all
        FROM rolling
        WHERE rn >= 150
    ),
    -- Only milestone rows (every 30 PA, after 150 PA of history)
    milestones AS (
        SELECT r.*, pb.pct_rank_all AS snap_percentile
        FROM rolling r
        JOIN pct_base pb ON pb.batter = r.batter AND pb.rn = r.rn
        WHERE r.rn >= 150 AND r.rn % 30 = 0
    ),
    -- For next-PA outcomes: join back to rolling to get events after each milestone
    next_pa AS (
        SELECT
            m.batter,
            m.rn AS snap_rn,
            m.roll150 AS snap_l150,
            m.total_career_pa AS snap_total_pa,
            m.month AS snap_month,
            m.game_date AS snap_date,
            m.player_age AS snap_age,
            COALESCE(m.snap_percentile, 0.5) AS snap_percentile,
            -- next 30 PA
            AVG(e.xwoba) FILTER (WHERE e.rn > m.rn AND e.rn <= m.rn + 30) AS next_30pa_xwoba,
            -- next 60 PA
            AVG(e.xwoba) FILTER (WHERE e.rn > m.rn AND e.rn <= m.rn + 60) AS next_60pa_xwoba,
            -- next 90 PA
            AVG(e.xwoba) FILTER (WHERE e.rn > m.rn AND e.rn <= m.rn + 90) AS next_90pa_xwoba,
            -- Count to ensure we have enough PA for outcome windows
            COUNT(e.xwoba) FILTER (WHERE e.rn > m.rn AND e.rn <= m.rn + 30) AS n_next_30,
            COUNT(e.xwoba) FILTER (WHERE e.rn > m.rn AND e.rn <= m.rn + 60) AS n_next_60,
            COUNT(e.xwoba) FILTER (WHERE e.rn > m.rn AND e.rn <= m.rn + 90) AS n_next_90,
            -- Career median for bounce-above-median metric
            MEDIAN(e.xwoba) FILTER (WHERE e.rn <= m.rn) AS career_median_at_snap
        FROM milestones m
        JOIN rolling e ON e.batter = m.batter
        GROUP BY m.batter, m.rn, m.roll150, m.total_career_pa, m.month,
                 m.game_date, m.player_age, m.snap_percentile
    )
    -- Only keep snapshots that have at least 30 PA of outcome data
    SELECT * FROM next_pa
    WHERE n_next_30 >= 30
    """

    con.execute(sql)
    count = con.execute("SELECT COUNT(*) FROM hist_snapshots").fetchone()[0]
    elapsed = time.time() - t0
    print(f"[snapshot-db] built {count:,} snapshots in {elapsed:.1f}s")

    # Cache to parquet for reuse
    print(f"[snapshot-db] caching to {CACHE_PATH.name}...")
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY hist_snapshots TO '{CACHE_PATH.as_posix()}' (FORMAT PARQUET)")
    print("[snapshot-db] cache saved")


# ---------------------------------------------------------------------------
# Compute target batter current state (including age)
# ---------------------------------------------------------------------------

def compute_target_snapshots(
    con: duckdb.DuckDBPyConnection,
    batter_ids: list[int],
) -> pd.DataFrame:
    """Compute current-state snapshot for each target batter (using 2015-2026 data).

    Returns a DataFrame with columns:
        batter, current_total_pa, current_month, current_l150,
        current_percentile, current_age
    """
    ids_csv = ",".join(str(b) for b in batter_ids)
    union = _union_sql(TARGET_YEARS, batter_filter=ids_csv, include_age=True)

    sql = f"""
    WITH all_events AS (
        {union}
    ),
    ranked AS (
        SELECT batter, game_date, xwoba, player_age,
               EXTRACT(MONTH FROM CAST(game_date AS DATE)) AS month,
               ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date, xwoba) AS rn,
               COUNT(*) OVER (PARTITION BY batter) AS total_pa
        FROM all_events
    ),
    rolling AS (
        SELECT batter, rn, total_pa, month, game_date, xwoba, player_age,
               AVG(xwoba) OVER (
                   PARTITION BY batter ORDER BY rn
                   ROWS BETWEEN 149 PRECEDING AND CURRENT ROW
               ) AS roll150
        FROM ranked
    ),
    current_row AS (
        SELECT * FROM rolling WHERE rn = total_pa
    ),
    percentile AS (
        SELECT r.batter,
               SUM(CASE WHEN r.roll150 < c.roll150 THEN 1 ELSE 0 END) * 1.0
                   / NULLIF(COUNT(r.roll150), 0) AS current_percentile
        FROM rolling r
        JOIN current_row c ON c.batter = r.batter
        WHERE r.rn >= 150
        GROUP BY r.batter
    )
    SELECT c.batter, c.total_pa AS current_total_pa, c.month AS current_month,
           c.roll150 AS current_l150, p.current_percentile,
           c.player_age AS current_age
    FROM current_row c
    LEFT JOIN percentile p ON p.batter = c.batter
    """

    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# Load name resolution
# ---------------------------------------------------------------------------

def load_name_map() -> dict[int, str]:
    """Return {batter_mlbam: player_name} from the name resolution CSV."""
    if not NAME_RES_PATH.exists():
        return {}
    df = pd.read_csv(NAME_RES_PATH)
    return dict(zip(df["batter_mlbam"].astype(int), df["player_name"]))


# ---------------------------------------------------------------------------
# Core matching function
# ---------------------------------------------------------------------------

def batch_historical_comps(
    batter_ids: list[int],
    mode: str = "slump",              # "slump" or "peak" (informational only)
    percentile_window: float = 0.10,  # ±10 percentile points
    pa_window: float = 0.20,          # ±20% of total_pa
    month_window: int = 1,            # ±1 calendar month
    age_window: int = 3,              # ±3 years — new in v2
) -> dict[int, dict]:
    """Find historical comps for each target batter and return outcome distributions.

    Parameters
    ----------
    batter_ids:
        List of MLB batter IDs (mlbam) to analyze.
    mode:
        "slump" or "peak" — informational label only; does not change matching.
    percentile_window:
        Match snapshots within ±this many percentile points.
    pa_window:
        Match snapshots within ±this fraction of the target's career PA.
    month_window:
        Match snapshots within ±this many calendar months (handles Nov/Jan wrap).
    age_window:
        Match snapshots within ±this many years of the target's current age.
        If current age is unavailable for a batter, the age filter is skipped
        and ``current_age`` will be ``None`` in the result dict.

    Returns
    -------
    dict mapping batter_id → outcome dict (or {"insufficient_comps": True}).

    New keys in v2 result dict
    --------------------------
    current_age : int | None
    age_window_used : int
    n_comps_before_age_filter : int   (comps matching pct/pa/month but not yet age-filtered)
    n_comps_age_filtered : int        (comps remaining after age filter; equals n_comps)
    """
    con = duckdb.connect()
    name_map = load_name_map()

    # Build or load snapshot DB (auto-rebuilds if snap_age column missing)
    build_snapshot_db(con)

    # Compute current state for all targets in one pass
    print(f"[targets] computing current state for {len(batter_ids)} batters...")
    targets_df = compute_target_snapshots(con, batter_ids)

    results: dict[int, dict] = {}

    for batter_id in batter_ids:
        row = targets_df[targets_df["batter"] == batter_id]
        if row.empty:
            results[batter_id] = {"error": "no statcast data found", "n_comps": 0}
            continue

        row = row.iloc[0]
        cur_pct = float(row["current_percentile"]) if pd.notna(row["current_percentile"]) else 0.5
        cur_pa = int(row["current_total_pa"])
        cur_month = int(row["current_month"])
        cur_l150 = float(row["current_l150"]) if pd.notna(row["current_l150"]) else None

        # Age — may be None if statcast doesn't have age_bat for this batter
        cur_age: int | None = (
            int(row["current_age"]) if pd.notna(row.get("current_age", float("nan"))) else None
        )

        if cur_l150 is None:
            results[batter_id] = {"error": "insufficient PA for rolling-150", "n_comps": 0}
            continue

        # PA bounds
        pa_lo = cur_pa * (1 - pa_window)
        pa_hi = cur_pa * (1 + pa_window)

        # Month bounds (modular)
        month_lo = cur_month - month_window
        month_hi = cur_month + month_window

        # Build month list (handles wrap around Dec/Jan)
        valid_months = set()
        for m in range(month_lo, month_hi + 1):
            valid_months.add(((m - 1) % 12) + 1)
        months_str = ",".join(str(m) for m in sorted(valid_months))

        # Base query (pct + pa + month) — same as v1
        base_sql = f"""
        SELECT snap_l150, snap_total_pa, snap_month, snap_percentile,
               snap_age,
               next_30pa_xwoba, next_60pa_xwoba, next_90pa_xwoba,
               career_median_at_snap, batter, snap_date
        FROM hist_snapshots
        WHERE batter != {batter_id}
          AND ABS(snap_percentile - {cur_pct}) <= {percentile_window}
          AND snap_total_pa BETWEEN {pa_lo} AND {pa_hi}
          AND snap_month IN ({months_str})
          AND next_30pa_xwoba IS NOT NULL
        """
        comps_base = con.execute(base_sql).df()
        n_comps_before_age = len(comps_base)

        # Age filter — only apply if we have current_age AND snap_age is populated
        if cur_age is not None and "snap_age" in comps_base.columns:
            age_mask = comps_base["snap_age"].notna() & (
                (comps_base["snap_age"] - cur_age).abs() <= age_window
            )
            comps = comps_base[age_mask].copy()
        else:
            comps = comps_base.copy()

        n_comps = len(comps)

        if n_comps < 5:
            results[batter_id] = {
                "insufficient_comps": True,
                "n_comps": n_comps,
                "n_comps_before_age_filter": n_comps_before_age,
                "current_age": cur_age,
                "age_window_used": age_window,
            }
            continue

        arr30 = comps["next_30pa_xwoba"].dropna().values
        arr60 = comps["next_60pa_xwoba"].dropna().values

        # Bounce thresholds
        bounce_threshold = 0.010
        p_bounced_30 = float(np.mean(arr30 > comps["snap_l150"].values + bounce_threshold))
        p_bounced_60 = (
            float(np.mean(arr60 > comps["snap_l150"].values[:len(arr60)] + bounce_threshold))
            if len(arr60) > 0
            else float("nan")
        )
        p_bounced_above_median = float(
            np.mean(arr30 > comps["career_median_at_snap"].dropna().values[:len(arr30)])
        )

        # Build comp_sample: up to 5 example descriptions
        comp_sample_rows = comps.head(5)
        comp_sample = []
        for _, cr in comp_sample_rows.iterrows():
            bid = int(cr["batter"])
            name = name_map.get(bid, f"Batter#{bid}")
            year = str(cr["snap_date"])[:4] if pd.notna(cr["snap_date"]) else "????"
            pct = cr["snap_percentile"]
            age_str = f", age {int(cr['snap_age'])}" if pd.notna(cr.get("snap_age")) else ""
            comp_sample.append(f"{name} ({year}{age_str}) at {pct:.0%} form")

        results[batter_id] = {
            "current_percentile": cur_pct,
            "current_total_pa": cur_pa,
            "current_l150": cur_l150,
            "current_age": cur_age,
            "age_window_used": age_window,
            "n_comps": n_comps,
            "n_comps_before_age_filter": n_comps_before_age,
            "n_comps_age_filtered": n_comps,
            "p_bounced_30pa": p_bounced_30,
            "p_bounced_60pa": p_bounced_60,
            "p_bounced_above_career_median": p_bounced_above_median,
            "median_next_30pa": float(np.median(arr30)),
            "median_next_60pa": float(np.median(arr60)) if len(arr60) > 0 else float("nan"),
            "p10_next_30pa": float(np.percentile(arr30, 10)),
            "p25_next_30pa": float(np.percentile(arr30, 25)),
            "p75_next_30pa": float(np.percentile(arr30, 75)),
            "p90_next_30pa": float(np.percentile(arr30, 90)),
            "worst_case_30pa": float(np.percentile(arr30, 5)),
            "best_case_30pa": float(np.percentile(arr30, 95)),
            "comp_sample": comp_sample,
        }

    con.close()
    return results


# ---------------------------------------------------------------------------
# CLI / __main__
# ---------------------------------------------------------------------------

def _print_result(batter_id: int, result: dict, name_map: dict[int, str]) -> None:
    name = name_map.get(batter_id, f"Batter#{batter_id}")
    print(f"\n{'='*60}")
    print(f"  {name} (mlbam={batter_id})")
    print(f"{'='*60}")

    if result.get("error"):
        print(f"  ERROR: {result['error']}")
        return
    if result.get("insufficient_comps"):
        cur_age = result.get("current_age")
        age_str = f", age {cur_age}" if cur_age is not None else ""
        print(f"  INSUFFICIENT COMPS: {result['n_comps']} after age filter "
              f"(was {result.get('n_comps_before_age_filter', '?')} before){age_str} — need ≥5")
        return

    age_str = f", age {result['current_age']}" if result.get("current_age") is not None else ""
    before = result.get("n_comps_before_age_filter", result["n_comps"])
    after = result["n_comps"]
    age_win = result.get("age_window_used", "?")

    print(f"  Current form  : {result['current_percentile']:.0%} career percentile")
    print(f"  Current L150  : {result['current_l150']:.3f} xwOBA")
    print(f"  Career PA     : {result['current_total_pa']:,}")
    print(f"  Age           : {result['current_age'] if result['current_age'] is not None else 'n/a'}{age_str}")
    print(f"  Comps (before age filter ±{age_win}yr): {before:,}")
    print(f"  Comps (after  age filter ±{age_win}yr): {after:,}  [{before - after:,} removed]")
    print()
    print(f"  Outcome distributions (next 30 PA):")
    print(f"    Worst (P5)  : {result['worst_case_30pa']:.3f}")
    print(f"    P10         : {result['p10_next_30pa']:.3f}")
    print(f"    P25         : {result['p25_next_30pa']:.3f}")
    print(f"    Median      : {result['median_next_30pa']:.3f}")
    print(f"    P75         : {result['p75_next_30pa']:.3f}")
    print(f"    P90         : {result['p90_next_30pa']:.3f}")
    print(f"    Best (P95)  : {result['best_case_30pa']:.3f}")
    print()
    print(f"  Probabilities:")
    print(f"    P(meaningful bounce in 30 PA): {result['p_bounced_30pa']:.1%}")
    print(f"    P(meaningful bounce in 60 PA): {result['p_bounced_60pa']:.1%}")
    print(f"    P(above career median in 30 PA): {result['p_bounced_above_career_median']:.1%}")
    print(f"    Median next-60 PA xwOBA: {result['median_next_60pa']:.3f}")
    print()
    print(f"  Example comps:")
    for c in result["comp_sample"]:
        print(f"    - {c}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical comp matcher for hitters (v2: age-aware)")
    parser.add_argument(
        "--batter-ids", nargs="+", type=int,
        help="MLB batter IDs (mlbam). Defaults to test set.",
    )
    parser.add_argument(
        "--mode", choices=["slump", "peak"], default="slump",
        help="Informational label for the analysis (default: slump)",
    )
    parser.add_argument(
        "--percentile-window", type=float, default=0.10,
        help="±percentile window for matching (default: 0.10)",
    )
    parser.add_argument(
        "--pa-window", type=float, default=0.20,
        help="±fraction of career PA for matching (default: 0.20)",
    )
    parser.add_argument(
        "--month-window", type=int, default=1,
        help="±calendar months for matching (default: 1)",
    )
    parser.add_argument(
        "--age-window", type=int, default=3,
        help="±years for age matching (default: 3); set to 99 to disable",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Force rebuild of the historical snapshot cache",
    )
    args = parser.parse_args()

    # Default test set: Vlad Guerrero Jr., Manny Machado, Freddie Freeman,
    # Josh Naylor, Cal Raleigh
    default_ids = [
        665489,  # Vladimir Guerrero Jr. (27)
        592518,  # Manny Machado (33)
        518692,  # Freddie Freeman (36)
        647304,  # Josh Naylor (27)
        663728,  # Cal Raleigh (28)
    ]
    batter_ids = args.batter_ids or default_ids

    if args.rebuild and CACHE_PATH.exists():
        print(f"[rebuild] removing {CACHE_PATH.name}...")
        CACHE_PATH.unlink()

    print(f"[historical_comp_matcher v2] analyzing {len(batter_ids)} batters "
          f"(mode={args.mode}, age_window=±{args.age_window}yr)")

    results = batch_historical_comps(
        batter_ids=batter_ids,
        mode=args.mode,
        percentile_window=args.percentile_window,
        pa_window=args.pa_window,
        month_window=args.month_window,
        age_window=args.age_window,
    )

    name_map = load_name_map()
    for bid, result in results.items():
        _print_result(bid, result, name_map)

    # Summary table
    print(f"\n{'='*60}")
    print("  AGE-FILTER IMPACT SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Player':<25} {'Age':>4} {'Before':>8} {'After':>8} {'Removed':>9} {'P(bounce30)':>12}")
    print(f"  {'-'*25} {'-'*4} {'-'*8} {'-'*8} {'-'*9} {'-'*12}")
    name_map = load_name_map()
    for bid in batter_ids:
        r = results.get(bid, {})
        name = name_map.get(bid, f"Batter#{bid}")
        if r.get("error") or r.get("insufficient_comps"):
            age = r.get("current_age", "?")
            before = r.get("n_comps_before_age_filter", "?")
            after = r.get("n_comps", "?")
            removed = (before - after) if isinstance(before, int) and isinstance(after, int) else "?"
            print(f"  {name:<25} {str(age):>4} {str(before):>8} {str(after):>8} {str(removed):>9}  INSUFF/ERR")
        else:
            age = r.get("current_age", "?")
            before = r.get("n_comps_before_age_filter", r["n_comps"])
            after = r["n_comps"]
            removed = before - after
            pb = r["p_bounced_30pa"]
            print(f"  {name:<25} {str(age):>4} {before:>8,} {after:>8,} {removed:>9,}  {pb:>11.1%}")

    print(f"\n[done] {len(results)} batters processed")


if __name__ == "__main__":
    main()
