"""
peak_breakout_validator.py
==========================
Batch-classify PEAK-form hitters as PROCESS_DRIVEN, OUTCOME_DRIVEN,
MIXED, or UNCONFIRMED by comparing bat-tracking and discipline metrics
across three windows: 2025 full season, 2026 season-to-date, 2026 L21d.

Usage
-----
    from scripts.xfp.peak_breakout_validator import batch_peak_validator
    results = batch_peak_validator([669257, 596748, 682928])
"""

from __future__ import annotations

import os
from typing import Any

import duckdb

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PARQUET_2025 = os.path.join(_REPO_ROOT, "data", "research", "xfp_cache", "statcast_2025.parquet")
_PARQUET_2026 = os.path.join(_REPO_ROOT, "data", "research", "xfp_cache", "statcast_2026.parquet")

# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------
_SWING_DESC = (
    "description IN ("
    "'swinging_strike','swinging_strike_blocked','foul','foul_tip','hit_into_play'"
    ")"
)

_METRIC_SELECT = """
    batter,
    AVG(CASE WHEN bat_speed IS NOT NULL AND {swing} THEN bat_speed END)                          AS avg_bat_speed,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY launch_speed)
        FILTER (WHERE launch_speed IS NOT NULL)                                                   AS ev90,
    AVG(CASE WHEN launch_speed IS NOT NULL THEN CAST(launch_speed >= 95 AS INTEGER) END)          AS hard_hit_pct,
    -- whiff_pct: swinging strikes / total swings
    CAST(
        SUM(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked') THEN 1 ELSE 0 END)
        AS DOUBLE
    ) / NULLIF(SUM(CASE WHEN {swing} THEN 1 ELSE 0 END), 0)                                      AS whiff_pct,
    -- chase_pct: OOZ swings / OOZ pitches
    CAST(
        SUM(CASE WHEN (zone < 1 OR zone > 9) AND {swing} THEN 1 ELSE 0 END)
        AS DOUBLE
    ) / NULLIF(SUM(CASE WHEN zone < 1 OR zone > 9 THEN 1 ELSE 0 END), 0)                        AS chase_pct,
    -- z_contact_pct: in-zone contacts / in-zone swings
    CAST(
        SUM(CASE WHEN zone BETWEEN 1 AND 9 AND {swing}
                  AND description NOT IN ('swinging_strike','swinging_strike_blocked')
             THEN 1 ELSE 0 END)
        AS DOUBLE
    ) / NULLIF(SUM(CASE WHEN zone BETWEEN 1 AND 9 AND {swing} THEN 1 ELSE 0 END), 0)            AS z_contact_pct,
    AVG(CASE WHEN launch_speed IS NOT NULL THEN estimated_woba_using_speedangle END)              AS xwobacon,
    SUM(CASE WHEN {swing} THEN 1 ELSE 0 END)                                                     AS n_swings
""".format(swing=_SWING_DESC)


def _pull_season_metrics(con: duckdb.DuckDBPyConnection, parquet: str, batter_ids: list[int]) -> dict[int, dict]:
    """Aggregate full-season metrics for a set of batter IDs from one parquet."""
    ids_sql = ", ".join(str(b) for b in batter_ids)
    sql = f"""
        SELECT
            {_METRIC_SELECT}
        FROM read_parquet('{parquet}')
        WHERE batter IN ({ids_sql})
        GROUP BY batter
    """
    rows = con.execute(sql).fetchall()
    cols = ["batter", "avg_bat_speed", "ev90", "hard_hit_pct", "whiff_pct",
            "chase_pct", "z_contact_pct", "xwobacon", "n_swings"]
    result: dict[int, dict] = {}
    for row in rows:
        d = dict(zip(cols, row))
        bid = int(d.pop("batter"))
        # convert whiff/chase/z_contact/hard_hit to percentages (* 100)
        for pct_col in ("whiff_pct", "chase_pct", "z_contact_pct", "hard_hit_pct"):
            if d[pct_col] is not None:
                d[pct_col] = round(d[pct_col] * 100, 2)
        for col in ("avg_bat_speed", "ev90", "xwobacon"):
            if d[col] is not None:
                d[col] = round(float(d[col]), 3)
        if d["n_swings"] is not None:
            d["n_swings"] = int(d["n_swings"])
        result[bid] = d
    return result


