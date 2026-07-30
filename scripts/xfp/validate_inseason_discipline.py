"""Validate the in-season discipline composite against the FULL rh3 baseline.

Pre-registered: data/research/validation_runs/inseason_discipline_composite_2026-07-29.md

Candidate: z(-d_chase) + z(d_zswing) + z(d_bb) + z(-d_k), where d_* is
RECENT(~last 42d) minus EARLY(season-to-date at split_day-42), built purely
from counts at or before the cutoff (leakage-safe by construction).

Gates:
  (a) pooled partial r >= 0.10 vs obvious-prior baseline (same-metric levels
      + prior_fp_per_pa)
  (b) sign consistency >= 5/7 training years
  (c) holdout 2024-2025 partial r >= 0.05 same sign
  Integration (Rule 9): cross_year_r(RH3_FEATS+cand) - cross_year_r(RH3_FEATS)
      >= +0.005, baseline = ALL 22 production features
  Rule 8: per-split-day-band sign stability
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

from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from plv_clone.models.xfp.rh3 import (
    RH3_FEATS, TARGET, TRAIN_YEARS, EVAL_PA_MIN, ROS_PA_MIN,
)
from plv_clone.models.xfp.frames import build_rh3_frame

HOLDOUT = [2024, 2025]
TRAIN = [y for y in TRAIN_YEARS if y not in HOLDOUT]      # 2018,19,21,22,23
MIN_PITCH_E, MIN_PITCH_R = 300, 300
MIN_INZ_R, MIN_OUZ_R = 80, 80
LAG = 42

COUNT_COLS = ['pitches_to', 'pa_to', 'in_zone_to', 'swing_to', 'o_swing_to',
              'bb_to', 'k_to']


def attach_production_features(
    rolling: pd.DataFrame | None = None,
    multiyr: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """The real production substrate — all 22 RH3_FEATS, from the ONE assembly.

    Was a hand-maintained transcription of ``rh3.main()``'s feature attachment.
    Now delegates to ``plv_clone.models.xfp.frames.build_rh3_frame`` (migrated
    2026-07-29), which is the same code production runs and is pinned
    byte-identical to it by ``tests/test_xfp_frames.py``. Rule 9 wants the
    baseline to BE production's 22 features; a copy of production is a baseline
    that eventually silently isn't (docs/rh3_harness_root_bug_2026-07-28.md).

    ``rolling`` / ``multiyr`` stay in the signature because three sibling
    harnesses call this positionally with the raw CSVs already loaded
    (``validate_delta_grid``, ``validate_bat_speed_delta``,
    ``validate_lgbm_headroom``); they are forwarded through unchanged. Omit
    both and the assembly reads the production CSVs itself.
    """
    return build_rh3_frame(rolling=rolling, multiyr=multiyr, verbose=False).rolling


def build_candidate(rolling: pd.DataFrame) -> pd.DataFrame:
    """RECENT-minus-EARLY deltas from lagged season-to-date counts."""
    lag = rolling[['batter', 'year', 'split_day'] + COUNT_COLS].copy()
    lag['split_day'] = lag['split_day'] + LAG            # aligns t-42 onto t
    lag = lag.rename(columns={c: c.replace('_to', '_lag') for c in COUNT_COLS})
    df = rolling.merge(lag, on=['batter', 'year', 'split_day'], how='left')

    e_pitch = df['pitches_lag']
    for c in COUNT_COLS:
        df[c.replace('_to', '_rec')] = df[c] - df[c.replace('_to', '_lag')]

    df['ouz_lag'] = df['pitches_lag'] - df['in_zone_lag']
    df['ouz_rec'] = df['pitches_rec'] - df['in_zone_rec']

    def rates(sfx):
        chase = df[f'o_swing_{sfx}'] / df[f'ouz_{sfx}']
        zswing = (df[f'swing_{sfx}'] - df[f'o_swing_{sfx}']) / df[f'in_zone_{sfx}']
        bb = df[f'bb_{sfx}'] / df[f'pa_{sfx}']
        k = df[f'k_{sfx}'] / df[f'pa_{sfx}']
        return chase, zswing, bb, k

    ch_e, zs_e, bb_e, k_e = rates('lag')
    ch_r, zs_r, bb_r, k_r = rates('rec')
    df['d_chase'] = ch_r - ch_e
    df['d_zswing'] = zs_r - zs_e
    df['d_bb'] = bb_r - bb_e
    df['d_k'] = k_r - k_e

    ok = ((e_pitch >= MIN_PITCH_E) & (df['pitches_rec'] >= MIN_PITCH_R)
          & (df['in_zone_rec'] >= MIN_INZ_R) & (df['ouz_rec'] >= MIN_OUZ_R)
          & (df['pa_lag'] > 0) & (df['pa_rec'] > 0))
    df = df[ok & df[['d_chase', 'd_zswing', 'd_bb', 'd_k']].notna().all(axis=1)].copy()

    # z within (year, split_day) cell, signed so + = improvement
    def zin(col, sign):
        g = df.groupby(['year', 'split_day'])[col]
        return sign * (df[col] - g.transform('mean')) / g.transform('std')

    df['cand'] = (zin('d_chase', -1) + zin('d_zswing', +1)
                  + zin('d_bb', +1) + zin('d_k', -1)) / 4
    df = df[df['cand'].notna()]
    return df


def partial_r(df, cand_col, ctrl_cols, y_col):
    """r(resid(cand|ctrl), resid(y|ctrl))."""
    X = df[ctrl_cols].values
    lr1 = LinearRegression().fit(X, df[cand_col].values)
    lr2 = LinearRegression().fit(X, df[y_col].values)
    r1 = df[cand_col].values - lr1.predict(X)
    r2 = df[y_col].values - lr2.predict(X)
    if r1.std() < 1e-12 or r2.std() < 1e-12:
        return np.nan
    return float(np.corrcoef(r1, r2)[0, 1])


def make_pipe():
    return Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])


def cross_year_r(df, feats, years):
    """Production-style leave-one-year-out mean r (pooled per held year)."""
    rs = []
    for held in years:
        tr, te = df[df['year'] != held], df[df['year'] == held]
        if len(tr) < 200 or len(te) < 30:
            continue
        pipe = make_pipe()
        pipe.fit(tr[feats].values, tr[TARGET].values)
        p = pipe.predict(te[feats].values)
        rs.append((held, float(np.corrcoef(p, te[TARGET].values)[0, 1]), len(te)))
    return rs


def main():
    print('=== validate_inseason_discipline (pre-reg 2026-07-29) ===')
    rolling = attach_production_features()
    df = build_candidate(rolling)

    df = df.dropna(subset=RH3_FEATS + [TARGET])
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN)
            & (df['year'] != 2020) & (df['split_day'] >= 79)]
    print(f'frame: {len(df)} rows, years {sorted(df.year.unique())}, '
          f'splits {df.split_day.min()}-{df.split_day.max()}')
    print(df.groupby('year').size().to_string())

    # ---- Gate (a): pooled partial r vs obvious-prior controls (train yrs) ----
    ctrl = ['chase_pct_to_sh', 'k_pct_to_sh', 'bb_pct_to_sh', 'whiff_pct_to_sh',
            'prior_fp_per_pa', 'pa_to']
    tr = df[df['year'].isin(TRAIN)]
    pr = partial_r(tr, 'cand', ctrl, TARGET)
    print(f'\n[a] pooled partial r (train {TRAIN}, n={len(tr)}): {pr:+.4f}  '
          f'(bar >= +0.10)')

    # ---- Gate (b): per-year sign ----
    print('\n[b] per-year partial r:')
    signs = []
    for y in TRAIN + HOLDOUT:
        sub = df[df['year'] == y]
        if len(sub) < 30:
            print(f'   {y}: n={len(sub)} < 30, skipped')
            continue
        r = partial_r(sub, 'cand', ctrl, TARGET)
        signs.append((y, r, len(sub)))
        print(f'   {y}: {r:+.4f}  (n={len(sub)})')
    tr_signs = [r for y, r, n in signs if y in TRAIN]
    n_pos = sum(1 for r in tr_signs if r > 0)
    print(f'   train-year sign consistency: {n_pos}/{len(tr_signs)} positive')

    # ---- Gate (c): holdout ----
    ho = df[df['year'].isin(HOLDOUT)]
    pr_ho = partial_r(ho, 'cand', ctrl, TARGET)
    print(f'\n[c] holdout {HOLDOUT} partial r (n={len(ho)}): {pr_ho:+.4f}  '
          f'(bar >= +0.05 same sign)')

    # ---- Component diagnostics (NOT selected over) ----
    print('\n[diag] per-component partial r (train | holdout):')
    for comp, sign in [('d_chase', -1), ('d_zswing', +1), ('d_bb', +1), ('d_k', -1)]:
        tr2, ho2 = tr.copy(), ho.copy()
        tr2['c'] = sign * tr2[comp]
        ho2['c'] = sign * ho2[comp]
        print(f'   {comp:9s}: {partial_r(tr2, "c", ctrl, TARGET):+.4f} | '
              f'{partial_r(ho2, "c", ctrl, TARGET):+.4f}')

    # ---- Integration gate (Rule 9): full 22-feature baseline ----
    print(f'\n[Rule 9] cross-year r, baseline = ALL {len(RH3_FEATS)} RH3_FEATS:')
    yrs = [y for y in TRAIN_YEARS if y in df['year'].unique()]
    base = cross_year_r(df, RH3_FEATS, yrs)
    plus = cross_year_r(df, RH3_FEATS + ['cand'], yrs)
    b_mu = np.mean([r for _, r, _ in base])
    p_mu = np.mean([r for _, r, _ in plus])
    print('   year   base      +cand     delta')
    for (y, rb, n), (_, rp, _) in zip(base, plus):
        print(f'   {y}   {rb:+.4f}   {rp:+.4f}   {rp - rb:+.4f}   (n={n})')
    print(f'   MEAN   {b_mu:+.4f}   {p_mu:+.4f}   {p_mu - b_mu:+.4f}   '
          f'(strict bar >= +0.005)')

    # ---- Rule 8: split-day band stability ----
    print('\n[Rule 8] partial r by split-day band (train years):')
    for lo, hi in [(79, 107), (108, 142), (143, 191)]:
        sub = tr[(tr['split_day'] >= lo) & (tr['split_day'] <= hi)]
        if len(sub) < 100:
            continue
        print(f'   days {lo}-{hi}: {partial_r(sub, "cand", ctrl, TARGET):+.4f} '
              f'(n={len(sub)})')

    print('\ndone.')


if __name__ == '__main__':
    main()
