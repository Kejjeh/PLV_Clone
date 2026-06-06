"""Canonical SP marker aggregation + hitter-marker alias for the process panel.

Single source of truth so SP marker definitions don't drift from
`scripts/xfp/build_rolling_pitchers.py:23` (SWSTR_DESC, c_plus_swstr,
barrel via `launch_speed_angle == 6` numeric, valid-xwOBA BIP for
xwoba_contact) or `scripts/xfp/pitcher_sustainability.py` (the canonical
9-marker list).

The helper accepts ONE OR MORE parquet paths so cross-year L30 windows
can UNION raw rows in a single DuckDB pass before computing rates from
the correct per-metric denominator (pitches vs OOZ pitches vs BIP vs
valid-xwOBA BIP). NEVER concat-then-reaggregate across years.
"""
from __future__ import annotations
from datetime import date
from typing import Iterable, List, Optional, Union

import duckdb
import pandas as pd

# Canonical SwStr description set per build_rolling_pitchers.py:24
# (swinging_strike + swinging_strike_blocked + foul_tip + missed_bunt).
# Bare 'swinging_strike' alone would silently UNDERCOUNT whiffs.
SWSTR_DESC = {'swinging_strike', 'swinging_strike_blocked', 'foul_tip', 'missed_bunt'}

# Canonical 9-marker list per pitcher_sustainability.py:MARKERS.
SP_MARKERS = [
    'avg_velo',
    'swstr_pct',
    'c_plus_swstr',
    'o_swing_pct',
    'k_pct',
    'bb_pct',
    'hard_hit_pct',
    'barrel_pct',
    'xwoba_contact',
]

# Direction map: '+' = higher is better (z-score multiplied by +1),
# '-' = lower is better (z-score multiplied by -1). Used by the panel
# composite to flip sign on negative-direction markers.
SP_MARKER_DIRS = {
    'avg_velo':      +1,
    'swstr_pct':     +1,
    'c_plus_swstr':  +1,
    'o_swing_pct':   +1,
    'k_pct':         +1,
    'bb_pct':        -1,
    'hard_hit_pct':  -1,
    'barrel_pct':    -1,
    'xwoba_contact': -1,
}

# Hitter marker alias resolution (Gate 0d): the rolling-features cache
# emits `chase_pct`; pitcher_sustainability + the SP helper canonically
# call the same quantity `o_swing_pct`. Resolve via this map before any
# dataframe column access.
HITTER_MARKER_ALIASES = {
    'o_swing_pct': 'chase_pct',
}


def resolve_hitter_marker(name: str) -> str:
    """Return the rolling-features column name for a canonical marker.

    For most markers this is identity (`avg_ev` -> `avg_ev`). The single
    documented alias is `o_swing_pct` -> `chase_pct`.
    """
    return HITTER_MARKER_ALIASES.get(name, name)


def _normalize_parquet_paths(parquet_paths: Union[str, Iterable[str]]) -> List[str]:
    if isinstance(parquet_paths, str):
        return [parquet_paths]
    out = list(parquet_paths)
    if not out:
        raise ValueError(
            "aggregate_sp_markers_statcast: parquet_paths must contain at least one path"
        )
    return out


