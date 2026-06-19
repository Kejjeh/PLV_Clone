"""park_player_splits.py — per-batter career splits by ballpark.

For each batter, compute career fp/PA at each ballpark (identified via
home_team). Identify each player's "career hot parks" (lift > +15%) and
"career cold parks" (lift < -15%) where they have ≥40 PA of sample.

Usage in projections / decisions:
  - When evaluating a player, check their next 7-14 days of scheduled
    games against their park splits. A player with 12 games scheduled at
    his career hot parks vs cold parks is a different RoS bet.
  - Sneaky-trade compounding: a guy whose YTD is inflated because he
    played his early games at hot parks; his upcoming schedule is at
    cold parks. Sell-high.

Output:
  data/outputs/park_player_splits.csv  (long format: batter × park rows)
  data/outputs/park_player_summary.csv  (per-batter top hot/cold parks)
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from plv_clone.projections import PROJECTIONS
import numpy as np

from plv_clone.paths import ROOT
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


def hitter_park_splits(years=range(2018, 2026)) -> pd.DataFrame:
    """Per-batter career fp/PA at each home park (proxy = home_team)."""
    frames = []
    for year in years:
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['batter', 'home_team', 'events'])
        df = df[df['events'].isin(PA_EVENTS)].copy()
        if df.empty:
            continue
        df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
        df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
        df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['core_fp'] = df['tb'] + df['bb'] + df['hbp'] - df['k']
        df['pa'] = 1
        df['year'] = year
        agg = df.groupby(['batter', 'home_team'], as_index=False).agg(
            pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
        frames.append(agg)
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    # Sum across years
    full = full.groupby(['batter', 'home_team'], as_index=False).agg(
        pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
    full = full[full['pa'] >= 40]  # min 40 career PA at park
    full['rate'] = full['core_fp'] / full['pa']

    # Per-batter annual rate (across all parks)
    overall = full.groupby('batter', as_index=False).agg(
        total_pa=('pa', 'sum'), total_fp=('core_fp', 'sum'))
    overall['annual_rate'] = overall['total_fp'] / overall['total_pa']
    overall = overall[overall['total_pa'] >= 800]

    full = full.merge(overall[['batter', 'annual_rate', 'total_pa']], on='batter', how='inner')
    full['lift_pct'] = (full['rate'] - full['annual_rate']) / full['annual_rate'].replace(0, np.nan) * 100
    full['lift_pct'] = full['lift_pct'].round(1)
    return full


def park_summary(splits: pd.DataFrame) -> pd.DataFrame:
    """Per-batter: hottest 3 parks and coldest 3 parks."""
    rows = []
    for batter, sub in splits.groupby('batter'):
        sub = sub.sort_values('lift_pct', ascending=False)
        hot = sub.head(3)
        cold = sub.sort_values('lift_pct').head(3)
        record = {
            'batter': int(batter),
            'total_pa': int(sub['total_pa'].iloc[0]),
            'annual_rate': round(sub['annual_rate'].iloc[0], 4),
            'n_parks': len(sub),
            'hot1_park': hot['home_team'].iloc[0] if len(hot) > 0 else None,
            'hot1_lift': hot['lift_pct'].iloc[0] if len(hot) > 0 else None,
            'hot1_pa': int(hot['pa'].iloc[0]) if len(hot) > 0 else None,
            'hot2_park': hot['home_team'].iloc[1] if len(hot) > 1 else None,
            'hot2_lift': hot['lift_pct'].iloc[1] if len(hot) > 1 else None,
            'hot3_park': hot['home_team'].iloc[2] if len(hot) > 2 else None,
            'hot3_lift': hot['lift_pct'].iloc[2] if len(hot) > 2 else None,
            'cold1_park': cold['home_team'].iloc[0] if len(cold) > 0 else None,
            'cold1_lift': cold['lift_pct'].iloc[0] if len(cold) > 0 else None,
            'cold1_pa': int(cold['pa'].iloc[0]) if len(cold) > 0 else None,
            'cold2_park': cold['home_team'].iloc[1] if len(cold) > 1 else None,
            'cold2_lift': cold['lift_pct'].iloc[1] if len(cold) > 1 else None,
            'cold3_park': cold['home_team'].iloc[2] if len(cold) > 2 else None,
            'cold3_lift': cold['lift_pct'].iloc[2] if len(cold) > 2 else None,
        }
        rows.append(record)
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print('[park-player] computing hitter career splits 2018-2025...')
    splits = hitter_park_splits()
    if splits.empty:
        print('  no data')
        return
    rh = PROJECTIONS.rh3()
    splits = splits.merge(rh[['batter', 'player_name', 'team', 'rank']], on='batter', how='left')
    out_long = OUT / 'park_player_splits.csv'
    splits.to_csv(out_long, index=False)
    print(f'  wrote {out_long} ({len(splits)} batter-park rows, '
          f'{splits["batter"].nunique()} hitters)')

    summary = park_summary(splits)
    summary = summary.merge(rh[['batter', 'player_name', 'team', 'rank']], on='batter', how='left')
    out_sum = OUT / 'park_player_summary.csv'
    summary.to_csv(out_sum, index=False)
    print(f'  wrote {out_sum} ({len(summary)} hitter rows)')


if __name__ == '__main__':
    main()
