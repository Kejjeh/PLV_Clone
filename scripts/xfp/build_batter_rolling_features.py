"""build_batter_rolling_features.py — shared per-batter rolling-feature cache.

Produces ONE row per batter (career PA >= 300 across 2015-2026 statcast
parquets) with everything the sustainability / career-form / slump skills
need to avoid re-walking 12 years of statcast on every invocation.

Columns:
  batter, player_name, team_recent, total_career_pa,
  current_l150_xwoba,
  career_l150_median, career_l150_min, career_l150_max, career_l150_mean,
  career_percentile,
  -- latest-150-PA 9-marker decomposition --
  avg_ev, ev90, hard_hit_pct, barrel_pct, xwoba_on_contact,
  k_pct, bb_pct, chase_pct, sweet_spot_pct,
  -- last-21-calendar-day version of the same 9 markers --
  avg_ev_l21d, ev90_l21d, hard_hit_pct_l21d, barrel_pct_l21d,
  xwoba_on_contact_l21d, k_pct_l21d, bb_pct_l21d,
  chase_pct_l21d, sweet_spot_pct_l21d,
  n_pa_l21d, built_at

Writes:
  data/research/xfp_cache/batter_rolling_features.csv

Single DuckDB connection, single output CSV, no per-batter Python loops.

Usage:
  python -X utf8 scripts/xfp/build_batter_rolling_features.py
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_CSV = CACHE / 'batter_rolling_features.csv'

YEARS = list(range(2015, 2027))  # statcast_2015.parquet .. statcast_2026.parquet
MIN_CAREER_PA = 300

# PA-defining event set (mirrors build_rolling_hitters.py)
K_EVENTS = ('strikeout', 'strikeout_double_play', 'strikeout_triple_play')
BB_EVENTS = ('walk', 'intent_walk')
HBP_EVENT = 'hit_by_pitch'
NON_PA = (
    'stolen_base_2b', 'stolen_base_3b', 'stolen_base_home',
    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
    'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
    'wild_pitch', 'passed_ball', 'balk',
)


def _quote_list(xs):
    return ", ".join(f"'{x}'" for x in xs)


def _statcast_union_sql() -> str:
    paths = [CACHE / f'statcast_{y}.parquet' for y in YEARS]
    existing = [p for p in paths if p.exists()]
    if not existing:
        raise FileNotFoundError(f'No statcast parquets found under {CACHE}')
    files = ", ".join(f"'{p.as_posix()}'" for p in existing)
    # union_by_name handles schema drift across years (bat_speed etc only in newer)
    return f"read_parquet([{files}], union_by_name=True)"


def main():
    t0 = time.time()
    print(f'[build_batter_rolling_features] start  out={OUT_CSV}')

    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    sc = _statcast_union_sql()

    k_events = _quote_list(K_EVENTS)
    bb_events = _quote_list(BB_EVENTS)
    non_pa = _quote_list(NON_PA)

    # Build a per-pitch annotated relation (events resolved to PA / marker flags).
    # NOTE: zone 1..9 is in-strike-zone; barrel via launch_speed_angle == 6;
    # sweet_spot: launch_angle in [8, 32]; hard_hit: launch_speed >= 95.
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW pitches AS
        SELECT
          batter,
          CAST(game_date AS DATE) AS game_date,
          game_year,
          events,
          description,
          zone,
          TRY_CAST(launch_speed AS DOUBLE)         AS launch_speed,
          TRY_CAST(launch_angle AS DOUBLE)         AS launch_angle,
          TRY_CAST(launch_speed_angle AS DOUBLE)   AS lsa,
          TRY_CAST(estimated_woba_using_speedangle AS DOUBLE) AS xwoba_pa,
          -- PA flags
          (events IS NOT NULL AND events != '' AND events NOT IN ({non_pa})) AS is_pa,
          (events IN ({k_events}))  AS is_k,
          (events IN ({bb_events})) AS is_bb,
          (events = '{HBP_EVENT}')  AS is_hbp,
          -- Swing / contact taxonomy
          (description IN ('swinging_strike','swinging_strike_blocked','foul','foul_tip',
                           'hit_into_play','foul_bunt','missed_bunt')) AS is_swing,
          (description IN ('swinging_strike','swinging_strike_blocked','foul_tip','missed_bunt')) AS is_swstr,
          (zone BETWEEN 1 AND 9) AS in_zone
        FROM {sc}
        WHERE batter IS NOT NULL
    """)

    # Eligible batter universe — career PA >= MIN_CAREER_PA
    print('[build_batter_rolling_features] enumerating universe ...')
    universe = con.execute(f"""
        SELECT batter, SUM(CASE WHEN is_pa THEN 1 ELSE 0 END) AS total_career_pa
        FROM pitches
        GROUP BY batter
        HAVING total_career_pa >= {MIN_CAREER_PA}
    """).df()
    print(f'  universe size: {len(universe)} batters (career_pa >= {MIN_CAREER_PA})')

    con.register('universe_df', universe[['batter']])
    con.execute("CREATE OR REPLACE TEMP VIEW universe AS SELECT batter FROM universe_df")

    # --- Career rolling-150 (PA-events only, ordered by game_date) ---
    # We compute rolling per-PA xwoba on PA-events (where xwoba is defined OR
    # filled for BB/K/HBP -- we follow career-form-rank: include events where
    # estimated_woba_using_speedangle IS NOT NULL).
    print('[build_batter_rolling_features] computing rolling-150 career windows ...')
    rolling = con.execute("""
        WITH pa_events AS (
          SELECT p.batter, p.game_date, p.xwoba_pa
          FROM pitches p
          JOIN universe u USING (batter)
          WHERE p.events IS NOT NULL AND p.events != ''
            AND p.xwoba_pa IS NOT NULL
        ),
        ranked AS (
          SELECT batter, game_date, xwoba_pa,
                 ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date, xwoba_pa) AS rn,
                 COUNT(*)     OVER (PARTITION BY batter) AS total_pa_xwoba
          FROM pa_events
        ),
        rolling AS (
          SELECT batter, rn, total_pa_xwoba,
                 AVG(xwoba_pa) OVER (PARTITION BY batter ORDER BY rn
                                     ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS roll150
          FROM ranked
        ),
        agg AS (
          SELECT
            batter,
            ANY_VALUE(total_pa_xwoba) AS total_pa_xwoba,
            AVG(roll150)    FILTER (WHERE rn >= 150) AS career_l150_mean,
            MEDIAN(roll150) FILTER (WHERE rn >= 150) AS career_l150_median,
            MIN(roll150)    FILTER (WHERE rn >= 150) AS career_l150_min,
            MAX(roll150)    FILTER (WHERE rn >= 150) AS career_l150_max,
            MAX(CASE WHEN rn = total_pa_xwoba THEN roll150 END) AS current_l150_xwoba
          FROM rolling
          GROUP BY batter
        ),
        pct AS (
          SELECT r.batter,
                 SUM(CASE WHEN r.roll150 < a.current_l150_xwoba THEN 1 ELSE 0 END) * 1.0
                   / NULLIF(COUNT(*), 0) AS career_percentile
          FROM rolling r
          JOIN agg a USING (batter)
          WHERE r.rn >= 150
          GROUP BY r.batter
        )
        SELECT a.batter,
               a.total_pa_xwoba,
               a.current_l150_xwoba,
               a.career_l150_mean, a.career_l150_median,
               a.career_l150_min, a.career_l150_max,
               p.career_percentile
        FROM agg a
        LEFT JOIN pct p USING (batter)
    """).df()
    print(f'  rolling-150 rows: {len(rolling)}')

    # --- Latest-150-PA marker decomposition ---
    # We rank PA-events (events != '') by date desc, take 150 latest *PA events*
    # per batter, then aggregate pitch-level markers OVER ALL pitches whose
    # game_date >= the cutoff date that captures those 150 PA. We approximate
    # via a per-batter cutoff_date computed from the 150th-most-recent PA.
    print('[build_batter_rolling_features] computing latest-150-PA markers ...')
    con.execute("""
        CREATE OR REPLACE TEMP VIEW pa_only AS
        SELECT p.batter, p.game_date
        FROM pitches p
        JOIN universe u USING (batter)
        WHERE p.is_pa
    """)
    cutoffs150 = con.execute("""
        WITH ranked AS (
          SELECT batter, game_date,
                 ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date DESC) AS rrn
          FROM pa_only
        )
        SELECT batter, MIN(game_date) AS cutoff150
        FROM (
          SELECT batter, game_date FROM ranked WHERE rrn <= 150
        ) GROUP BY batter
    """).df()
    print(f'  150-PA cutoffs computed for {len(cutoffs150)} batters')

    con.register('cutoffs150_df', cutoffs150)

    markers_l150 = con.execute("""
        WITH scoped AS (
          SELECT p.*
          FROM pitches p
          JOIN cutoffs150_df c USING (batter)
          WHERE p.game_date >= c.cutoff150
        )
        SELECT
          batter,
          AVG(launch_speed) FILTER (WHERE launch_speed IS NOT NULL
              AND events IS NOT NULL AND events != ''
              AND NOT is_k AND NOT is_bb AND NOT is_hbp) AS avg_ev,
          QUANTILE_CONT(launch_speed, 0.9) FILTER (WHERE launch_speed IS NOT NULL
              AND events IS NOT NULL AND events != ''
              AND NOT is_k AND NOT is_bb AND NOT is_hbp) AS ev90,
          SUM(CASE WHEN launch_speed >= 95
                    AND events IS NOT NULL AND events != ''
                    AND NOT is_k AND NOT is_bb AND NOT is_hbp THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN events IS NOT NULL AND events != ''
                                 AND NOT is_k AND NOT is_bb AND NOT is_hbp
                                 AND launch_speed IS NOT NULL
                                THEN 1 ELSE 0 END), 0) AS hard_hit_pct,
          SUM(CASE WHEN lsa = 6
                    AND events IS NOT NULL AND events != ''
                    AND NOT is_k AND NOT is_bb AND NOT is_hbp THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN events IS NOT NULL AND events != ''
                                 AND NOT is_k AND NOT is_bb AND NOT is_hbp
                                 AND launch_speed IS NOT NULL
                                THEN 1 ELSE 0 END), 0) AS barrel_pct,
          AVG(xwoba_pa) FILTER (WHERE xwoba_pa IS NOT NULL
              AND events IS NOT NULL AND events != ''
              AND NOT is_k AND NOT is_bb AND NOT is_hbp) AS xwoba_on_contact,
          SUM(CASE WHEN is_k  THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN is_pa THEN 1 ELSE 0 END), 0) AS k_pct,
          SUM(CASE WHEN is_bb THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN is_pa THEN 1 ELSE 0 END), 0) AS bb_pct,
          SUM(CASE WHEN is_swing AND NOT in_zone THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN NOT in_zone THEN 1 ELSE 0 END), 0) AS chase_pct,
          SUM(CASE WHEN launch_angle BETWEEN 8 AND 32
                    AND events IS NOT NULL AND events != ''
                    AND NOT is_k AND NOT is_bb AND NOT is_hbp THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN events IS NOT NULL AND events != ''
                                 AND NOT is_k AND NOT is_bb AND NOT is_hbp
                                 AND launch_angle IS NOT NULL
                                THEN 1 ELSE 0 END), 0) AS sweet_spot_pct
        FROM scoped
        GROUP BY batter
    """).df()
    print(f'  L150 marker rows: {len(markers_l150)}')

    # --- Last 21 calendar days markers ---
    # Cutoff = max(game_date) overall - 21 days. We use the global max so all
    # batters share an "asof" anchor (mirrors how live dashboards anchor today).
    asof = con.execute("SELECT MAX(game_date) FROM pitches").fetchone()[0]
    cutoff21 = pd.Timestamp(asof) - pd.Timedelta(days=21)
    print(f'  asof game_date: {asof}  l21d cutoff: {cutoff21.date()}')

    markers_l21d = con.execute(f"""
        WITH scoped AS (
          SELECT p.*
          FROM pitches p
          JOIN universe u USING (batter)
          WHERE p.game_date >= DATE '{cutoff21.date()}'
        )
        SELECT
          batter,
          SUM(CASE WHEN is_pa THEN 1 ELSE 0 END) AS n_pa_l21d,
          AVG(launch_speed) FILTER (WHERE launch_speed IS NOT NULL
              AND events IS NOT NULL AND events != ''
              AND NOT is_k AND NOT is_bb AND NOT is_hbp) AS avg_ev_l21d,
          QUANTILE_CONT(launch_speed, 0.9) FILTER (WHERE launch_speed IS NOT NULL
              AND events IS NOT NULL AND events != ''
              AND NOT is_k AND NOT is_bb AND NOT is_hbp) AS ev90_l21d,
          SUM(CASE WHEN launch_speed >= 95
                    AND events IS NOT NULL AND events != ''
                    AND NOT is_k AND NOT is_bb AND NOT is_hbp THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN events IS NOT NULL AND events != ''
                                 AND NOT is_k AND NOT is_bb AND NOT is_hbp
                                 AND launch_speed IS NOT NULL
                                THEN 1 ELSE 0 END), 0) AS hard_hit_pct_l21d,
          SUM(CASE WHEN lsa = 6
                    AND events IS NOT NULL AND events != ''
                    AND NOT is_k AND NOT is_bb AND NOT is_hbp THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN events IS NOT NULL AND events != ''
                                 AND NOT is_k AND NOT is_bb AND NOT is_hbp
                                 AND launch_speed IS NOT NULL
                                THEN 1 ELSE 0 END), 0) AS barrel_pct_l21d,
          AVG(xwoba_pa) FILTER (WHERE xwoba_pa IS NOT NULL
              AND events IS NOT NULL AND events != ''
              AND NOT is_k AND NOT is_bb AND NOT is_hbp) AS xwoba_on_contact_l21d,
          SUM(CASE WHEN is_k  THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN is_pa THEN 1 ELSE 0 END), 0) AS k_pct_l21d,
          SUM(CASE WHEN is_bb THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN is_pa THEN 1 ELSE 0 END), 0) AS bb_pct_l21d,
          SUM(CASE WHEN is_swing AND NOT in_zone THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN NOT in_zone THEN 1 ELSE 0 END), 0) AS chase_pct_l21d,
          SUM(CASE WHEN launch_angle BETWEEN 8 AND 32
                    AND events IS NOT NULL AND events != ''
                    AND NOT is_k AND NOT is_bb AND NOT is_hbp THEN 1 ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN events IS NOT NULL AND events != ''
                                 AND NOT is_k AND NOT is_bb AND NOT is_hbp
                                 AND launch_angle IS NOT NULL
                                THEN 1 ELSE 0 END), 0) AS sweet_spot_pct_l21d
        FROM scoped
        GROUP BY batter
    """).df()
    print(f'  L21d marker rows: {len(markers_l21d)}')

    # --- Display name + team_recent from hitters_multiyr (most-recent year per batter) ---
    multiyr_path = CACHE / 'hitters_multiyr_2015_2026.csv'
    if multiyr_path.exists():
        my = pd.read_csv(multiyr_path, usecols=['batter', 'player_name', 'team', 'year'])
        my = my.sort_values(['batter', 'year']).groupby('batter', as_index=False).tail(1)
        my = my.rename(columns={'team': 'team_recent'})[['batter', 'player_name', 'team_recent']]
    else:
        print('  WARN: hitters_multiyr csv missing; player_name/team_recent will be blank')
        my = pd.DataFrame(columns=['batter', 'player_name', 'team_recent'])

    # --- Stitch together ---
    out = universe.merge(rolling, on='batter', how='left')
    out = out.merge(markers_l150, on='batter', how='left')
    out = out.merge(markers_l21d, on='batter', how='left')
    out = out.merge(my, on='batter', how='left')
    out['built_at'] = datetime.now(timezone.utc).isoformat()

    # Column order
    cols = [
        'batter', 'player_name', 'team_recent', 'total_career_pa',
        'current_l150_xwoba',
        'career_l150_median', 'career_l150_min', 'career_l150_max', 'career_l150_mean',
        'career_percentile',
        'avg_ev', 'ev90', 'hard_hit_pct', 'barrel_pct', 'xwoba_on_contact',
        'k_pct', 'bb_pct', 'chase_pct', 'sweet_spot_pct',
        'avg_ev_l21d', 'ev90_l21d', 'hard_hit_pct_l21d', 'barrel_pct_l21d',
        'xwoba_on_contact_l21d', 'k_pct_l21d', 'bb_pct_l21d',
        'chase_pct_l21d', 'sweet_spot_pct_l21d',
        'n_pa_l21d', 'built_at',
    ]
    for c in cols:
        if c not in out.columns:
            out[c] = pd.NA
    out = out[cols].sort_values('total_career_pa', ascending=False)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    size_kb = OUT_CSV.stat().st_size / 1024
    elapsed = time.time() - t0
    print(f'[build_batter_rolling_features] wrote {len(out)} rows  '
          f'{size_kb:,.0f} KB  in {elapsed:.1f}s  → {OUT_CSV}')


if __name__ == '__main__':
    main()
