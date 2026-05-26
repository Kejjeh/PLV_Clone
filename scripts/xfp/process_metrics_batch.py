"""
process_metrics_batch.py
========================
Batch compute discipline / contact-quality / bat-tracking metrics for a list
of batters across three windows:

  - "2025"     : full 2025 Statcast season
  - "2026_szn" : 2026 season-to-date
  - "l21d"     : last 21 PA events (event-based) from the 2026 parquet

Returns a dict[batter_id, {...}] with per-window metrics, deltas (l21d vs 2025),
a process_verdict, and human-readable process_notes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("c:/Users/Joshua/plv_clone")
sys.path.insert(0, str(ROOT))

import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Parquet paths
# ---------------------------------------------------------------------------
P2025 = (ROOT / "data/research/xfp_cache/statcast_2025.parquet").as_posix()
P2026 = (ROOT / "data/research/xfp_cache/statcast_2026.parquet").as_posix()

# ---------------------------------------------------------------------------
# Description column sets
# ---------------------------------------------------------------------------
SWING_DESCS = ("swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play")
CONTACT_DESCS = ("foul", "hit_into_play")  # for z_contact_pct numerator


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _metric_cols() -> str:
    """Return the SELECT expressions for per-pitch metrics (no GROUP BY yet)."""
    swing_in = ", ".join(f"'{d}'" for d in SWING_DESCS)
    contact_in = ", ".join(f"'{d}'" for d in CONTACT_DESCS)
    return f"""
        batter,
        -- swing flag
        CASE WHEN description IN ({swing_in}) THEN 1 ELSE 0 END AS is_swing,
        -- whiff flag (numerator of whiff%)
        CASE WHEN description = 'swinging_strike' THEN 1 ELSE 0 END AS is_whiff,
        -- OOZ pitch flag
        CASE WHEN zone IS NOT NULL AND zone NOT BETWEEN 1 AND 9 THEN 1 ELSE 0 END AS is_ooz,
        -- OOZ swing flag
        CASE WHEN zone IS NOT NULL AND zone NOT BETWEEN 1 AND 9
              AND description IN ({swing_in}) THEN 1 ELSE 0 END AS is_ooz_swing,
        -- in-zone swing flag
        CASE WHEN zone BETWEEN 1 AND 9
              AND description IN ({swing_in}) THEN 1 ELSE 0 END AS is_iz_swing,
        -- in-zone contact flag
        CASE WHEN zone BETWEEN 1 AND 9
              AND description IN ({contact_in}) THEN 1 ELSE 0 END AS is_iz_contact,
        -- batted ball flags
        CASE WHEN events IS NOT NULL AND events != '' AND launch_speed IS NOT NULL
             THEN 1 ELSE 0 END AS is_bip_spd,
        CASE WHEN events IS NOT NULL AND events != '' AND launch_speed IS NOT NULL
             THEN launch_speed ELSE NULL END AS bip_speed,
        -- hard-hit flag
        CASE WHEN events IS NOT NULL AND events != '' AND launch_speed >= 95
             THEN 1 ELSE 0 END AS is_hard_hit,
        -- bat speed (NULL when not a swing or not tracked)
        CASE WHEN bat_speed IS NOT NULL THEN bat_speed ELSE NULL END AS bat_speed_val,
        -- PA event flag
        CASE WHEN events IS NOT NULL AND events != '' THEN 1 ELSE 0 END AS is_pa
    """


def _agg_sql(source_expr: str, batter_list: str) -> str:
    """Build a GROUP BY aggregation query from a source expression (subquery alias or table)."""
    return f"""
        SELECT
            batter,
            SUM(is_swing)        AS n_swings,
            SUM(is_whiff)        AS n_whiffs,
            SUM(is_ooz)          AS n_ooz,
            SUM(is_ooz_swing)    AS n_ooz_swings,
            SUM(is_iz_swing)     AS n_iz_swings,
            SUM(is_iz_contact)   AS n_iz_contacts,
            SUM(is_bip_spd)      AS n_bip,
            SUM(is_hard_hit)     AS n_hard_hit,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY bip_speed) AS ev90,
            AVG(bat_speed_val)   AS avg_bat_speed,
            SUM(is_pa)           AS n_pa
        FROM ({source_expr}) t
        WHERE batter IN ({batter_list})
        GROUP BY batter
    """


def _base_select(parquet_path: str, batter_list: str) -> str:
    return f"""
        SELECT {_metric_cols()}
        FROM read_parquet('{parquet_path}')
        WHERE batter IN ({batter_list})
    """


# ---------------------------------------------------------------------------
# Metric computation from a DataFrame row
# ---------------------------------------------------------------------------

def _row_to_metrics(row: pd.Series) -> dict:
    n_swings = int(row.get("n_swings", 0) or 0)
    n_whiffs = int(row.get("n_whiffs", 0) or 0)
    n_ooz = int(row.get("n_ooz", 0) or 0)
    n_ooz_swings = int(row.get("n_ooz_swings", 0) or 0)
    n_iz_swings = int(row.get("n_iz_swings", 0) or 0)
    n_iz_contacts = int(row.get("n_iz_contacts", 0) or 0)
    n_bip = int(row.get("n_bip", 0) or 0)
    n_hard_hit = int(row.get("n_hard_hit", 0) or 0)
    n_pa = int(row.get("n_pa", 0) or 0)
    ev90 = row.get("ev90")
    avg_bat_speed = row.get("avg_bat_speed")

    return {
        "whiff_pct": round(n_whiffs / n_swings, 4) if n_swings else None,
        "chase_pct": round(n_ooz_swings / n_ooz, 4) if n_ooz else None,
        "z_contact_pct": round(n_iz_contacts / n_iz_swings, 4) if n_iz_swings else None,
        "ev90": round(float(ev90), 1) if ev90 is not None and not pd.isna(ev90) else None,
        "hard_hit_pct": round(n_hard_hit / n_bip, 4) if n_bip else None,
        "avg_bat_speed": round(float(avg_bat_speed), 1) if avg_bat_speed is not None and not pd.isna(avg_bat_speed) else None,
        "n_swings": n_swings,
        "n_pa": n_pa,
    }


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

_WHIFF_IMPR_THRESH = -0.02     # negative = fewer whiffs = good
_WHIFF_DECL_THRESH = +0.02     # positive > 2pt = bad
_CHASE_IMPR_THRESH = -0.01
_ZCON_IMPR_THRESH = +0.01
_EV90_DECL_THRESH = -2.0       # more than 2mph drop = flagging
_HH_DECL_THRESH = -0.03        # more than 3pt drop = bad
_MIN_L21D_SWINGS = 25


def _compute_verdict(l21d: dict, s2025: dict) -> tuple[str, str]:
    """Return (verdict, notes) comparing l21d window to 2025 baseline."""
    # Check sample size
    if l21d.get("n_swings", 0) < _MIN_L21D_SWINGS:
        return "INSUFFICIENT", f"only {l21d.get('n_swings', 0)} swings in L21d (need {_MIN_L21D_SWINGS})"

    def delta(key: str):
        v_l21d = l21d.get(key)
        v_2025 = s2025.get(key)
        if v_l21d is None or v_2025 is None:
            return None
        return round(v_l21d - v_2025, 4)

    d_whiff = delta("whiff_pct")
    d_chase = delta("chase_pct")
    d_zcon = delta("z_contact_pct")
    d_ev90 = delta("ev90")
    d_hh = delta("hard_hit_pct")
    d_bat = delta("avg_bat_speed")

    # Build note fragments
    frags = []
    if d_whiff is not None:
        sign = "-" if d_whiff < 0 else "+"
        frags.append(f"whiff% {sign}{abs(d_whiff)*100:.1f}pt {'(improving)' if d_whiff < 0 else '(worsening)'}")
    if d_chase is not None:
        sign = "-" if d_chase < 0 else "+"
        frags.append(f"chase% {sign}{abs(d_chase)*100:.1f}pt {'(improving)' if d_chase < 0 else '(worsening)'}")
    if d_zcon is not None:
        sign = "+" if d_zcon > 0 else "-"
        frags.append(f"z-contact% {sign}{abs(d_zcon)*100:.1f}pt {'(improving)' if d_zcon > 0 else '(worsening)'}")
    if d_ev90 is not None:
        sign = "+" if d_ev90 > 0 else "-"
        frags.append(f"EV90 {sign}{abs(d_ev90):.1f}mph {'(power up)' if d_ev90 > 0 else '(power flagging)'}")
    if d_hh is not None:
        sign = "+" if d_hh > 0 else "-"
        frags.append(f"hard-hit% {sign}{abs(d_hh)*100:.1f}pt {'(up)' if d_hh > 0 else '(down)'}")
    if d_bat is not None:
        sign = "+" if d_bat > 0 else "-"
        frags.append(f"bat speed {sign}{abs(d_bat):.1f}mph")

    notes = "; ".join(frags) if frags else "no baseline data"

    # Verdict logic
    whiff_impr = d_whiff is not None and d_whiff <= _WHIFF_IMPR_THRESH
    chase_impr = d_chase is not None and d_chase <= _CHASE_IMPR_THRESH
    zcon_impr = d_zcon is not None and d_zcon >= _ZCON_IMPR_THRESH
    ev90_ok = d_ev90 is None or d_ev90 > _EV90_DECL_THRESH  # not dropping hard

    whiff_decl = d_whiff is not None and d_whiff >= _WHIFF_DECL_THRESH
    ev90_decl = d_ev90 is not None and d_ev90 <= _EV90_DECL_THRESH
    hh_decl = d_hh is not None and d_hh <= _HH_DECL_THRESH

    improving = whiff_impr and (chase_impr or zcon_impr) and ev90_ok
    declining = (whiff_decl or ev90_decl) and hh_decl

    if improving:
        verdict = "IMPROVING"
    elif declining:
        verdict = "DECLINING"
    else:
        # Count directional signals
        good_signals = sum([
            d_whiff is not None and d_whiff < 0,
            d_chase is not None and d_chase < 0,
            d_zcon is not None and d_zcon > 0,
            d_ev90 is not None and d_ev90 > 0,
            d_hh is not None and d_hh > 0,
        ])
        bad_signals = sum([
            d_whiff is not None and d_whiff > 0,
            d_chase is not None and d_chase > 0,
            d_zcon is not None and d_zcon < 0,
            d_ev90 is not None and d_ev90 < 0,
            d_hh is not None and d_hh < 0,
        ])
        if good_signals >= 3 and bad_signals <= 1:
            verdict = "STABLE"  # mostly green
        elif bad_signals >= 3 and good_signals <= 1:
            verdict = "DECLINING"
        elif abs(good_signals - bad_signals) <= 1:
            verdict = "MIXED"
        else:
            verdict = "STABLE"

    return verdict, notes


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def batch_process_metrics(batter_ids: list[int]) -> dict[int, dict]:
    """
    Compute discipline / contact-quality / bat-tracking metrics for each batter
    across three windows (2025, 2026_szn, l21d).

    Parameters
    ----------
    batter_ids : list of MLB batter IDs (MLBAM integers)

    Returns
    -------
    dict[batter_id, {
        "2025": {...},
        "2026_szn": {...},
        "l21d": {...},
        "deltas": {...},
        "process_verdict": str,
        "process_notes": str,
    }]
    """
    if not batter_ids:
        return {}

    batter_list = ", ".join(str(b) for b in batter_ids)
    con = duckdb.connect()

    # ------------------------------------------------------------------
    # 1. Pull 2025 aggregates in one shot
    # ------------------------------------------------------------------
    sql_2025 = _agg_sql(_base_select(P2025, batter_list), batter_list)
    df_2025 = con.execute(sql_2025).df()
    df_2025 = df_2025.set_index("batter")

    # ------------------------------------------------------------------
    # 2. Pull ALL 2026 pitch-level rows for these batters, then split
    #    into 2026_szn (all) and l21d (last 21 PA events per batter)
    # ------------------------------------------------------------------
    sql_2026_raw = f"""
        SELECT
            batter,
            game_date,
            at_bat_number,
            {_metric_cols().strip().replace('batter,', '').strip()}
        FROM read_parquet('{P2026}')
        WHERE batter IN ({batter_list})
        ORDER BY batter, game_date, at_bat_number
    """
    df_raw = con.execute(sql_2026_raw).df()
    con.close()

    # ------------------------------------------------------------------
    # 2a. 2026 season aggregate — register df and query with duckdb
    # ------------------------------------------------------------------
    con2 = duckdb.connect()
    con2.register("raw2026", df_raw)

    sql_2026_szn_agg = f"""
        SELECT
            batter,
            SUM(is_swing)        AS n_swings,
            SUM(is_whiff)        AS n_whiffs,
            SUM(is_ooz)          AS n_ooz,
            SUM(is_ooz_swing)    AS n_ooz_swings,
            SUM(is_iz_swing)     AS n_iz_swings,
            SUM(is_iz_contact)   AS n_iz_contacts,
            SUM(is_bip_spd)      AS n_bip,
            SUM(is_hard_hit)     AS n_hard_hit,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY bip_speed) AS ev90,
            AVG(bat_speed_val)   AS avg_bat_speed,
            SUM(is_pa)           AS n_pa
        FROM raw2026
        GROUP BY batter
    """
    df_2026_szn = con2.execute(sql_2026_szn_agg).df().set_index("batter")

    # ------------------------------------------------------------------
    # 2b. L21d — last 21 PA events per batter (event-based, not date-based)
    #     PA event = is_pa == 1
    # ------------------------------------------------------------------
    # Pull only the PA rows per batter, ranked by (game_date, at_bat_number)
    # Take the last 21.
    l21d_frames = []
    for bid, grp in df_raw.groupby("batter"):
        pa_rows = grp[grp["is_pa"] == 1].copy()
        pa_rows = pa_rows.sort_values(["game_date", "at_bat_number"])
        last_21_abs = pa_rows.tail(21)["at_bat_number"].unique()
        # Get all pitches from those at-bats (to compute whiff/chase etc. on full ABs)
        l21_pitches = grp[grp["at_bat_number"].isin(last_21_abs)]
        l21d_frames.append(l21_pitches)

    if l21d_frames:
        df_l21d_raw = pd.concat(l21d_frames, ignore_index=True)
        con2.register("l21d_raw", df_l21d_raw)
        sql_l21d_agg = f"""
            SELECT
                batter,
                SUM(is_swing)        AS n_swings,
                SUM(is_whiff)        AS n_whiffs,
                SUM(is_ooz)          AS n_ooz,
                SUM(is_ooz_swing)    AS n_ooz_swings,
                SUM(is_iz_swing)     AS n_iz_swings,
                SUM(is_iz_contact)   AS n_iz_contacts,
                SUM(is_bip_spd)      AS n_bip,
                SUM(is_hard_hit)     AS n_hard_hit,
                PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY bip_speed) AS ev90,
                AVG(bat_speed_val)   AS avg_bat_speed,
                SUM(is_pa)           AS n_pa
            FROM l21d_raw
            GROUP BY batter
        """
        df_l21d = con2.execute(sql_l21d_agg).df().set_index("batter")
    else:
        df_l21d = pd.DataFrame()

    con2.close()

    # ------------------------------------------------------------------
    # 3. Assemble results per batter
    # ------------------------------------------------------------------
    results = {}
    for bid in batter_ids:
        m_2025 = _row_to_metrics(df_2025.loc[bid]) if bid in df_2025.index else _empty_metrics()
        m_2026 = _row_to_metrics(df_2026_szn.loc[bid]) if bid in df_2026_szn.index else _empty_metrics()
        m_l21d = _row_to_metrics(df_l21d.loc[bid]) if not df_l21d.empty and bid in df_l21d.index else _empty_metrics()

        # Deltas: l21d vs 2025
        delta_keys = ["whiff_pct", "chase_pct", "z_contact_pct", "ev90", "hard_hit_pct", "avg_bat_speed"]
        deltas = {}
        for k in delta_keys:
            v_l21d = m_l21d.get(k)
            v_2025 = m_2025.get(k)
            if v_l21d is not None and v_2025 is not None:
                deltas[k] = round(v_l21d - v_2025, 4)
            else:
                deltas[k] = None

        verdict, notes = _compute_verdict(m_l21d, m_2025)

        results[bid] = {
            "2025": m_2025,
            "2026_szn": m_2026,
            "l21d": m_l21d,
            "deltas": deltas,
            "process_verdict": verdict,
            "process_notes": notes,
        }

    return results


def _empty_metrics() -> dict:
    return {
        "whiff_pct": None,
        "chase_pct": None,
        "z_contact_pct": None,
        "ev90": None,
        "hard_hit_pct": None,
        "avg_bat_speed": None,
        "n_swings": 0,
        "n_pa": 0,
    }


# ---------------------------------------------------------------------------
# CLI / smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    TEST_IDS = {
        665742: "Juan Soto",
        660670: "Ronald Acuna Jr.",
        545361: "Vlad Guerrero Jr.",
    }

    print("=" * 70)
    print("batch_process_metrics smoke test")
    print("=" * 70)

    results = batch_process_metrics(list(TEST_IDS.keys()))

    for bid, name in TEST_IDS.items():
        r = results.get(bid, {})
        print(f"\n--- {name} (ID: {bid}) ---")
        print(f"  2025 season : {r.get('2025')}")
        print(f"  2026 season : {r.get('2026_szn')}")
        print(f"  L21d        : {r.get('l21d')}")
        print(f"  Deltas      : {r.get('deltas')}")
        print(f"  VERDICT     : {r.get('process_verdict')}")
        print(f"  NOTES       : {r.get('process_notes')}")

    print("\n" + "=" * 70)
    print("Done — no errors.")
