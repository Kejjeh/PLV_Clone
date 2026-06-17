"""sp_lineup_pass.py — per-SP fp degradation by time-through-the-order.

Statcast field n_thruorder_pitcher = 1 (1st time), 2, 3, 4+ for each PA.
Compute per-SP career fp/PA at TTO=1, 2, 3 and the lift (or drop) at each
pass relative to overall.

Useful as: in-game projection adjustment when an SP has high TTO=2/3 drop;
also for evaluating which SPs bullpen-cap (i.e., truly are 5.5-inning guys).

Output: data/outputs/sp_lineup_pass.csv
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
    'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for year in range(2018, 2027):
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['pitcher', 'events', 'n_thruorder_pitcher', 'inning'])
        # SP-only proxy: had inning-1 appearance in this game (we can't easily filter
        # by start here, but TTO=1+ ordering naturally restricts to SP-style usage).
        # Filter PA events.
        df = df[df['events'].isin(PA_EVENTS) & df['n_thruorder_pitcher'].notna()]
        if df.empty:
            continue
        df['tto'] = df['n_thruorder_pitcher'].astype(int)
        df['tto'] = df['tto'].clip(upper=4)  # 4+ collapses
        df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
        df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
        df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        # Pitcher-side core: K - (TB + BB + HBP)
        df['core_fp_pit'] = df['k'] - df['tb'] - df['bb'] - df['hbp']
        df['pa'] = 1
        agg = df.groupby(['pitcher', 'tto'], as_index=False).agg(
            pa=('pa', 'sum'), core_fp_pit=('core_fp_pit', 'sum'),
            k=('k', 'sum'), bb=('bb', 'sum'), hr=('events', lambda x: (x == 'home_run').sum()))
        frames.append(agg)
    if not frames:
        print('  no data'); return
    full = pd.concat(frames, ignore_index=True)
    full = full.groupby(['pitcher', 'tto'], as_index=False).agg(
        pa=('pa', 'sum'), core_fp_pit=('core_fp_pit', 'sum'),
        k=('k', 'sum'), bb=('bb', 'sum'), hr=('hr', 'sum'))
    full['rate'] = full['core_fp_pit'] / full['pa']

    # Min-PA filter per cell
    full = full[full['pa'] >= 50]

    # Overall rate per pitcher
    overall = full.groupby('pitcher', as_index=False).agg(
        total_pa=('pa', 'sum'), total_core=('core_fp_pit', 'sum'))
    overall['overall_rate'] = overall['total_core'] / overall['total_pa']
    overall = overall[overall['total_pa'] >= 600]  # ~1 full season worth

    full = full.merge(overall[['pitcher', 'overall_rate', 'total_pa']], on='pitcher', how='inner')
    full['delta_vs_overall'] = (full['rate'] - full['overall_rate']).round(4)

    pivot = full.pivot_table(index='pitcher', columns='tto',
                              values=['pa', 'rate', 'delta_vs_overall'])
    pivot.columns = [f'tto{int(c)}_{m}' for m, c in pivot.columns]
    pivot = pivot.reset_index()
    pivot = pivot.merge(overall[['pitcher', 'overall_rate', 'total_pa']], on='pitcher', how='left')

    # 3rd-time penalty: raw drop in core_fp/PA from TTO1 to TTO3
    # negative = pitcher worse on 3rd time through (the typical case)
    if 'tto3_rate' in pivot.columns and 'tto1_rate' in pivot.columns:
        pivot['tto3_minus_tto1'] = (pivot['tto3_rate'] - pivot['tto1_rate']).round(4)

    name_map_path = CACHE / 'mlb_player_id_name.csv'
    if name_map_path.exists():
        nm = pd.read_csv(name_map_path)
        nm['pitcher'] = pd.to_numeric(nm['mlb_id'], errors='coerce').astype('Int64')
        nm = nm[['pitcher', 'name']].rename(columns={'name': 'player_name'}).dropna()
        pivot = pivot.merge(nm, on='pitcher', how='left')
    else:
        pivot['player_name'] = None

    fname = OUT / 'sp_lineup_pass.csv'
    pivot.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(pivot)} SPs)')

    print('\n  Top 10 SPs hurt MOST by 3rd time through (raw core_fp/PA drop):')
    bad = pivot[pivot['tto3_pa'].notna() & (pivot['tto3_pa'] >= 100)].copy()
    bad = bad[bad['tto3_minus_tto1'].notna()].sort_values('tto3_minus_tto1')
    print(bad.head(10)[['player_name', 'total_pa', 'tto1_rate', 'tto3_rate', 'tto3_minus_tto1']].to_string(index=False))
    print('\n  Top 10 SPs IMMUNE to 3rd-time penalty (improve or hold):')
    print(bad.tail(10)[['player_name', 'total_pa', 'tto1_rate', 'tto3_rate', 'tto3_minus_tto1']].to_string(index=False))


if __name__ == '__main__':
    main()
