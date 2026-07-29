"""PART A — empirical cutoff stabilization curves for 12 hitter rate metrics.

Pre-registered: data/research/validation_runs/inseason_delta_grid_2026-07-29.md

For each metric: forward reliability r(metric_to, metric_rest_of_season)
bucketed by the metric's own denominator size at the snapshot. rest = multiyr
season count - rolling _to count (same year, so no cross-season drift).
Empirical cutoff = interpolated denominator where forward r crosses 0.50 / 0.70.

This is the decision-relevant stabilization quantity ("how much does N units
of measurement tell you about the remainder"), not pure split-half
reliability — it conflates measurement noise with true in-season drift,
which is exactly the uncertainty a forward-looking decision faces.
"""
from __future__ import annotations
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from plv_clone.models.xfp.rh3 import ROLLING_CSV, MULTIYR_CSV

# metric -> (numer counts, denom counts, denominator kind)
# Each entry gives season (multiyr) col names; rolling versions carry _to.
METRICS = {
    'chase':    (['o_swing'], 'out_zone', 'pitches'),
    'zswing':   (['swing', '-o_swing'], 'in_zone', 'pitches'),
    'z_contact': (['z_contact'], 'z_swing', 'pitches'),
    'whiff':    (['swing', '-contact'], 'swing', 'pitches'),
    'swstr':    (['swstr'], 'pitches', 'pitches'),
    'k_pct':    (['k'], 'pa', 'pa'),
    'bb_pct':   (['bb'], 'pa', 'pa'),
    'hard_hit': (['hard_hit_n'], 'bip', 'bip'),
    'barrel':   (['barrel_n'], 'bip', 'bip'),
    'xwoba_ppa': (['xwoba_sum'], 'pa', 'pa'),
    'iso':      (['tb', '-h'], 'ab', 'ab'),
    'hr_ppa':   (['hr'], 'pa', 'pa'),
}
BUCKETS = {
    'pitches': np.arange(100, 2101, 100),
    'pa': np.arange(25, 526, 25),
    'bip': np.arange(20, 421, 20),
    'ab': np.arange(25, 526, 25),
}
REST_FLOOR = {'pitches': 200, 'pa': 50, 'bip': 40, 'ab': 50}


def col_sum(df, names, sfx):
    """Signed sum of count columns ('-x' subtracts)."""
    out = 0.0
    for n in names:
        if n.startswith('-'):
            out = out - df[n[1:] + sfx]
        else:
            out = out + df[n + sfx]
    return out


def main():
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)

    # Rolling lacks out_zone_to / z_swing_to as counts — derive.
    rolling['out_zone_to'] = rolling['pitches_to'] - rolling['in_zone_to']
    rolling['z_swing_to'] = rolling['swing_to'] - rolling['o_swing_to']
    rolling['xwoba_sum_to'] = rolling['xwoba_per_pa_to'] * rolling['pa_to']
    multiyr = multiyr.copy()
    multiyr['z_swing'] = multiyr['swing'] - multiyr['o_swing']
    multiyr['xwoba_sum'] = multiyr['xwoba_per_pa'] * multiyr['pa']

    season_cols = set()
    for nums, den, _ in METRICS.values():
        season_cols.update(n.lstrip('-') for n in nums)
        season_cols.add(den)
    season_cols |= {'batter', 'year'}
    df = rolling.merge(multiyr[list(season_cols)], on=['batter', 'year'],
                       how='inner', suffixes=('', '_season'))
    df = df[df['year'] != 2020]
    print(f'joined snapshots: {len(df)}  years {sorted(df.year.unique())}')

    print(f'\n{"metric":<10} {"denom":<8} {"r=0.50 at":<12} {"r=0.70 at":<12} '
          f'{"curve (denom_mid: r)"}')
    print('-' * 110)
    results = {}
    for m, (nums, den, kind) in METRICS.items():
        num_to = col_sum(df, nums, '_to')
        den_to = df[den + '_to']
        num_season = col_sum(df, nums, '')
        den_season = df[den]
        num_rest = num_season - num_to
        den_rest = den_season - den_to

        ok = (den_to > 0) & (den_rest >= REST_FLOOR[kind])
        rate_to = (num_to / den_to)[ok]
        rate_rest = (num_rest / den_rest)[ok]
        d_to = den_to[ok]

        edges = BUCKETS[kind]
        mids, rs, ns = [], [], []
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = (d_to >= lo) & (d_to < hi)
            if sel.sum() < 200:
                continue
            r = float(np.corrcoef(rate_to[sel], rate_rest[sel])[0, 1])
            mids.append((lo + hi) / 2)
            rs.append(r)
            ns.append(int(sel.sum()))
        results[m] = (kind, mids, rs, ns)

        def crossing(level):
            for i in range(len(rs)):
                if rs[i] >= level:
                    if i == 0:
                        return mids[0]
                    # linear interpolation between the straddling buckets
                    x0, x1, y0, y1 = mids[i - 1], mids[i], rs[i - 1], rs[i]
                    return x0 + (level - y0) * (x1 - x0) / (y1 - y0)
            return None

        c50, c70 = crossing(0.50), crossing(0.70)
        curve = '  '.join(f'{int(x)}:{r:+.2f}' for x, r in zip(mids[:8], rs[:8]))
        f50 = f'{c50:.0f} {kind}' if c50 else 'never'
        f70 = f'{c70:.0f} {kind}' if c70 else 'never'
        print(f'{m:<10} {kind:<8} {f50:<12} {f70:<12} {curve}')

    # Registry-ready empirical minimums (r>=0.50, rounded up to nearest 25)
    print('\nEMPIRICAL MINIMUMS (r>=0.50 crossing, ceil to 25):')
    for m, (kind, mids, rs, ns) in results.items():
        c = next((mids[i] for i in range(len(rs)) if rs[i] >= 0.50), None)
        if c is None:
            print(f'  {m:<10} NEVER STABILIZES in-window ({kind}); mark UNDERPOWERED')
        else:
            print(f'  {m:<10} {int(np.ceil(c / 25) * 25)} {kind}')


if __name__ == '__main__':
    main()
