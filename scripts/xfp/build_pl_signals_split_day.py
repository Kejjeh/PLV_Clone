"""
Build TRUE split-day-aware FPS% and putaway% caches.

For each (pitcher, year, cutoff_date) in rolling_pitchers, compute:
  fps_pct_to_sd     = first-pitch strikes / first pitches, on game_date <= cutoff_date
  putaway_pct_to_sd = K events / 2-strike PAs, on game_date <= cutoff_date

Approach: for each year, build per-(pitcher, game_date) cumulative running counts.
Then merge to rolling_pitchers on (pitcher, year), filter cum game_date <= cutoff_date,
take the latest row per (pitcher, cutoff_date).
"""
from __future__ import annotations
import os
import duckdb
import pandas as pd

from plv_clone.paths import ROOT as _ROOT
ROOT = str(_ROOT)
ROLLING_CSV   = f"{ROOT}/data/research/xfp_cache/rolling_pitchers_2018_2026.csv"
STATCAST_TMPL = f"{ROOT}/data/research/xfp_cache/statcast_{{yr}}.parquet"
OUT_CSV       = f"{ROOT}/data/research/xfp_cache/pl_signals_split_day_2018_2026.csv"


def build_year(yr: int) -> pd.DataFrame:
    pq = STATCAST_TMPL.format(yr=yr)
    if not os.path.exists(pq):
        print(f"  [{yr}] no parquet — skipped")
        return pd.DataFrame()

    con = duckdb.connect()

    # 1) Per-(pitcher, game_date) running cumulative counts.
    # First-pitches: pitch_number == 1.
    # First-pitch strike: pitch_number == 1 AND description in {called_strike, swinging_strike,
    #   foul, foul_tip, foul_bunt, hit_into_play}.
    # 2-strike PA: any pitch in PA had strikes == 2 (at-start-of-pitch count).
    # Putaway K: PA ended in 'strikeout' (and by definition reached 2 strikes).
    print(f"  [{yr}] aggregating per-(pitcher, game_date)...")
    daily = con.execute(f"""
        WITH pa_level AS (
            SELECT pitcher, game_pk, game_date, at_bat_number,
                   MAX(CASE WHEN strikes = 2 THEN 1 ELSE 0 END)            AS reached_2k,
                   MAX(CASE WHEN events  = 'strikeout' THEN 1 ELSE 0 END)  AS is_k,
                   MAX(CASE WHEN pitch_number = 1 THEN 1 ELSE 0 END)       AS has_fp,
                   MAX(CASE WHEN pitch_number = 1
                              AND description IN ('called_strike','swinging_strike',
                                                  'foul','foul_tip','foul_bunt',
                                                  'missed_bunt','hit_into_play')
                            THEN 1 ELSE 0 END)                              AS fp_strike
            FROM read_parquet('{pq}')
            WHERE pitcher IS NOT NULL
            GROUP BY pitcher, game_pk, game_date, at_bat_number
        )
        SELECT pitcher, game_date,
               SUM(has_fp)     AS fp_n,
               SUM(fp_strike)  AS fp_strike_n,
               SUM(reached_2k) AS twok_n,
               SUM(is_k)       AS k_n
        FROM pa_level
        GROUP BY pitcher, game_date
        ORDER BY pitcher, game_date
    """).df()
    con.close()

    if daily.empty:
        return pd.DataFrame()

    # 2) Running cumulative sums per (pitcher, game_date).
    daily['game_date'] = pd.to_datetime(daily['game_date'])
    daily = daily.sort_values(['pitcher', 'game_date'])
    grp = daily.groupby('pitcher', sort=False)
    daily['cum_fp_n']        = grp['fp_n'].cumsum()
    daily['cum_fp_strike_n'] = grp['fp_strike_n'].cumsum()
    daily['cum_twok_n']      = grp['twok_n'].cumsum()
    daily['cum_k_n']         = grp['k_n'].cumsum()
    daily['year'] = yr
    return daily[['pitcher', 'year', 'game_date',
                  'cum_fp_n', 'cum_fp_strike_n', 'cum_twok_n', 'cum_k_n']]


def lookup_at_cutoff(daily: pd.DataFrame, rolling: pd.DataFrame) -> pd.DataFrame:
    """For each rolling row (pitcher, year, cutoff_date), find latest daily row
    where game_date <= cutoff_date. Compute fps_pct and putaway_pct at that point.
    """
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    # DuckDB ASOF join for efficient as-of-date lookup.
    con = duckdb.connect()
    con.register('daily', daily)
    con.register('rolling', rolling[['pitcher', 'year', 'split_day', 'cutoff_date']])
    res = con.execute("""
        SELECT r.pitcher, r.year, r.split_day, r.cutoff_date,
               d.cum_fp_n        AS fp_n_to,
               d.cum_fp_strike_n AS fp_strike_n_to,
               d.cum_twok_n      AS twok_n_to,
               d.cum_k_n         AS k_n_to
        FROM rolling r
        ASOF LEFT JOIN daily d
          ON r.pitcher  = d.pitcher
         AND r.year     = d.year
         AND r.cutoff_date >= d.game_date
    """).df()
    con.close()

    res['fps_pct_to_sd']     = res['fp_strike_n_to'] / res['fp_n_to']
    res['putaway_pct_to_sd'] = res['k_n_to'] / res['twok_n_to']
    # Stabilization gates: require minimum sample sizes
    res.loc[res['fp_n_to']   < 50,  'fps_pct_to_sd']     = pd.NA  # ~6 GS worth of first pitches
    res.loc[res['twok_n_to'] < 30,  'putaway_pct_to_sd'] = pd.NA  # ~5 GS worth of 2-strike PAs
    return res[['pitcher', 'year', 'split_day',
                'fps_pct_to_sd', 'putaway_pct_to_sd',
                'fp_n_to', 'twok_n_to']]


def main():
    print("=== build_pl_signals_split_day ===")
    rolling = pd.read_csv(ROLLING_CSV)
    print(f"Rolling rows: {len(rolling)}")

    frames = []
    for yr in sorted(rolling['year'].unique()):
        df_yr = build_year(int(yr))
        if not df_yr.empty:
            frames.append(df_yr)
    if not frames:
        print("No data built.")
        return

    daily = pd.concat(frames, ignore_index=True)
    print(f"\nTotal daily rows: {len(daily)}")

    print("Joining as-of cutoff_date...")
    out = lookup_at_cutoff(daily, rolling)
    print(f"Joined rows: {len(out)}")
    print(f"  fps_pct_to_sd non-null:     {out['fps_pct_to_sd'].notna().sum()} ({out['fps_pct_to_sd'].notna().mean()*100:.1f}%)")
    print(f"  putaway_pct_to_sd non-null: {out['putaway_pct_to_sd'].notna().sum()} ({out['putaway_pct_to_sd'].notna().mean()*100:.1f}%)")

    # Sanity check: at higher split_day, FPS_pct should stabilize (small drift from earlier)
    print("\nFPS_pct distribution by split_day (mean, std):")
    print(out.groupby('split_day')['fps_pct_to_sd'].agg(['mean', 'std', 'count']))
    print("\nPutaway_pct distribution by split_day:")
    print(out.groupby('split_day')['putaway_pct_to_sd'].agg(['mean', 'std', 'count']))

    out.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV}")


if __name__ == '__main__':
    main()
