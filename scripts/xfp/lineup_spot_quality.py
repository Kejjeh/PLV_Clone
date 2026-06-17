"""lineup_spot_quality.py — per-batter career fp/PA by lineup spot.

Joins per-game lineup spot with statcast PA events to get fp/PA per batter
per lineup position. Reveals which players gain disproportionately from
hitting at the top of the order vs bottom.

Useful as: in-season signal when a manager moves a player to leadoff (more
PAs), and per-batter trade context (a guy locked into the #2 spot on a
good lineup is more valuable than the same guy in the #6 spot).

Output: data/outputs/lineup_spot_quality.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
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


def lineup_splits(years=range(2018, 2026)) -> pd.DataFrame:
    frames = []
    for year in years:
        if year == 2020: continue
        sc_path = CACHE / f'statcast_{year}.parquet'
        lu_path = CACHE / f'hitter_lineup_appearances_{year}.parquet'
        if not (sc_path.exists() and lu_path.exists()): continue
        sc = pd.read_parquet(sc_path, columns=['game_pk','batter','events'])
        sc = sc[sc['events'].isin(PA_EVENTS)].copy()
        if sc.empty: continue
        lu = pd.read_parquet(lu_path, columns=['game_pk','batter','lineup_spot','started_game'])
        lu = lu[lu['started_game'] & lu['lineup_spot'].notna()]
        lu['lineup_spot'] = lu['lineup_spot'].astype(int)
        sc = sc.merge(lu[['game_pk','batter','lineup_spot']], on=['game_pk','batter'], how='inner')
        if sc.empty: continue
        sc['tb'] = sc['events'].map({'single':1,'double':2,'triple':3,'home_run':4}).fillna(0).astype(int)
        sc['bb'] = sc['events'].isin({'walk','intent_walk'}).astype(int)
        sc['hbp'] = (sc['events'] == 'hit_by_pitch').astype(int)
        sc['k'] = sc['events'].isin({'strikeout','strikeout_double_play'}).astype(int)
        sc['core_fp'] = sc['tb'] + sc['bb'] + sc['hbp'] - sc['k']
        sc['pa'] = 1
        agg = sc.groupby(['batter','lineup_spot'], as_index=False).agg(
            pa=('pa','sum'), core_fp=('core_fp','sum'))
        frames.append(agg)
    if not frames: return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full = full.groupby(['batter','lineup_spot'], as_index=False).agg(
        pa=('pa','sum'), core_fp=('core_fp','sum'))
    full = full[full['pa'] >= 30]
    full['rate'] = full['core_fp']/full['pa']

    overall = full.groupby('batter', as_index=False).agg(
        total_pa=('pa','sum'), total_fp=('core_fp','sum'))
    overall['annual_rate'] = overall['total_fp']/overall['total_pa']
    overall = overall[overall['total_pa'] >= 800]

    full = full.merge(overall[['batter','annual_rate','total_pa']], on='batter', how='inner')
    full['lift_pct'] = ((full['rate']-full['annual_rate'])/full['annual_rate'].replace(0,np.nan)*100).round(1)

    pivot = full.pivot_table(index='batter', columns='lineup_spot',
                              values=['pa','rate','lift_pct'])
    pivot.columns = [f'spot{int(c)}_{m}' for m, c in pivot.columns]
    pivot = pivot.reset_index()
    pivot = pivot.merge(overall[['batter','annual_rate','total_pa']], on='batter', how='left')
    return pivot


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    out = lineup_splits()
    if out.empty:
        print('  no data'); return
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    out = out.merge(rh[['batter','player_name','team','rank']], on='batter', how='left')
    fname = OUT / 'lineup_spot_quality.csv'
    out.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(out)} hitters)')


if __name__ == '__main__':
    main()
