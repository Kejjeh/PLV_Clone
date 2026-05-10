"""week_level_substrate.py — build batter × eval_date dataset for leading-indicator test.

For each year 2018-2025 (excl 2020), at each weekly evaluation date (Mondays
May–Sep), compute per qualifying batter:

  Last-21-day features (LEADING INDICATORS):
    L21_pa, L21_k_pct, L21_bb_pct, L21_swstr_pct, L21_contact_pct,
    L21_chase_pct, L21_xwoba_per_pa, L21_woba_per_pa, L21_xwoba_residual,
    L21_iso, L21_hard_hit_pct, L21_barrel_pct, L21_hr_per_pa

  Career-to-date features (TALENT BASELINE — same window as eval_date):
    CTD_pa, CTD_xwoba_per_pa, CTD_woba_per_pa, CTD_swstr_pct, CTD_k_pct,
    CTD_bb_pct, CTD_xwoba_residual, CTD_fp_per_pa

  Recent-vs-career deltas (RESIDUAL LEADING INDICATORS):
    DELTA_swstr  = L21_swstr_pct - CTD_swstr_pct
    DELTA_xwoba  = L21_xwoba_per_pa - CTD_xwoba_per_pa
    DELTA_contact = L21_contact_pct - CTD_contact_pct

  Target:
    NEXT7_fp_per_pa  (core_fp = TB+BB+HBP-K, divided by NEXT7_pa)
    NEXT7_pa         (sample-size signal)

Output: data/research/week_level_substrate.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RES = ROOT / 'data' / 'research'

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}
SWINGS = {'foul', 'foul_tip', 'hit_into_play', 'swinging_strike',
          'swinging_strike_blocked', 'missed_bunt'}
WHIFFS = {'swinging_strike', 'swinging_strike_blocked'}

L21_MIN_PA = 30
NEXT7_MIN_PA = 5
CTD_MIN_PA = 50  # cumulative season-to-date min


def make_eval_dates(year: int) -> list[pd.Timestamp]:
    """Mondays May 1 through Sep 30 — covers most of the season."""
    start = pd.Timestamp(year=year, month=5, day=1)
    end = pd.Timestamp(year=year, month=9, day=30)
    dates = pd.date_range(start, end, freq='W-MON')
    return list(dates)


def load_year_pa(year: int) -> pd.DataFrame:
    """Load year's statcast events at PA level + per-PA derived stats."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=[
        'game_date', 'batter', 'events', 'description', 'pitch_type',
        'estimated_woba_using_speedangle', 'woba_value', 'woba_denom',
        'launch_speed', 'launch_angle'])
    df = df[df['batter'].notna()].copy()
    df['game_date'] = pd.to_datetime(df['game_date'])

    # Pitch-level flags (for swstr%, contact%)
    df['is_swing'] = df['description'].isin(SWINGS).astype(int)
    df['is_whiff'] = df['description'].isin(WHIFFS).astype(int)
    df['is_pitch'] = 1
    df['is_pa_terminal'] = df['events'].isin(PA_EVENTS).astype(int)
    df['is_K'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    df['is_BB'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
    df['is_HBP'] = (df['events'] == 'hit_by_pitch').astype(int)
    df['is_H'] = df['events'].isin({'single', 'double', 'triple', 'home_run'}).astype(int)
    df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
    df['hr'] = (df['events'] == 'home_run').astype(int)
    df['core_fp'] = df['tb'] + df['is_BB'] + df['is_HBP'] - df['is_K']
    ls = df['launch_speed'].fillna(0)
    la = df['launch_angle'].fillna(0)
    df['hard_hit'] = ((ls >= 95) & (df['is_pa_terminal'] == 1)).astype(int)
    df['barrel'] = ((ls >= 98) & la.between(26, 30) & (df['is_pa_terminal'] == 1)).astype(int)
    df['xwoba_value'] = df['estimated_woba_using_speedangle']

    return df


def aggregate_window(df: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    """Aggregate per-batter stats over [start_date, end_date] inclusive."""
    sub = df[(df['game_date'] >= start_date) & (df['game_date'] <= end_date)]
    if sub.empty:
        return pd.DataFrame()
    agg = sub.groupby('batter', as_index=False).agg(
        pa=('is_pa_terminal', 'sum'),
        pitches=('is_pitch', 'sum'),
        swings=('is_swing', 'sum'),
        whiffs=('is_whiff', 'sum'),
        k=('is_K', 'sum'),
        bb=('is_BB', 'sum'),
        hbp=('is_HBP', 'sum'),
        h=('is_H', 'sum'),
        hr=('hr', 'sum'),
        tb=('tb', 'sum'),
        core_fp=('core_fp', 'sum'),
        hard_hit_n=('hard_hit', 'sum'),
        barrel_n=('barrel', 'sum'),
        woba_v_sum=('woba_value', 'sum'),
        woba_d_sum=('woba_denom', 'sum'),
        xwoba_v_sum=('xwoba_value', 'sum'),
        xwoba_n=('xwoba_value', lambda x: x.notna().sum()),
        bbe=('launch_speed', lambda x: x.notna().sum()),
    )
    agg['k_pct'] = agg['k'] / agg['pa'].replace(0, np.nan)
    agg['bb_pct'] = agg['bb'] / agg['pa'].replace(0, np.nan)
    agg['swstr_pct'] = agg['whiffs'] / agg['pitches'].replace(0, np.nan)
    agg['contact_pct'] = (agg['swings'] - agg['whiffs']) / agg['swings'].replace(0, np.nan)
    agg['hard_hit_pct'] = agg['hard_hit_n'] / agg['bbe'].replace(0, np.nan)
    agg['barrel_pct'] = agg['barrel_n'] / agg['bbe'].replace(0, np.nan)
    agg['hr_per_pa'] = agg['hr'] / agg['pa'].replace(0, np.nan)
    agg['iso'] = (agg['tb'] - agg['h']) / (agg['pa'] - agg['bb'] - agg['hbp']).replace(0, np.nan)
    agg['woba_per_pa'] = agg['woba_v_sum'] / agg['pa'].replace(0, np.nan)
    agg['xwoba_per_pa'] = agg['xwoba_v_sum'] / agg['xwoba_n'].replace(0, np.nan)
    agg['xwoba_residual'] = agg['xwoba_per_pa'] - agg['woba_per_pa']
    agg['core_fp_per_pa'] = agg['core_fp'] / agg['pa'].replace(0, np.nan)
    return agg


def main():
    RES.mkdir(parents=True, exist_ok=True)
    rows = []
    for year in [2018, 2019, 2021, 2022, 2023, 2024, 2025]:
        print(f'\n[{year}] loading PA events...')
        df = load_year_pa(year)
        if df.empty:
            continue
        eval_dates = make_eval_dates(year)
        print(f'   {len(df)} pitches, {len(eval_dates)} eval Mondays')

        for ed in eval_dates:
            l21_start = ed - pd.Timedelta(days=21)
            l21_end = ed - pd.Timedelta(days=1)
            next7_end = ed + pd.Timedelta(days=6)

            l21 = aggregate_window(df, l21_start, l21_end)
            next7 = aggregate_window(df, ed, next7_end)
            ctd = aggregate_window(df, pd.Timestamp(year=year, month=3, day=1), l21_end)

            if l21.empty or next7.empty or ctd.empty:
                continue

            # Filter
            l21 = l21[l21['pa'] >= L21_MIN_PA]
            next7 = next7[next7['pa'] >= NEXT7_MIN_PA]
            ctd = ctd[ctd['pa'] >= CTD_MIN_PA]
            shared = set(l21['batter']) & set(next7['batter']) & set(ctd['batter'])
            if not shared:
                continue

            l21 = l21[l21['batter'].isin(shared)]
            next7 = next7[next7['batter'].isin(shared)]
            ctd = ctd[ctd['batter'].isin(shared)]

            l21 = l21.add_prefix('L21_').rename(columns={'L21_batter': 'batter'})
            next7 = next7[['batter', 'pa', 'core_fp', 'core_fp_per_pa']].add_prefix('NEXT7_').rename(
                columns={'NEXT7_batter': 'batter'})
            ctd = ctd.add_prefix('CTD_').rename(columns={'CTD_batter': 'batter'})

            merged = l21.merge(next7, on='batter').merge(ctd, on='batter')
            merged['eval_date'] = ed
            merged['year'] = year

            # Deltas (recent vs cumulative)
            merged['DELTA_swstr_pct'] = merged['L21_swstr_pct'] - merged['CTD_swstr_pct']
            merged['DELTA_contact_pct'] = merged['L21_contact_pct'] - merged['CTD_contact_pct']
            merged['DELTA_xwoba_per_pa'] = merged['L21_xwoba_per_pa'] - merged['CTD_xwoba_per_pa']
            merged['DELTA_k_pct'] = merged['L21_k_pct'] - merged['CTD_k_pct']
            merged['DELTA_bb_pct'] = merged['L21_bb_pct'] - merged['CTD_bb_pct']
            merged['DELTA_hard_hit_pct'] = merged['L21_hard_hit_pct'] - merged['CTD_hard_hit_pct']
            merged['DELTA_barrel_pct'] = merged['L21_barrel_pct'] - merged['CTD_barrel_pct']

            rows.append(merged)

    if not rows:
        print('  no data'); return
    full = pd.concat(rows, ignore_index=True)
    print(f'\nTotal eval rows: {len(full)}')
    print(f'  unique batters: {full["batter"].nunique()}')
    print(f'  per-year counts: {full.groupby("year").size().to_dict()}')

    fname = RES / 'week_level_substrate.csv'
    full.to_csv(fname, index=False)
    print(f'\n  wrote {fname}')


if __name__ == '__main__':
    main()
