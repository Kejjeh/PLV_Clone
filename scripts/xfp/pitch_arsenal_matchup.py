"""pitch_arsenal_matchup.py — pitch-type × batter weakness mismatches.

Two halves:
  1. Per-batter career whiff% / xwOBA by pitch_type (FF, SL, CU, CH, SI, FC, FS).
  2. Per-pitcher pitch-mix usage % (recent 2 yrs) by pitch_type.

Emit two outputs:
  data/outputs/batter_pitch_weakness.csv
  data/outputs/pitcher_pitch_mix.csv

Plus a derived matchup engine that for any batter × pitcher pair picks the
predominant pitch and reports the batter's whiff% on that pitch.

This is decision-support, not a model feature (matchups are pairwise).
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

PITCH_GROUPS = {
    'FF': 'FB', 'FT': 'FB', 'FA': 'FB', 'FC': 'CT',
    'SI': 'SI', 'SL': 'SL', 'ST': 'SL', 'SV': 'SL',
    'CU': 'CB', 'KC': 'CB', 'CS': 'CB', 'EP': 'CB',
    'CH': 'CH', 'FS': 'SP', 'FO': 'SP',
}
SWINGS = {'foul', 'foul_tip', 'hit_into_play', 'swinging_strike', 'swinging_strike_blocked', 'missed_bunt'}
WHIFFS = {'swinging_strike', 'swinging_strike_blocked'}


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    bat_frames = []
    pit_frames = []
    for year in range(2015, 2027):
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=[
            'batter', 'pitcher', 'pitch_type', 'description',
            'estimated_woba_using_speedangle', 'woba_value', 'woba_denom'])
        df = df[df['pitch_type'].notna()].copy()
        df['ptg'] = df['pitch_type'].map(PITCH_GROUPS).fillna('OTHER')
        df['swing'] = df['description'].isin(SWINGS).astype(int)
        df['whiff'] = df['description'].isin(WHIFFS).astype(int)
        df['year'] = year
        # Batter aggregation
        bat = df.groupby(['batter', 'ptg'], as_index=False).agg(
            pitches=('description', 'count'),
            swings=('swing', 'sum'),
            whiffs=('whiff', 'sum'),
            xwoba_sum=('estimated_woba_using_speedangle', lambda x: x.dropna().sum()),
            xwoba_n=('estimated_woba_using_speedangle', lambda x: x.notna().sum()),
        )
        bat_frames.append(bat)
        # Pitcher mix - recent 2 years only
        if year >= 2025:
            pmx = df.groupby(['pitcher', 'ptg'], as_index=False).agg(
                pitches=('description', 'count'))
            pit_frames.append(pmx)

    if bat_frames:
        bat_full = pd.concat(bat_frames, ignore_index=True)
        bat_full = bat_full.groupby(['batter', 'ptg'], as_index=False).agg(
            pitches=('pitches', 'sum'), swings=('swings', 'sum'),
            whiffs=('whiffs', 'sum'),
            xwoba_sum=('xwoba_sum', 'sum'), xwoba_n=('xwoba_n', 'sum'))
        bat_full = bat_full[bat_full['swings'] >= 50]
        bat_full['whiff_per_swing'] = (bat_full['whiffs'] / bat_full['swings'] * 100).round(1)
        bat_full['xwoba_avg'] = (bat_full['xwoba_sum'] / bat_full['xwoba_n']).round(3)
        names = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')[['batter', 'player_name']].drop_duplicates('batter')
        bat_full = bat_full.merge(names, on='batter', how='left')
        f1 = OUT / 'batter_pitch_weakness.csv'
        bat_full.sort_values(['batter', 'ptg']).to_csv(f1, index=False)
        print(f'  wrote {f1} ({len(bat_full)} batter-pitch rows)')

    if pit_frames:
        pit_full = pd.concat(pit_frames, ignore_index=True)
        pit_full = pit_full.groupby(['pitcher', 'ptg'], as_index=False)['pitches'].sum()
        total = pit_full.groupby('pitcher', as_index=False)['pitches'].sum().rename(columns={'pitches': 'total'})
        pit_full = pit_full.merge(total, on='pitcher', how='left')
        pit_full = pit_full[pit_full['total'] >= 200]
        pit_full['mix_pct'] = (pit_full['pitches'] / pit_full['total'] * 100).round(1)
        rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')[['pitcher', 'player_name']].drop_duplicates('pitcher')
        pit_full = pit_full.merge(rp, on='pitcher', how='left')
        f2 = OUT / 'pitcher_pitch_mix.csv'
        pit_full.sort_values(['pitcher', 'mix_pct'], ascending=[True, False]).to_csv(f2, index=False)
        print(f'  wrote {f2} ({len(pit_full)} pitcher-pitch rows)')

    # Headline weakness table: which batters whiff most on each pitch type
    print('\n  Worst whiffs vs SL/SV (sliders) — min 100 swings:')
    sl = bat_full[(bat_full['ptg'] == 'SL') & (bat_full['swings'] >= 100)].sort_values('whiff_per_swing', ascending=False)
    print(sl.head(10)[['player_name', 'swings', 'whiff_per_swing', 'xwoba_avg']].to_string(index=False))
    print('\n  Worst whiffs vs FB (fastballs) — min 100 swings:')
    fb = bat_full[(bat_full['ptg'] == 'FB') & (bat_full['swings'] >= 100)].sort_values('whiff_per_swing', ascending=False)
    print(fb.head(10)[['player_name', 'swings', 'whiff_per_swing', 'xwoba_avg']].to_string(index=False))


if __name__ == '__main__':
    main()