def aggregate_sp_markers_statcast(
    parquet_paths: Union[str, Iterable[str]],
    *,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
    pitcher_ids: Optional[Iterable[int]] = None,
) -> pd.DataFrame:
    """Aggregate the 9 canonical SP markers from one or more Statcast parquets.

    Single source of truth for SP marker definitions across the process
    panel. Cross-year aggregation: accepts a list of parquet paths and
    UNIONs raw rows in DuckDB BEFORE computing rates — never concat
    aggregated chunks (denominators differ per metric: pitches vs OOZ
    pitches vs BIP vs valid-xwOBA BIP).

    Definitions MATCH `build_rolling_pitchers.py:23-72`:

      - avg_velo       AVG(release_speed)
      - swstr_pct      SUM(description IN SWSTR_DESC) / pitches
      - c_plus_swstr   SUM(called_strike + SWSTR_DESC) / pitches
                       (canonical CSW; uses the full SWSTR_DESC set)
      - o_swing_pct    SUM(swing AND outside zone) / OOZ pitches
                       (swing taxonomy: swinging_strike, swinging_strike_blocked,
                        foul, foul_tip, hit_into_play, foul_bunt, missed_bunt)
                       (zone IN 1..9 = in-strike-zone; OOZ = NOT IN 1..9)
      - k_pct          strikeouts / batters_faced
      - bb_pct         walks / batters_faced
      - hard_hit_pct   SUM(launch_speed >= 95) / batted_balls
      - barrel_pct     SUM(launch_speed_angle == 6) / batted_balls
                       (NUMERIC 6, not string 'barrel')
      - xwoba_contact  AVG(estimated_woba_using_speedangle)
                       WHERE batted_ball AND estimated_woba_using_speedangle IS NOT NULL
                       (over valid-xwOBA BIP rows only)

    Args:
        parquet_paths: One parquet path or an iterable of parquet paths.
            When more than one path is provided the helper builds a
            `read_parquet([...], union_by_name=True)` relation so cross-year
            L30 windows aggregate correctly across an end-of-season /
            start-of-season boundary.
        date_start: Optional inclusive lower bound on `game_date`. `None`
            means no lower bound (prior-year window).
        date_end: Optional inclusive upper bound on `game_date`. `None`
            means no upper bound.
        pitcher_ids: Optional iterable of MLBAM pitcher IDs to restrict
            aggregation to. `None` means all pitchers in the parquet(s).

    Returns:
        DataFrame indexed (default integer index) with columns:
        `pitcher`, `pitches`, `tbf`, `bip`, plus the 9 markers
        (`avg_velo`, `swstr_pct`, `c_plus_swstr`, `o_swing_pct`, `k_pct`,
        `bb_pct`, `hard_hit_pct`, `barrel_pct`, `xwoba_contact`).
    """
    paths = _normalize_parquet_paths(parquet_paths)
    quoted = ", ".join(f"'{p}'" for p in paths)
    pq_relation = f"read_parquet([{quoted}], union_by_name=True)"

    where_clauses: List[str] = []
    if date_start is not None:
        where_clauses.append(f"CAST(game_date AS DATE) >= DATE '{date_start.isoformat()}'")
    if date_end is not None:
        where_clauses.append(f"CAST(game_date AS DATE) <= DATE '{date_end.isoformat()}'")
    if pitcher_ids is not None:
        ids = list(pitcher_ids)
        if not ids:
            return pd.DataFrame(
                columns=['pitcher', 'pitches', 'tbf', 'bip'] + SP_MARKERS,
            )
        id_list = ", ".join(str(int(i)) for i in ids)
        where_clauses.append(f"pitcher IN ({id_list})")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    swstr_list = ", ".join(f"'{d}'" for d in sorted(SWSTR_DESC))

    sql = f"""
    WITH src AS (
      SELECT
        pitcher,
        CAST(game_date AS DATE) AS game_date,
        events,
        description,
        zone,
        TRY_CAST(release_speed AS DOUBLE)            AS release_speed,
        TRY_CAST(launch_speed AS DOUBLE)             AS launch_speed,
        TRY_CAST(launch_speed_angle AS DOUBLE)       AS lsa,
        TRY_CAST(estimated_woba_using_speedangle AS DOUBLE) AS xwoba_pa
      FROM {pq_relation}
      {where_sql}
    ),
    anno AS (
      SELECT
        pitcher,
        release_speed,
        events,
        description,
        zone,
        launch_speed,
        lsa,
        xwoba_pa,
        (description IN ({swstr_list}))                                       AS is_swstr,
        (description = 'called_strike')                                       AS is_called_strike,
        (description IN ('swinging_strike','swinging_strike_blocked','foul',
                         'foul_tip','hit_into_play','foul_bunt','missed_bunt')) AS is_swing,
        (zone BETWEEN 1 AND 9)                                                AS in_zone,
        (events IS NOT NULL AND events != '')                                 AS is_pa_end,
        (events = 'strikeout')                                                AS is_k,
        (events = 'walk')                                                     AS is_bb,
        (events = 'hit_by_pitch')                                             AS is_hbp,
        (events IS NOT NULL AND events != ''
            AND events NOT IN ('strikeout','walk','hit_by_pitch'))             AS is_bip
      FROM src
    ),
    flagged AS (
      SELECT
        pitcher,
        release_speed,
        is_swstr,
        is_called_strike,
        is_swing,
        in_zone,
        is_pa_end,
        is_k,
        is_bb,
        is_hbp,
        is_bip,
        launch_speed,
        lsa,
        xwoba_pa,
        (is_swing AND NOT in_zone) AS o_swing,
        (is_bip AND launch_speed >= 95.0) AS is_hard_hit,
        (is_bip AND lsa = 6) AS is_barrel,
        (is_bip AND xwoba_pa IS NOT NULL) AS bip_with_xwoba
      FROM anno
    )
    SELECT
      pitcher,
      COUNT(*)                                                AS pitches,
      SUM(CASE WHEN is_pa_end THEN 1 ELSE 0 END)              AS tbf,
      SUM(CASE WHEN is_bip THEN 1 ELSE 0 END)                 AS bip,
      AVG(release_speed)                                      AS avg_velo,
      SUM(CASE WHEN is_swstr THEN 1 ELSE 0 END) * 1.0
        / NULLIF(COUNT(*), 0)                                 AS swstr_pct,
      SUM(CASE WHEN is_called_strike OR is_swstr THEN 1 ELSE 0 END) * 1.0
        / NULLIF(COUNT(*), 0)                                 AS c_plus_swstr,
      SUM(CASE WHEN o_swing THEN 1 ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN NOT in_zone THEN 1 ELSE 0 END), 0)
                                                              AS o_swing_pct,
      SUM(CASE WHEN is_k THEN 1 ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN is_pa_end THEN 1 ELSE 0 END), 0) AS k_pct,
      SUM(CASE WHEN is_bb THEN 1 ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN is_pa_end THEN 1 ELSE 0 END), 0) AS bb_pct,
      SUM(CASE WHEN is_hard_hit THEN 1 ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN is_bip THEN 1 ELSE 0 END), 0)  AS hard_hit_pct,
      SUM(CASE WHEN is_barrel THEN 1 ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN is_bip THEN 1 ELSE 0 END), 0)  AS barrel_pct,
      SUM(CASE WHEN bip_with_xwoba THEN xwoba_pa ELSE 0.0 END) * 1.0
        / NULLIF(SUM(CASE WHEN bip_with_xwoba THEN 1 ELSE 0 END), 0)
                                                              AS xwoba_contact
    FROM flagged
    WHERE pitcher IS NOT NULL
    GROUP BY pitcher
    ORDER BY pitcher
    """

    con = duckdb.connect()
    try:
        con.execute("PRAGMA threads=4")
        df = con.execute(sql).df()
    finally:
        con.close()
    return df
