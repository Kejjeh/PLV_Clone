"""PART B — pre-registered 60-cell in-season delta grid for rh3.

Pre-registered: data/research/validation_runs/inseason_delta_grid_2026-07-29.md

12 metrics x 4 lags {21,42,63,84}d + 3 composites x 4 lags = 60 cells.
NON-OVERLAPPING snapshots per lag. Min-sample gates = Part A empirical
r>=0.50 crossings (validate_cutoff_stabilization.py), not hand-picks.

Funnel: BH-FDR(q=.05) + |r|>=.05 floor on TRAIN -> holdout gate -> Rule 9
integration vs ALL 22 RH3_FEATS (only gate that can promote, bar +0.005).
"""
from __future__ import annotations
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from plv_clone.models.xfp.rh3 import (
    RH3_FEATS, TARGET, TRAIN_YEARS, EVAL_PA_MIN, ROS_PA_MIN,
    ROLLING_CSV, MULTIYR_CSV,
)
from validate_inseason_discipline import attach_production_features

HOLDOUT = [2024, 2025]
TRAIN = [y for y in TRAIN_YEARS if y not in HOLDOUT]
LAGS = [21, 42, 63, 84]
NONOVERLAP = {21: [79, 100, 121, 142, 163, 184],
              42: [79, 121, 163],
              63: [79, 142],
              84: [79, 163]}

# metric: (numer '-'-signed count cols, denom count col, expected sign,
#          empirical min for EARLY & RECENT denominators — Part A r>=0.50)
METRICS = {
    'chase':    (['o_swing'], 'out_zone', -1, 150),
    'zswing':   (['swing', '-o_swing'], 'in_zone', +1, 150),
    'z_contact': (['z_contact'], 'z_swing', +1, 150),
    'whiff':    (['swing', '-contact'], 'swing', -1, 150),
    'swstr':    (['swstr'], 'pitches', -1, 150),
    'k_pct':    (['k'], 'pa', -1, 50),
    'bb_pct':   (['bb'], 'pa', +1, 175),
    'hard_hit': (['hard_hit_n'], 'bip', +1, 50),
    'barrel':   (['barrel_n'], 'bip', +1, 50),
    'xwoba_ppa': (['xwoba_sum'], 'pa', +1, 225),
    'iso':      (['tb', '-h'], 'ab', +1, 275),
    'hr_ppa':   (['hr'], 'pa', +1, 275),
}
COMPOSITES = {'discipline4': [('chase', -1), ('zswing', +1), ('bb_pct', +1), ('k_pct', -1)],
              'contact3': [('hard_hit', +1), ('barrel', +1), ('xwoba_ppa', +1)],
              'all7': [('chase', -1), ('zswing', +1), ('bb_pct', +1), ('k_pct', -1),
                       ('hard_hit', +1), ('barrel', +1), ('xwoba_ppa', +1)]}
# controls: same-metric season-to-date level (shrunk where production has it)
LEVEL_CTRL = {'chase': 'chase_pct_to_sh', 'k_pct': 'k_pct_to_sh',
              'bb_pct': 'bb_pct_to_sh', 'whiff': 'whiff_pct_to_sh',
              'swstr': 'swstr_pct_to_sh', 'hard_hit': 'hard_hit_pct_to_sh',
              'barrel': 'barrel_pct_to_sh', 'xwoba_ppa': 'xwoba_per_pa_to_sh',
              'iso': 'iso_to_sh', 'hr_ppa': 'hr_per_pa_to_sh',
              'zswing': None, 'z_contact': 'contact_pct_to_sh'}
COUNTS = ['pitches', 'pa', 'bip', 'ab', 'in_zone', 'out_zone', 'swing',
          'o_swing', 'z_swing', 'z_contact', 'contact', 'swstr', 'k', 'bb',
          'hard_hit_n', 'barrel_n', 'tb', 'h', 'hr', 'xwoba_sum']


def col_sum(df, names, sfx):
    out = 0.0
    for n in names:
        out = (out - df[n[1:] + sfx]) if n.startswith('-') else (out + df[n + sfx])
    return out