def _pull_l21d_metrics(con: duckdb.DuckDBPyConnection, parquet: str, batter_ids: list[int]) -> dict[int, dict]:
    """Pull last-21 PA events per batter and compute the same metrics."""
    ids_sql = ", ".join(str(b) for b in batter_ids)

    # Rank PA events per batter (PA = row where events IS NOT NULL and != '')
    # then take the last 21, then expand to all pitches in those at-bats,
    # but spec says "last 21 PA events" so we interpret as last 21 rows where
    # events column is non-null, then pull all pitches for those at_bat_numbers.
    # Simpler spec-faithful approach: just take all pitches within the game_dates
    # of those 21 PA rows.

    sql_pa_ranked = f"""
        WITH pa_events AS (
            SELECT *,
                ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date, at_bat_number) AS pa_rn,
                COUNT(*) OVER (PARTITION BY batter) AS total_pas
            FROM read_parquet('{parquet}')
            WHERE batter IN ({ids_sql})
              AND events IS NOT NULL
              AND events != ''
        ),
        last21_pa AS (
            SELECT batter, game_pk, at_bat_number
            FROM pa_events
            WHERE pa_rn > total_pas - 21
        ),
        l21d_pitches AS (
            SELECT p.*
            FROM read_parquet('{parquet}') p
            JOIN last21_pa l
              ON p.batter = l.batter
             AND p.game_pk = l.game_pk
             AND p.at_bat_number = l.at_bat_number
        )
        SELECT
            batter,
            AVG(CASE WHEN bat_speed IS NOT NULL AND {_SWING_DESC} THEN bat_speed END) AS avg_bat_speed,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY launch_speed)
                FILTER (WHERE launch_speed IS NOT NULL)                                AS ev90,
            AVG(CASE WHEN launch_speed IS NOT NULL THEN CAST(launch_speed >= 95 AS INTEGER) END) AS hard_hit_pct,
            CAST(
                SUM(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked') THEN 1 ELSE 0 END)
                AS DOUBLE
            ) / NULLIF(SUM(CASE WHEN {_SWING_DESC} THEN 1 ELSE 0 END), 0)             AS whiff_pct,
            CAST(
                SUM(CASE WHEN (zone < 1 OR zone > 9) AND {_SWING_DESC} THEN 1 ELSE 0 END)
                AS DOUBLE
            ) / NULLIF(SUM(CASE WHEN zone < 1 OR zone > 9 THEN 1 ELSE 0 END), 0)     AS chase_pct,
            CAST(
                SUM(CASE WHEN zone BETWEEN 1 AND 9 AND {_SWING_DESC}
                          AND description NOT IN ('swinging_strike','swinging_strike_blocked')
                     THEN 1 ELSE 0 END)
                AS DOUBLE
            ) / NULLIF(SUM(CASE WHEN zone BETWEEN 1 AND 9 AND {_SWING_DESC} THEN 1 ELSE 0 END), 0) AS z_contact_pct,
            AVG(CASE WHEN launch_speed IS NOT NULL THEN estimated_woba_using_speedangle END) AS xwobacon,
            SUM(CASE WHEN {_SWING_DESC} THEN 1 ELSE 0 END)                             AS n_swings
        FROM l21d_pitches
        GROUP BY batter
    """

    rows = con.execute(sql_pa_ranked).fetchall()
    cols = ["batter", "avg_bat_speed", "ev90", "hard_hit_pct", "whiff_pct",
            "chase_pct", "z_contact_pct", "xwobacon", "n_swings"]
    result: dict[int, dict] = {}
    for row in rows:
        d = dict(zip(cols, row))
        bid = int(d.pop("batter"))
        for pct_col in ("whiff_pct", "chase_pct", "z_contact_pct", "hard_hit_pct"):
            if d[pct_col] is not None:
                d[pct_col] = round(d[pct_col] * 100, 2)
        for col in ("avg_bat_speed", "ev90", "xwobacon"):
            if d[col] is not None:
                d[col] = round(float(d[col]), 3)
        if d["n_swings"] is not None:
            d["n_swings"] = int(d["n_swings"])
        result[bid] = d
    return result


