"""
Build rolling-last-N-PA-aware FPS% and putaway% caches.

For each (pitcher, year, cutoff_date) in rolling_pitchers, compute:
  fps_pct_last100pa     = FPS% over pitcher's most recent 100 first-pitch PAs <= cutoff_date
  putaway_pct_last50pa  = putaway% over most recent 50 two-strike PAs <= cutoff_date
  fps_pct_delta_l100    = fps_pct_last100pa - fps_pct_to_sd  (recent - season avg)
  putaway_pct_delta_l50 = putaway_pct_last50pa - putaway_pct_to_sd

PA-level granularity: rolling-sum across the pitcher's PA log, ordered by
(game_date, game_pk, at_bat_number).
"""
from __future__ import annotations
import os
import duckdb
import pandas as pd

from plv_clone.paths import ROOT as _ROOT
ROOT = str(_ROOT)
ROLLING_CSV    = f"{ROOT}/data/research/xfp_cache/rolling_pitchers_2018_2026.csv"
STATCAST_TMPL  = f"{ROOT}/data/research/xfp_cache/statcast_{{yr}}.parquet"
SD_CSV         = f"{ROOT}/data/research/xfp_cache/pl_signals_split_day_2018_2026.csv"
OUT_CSV        = f"{ROOT}/data/research/xfp_cache/pl_signals_lastpa_2018_2026.csv"

FPS_WINDOW     = 100   # PAs
PUTAWAY_WINDOW = 50    # two-strike PAs