def partial_r(df, cand, ctrl, y=TARGET):
    X = df[ctrl].values
    r1 = df[cand].values - LinearRegression().fit(X, df[cand].values).predict(X)
    r2 = df[y].values - LinearRegression().fit(X, df[y].values).predict(X)
    if r1.std() < 1e-12 or r2.std() < 1e-12:
        return np.nan, np.nan, len(df)
    r = float(np.corrcoef(r1, r2)[0, 1])
    dfree = len(df) - len(ctrl) - 2
    t = r * np.sqrt(dfree / max(1e-12, 1 - r * r))
    p = 2 * sps.t.sf(abs(t), dfree)
    return r, p, len(df)


def build_frames(rolling):
    """One delta frame per lag, non-overlapping snapshots, count-derived."""
    rolling = rolling.copy()
    rolling['out_zone_to'] = rolling['pitches_to'] - rolling['in_zone_to']
    rolling['z_swing_to'] = rolling['swing_to'] - rolling['o_swing_to']
    rolling['xwoba_sum_to'] = rolling['xwoba_per_pa_to'] * rolling['pa_to']
    frames = {}
    for L in LAGS:
        lag = rolling[['batter', 'year', 'split_day'] + [c + '_to' for c in COUNTS]].copy()
        lag['split_day'] = lag['split_day'] + L
        lag.columns = ['batter', 'year', 'split_day'] + [c + '_lag' for c in COUNTS]
        df = rolling[rolling['split_day'].isin(NONOVERLAP[L])].merge(
            lag, on=['batter', 'year', 'split_day'], how='inner')
        for c in COUNTS:
            df[c + '_rec'] = df[c + '_to'] - df[c + '_lag']
        for m, (nums, den, sign, mn) in METRICS.items():
            e_den, r_den = df[den + '_lag'], df[den + '_rec']
            e_rate = col_sum(df, nums, '_lag') / e_den
            r_rate = col_sum(df, nums, '_rec') / r_den
            d = (r_rate - e_rate).where((e_den >= mn) & (r_den >= mn))
            g = d.groupby([df['year'], df['split_day']])
            df['d_' + m] = d
            df['dz_' + m] = sign * (d - g.transform('mean')) / g.transform('std')
        for cname, comps in COMPOSITES.items():
            zc = pd.concat([df['dz_' + m] for m, _ in comps], axis=1)
            df['dz_' + cname] = zc.mean(axis=1).where(zc.notna().all(axis=1))
        frames[L] = df
    return frames


def make_pipe():
    return Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])


def cross_year_r(df, feats):
    rs = []
    for held in [y for y in TRAIN_YEARS if y in df['year'].unique()]:
        tr, te = df[df['year'] != held], df[df['year'] == held]
        if len(tr) < 200 or len(te) < 30:
            continue
        pipe = make_pipe()
        pipe.fit(tr[feats].values, tr[TARGET].values)
        rs.append(float(np.corrcoef(pipe.predict(te[feats].values),
                                    te[TARGET].values)[0, 1]))
    return float(np.mean(rs)) if rs else np.nan