def _empty_metrics() -> dict:
    return {
        "avg_bat_speed": None, "ev90": None, "hard_hit_pct": None,
        "whiff_pct": None, "chase_pct": None, "z_contact_pct": None,
        "xwobacon": None, "n_swings": 0,
    }


def _compute_deltas(m2026: dict, m2025: dict) -> dict:
    """Return delta for each metric (2026_szn minus 2025). None if either side is None."""
    metrics = ["avg_bat_speed", "ev90", "hard_hit_pct", "whiff_pct",
               "chase_pct", "z_contact_pct", "xwobacon"]
    out: dict[str, float | None] = {}
    for m in metrics:
        a, b = m2026.get(m), m2025.get(m)
        if a is not None and b is not None:
            out[m] = round(a - b, 4)
        else:
            out[m] = None
    return out


def _classify(deltas: dict, n_swings_2026: int) -> tuple[str, str, int]:
    """Return (peak_type, peak_note, n_process_signals)."""
    if n_swings_2026 < 100:
        return "UNCONFIRMED", "Insufficient 2026 data (n_swings < 100).", 0

    signals: list[str] = []
    signal_count = 0

    def _check(val, threshold, label, higher_is_better=True):
        nonlocal signal_count
        if val is None:
            return
        improved = (val > threshold) if higher_is_better else (val < threshold)
        if improved:
            signal_count += 1
            signals.append(label)

    _check(deltas.get("avg_bat_speed"), 1.0,  f"bat_speed {_fmt(deltas.get('avg_bat_speed'))}mph")
    _check(deltas.get("ev90"),          1.5,  f"EV90 {_fmt(deltas.get('ev90'))}mph")
    _check(deltas.get("whiff_pct"),    -2.0,  f"whiff% {_fmt(deltas.get('whiff_pct'))}pt",  higher_is_better=False)
    _check(deltas.get("chase_pct"),    -2.0,  f"chase% {_fmt(deltas.get('chase_pct'))}pt",  higher_is_better=False)
    _check(deltas.get("z_contact_pct"), 2.0,  f"z_contact% {_fmt(deltas.get('z_contact_pct'))}pt")
    _check(deltas.get("xwobacon"),      0.020, f"xwOBAcon {_fmt(deltas.get('xwobacon'), 3)}")

    if signal_count >= 3:
        peak_type = "PROCESS_DRIVEN"
        note = " — ".join(signals) + " — all physical inputs improved"
    elif signal_count == 0:
        peak_type = "OUTCOME_DRIVEN"
        note = "No process metrics improved. Surface outcomes likely inflated over true skill."
    else:
        peak_type = "MIXED"
        improving = "; ".join(signals) if signals else "none"
        note = f"Partial process improvement ({signal_count}/6). Improving: {improving}"

    return peak_type, note, signal_count


def _fmt(val, decimals=1) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.{decimals}f}"


