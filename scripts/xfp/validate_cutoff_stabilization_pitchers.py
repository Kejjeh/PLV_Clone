"""Pitcher-side empirical cutoff stabilization (SP + RP).

Pre-registered: data/research/validation_runs/pitcher_cutoff_stabilization_2026-07-29.md
Mirrors validate_cutoff_stabilization.py (hitters). Forward reliability
r(metric_to, metric_rest_of_season) bucketed by the metric's own denominator.
"""
from __future__ import annotations
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

# metric -> (numer count cols ('-' subtracts), denom col, bucket kind)
SP_METRICS = {
    'chase':    (['o_swing'], 'out_zone', 'pitches'),
    'zswing':   (['z_swing'], 'in_zone', 'pitches'),
    'whiff':    (['swing', '-contact'], 'swing', 'pitches'),
    'swstr':    (['swstr'], 'pitches', 'pitches'),
    'csw':      (['swstr', 'called_strike'], 'pitches', 'pitches'),
    'k_pct':    (['k'], 'tbf', 'tbf'),
    'bb_pct':   (['bb'], 'tbf', 'tbf'),
    'hard_hit': (['hard_hit_n'], 'bip', 'bip'),
    'barrel':   (['barrel_n'], 'bip', 'bip'),
    'gb':       (['gb_n'], 'bip', 'bip'),
    'woba_agn': (['woba_v_sum'], 'woba_d_sum', 'tbf'),
    'hr_rate':  (['hr'], 'tbf', 'tbf'),
}
RP_METRICS = {k: v for k, v in SP_METRICS.items()
              if k in ('chase', 'zswing', 'whiff', 'swstr', 'csw', 'k_pct',
                       'bb_pct', 'woba_agn')}
BUCKETS = {'pitches': np.arange(100, 2101, 100),
           'tbf': np.arange(25, 626, 25),
           'bip': np.arange(20, 421, 20)}
REST_FLOOR = {'pitches': 200, 'tbf': 40, 'bip': 30}
MIN_BUCKET_N = 200


def col_sum(df, names, sfx):
    out = 0.0
    for n in names:
        out = (out - df[n[1:] + sfx]) if n.startswith('-') else (out + df[n + sfx])
    return out


def run_side(label, rolling_path, multiyr_path, metrics, year_col='year'):
    rolling = pd.read_csv(rolling_path)
    multiyr = pd.read_csv(multiyr_path)
    if 'o_swing_num' in multiyr.columns:
        multiyr = multiyr.rename(columns={'o_swing_num': 'o_swing'})
    if 'out_zone' not in multiyr.columns:
        multiyr['out_zone'] = multiyr['pitches'] - multiyr['in_zone']
    rolling['out_zone_to'] = rolling['pitches_to'] - rolling['in_zone_to']

    season_cols = {'pitcher', year_col}
    for nums, den, _ in metrics.values():
        season_cols.update(n.lstrip('-') for n in nums)
        season_cols.add(den)
    season_cols.add('avg_velo'); season_cols.add('pitches')
    season_cols &= set(multiyr.columns) | {'pitcher', year_col}
    df = rolling.merge(multiyr[list(season_cols)].rename(columns={year_col: 'year'}),
                       on=['pitcher', 'year'], how='inner', suffixes=('', '_season'))
    df = df[df['year'] != 2020]
    print(f'\n===== {label}: {len(df)} joined snapshots, '
          f'years {sorted(df.year.unique())} =====')
    print(f'{"metric":<9} {"denom":<8} {"r=0.50 at":<12} {"r=0.70 at":<12} curve')
    print('-' * 108)

    mins = {}
    for m, (nums, den, kind) in metrics.items():
        if any(n.lstrip('-') not in df.columns for n in nums) or den not in df.columns:
            print(f'{m:<9} NOT MEASURABLE (season counts absent)')
            continue
        num_to, den_to = col_sum(df, nums, '_to'), df[den + '_to']
        num_rest = col_sum(df, nums, '') - num_to
        den_rest = df[den] - den_to
        # rest floor keyed on the bucket kind's natural unit (lazy — RP
        # multiyr has no bip counts)
        floor_src = {'pitches': 'pitches', 'tbf': 'tbf', 'bip': 'bip'}[kind]
        if floor_src not in df.columns:
            print(f'{m:<9} NOT MEASURABLE (no season {floor_src} counts)')
            continue
        floor_col = df[floor_src] - df[floor_src + '_to']
        ok = (den_to > 0) & (den_rest > 0) & (floor_col >= REST_FLOOR[kind])
        r_to, r_rest, d_to = (num_to / den_to)[ok], (num_rest / den_rest)[ok], den_to[ok]
        mins[m] = curve(m, kind, r_to, r_rest, d_to)

    # velocity: pitch-weighted average
    if 'avg_velo' in df.columns and 'avg_velo_to' in df.columns:
        p_to, p_all = df['pitches_to'], df['pitches']
        p_rest = p_all - p_to
        v_rest = (p_all * df['avg_velo'] - p_to * df['avg_velo_to']) / p_rest
        ok = (p_to > 0) & (p_rest >= REST_FLOOR['pitches']) & df['avg_velo_to'].notna() & v_rest.notna()
        mins['velo'] = curve('velo', 'pitches', df['avg_velo_to'][ok], v_rest[ok],
                             p_to[ok])
    print(f'\n{label} EMPIRICAL MINIMUMS (r>=0.50, ceil 25):')
    for m, c in mins.items():
        print(f'  {m:<9} ' + (f'{int(np.ceil(c / 25) * 25)}' if c else 'NEVER STABILIZES in-window'))
    return mins


def curve(name, kind, rate_to, rate_rest, d_to):
    edges = BUCKETS[kind]
    mids, rs = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (d_to >= lo) & (d_to < hi)
        if sel.sum() < MIN_BUCKET_N:
            continue
        rs.append(float(np.corrcoef(rate_to[sel], rate_rest[sel])[0, 1]))
        mids.append((lo + hi) / 2)
    if not mids:
        print(f'{name:<9} {kind:<8} UNDERPOWERED (no bucket >= {MIN_BUCKET_N})')
        return None

    def crossing(level):
        for i, r in enumerate(rs):
            if r >= level:
                if i == 0:
                    return mids[0]
                x0, x1, y0, y1 = mids[i - 1], mids[i], rs[i - 1], rs[i]
                return x0 + (level - y0) * (x1 - x0) / (y1 - y0)
        return None

    c50, c70 = crossing(0.50), crossing(0.70)
    cv = '  '.join(f'{int(x)}:{r:+.2f}' for x, r in zip(mids[:8], rs[:8]))
    print(f'{name:<9} {kind:<8} '
          f'{(f"{c50:.0f} " + kind) if c50 else "never":<12} '
          f'{(f"{c70:.0f} " + kind) if c70 else "never":<12} {cv}')
    return c50


def main():
    run_side('SP', CACHE / 'rolling_pitchers_2018_2026.csv',
             CACHE / 'sp_multiyr_2015_2025.csv', SP_METRICS)
    run_side('RP', CACHE / 'rolling_relievers_2018_2026.csv',
             CACHE / 'relievers_multiyr_2018_2026.csv', RP_METRICS)
    print('\ndone.')


if __name__ == '__main__':
    main()