def main():
    rolling = attach_production_features(pd.read_csv(ROLLING_CSV),
                                         pd.read_csv(MULTIYR_CSV))
    rolling = rolling.dropna(subset=RH3_FEATS + [TARGET])
    rolling = rolling[(rolling['pa_to'] >= EVAL_PA_MIN)
                      & (rolling['ros_pa'] >= ROS_PA_MIN)
                      & (rolling['year'] != 2020)]
    frames = build_frames(rolling)
    for L in LAGS:
        print(f'lag {L}d frame: {len(frames[L])} rows '
              f'(splits {NONOVERLAP[L]})')

    # ---- STAGE 1: screen on TRAIN, BH-FDR across all 60 cells ----
    cells = []
    for L in LAGS:
        df = frames[L]
        tr = df[df['year'].isin(TRAIN)]
        for name in list(METRICS) + list(COMPOSITES):
            cand = 'dz_' + name
            lvl = LEVEL_CTRL.get(name)
            ctrl = ([lvl] if lvl else []) + ['prior_fp_per_pa', 'pa_to']
            sub = tr.dropna(subset=[cand] + ctrl)
            if len(sub) < 300:
                cells.append(dict(metric=name, lag=L, r=np.nan, p=np.nan,
                                  n=len(sub), status='UNDERPOWERED'))
                continue
            r, p, n = partial_r(sub, cand, ctrl)
            cells.append(dict(metric=name, lag=L, r=r, p=p, n=n, status=''))
    C = pd.DataFrame(cells)
    tested = C[C['p'].notna()].sort_values('p').reset_index(drop=True)
    m = len(tested)
    tested['bh_crit'] = 0.05 * (tested.index + 1) / m
    k = (tested['p'] <= tested['bh_crit'])
    cut = tested.index[k].max() if k.any() else -1
    tested['fdr_pass'] = tested.index <= cut
    tested['screen_pass'] = tested['fdr_pass'] & (tested['r'].abs() >= 0.05) & (tested['r'] > 0)
    C = C.merge(tested[['metric', 'lag', 'fdr_pass', 'screen_pass']],
                on=['metric', 'lag'], how='left')
    print(f'\n[stage 1] {m} testable cells; BH-FDR q=.05 pass: '
          f'{int(tested.fdr_pass.sum())}; + |r|>=.05 floor: '
          f'{int(tested.screen_pass.sum())}')
    print('\nper-cell screen (train partial r; * = FDR pass, ** = screen pass):')
    piv = C.pivot_table(index='metric', columns='lag', values='r')
    flag = C.pivot_table(index='metric', columns='lag', values='screen_pass',
                         aggfunc='first')
    fd = C.pivot_table(index='metric', columns='lag', values='fdr_pass',
                       aggfunc='first')
    order = list(METRICS) + list(COMPOSITES)
    for mname in order:
        row = []
        for L in LAGS:
            v = piv.loc[mname, L] if (mname in piv.index and L in piv.columns) else np.nan
            if pd.isna(v):
                row.append('   n/a  ')
                continue
            mark = '**' if flag.loc[mname, L] else ('* ' if fd.loc[mname, L] else '  ')
            row.append(f'{v:+.3f}{mark}')
        print(f'   {mname:<12} ' + '  '.join(row))

    # ---- STAGE 2: holdout gate for screen survivors ----
    surv = C[C['screen_pass'] == True]  # noqa: E712
    print(f'\n[stage 2] holdout gate on {len(surv)} survivors:')
    finalists = []
    for _, c in surv.iterrows():
        df = frames[c['lag']]
        ho = df[df['year'].isin(HOLDOUT)]
        cand = 'dz_' + c['metric']
        lvl = LEVEL_CTRL.get(c['metric'])
        ctrl = ([lvl] if lvl else []) + ['prior_fp_per_pa', 'pa_to']
        sub = ho.dropna(subset=[cand] + ctrl)
        r, p, n = partial_r(sub, cand, ctrl)
        ok = (not pd.isna(r)) and r >= 0.05
        print(f'   {c["metric"]:<12} lag{c["lag"]:>3}  train {c["r"]:+.3f}  '
              f'holdout {r:+.3f} (n={n})  -> {"ADVANCE" if ok else "DIES"}')
        if ok:
            finalists.append((c['metric'], c['lag']))

    # ---- STAGE 3: Rule 9 integration for holdout survivors ----
    print(f'\n[stage 3] Rule 9 integration ({len(finalists)} finalists), '
          f'baseline = ALL {len(RH3_FEATS)} RH3_FEATS:')
    for mname, L in finalists:
        df = frames[L].dropna(subset=RH3_FEATS + [TARGET, 'dz_' + mname])
        base = cross_year_r(df, RH3_FEATS)
        plus = cross_year_r(df, RH3_FEATS + ['dz_' + mname])
        verdict = 'PASS' if (plus - base) >= 0.005 else 'FAIL (<+0.005)'
        print(f'   {mname:<12} lag{L:>3}  base {base:+.4f} -> +cand {plus:+.4f}  '
              f'delta {plus - base:+.4f}  {verdict}  (n={len(df)})')
    if not finalists:
        print('   none — family closed at stage 2.')
    print('\ndone.')


if __name__ == '__main__':
    main()