_TRADE_IMPLICATIONS = {
    "PROCESS_DRIVEN": "Hold. Peak is real. Don't sell.",
    "OUTCOME_DRIVEN": "Sell-high window. Surface wOBA > xwOBA. Reversion likely.",
    "MIXED":          "Partial. Monitor one more week.",
    "UNCONFIRMED":    "Insufficient data.",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def batch_peak_validator(batter_ids: list[int]) -> dict[int, dict[str, Any]]:
    """
    Classify each batter's PEAK-form as PROCESS_DRIVEN / OUTCOME_DRIVEN /
    MIXED / UNCONFIRMED by comparing bat-tracking and discipline metrics
    across 2025, 2026 season, and 2026 L21d windows.

    Parameters
    ----------
    batter_ids : list of MLB batter IDs (Statcast `batter` column)

    Returns
    -------
    dict keyed by batter_id with metrics, deltas, classification, note, trade implication
    """
    if not batter_ids:
        return {}

    con = duckdb.connect()

    # Pull all data in bulk
    metrics_2025   = _pull_season_metrics(con, _PARQUET_2025, batter_ids)
    metrics_2026   = _pull_season_metrics(con, _PARQUET_2026, batter_ids)
    metrics_l21d   = _pull_l21d_metrics(con, _PARQUET_2026, batter_ids)

    con.close()

    results: dict[int, dict] = {}
    for bid in batter_ids:
        m25  = metrics_2025.get(bid, _empty_metrics())
        m26  = metrics_2026.get(bid, _empty_metrics())
        ml21 = metrics_l21d.get(bid, _empty_metrics())

        deltas = _compute_deltas(m26, m25)
        n_swings_2026 = m26.get("n_swings") or 0

        peak_type, peak_note, n_process = _classify(deltas, n_swings_2026)

        results[bid] = {
            "metrics": {
                "2025":     m25,
                "2026_szn": m26,
                "l21d":     ml21,
            },
            "deltas_szn_vs_2025": deltas,
            "peak_type":          peak_type,
            "peak_note":          peak_note,
            "trade_implication":  _TRADE_IMPLICATIONS[peak_type],
            "n_process_signals":  n_process,
        }

    return results


# ---------------------------------------------------------------------------
# __main__ smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    # Three known PEAK-form players from yesterday's audit
    TEST_BATTERS = {
        669257: "Shea Langeliers",
        596748: "Brandon Lowe",
        682928: "Drake Baldwin",
    }

    print("=" * 65)
    print("peak_breakout_validator — smoke test")
    print("=" * 65)

    results = batch_peak_validator(list(TEST_BATTERS.keys()))

    for bid, name in TEST_BATTERS.items():
        r = results.get(bid)
        if r is None:
            print(f"\n{name} ({bid}): NO DATA\n")
            continue

        print(f"\n{name} ({bid})")
        print(f"  peak_type        : {r['peak_type']}")
        print(f"  n_process_signals: {r['n_process_signals']}/6")
        print(f"  peak_note        : {r['peak_note']}")
        print(f"  trade_implication: {r['trade_implication']}")
        print()

        m25  = r["metrics"]["2025"]
        m26  = r["metrics"]["2026_szn"]
        ml21 = r["metrics"]["l21d"]
        d    = r["deltas_szn_vs_2025"]

        header = f"  {'Metric':<18} {'2025':>9} {'2026_szn':>9} {'delta':>9} {'l21d':>9}"
        print(header)
        print("  " + "-" * (len(header) - 2))

        metrics_order = ["avg_bat_speed", "ev90", "hard_hit_pct", "whiff_pct",
                         "chase_pct", "z_contact_pct", "xwobacon", "n_swings"]
        for m in metrics_order:
            v25  = m25.get(m)
            v26  = m26.get(m)
            vd   = d.get(m)
            vl   = ml21.get(m)
            fmt  = lambda v: f"{v:>9.3f}" if isinstance(v, float) else (f"{v:>9}" if v is not None else f"{'N/A':>9}")
            delta_str = _fmt(vd, 3) if isinstance(vd, float) else "N/A"
            print(f"  {m:<18} {fmt(v25)} {fmt(v26)} {delta_str:>9} {fmt(vl)}")

    print("\n" + "=" * 65)
