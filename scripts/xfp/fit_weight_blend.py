"""fit_weight_blend.py — Phase 2: fit a constrained nonneg weighted blend of all
independent predictors against historical actual FP, with multi-test gates.

Inputs:
  data/research/historical_panel/master_panel.parquet  (built by agent B)

For each player_type in {H, SP, RP}:
  1. Build feature matrix from prior_year_fp + arche_overall + arche_overall_prior +
     arche_career_pct + traj_up/down indicators + age
  2. Outcome = same-year fp_per_pa (H) / fp_per_start (SP) / fp_per_g (RP)
  3. Filter to complete cases (no rookies, no covid for RP)
  4. Fit NNLS weighted blend on year-folded CV (leave-one-year-out)
  5. Compare blend R^2 to baseline (prior-year-FP alone) per Rule 3 magnitude gate
  6. Per-feature partial contribution
  7. Multi-year stability (Rule 8 convergence)
  8. Report

Writes results to:
  data/research/validation_runs/weight_blend_<ptype>_2026-06-04.md
"""
from __future__ import annotations

import sys, json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from sklearn.metrics import r2_score
from sklearn.linear_model import LinearRegression

ROOT = Path('c:/Users/Joshua/plv_clone')
PANEL = ROOT / 'data' / 'research' / 'historical_panel' / 'master_panel.parquet'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'
OUT_DIR.mkdir(parents=True, exist_ok=True)


def build_features(df, ptype):
    if ptype == 'H':
        y_col = 'fp_per_pa'
        anchor_col = 'prior_year_fp_per_pa'
    elif ptype == 'SP':
        y_col = 'fp_per_start'
        anchor_col = 'prior_year_fp_per_start'
    else:  # RP
        y_col = 'fp_per_g'
        anchor_col = 'prior_year_fp_per_g_rp'

    sub = df[df['player_type'] == ptype].copy()

    # Filter: complete cases
    sub = sub[sub[y_col].notna() & sub[anchor_col].notna() & sub['arche_overall_prior'].notna()]
    if ptype == 'RP':
        # exclude pre-2017 (missing SV/HLD) and covid
        sub = sub[(sub['year'] >= 2017) & (~sub['covid_short'])]
    else:
        sub = sub[~sub['covid_short']]

    # Build features (all on the prior-year side except current-year archetype which is observable mid-season)
    sub['traj_up_prior'] = (sub['arche_traj_prior'] == 'TRENDING_UP').astype(int)
    sub['traj_down_prior'] = (sub['arche_traj_prior'] == 'TRENDING_DOWN').astype(int)
    sub['traj_career_low_prior'] = (sub['arche_traj_prior'] == 'CAREER_LOW').astype(int)
    sub['age_normalized'] = (sub['age'] - 28) / 5  # centered at 28

    features = [
        anchor_col,            # F1: historical baseline (the rh3/rp3 anchor)
        'arche_overall_prior', # F2: 20-80 archetype scoring (prior year)
        'arche_career_pct_prior',  # F3: where last year sat in career %ile
        'traj_up_prior',       # F4: TRENDING_UP at end of last year
        'traj_down_prior',     # F5: TRENDING_DOWN
        'traj_career_low_prior',  # F6: CAREER_LOW
        'age_normalized',      # F7: age (controlled for centering)
    ]

    sub = sub.dropna(subset=features + [y_col])
    return sub, features, y_col


def fit_loyo(sub, features, y_col):
    """Leave-one-year-out cross-validation. Fit each fold's NNLS weights on
    train, predict held-out year. Aggregate predictions."""
    years = sorted(sub['year'].unique())
    fold_results = []
    all_preds = []
    all_actual = []

    for held in years:
        train = sub[sub['year'] != held]
        test = sub[sub['year'] == held]

        # Standardize features per-fold (so weights are comparable)
        train_means = train[features].mean()
        train_stds = train[features].std().replace(0, 1)
        Xtr = ((train[features] - train_means) / train_stds).values
        Xte = ((test[features] - train_means) / train_stds).values
        ytr = train[y_col].values
        yte = test[y_col].values

        # Add intercept by appending column of ones
        Xtr_aug = np.column_stack([Xtr, np.ones(len(Xtr))])
        Xte_aug = np.column_stack([Xte, np.ones(len(Xte))])

        # OLS first (unconstrained)
        reg = LinearRegression(fit_intercept=False)
        reg.fit(Xtr_aug, ytr)
        pred_ols = reg.predict(Xte_aug)

        # Fair baseline: OLS fit on anchor alone (intercept + slope), trained on same train set
        anchor_train = train[[features[0]]].values
        anchor_test = test[[features[0]]].values
        anchor_reg = LinearRegression().fit(anchor_train, ytr)
        baseline_pred = anchor_reg.predict(anchor_test)

        r2_blend = r2_score(yte, pred_ols)
        r2_anchor = r2_score(yte, baseline_pred)
        n = len(test)

        fold_results.append({
            'held_year': held, 'n': n,
            'r2_blend': r2_blend, 'r2_anchor': r2_anchor, 'lift': r2_blend - r2_anchor,
            'weights': reg.coef_.tolist(),
        })
        all_preds.extend(pred_ols.tolist())
        all_actual.extend(yte.tolist())

    return fold_results, np.array(all_preds), np.array(all_actual)


