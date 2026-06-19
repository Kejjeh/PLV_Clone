"""hitter_handedness.py — per-batter career splits vs LHP / RHP.

For each batter, compute career fp/PA vs LHP and vs RHP separately.
Identifies extreme platoon hitters whose value depends heavily on opponent
SP handedness. Useful for matchup-of-the-day decisions and for sneaky-trade
context (a batter who feasts on RHP is more valuable in a week with 5 RHP
matchups than 5 LHP matchups).

Output: data/outputs/hitter_handedness.csv
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


def hitter_hand_splits(years=range(2018, 2026)) -> pd.DataFrame:
    frames = []
    for year in years:
        if year == 2020: continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists(): continue
        df = pd.read_parquet(path, columns=['batter', 'p_throws', 'events'])
        df = df[df['events'].isin(PA_EVENTS)].copy()
        if df.empty: continue
        df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
        df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
        df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['core_fp'] = df['tb'] + df['bb'] + df['hbp'] - df['k']
        df['pa'] = 1
        agg = df.groupby(['batter', 'p_throws'], as_index=False).agg(
            pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
        frames.append(agg)
    if not frames: return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full = full.groupby(['batter', 'p_throws'], as_index=False).agg(
        pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
    full['rate'] = full['core_fp'] / full['pa']

    # Pivot
    pivot = full.pivot_table(index='batter', columns='p_throws',
                              values=['pa', 'rate']).reset_index()
    pivot.columns = [f'{c}_{b}' if b else c for c, b in pivot.columns]
    pivot = pivot.rename(columns={'pa_L': 'pa_vs_L', 'pa_R': 'pa_vs_R',
                                    'rate_L': 'rate_vs_L', 'rate_vs_R': 'rate_vs_R'})

    # Annual
    overall = full.groupby('batter', as_index=False).agg(
        total_pa=('pa', 'sum'), total_fp=('core_fp', 'sum'))
    overall['annual_rate'] = overall['total_fp'] / overall['total_pa']
    overall = overall[overall['total_pa'] >= 800]

    out = pivot.merge(overall[['batter', 'annual_rate', 'total_pa']],
                       on='batter', how='inner')
    out['lift_vs_L_pct'] = ((out['rate_vs_L'] - out['annual_rate']) / out['annual_rate'].replace(0, np.nan) * 100).round(1)
    out['lift_vs_R_pct'] = ((out.get('rate_R', out.get('rate_vs_R')) - out['annual_rate']) / out['annual_rate'].replace(0, np.nan) * 100).round(1)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    h = hitter_hand_splits()
    if h.empty:
        print('  no data')
        return
    rh = PROJECTIONS.rh3()
    h = h.merge(rh[['batter', 'player_name', 'team', 'rank']], on='batter', how='left')
    out = OUT / 'hitter_handedness.csv'
    h.to_csv(out, index=False)
    print(f'  wrote {out} ({len(h)} hitters)')


if __name__ == '__main__':
    main()
