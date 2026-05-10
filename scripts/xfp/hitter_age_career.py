"""hitter_age_career.py — per-batter age + career-experience features.

Two outputs in one CSV:
  - age_year_T: batter's age in year T (from statcast age_bat field)
  - career_year_T: nth distinct MLB year through year T (1 = rookie, 2 = sophomore, ...)
  - peak_residual: distance from 27 (peak power) — abs(age - 27)

These directly address Tier C #11 (sophomore patterns) and #14 (age curves).

Output: data/outputs/hitter_age_career.csv
  columns: batter, year, age, career_year, age_residual_27
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for year in range(2015, 2027):
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['batter', 'age_bat', 'events'])
        df = df.dropna(subset=['age_bat'])
        if df.empty:
            continue
        agg = df.groupby('batter', as_index=False).agg(
            age=('age_bat', 'mean'),
            n_events=('events', 'count'))
        agg['year'] = year
        frames.append(agg)
    if not frames:
        print('  no data'); return
    full = pd.concat(frames, ignore_index=True)
    full['age'] = full['age'].round(0).astype(int)
    full['age_residual_27'] = (full['age'] - 27).abs()  # distance from peak

    # Career year: cumulative distinct years up to and including year T
    full = full.sort_values(['batter', 'year'])
    full['career_year'] = full.groupby('batter').cumcount() + 1

    out = full[['batter', 'year', 'age', 'age_residual_27', 'career_year']]
    fname = OUT / 'hitter_age_career.csv'
    out.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(out)} batter-year rows)')

    # Sanity
    print(f'  Age range: {out["age"].min()} - {out["age"].max()}')
    print(f'  Career year distribution: 1st={(out["career_year"]==1).sum()}, '
          f'2nd={(out["career_year"]==2).sum()}, 3rd={(out["career_year"]==3).sum()}')


if __name__ == '__main__':
    main()
