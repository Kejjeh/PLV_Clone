"""temp_player_profile.py — per-batter career splits by game temperature bucket.

Joins per-PA statcast events with game weather. Buckets temp:
  Dome:  closed-roof venues (treated as one bucket for consistency)
  Cold:  <60°F outdoor
  Cool:  60-69°F
  Warm:  70-79°F
  Hot:   80°F+

Computes per-batter fp/PA per temperature bucket. Identifies cold-weather
sufferers (Cold lift < -15%) vs cold-weather neutral. Useful for:
  - April/May residual analysis (early-season cold underweights)
  - Sneaky-trade compounding: a power hitter (FB%) whose YTD looks weak
    is actually consistent with their career cold-game line — buy-low now
  - Dome-team players whose home park is climate-controlled

Output:
  data/outputs/temp_player_profile.csv  (per-batter career temp splits)
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk',
    'hit_by_pitch', 'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


def temp_bucket(row) -> str:
    if row['dome']:
        return 'Dome'
    t = row['temp_f']
    if pd.isna(t):
        return 'Unknown'
    if t < 60: return 'Cold'
    if t < 70: return 'Cool'
    if t < 80: return 'Warm'
    return 'Hot'


def hitter_temp_splits(years=range(2018, 2026)) -> pd.DataFrame:
    weather = pd.read_csv(CACHE / 'game_weather.csv')
    weather['bucket'] = weather.apply(temp_bucket, axis=1)
    weather_lookup = dict(zip(weather['game_pk'], weather['bucket']))

    frames = []
    for year in years:
        if year == 2020: continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists(): continue
        df = pd.read_parquet(path, columns=['game_pk', 'batter', 'events'])
        df = df[df['events'].isin(PA_EVENTS)].copy()
        if df.empty: continue
        df['bucket'] = df['game_pk'].map(weather_lookup)
        df = df[df['bucket'].notna() & (df['bucket'] != 'Unknown')]
        if df.empty: continue
        df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
        df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
        df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['core_fp'] = df['tb'] + df['bb'] + df['hbp'] - df['k']
        df['pa'] = 1
        agg = df.groupby(['batter', 'bucket'], as_index=False).agg(
            pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
        frames.append(agg)
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full = full.groupby(['batter', 'bucket'], as_index=False).agg(
        pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
    full['rate'] = full['core_fp'] / full['pa']

    overall = full.groupby('batter', as_index=False).agg(
        total_pa=('pa', 'sum'), total_fp=('core_fp', 'sum'))
    overall['annual_rate'] = overall['total_fp'] / overall['total_pa']
    overall = overall[overall['total_pa'] >= 800]

    full = full.merge(overall[['batter', 'annual_rate', 'total_pa']],
                       on='batter', how='inner')
    full['lift_pct'] = (full['rate'] - full['annual_rate']) / full['annual_rate'].replace(0, np.nan) * 100
    full['lift_pct'] = full['lift_pct'].round(1)

    # Pivot wide
    pivot = full.pivot_table(index='batter',
                              columns='bucket',
                              values=['pa', 'rate', 'lift_pct'])
    pivot.columns = [f'{b}_{c}' for c, b in pivot.columns]
    pivot = pivot.reset_index()
    pivot = pivot.merge(overall[['batter', 'annual_rate', 'total_pa']],
                         on='batter', how='left')

    return pivot


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print('[temp-player] building hitter career temp splits...')
    out = hitter_temp_splits()
    if out.empty:
        print('  no data')
        return
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    out = out.merge(rh[['batter', 'player_name', 'team', 'rank']],
                     on='batter', how='left')
    target = OUT / 'temp_player_profile.csv'
    out.to_csv(target, index=False)
    print(f'  wrote {target} ({len(out)} hitters)')


if __name__ == '__main__':
    main()
