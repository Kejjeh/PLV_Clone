"""hitter_xwoba_residual.py — career xwOBA vs actual wOBA per hitter.

Statcast provides estimated_woba_using_speedangle (Quality of Contact only,
ignores Ks/BBs). Compute per-batter:
  woba_con (actual): batted-ball events only, sum(woba_value)/sum(woba_denom)
  xwoba_con (expected): mean of estimated_woba_using_speedangle per BBE

residual = xwoba_con - woba_con
  positive = "unlucky" (hits coming, regression up)
  negative = "lucky" (regression down likely)

Validate via cross-year r-lift on top of rh3 baseline.

Output: data/outputs/hitter_xwoba_residual.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from plv_clone.projections import PROJECTIONS
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for year in range(2018, 2027):
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=[
            'batter', 'estimated_woba_using_speedangle',
            'woba_value', 'woba_denom', 'launch_speed', 'launch_angle', 'events'])
        # BBE: rows with a batted-ball outcome (woba_denom>0 & launch_speed not null)
        df = df[df['woba_denom'].notna() & (df['woba_denom'] > 0)
                & df['launch_speed'].notna() & df['estimated_woba_using_speedangle'].notna()]
        if df.empty:
            continue
        df['year'] = year
        agg = df.groupby(['batter', 'year'], as_index=False).agg(
            bbe=('woba_value', 'count'),
            woba_value=('woba_value', 'sum'),
            woba_denom=('woba_denom', 'sum'),
            xwoba_sum=('estimated_woba_using_speedangle', 'sum'),
            ev_mean=('launch_speed', 'mean'),
            ev_p90=('launch_speed', lambda x: np.percentile(x, 90)),
            barrel_count=('launch_speed', lambda x: ((x >= 98) & (df.loc[x.index, 'launch_angle'].between(26, 30))).sum()),
        )
        frames.append(agg)
    if not frames:
        print('  no data'); return
    full = pd.concat(frames, ignore_index=True)
    full['woba_con'] = full['woba_value'] / full['woba_denom']
    full['xwoba_con'] = full['xwoba_sum'] / full['bbe']
    full['xwoba_residual'] = full['xwoba_con'] - full['woba_con']
    full['barrel_pct'] = full['barrel_count'] / full['bbe'] * 100

    # Career rollup: weighted by BBE
    out_rows = []
    for bid, sub in full.groupby('batter'):
        sub = sub[sub['bbe'] >= 30]
        if sub.empty:
            continue
        bbe_total = sub['bbe'].sum()
        # Latest year specifically (2025 or 2026)
        latest_year = sub['year'].max()
        latest = sub[sub['year'] == latest_year].iloc[0]
        # Multi-year career
        woba_career = (sub['woba_con'] * sub['bbe']).sum() / bbe_total
        xwoba_career = (sub['xwoba_con'] * sub['bbe']).sum() / bbe_total
        ev90_career = (sub['ev_p90'] * sub['bbe']).sum() / bbe_total
        barrel_career = (sub['barrel_pct'] * sub['bbe']).sum() / bbe_total
        out_rows.append({
            'batter': int(bid),
            'bbe_career': int(bbe_total),
            'woba_con_career': round(woba_career, 4),
            'xwoba_con_career': round(xwoba_career, 4),
            'xwoba_residual_career': round(xwoba_career - woba_career, 4),
            'ev90_career': round(ev90_career, 1),
            'barrel_pct_career': round(barrel_career, 1),
            'latest_year': int(latest_year),
            'bbe_latest': int(latest['bbe']),
            'woba_con_latest': round(latest['woba_con'], 4),
            'xwoba_con_latest': round(latest['xwoba_con'], 4),
            'xwoba_residual_latest': round(latest['xwoba_con'] - latest['woba_con'], 4),
            'ev90_latest': round(latest['ev_p90'], 1),
            'barrel_pct_latest': round(latest['barrel_pct'], 1),
        })
    out = pd.DataFrame(out_rows)
    rh = PROJECTIONS.rh3()[['batter', 'player_name']].drop_duplicates('batter')
    out = out.merge(rh, on='batter', how='left')

    fname = OUT / 'hitter_xwoba_residual.csv'
    out.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(out)} hitters)')

    print('\n  Top 10 UNLUCKY 2025/2026 (positive residual = hits coming):')
    recent = out[out['latest_year'] >= 2025].copy()
    recent = recent[recent['bbe_latest'] >= 100]
    print(recent.sort_values('xwoba_residual_latest', ascending=False).head(10)[
        ['player_name', 'latest_year', 'bbe_latest', 'woba_con_latest', 'xwoba_con_latest', 'xwoba_residual_latest', 'ev90_latest', 'barrel_pct_latest']].to_string(index=False))
    print('\n  Top 10 LUCKY 2025/2026 (negative residual = regression down):')
    print(recent.sort_values('xwoba_residual_latest').head(10)[
        ['player_name', 'latest_year', 'bbe_latest', 'woba_con_latest', 'xwoba_con_latest', 'xwoba_residual_latest', 'ev90_latest', 'barrel_pct_latest']].to_string(index=False))


if __name__ == '__main__':
    main()
