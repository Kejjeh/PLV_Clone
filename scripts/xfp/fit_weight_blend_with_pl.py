"""fit_weight_blend_with_pl.py — Phase 3: add PL historical ranks to the
weight blend and measure incremental R^2 lift on top of the existing
prior-year-FP + archetype + trajectory + age stack.

Inputs:
  data/research/historical_panel/master_panel.parquet
  data/research/historical_panel/pl_rank_panel.parquet

Methodology mirrors fit_weight_blend.py:
  - LOYO (leave-one-year-out) CV on inner-join (master x pl_rank)
  - 2020 dropped from RP (existing rule); also dropped from H/SP lifts
  - Feature set = baseline + {pl_rank_mid_inv, pl_rank_early_inv,
    pl_rank_late_inv}. Inverse rank (1 / (rank + 5)) gives smooth
    response and handles missingness via mean-imputation per fold.
  - Compare R^2 vs WITHOUT-PL blend on the SAME rows (so the lift
    estimate isn't confounded by sample composition).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

ROOT = Path('c:/Users/Joshua/plv_clone')
PANEL = ROOT / 'data' / 'research' / 'historical_panel' / 'master_panel.parquet'
PL = ROOT / 'data' / 'research' / 'historical_panel' / 'pl_rank_panel.parquet'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_FEATS_COMMON = [
    'arche_overall_prior', 'arche_career_pct_prior',
    'traj_up_prior', 'traj_down_prior', 'traj_career_low_prior',
    'age_normalized',
]


def prep(df, ptype):
    if ptype == 'H':
        y_col = 'fp_per_pa'; anchor = 'prior_year_fp_per_pa'
    elif ptype == 'SP':
        y_col = 'fp_per_start'; anchor = 'prior_year_fp_per_start'
    else:
        y_col = 'fp_per_g'; anchor = 'prior_year_fp_per_g_rp'

    sub = df[df['player_type'] == ptype].copy()
    sub = sub[sub[y_col].notna() & sub[anchor].notna() & sub['arche_overall_prior'].notna()]
    if ptype == 'RP':
        sub = sub[(sub['year'] >= 2017) & (~sub['covid_short'])]
    else:
        sub = sub[~sub['covid_short']]
    sub['traj_up_prior'] = (sub['arche_traj_prior'] == 'TRENDING_UP').astype(int)
    sub['traj_down_prior'] = (sub['arche_traj_prior'] == 'TRENDING_DOWN').astype(int)
    sub['traj_career_low_prior'] = (sub['arche_traj_prior'] == 'CAREER_LOW').astype(int)
    sub['age_normalized'] = (sub['age'] - 28) / 5
    sub = sub.rename(columns={anchor: 'anchor_fp'})
    base_feats = ['anchor_fp'] + BASELINE_FEATS_COMMON
    sub = sub.dropna(subset=base_feats + [y_col])
    return sub, base_feats, y_col


def add_pl(sub, pl):
    m = sub.merge(pl, on=['mlbam_id', 'year'], how='inner')
    # Inverse-rank transform (smaller rank = better). NaN-safe.
    for c in ['pl_rank_early', 'pl_rank_mid', 'pl_rank_late']:
        m[f'{c}_inv'] = 1.0 / (m[c].astype(float) + 5.0)
    # Mean-impute missing inv per fit (done inside fold for cleanliness),
    # but we need the columns present.
    return m


def fold_fit(sub, feats, y_col):
    years = sorted(sub['year'].unique())
    preds, actual, fold_rows = [], [], []
    for held in years:
        tr = sub[sub['year'] != held]
        te = sub[sub['year'] == held]
        if len(tr) < 50 or len(te) < 5:
            continue
        # mean-impute features using train means (NaN-safe)
        means = tr[feats].mean().fillna(0.0)
        stds = tr[feats].std().fillna(1.0).replace(0, 1)
        Xtr = ((tr[feats].fillna(means) - means) / stds).fillna(0.0).values
        Xte = ((te[feats].fillna(means) - means) / stds).fillna(0.0).values
        ytr = tr[y_col].values; yte = te[y_col].values
        reg = LinearRegression().fit(Xtr, ytr)
        p = reg.predict(Xte)
        fold_rows.append({'year': held, 'n': len(te),
                          'r2_fold': r2_score(yte, p) if len(yte) > 1 else np.nan})
        preds.extend(p.tolist()); actual.extend(yte.tolist())
    return np.array(preds), np.array(actual), fold_rows


def drop_test(sub, feats, y_col, drop):
    reduced = [f for f in feats if f != drop]
    # Pooled OLS (in-sample R^2 reduction)
    Xfull = sub[feats].fillna(sub[feats].mean())
    Xred = sub[reduced].fillna(sub[reduced].mean())
    y = sub[y_col]
    r2_full = LinearRegression().fit(Xfull, y).score(Xfull, y)
    r2_red = LinearRegression().fit(Xred, y).score(Xred, y)
    return r2_full - r2_red


def evaluate(panel, pl, ptype):
    sub, base_feats, y_col = prep(panel, ptype)
    joined = add_pl(sub, pl)
    if len(joined) < 100:
        return {'ptype': ptype, 'error': f'n={len(joined)}'}

    pl_feats = ['pl_rank_early_inv', 'pl_rank_mid_inv', 'pl_rank_late_inv']
    full_feats = base_feats + pl_feats

    # Lift comparison on IDENTICAL rows
    pred_b, act_b, folds_b = fold_fit(joined, base_feats, y_col)
    pred_f, act_f, folds_f = fold_fit(joined, full_feats, y_col)
    # Pooled excluding 2020 (per memo)
    base_year = pd.Series([f['year'] for f in folds_b])
    # We need the year for each prediction — easier to recompute per-year r2:
    r2_b_pooled = r2_score(act_b, pred_b)
    r2_f_pooled = r2_score(act_f, pred_f)

    # Per-fold lifts
    fold_lifts = []
    for fb, ff in zip(folds_b, folds_f):
        fold_lifts.append({'year': fb['year'], 'n': fb['n'],
                           'r2_baseline': round(fb['r2_fold'], 4),
                           'r2_with_pl': round(ff['r2_fold'], 4),
                           'lift': round(ff['r2_fold'] - fb['r2_fold'], 4)})
    # Convergence excluding 2020
    nz = [f for f in fold_lifts if f['year'] != 2020]
    conv_pos = sum(1 for f in nz if f['lift'] > 0)

    # Drop test on each PL feature
    drops = {f: round(drop_test(joined, full_feats, y_col, f), 4) for f in pl_feats}
    # Also drop_test baseline anchor for comparison
    drops['anchor_fp'] = round(drop_test(joined, full_feats, y_col, 'anchor_fp'), 4)
    drops['arche_overall_prior'] = round(drop_test(joined, full_feats, y_col, 'arche_overall_prior'), 4)

    # Bootstrap CI on pooled lift (resample player-years 500x)
    rng = np.random.default_rng(42)
    n = len(act_b)
    lifts = []
    for _ in range(500):
        idx = rng.integers(0, n, n)
        lifts.append(r2_score(act_f[idx], pred_f[idx]) - r2_score(act_b[idx], pred_b[idx]))
    lift_ci = (float(np.percentile(lifts, 2.5)), float(np.percentile(lifts, 97.5)))

    return {
        'ptype': ptype,
        'n_joined': len(joined),
        'n_baseline_panel': len(sub),
        'join_rate': round(len(joined) / max(len(sub), 1), 3),
        'years': sorted(joined['year'].unique()),
        'pooled_r2_baseline': round(r2_b_pooled, 4),
        'pooled_r2_with_pl': round(r2_f_pooled, 4),
        'pooled_lift': round(r2_f_pooled - r2_b_pooled, 4),
        'lift_ci_95': [round(lift_ci[0], 4), round(lift_ci[1], 4)],
        'fold_lifts': fold_lifts,
        'convergence_ex2020': f'{conv_pos}/{len(nz)}',
        'drop_test': drops,
    }


def main():
    panel = pd.read_parquet(PANEL)
    pl = pd.read_parquet(PL)
    print(f'master panel: {len(panel):,}  pl panel: {len(pl):,}')

    results = []
    for ptype in ['H', 'SP', 'RP']:
        print(f'\n=== {ptype} ===')
        r = evaluate(panel, pl, ptype)
        if 'error' in r:
            print(' ', r['error']); continue
        print(f"  n_joined={r['n_joined']}  join_rate={r['join_rate']}")
        print(f"  R2 baseline = {r['pooled_r2_baseline']}  with_PL = {r['pooled_r2_with_pl']}")
        print(f"  lift = {r['pooled_lift']:+.4f}  CI95 {r['lift_ci_95']}")
        print(f"  convergence (ex-2020): {r['convergence_ex2020']}")
        print(f"  drop_test: {r['drop_test']}")
        results.append(r)

    out = OUT_DIR / 'weight_blend_with_pl_2026-06-04.json'
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f'\nwrote {out}')
    return results


if __name__ == '__main__':
    main()