def build_year_pa_log(yr: int, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Per-PA log with first-pitch and two-strike markers, ordered by game time."""
    pq = STATCAST_TMPL.format(yr=yr)
    if not os.path.exists(pq):
        return pd.DataFrame()
    return con.execute(f"""
        SELECT pitcher, game_date, game_pk, at_bat_number,
               MAX(CASE WHEN strikes = 2 THEN 1 ELSE 0 END)              AS reached_2k,
               MAX(CASE WHEN events  = 'strikeout' THEN 1 ELSE 0 END)    AS is_k,
               MAX(CASE WHEN pitch_number = 1 THEN 1 ELSE 0 END)         AS has_fp,
               MAX(CASE WHEN pitch_number = 1
                          AND description IN ('called_strike','swinging_strike',
                                              'foul','foul_tip','foul_bunt',
                                              'missed_bunt','hit_into_play')
                        THEN 1 ELSE 0 END)                                AS fp_strike
        FROM read_parquet('{pq}')
        WHERE pitcher IS NOT NULL
        GROUP BY pitcher, game_date, game_pk, at_bat_number
    """).df()


def rolling_lastn(pa_log: pd.DataFrame, n_fps: int, n_putaway: int) -> pd.DataFrame:
    """Add rolling-last-N-PA window FPS% and putaway% per PA.

    FPS window = last n_fps first-pitch PAs (rows where has_fp == 1).
    Putaway window = last n_putaway two-strike PAs (rows where reached_2k == 1).
    """
    pa_log = pa_log.sort_values(['pitcher', 'game_date', 'game_pk', 'at_bat_number']).reset_index(drop=True)

    # FPS rolling — only over rows where has_fp == 1
    fp_rows = pa_log[pa_log['has_fp'] == 1].copy()
    fp_rows['cum_fp_strike']   = fp_rows.groupby('pitcher')['fp_strike'].cumsum()
    fp_rows['cum_fp']          = fp_rows.groupby('pitcher').cumcount() + 1
    fp_rows['lag_fp_strike']   = fp_rows.groupby('pitcher')['cum_fp_strike'].shift(n_fps).fillna(0)
    fp_rows['lag_fp']          = fp_rows.groupby('pitcher')['cum_fp'].shift(n_fps).fillna(0)
    fp_rows['win_fp_strike']   = fp_rows['cum_fp_strike'] - fp_rows['lag_fp_strike']
    fp_rows['win_fp']          = fp_rows['cum_fp']        - fp_rows['lag_fp']
    fp_rows['fps_pct_lastN']   = fp_rows['win_fp_strike'] / fp_rows['win_fp']
    # Only report when window is full (>= n_fps)
    fp_rows.loc[fp_rows['win_fp'] < n_fps, 'fps_pct_lastN'] = pd.NA

    # Putaway rolling — only over rows where reached_2k == 1
    p_rows = pa_log[pa_log['reached_2k'] == 1].copy()
    p_rows['cum_k']            = p_rows.groupby('pitcher')['is_k'].cumsum()
    p_rows['cum_twok']         = p_rows.groupby('pitcher').cumcount() + 1
    p_rows['lag_k']            = p_rows.groupby('pitcher')['cum_k'].shift(n_putaway).fillna(0)
    p_rows['lag_twok']         = p_rows.groupby('pitcher')['cum_twok'].shift(n_putaway).fillna(0)
    p_rows['win_k']            = p_rows['cum_k']    - p_rows['lag_k']
    p_rows['win_twok']         = p_rows['cum_twok'] - p_rows['lag_twok']
    p_rows['putaway_pct_lastN'] = p_rows['win_k'] / p_rows['win_twok']
    p_rows.loc[p_rows['win_twok'] < n_putaway, 'putaway_pct_lastN'] = pd.NA

    # For each (pitcher, game_date), take the LAST PA row's rolling-window value
    # (so we get the latest snapshot per game-day).
    fps_by_day = (fp_rows.sort_values(['pitcher', 'game_date', 'game_pk', 'at_bat_number'])
                  .groupby(['pitcher', 'game_date'])['fps_pct_lastN'].last().reset_index()
                  .rename(columns={'fps_pct_lastN': 'fps_pct_lastN'}))
    put_by_day = (p_rows.sort_values(['pitcher', 'game_date', 'game_pk', 'at_bat_number'])
                  .groupby(['pitcher', 'game_date'])['putaway_pct_lastN'].last().reset_index()
                  .rename(columns={'putaway_pct_lastN': 'putaway_pct_lastN'}))

    daily = fps_by_day.merge(put_by_day, on=['pitcher', 'game_date'], how='outer')
    daily['game_date'] = pd.to_datetime(daily['game_date'])
    # Forward-fill within pitcher across days where the player didn't pitch
    # (the rolling value is "as of the last time we observed them").
    daily = daily.sort_values(['pitcher', 'game_date']).reset_index(drop=True)
    daily['fps_pct_lastN']     = daily.groupby('pitcher')['fps_pct_lastN'].ffill()
    daily['putaway_pct_lastN'] = daily.groupby('pitcher')['putaway_pct_lastN'].ffill()
    return daily


def lookup_at_cutoff(daily: pd.DataFrame, rolling: pd.DataFrame) -> pd.DataFrame:
    """ASOF-join the daily rolling values to each rolling_pitchers row."""
    rolling = rolling.copy()
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    con = duckdb.connect()
    con.register('daily', daily)
    con.register('rolling', rolling[['pitcher', 'year', 'split_day', 'cutoff_date']])
    res = con.execute("""
        SELECT r.pitcher, r.year, r.split_day, r.cutoff_date,
               d.fps_pct_lastN     AS fps_pct_last100pa,
               d.putaway_pct_lastN AS putaway_pct_last50pa
        FROM rolling r
        ASOF LEFT JOIN daily d
          ON r.pitcher  = d.pitcher
         AND r.cutoff_date >= d.game_date
    """).df()
    con.close()
    return res


def main():
    print(f"=== build_pl_signals_lastpa (FPS={FPS_WINDOW}PA, putaway={PUTAWAY_WINDOW}PA) ===")
    rolling = pd.read_csv(ROLLING_CSV)
    print(f"Rolling rows: {len(rolling)}")

    con = duckdb.connect()
    all_daily = []
    for yr in sorted(rolling['year'].unique()):
        yr = int(yr)
        print(f"  [{yr}] building PA log...")
        pa = build_year_pa_log(yr, con)
        if pa.empty:
            continue
        pa['year'] = yr
        print(f"    PAs: {len(pa)}")
        daily = rolling_lastn(pa, FPS_WINDOW, PUTAWAY_WINDOW)
        daily['year'] = yr
        all_daily.append(daily)
    con.close()

    if not all_daily:
        print("No data."); return
    daily = pd.concat(all_daily, ignore_index=True)
    print(f"\nTotal daily snapshot rows: {len(daily)}")

    out = lookup_at_cutoff(daily, rolling)
    print(f"Joined: {len(out)}")

    # Add deltas vs season-to-date
    sd = pd.read_csv(SD_CSV)
    out = out.merge(sd[['pitcher', 'year', 'split_day',
                        'fps_pct_to_sd', 'putaway_pct_to_sd']],
                    on=['pitcher', 'year', 'split_day'], how='left')
    out['fps_pct_delta_l100']    = out['fps_pct_last100pa']     - out['fps_pct_to_sd']
    out['putaway_pct_delta_l50'] = out['putaway_pct_last50pa']  - out['putaway_pct_to_sd']

    print(f"  fps_pct_last100pa non-null:     {out['fps_pct_last100pa'].notna().sum()} ({out['fps_pct_last100pa'].notna().mean()*100:.1f}%)")
    print(f"  putaway_pct_last50pa non-null:  {out['putaway_pct_last50pa'].notna().sum()} ({out['putaway_pct_last50pa'].notna().mean()*100:.1f}%)")
    print(f"  fps_pct_delta_l100 non-null:    {out['fps_pct_delta_l100'].notna().sum()}")
    print(f"  putaway_pct_delta_l50 non-null: {out['putaway_pct_delta_l50'].notna().sum()}")

    print("\nMean/std by split_day for fps_pct_last100pa:")
    print(out.groupby('split_day')['fps_pct_last100pa'].agg(['mean', 'std', 'count']))
    print("\nMean/std by split_day for fps_pct_delta_l100:")
    print(out.groupby('split_day')['fps_pct_delta_l100'].agg(['mean', 'std', 'count']))

    out.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV}")


if __name__ == '__main__':
    main()
