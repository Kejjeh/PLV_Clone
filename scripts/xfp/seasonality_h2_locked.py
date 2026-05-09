"""seasonality_h2_locked.py — production-locked H2-lift career feature.

Best variant from the cross-year r-lift validation:
  - Cutoff: August 1 (vs the more common July 7 — Aug captures the cleaner
    "second half" effect after the All-Star break has had time to stick)
  - Min PA per half: 150 (filters small-sample noise out)
  - Metric: core_fp/PA (TB+BB+HBP-K)/PA, weighted by PA across qualifying seasons

Validation: cross-year r 0.5189 -> 0.5433, Δr = +0.0244 over baseline rh3 features.
This is the only career-profile feature that survives the empirical r-lift gate.

Output:
  data/outputs/seasonality_h2_locked.csv
    columns: batter, h1_pa, h2_pa, h1_rate, h2_rate, lift_h2_aug150
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
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

CUTOFF_DATE = '08-01'
MIN_PA_PER_HALF = 150


def _load_pa_aggregates(years=range(2018, 2026)) -> pd.DataFrame:
    frames = []
    for year in years:
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['game_date', 'batter', 'events'])
        df = df[df['events'].isin(PA_EVENTS)].copy()
        if df.empty:
            continue
        df['year'] = year
        df['date_md'] = pd.to_datetime(df['game_date']).dt.strftime('%m-%d')
        df['half'] = (df['date_md'] >= CUTOFF_DATE).astype(int)  # 0 = pre-Aug, 1 = Aug+
        df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
        df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
        df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['core_fp'] = df['tb'] + df['bb'] + df['hbp'] - df['k']
        df['pa'] = 1
        agg = df.groupby(['batter', 'year', 'half'], as_index=False).agg(
            pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
        frames.append(agg)
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full['core_fp_per_pa'] = full['core_fp'] / full['pa']
    return full


def compute_h2_locked(g: pd.DataFrame, min_pa: int = MIN_PA_PER_HALF) -> pd.DataFrame:
    qual = g[g['pa'] >= min_pa]
    rows = []
    for batter, sub in qual.groupby('batter'):
        h1 = sub[sub['half'] == 0]
        h2 = sub[sub['half'] == 1]
        if h1['year'].nunique() < 2 or h2['year'].nunique() < 2:
            continue
        h1_pa = h1['pa'].sum()
        h2_pa = h2['pa'].sum()
        if h1_pa <= 0 or h2_pa <= 0:
            continue
        h1_rate = (h1['core_fp_per_pa'] * h1['pa']).sum() / h1_pa
        h2_rate = (h2['core_fp_per_pa'] * h2['pa']).sum() / h2_pa
        lift = (h2_rate - h1_rate) / abs(h1_rate) * 100 if abs(h1_rate) > 0.001 else (h2_rate - h1_rate) * 100
        rows.append({
            'batter': int(batter),
            'h1_pa': int(h1_pa),
            'h2_pa': int(h2_pa),
            'h1_rate': round(h1_rate, 4),
            'h2_rate': round(h2_rate, 4),
            'lift_h2_aug150': round(lift, 2),
        })
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(f'[h2-locked] cutoff={CUTOFF_DATE}, min_pa={MIN_PA_PER_HALF}')
    g = _load_pa_aggregates()
    if g.empty:
        print('  no data'); return
    print(f'  PA half-aggregates: {len(g)} rows')
    out = compute_h2_locked(g)
    fname = OUT / 'seasonality_h2_locked.csv'
    out.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(out)} qualified hitters)')


if __name__ == '__main__':
    main()
