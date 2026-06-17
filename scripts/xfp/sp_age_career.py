"""sp_age_career.py — per-pitcher age + career-experience features.

Mirror of hitter_age_career.py for pitchers. Pitcher peak ≈ 28 (later than hitters).

Output: data/outputs/sp_age_career.csv
  columns: pitcher, year, age, age_residual_28, career_year
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

from plv_clone.paths import ROOT
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
        df = pd.read_parquet(path, columns=['pitcher', 'age_pit'])
        df = df.dropna(subset=['age_pit'])
        if df.empty:
            continue
        agg = df.groupby('pitcher', as_index=False).agg(age=('age_pit', 'mean'))
        agg['year'] = year
        frames.append(agg)
    if not frames:
        print('  no data'); return
    full = pd.concat(frames, ignore_index=True)
    full['age'] = full['age'].round(0).astype(int)
    full['age_residual_28'] = (full['age'] - 28).abs()

    full = full.sort_values(['pitcher', 'year'])
    full['career_year'] = full.groupby('pitcher').cumcount() + 1

    out = full[['pitcher', 'year', 'age', 'age_residual_28', 'career_year']]
    fname = OUT / 'sp_age_career.csv'
    out.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(out)} pitcher-year rows)')


if __name__ == '__main__':
    main()