def per_feature_contribution(sub, features, y_col):
    """Drop each feature, refit, measure R² drop."""
    full_r2 = LinearRegression().fit(sub[features], sub[y_col]).score(sub[features], sub[y_col])
    contributions = {}
    for f in features:
        reduced = [x for x in features if x != f]
        r2 = LinearRegression().fit(sub[reduced], sub[y_col]).score(sub[reduced], sub[y_col])
        contributions[f] = round(full_r2 - r2, 4)
    return contributions, full_r2


def fit_and_report(panel, ptype):
    sub, features, y_col = build_features(panel, ptype)
    if len(sub) < 100:
        return {'ptype': ptype, 'error': f'insufficient n ({len(sub)})'}

    fold_results, preds, actual = fit_loyo(sub, features, y_col)
    pooled_r2_blend = r2_score(actual, preds)
    # Fair anchor baseline: pooled OLS with intercept on the anchor alone
    anchor_X = sub[[features[0]]].values
    anchor_y = sub[y_col].values
    anchor_reg = LinearRegression().fit(anchor_X, anchor_y)
    anchor_preds = anchor_reg.predict(anchor_X)
    pooled_r2_anchor = r2_score(anchor_y, anchor_preds)
    pooled_lift = pooled_r2_blend - pooled_r2_anchor

    contributions, full_r2 = per_feature_contribution(sub, features, y_col)

    # Final unfolded weights (for production use)
    reg_final = LinearRegression().fit(
        (sub[features] - sub[features].mean()) / sub[features].std().replace(0, 1),
        sub[y_col]
    )
    final_weights = dict(zip(features, reg_final.coef_.round(4)))

    # Year-by-year lift (Rule 8 convergence)
    convergence_pass = sum(1 for f in fold_results if f['lift'] > 0)
    n_folds = len(fold_results)

    return {
        'ptype': ptype,
        'n_obs': len(sub),
        'years': sorted(sub['year'].unique()),
        'features': features,
        'pooled_r2_blend': round(pooled_r2_blend, 4),
        'pooled_r2_anchor': round(pooled_r2_anchor, 4),
        'pooled_lift_r2': round(pooled_lift, 4),
        'per_feature_contribution': contributions,
        'final_weights_z_standardized': final_weights,
        'convergence_pass_folds': f'{convergence_pass}/{n_folds}',
        'fold_lifts': [(f['held_year'], round(f['lift'], 4)) for f in fold_results],
    }


def main():
    print('Loading master panel...')
    panel = pd.read_parquet(PANEL)
    print(f'  {len(panel):,} total rows')

    results = []
    for ptype in ['H', 'SP', 'RP']:
        print(f'\n=== Fitting {ptype} ===')
        r = fit_and_report(panel, ptype)
        if 'error' in r:
            print(f'  ERROR: {r["error"]}')
            continue
        print(f'  n={r["n_obs"]:,}  years={r["years"]}')
        print(f'  pooled R² blend = {r["pooled_r2_blend"]:.4f}')
        print(f'  pooled R² anchor-only = {r["pooled_r2_anchor"]:.4f}')
        print(f'  lift = {r["pooled_lift_r2"]:+.4f}')
        print(f'  convergence: {r["convergence_pass_folds"]} folds with positive lift')
        print(f'  per-feature contribution (R² drop if removed):')
        for f, c in sorted(r['per_feature_contribution'].items(), key=lambda x: -x[1]):
            print(f'    {f:35s}  {c:+.4f}')
        print(f'  final standardized weights:')
        for f, w in r['final_weights_z_standardized'].items():
            print(f'    {f:35s}  {w:+.4f}')
        results.append(r)

    # Save full report
    out = OUT_DIR / 'weight_blend_2026-06-04.json'
    with open(out, 'w') as fp:
        json.dump(results, fp, indent=2, default=str)
    print(f'\nWrote {out}')


if __name__ == '__main__':
    main()
