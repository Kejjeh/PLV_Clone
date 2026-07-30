"""ONE pre-registered cell: is there NONLINEAR headroom left in rh3?

Pre-registered: data/research/validation_runs/rh3_nonlinear_headroom_lgbm_2026-07-29.md

Cell N1 — swap the LEARNER only. LGBMRegressor with FIXED params (declared in
the prereg, no sweep, no inner CV) vs the production RidgeCV pipeline, on the
EXACT live 22 RH3_FEATS, same TARGET, same LOO-by-year folds, same
EVAL_PA_MIN / ROS_PA_MIN filters, IDENTICAL rows per fold (asserted).

Metric of record = MEAN of per-held-year r (validate_delta_grid convention).
Pooled concat r also reported (2026-07-10 learner_upgrade convention).
Pass/fail arithmetic delegated to lib/rule9.py::rule9_lift (unit-tested).

Also emits a descriptive 22-feature importance table (LGBM gain + split,
held-out-year permutation importance, Ridge standardized |coef|). That table
is EXPLORATORY — it may seed a future pre-registered pruning study; it does
NOT authorize dropping any feature.

Ships nothing. No production file is written or modified.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# Marker-based repo root — move-proof (docs/rh3_harness_root_bug_2026-07-28.md).
ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / 'pyproject.toml').is_file())
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp' / 'lib'))

from lightgbm import LGBMRegressor                                # noqa: E402
from sklearn.inspection import permutation_importance             # noqa: E402
from sklearn.linear_model import RidgeCV                          # noqa: E402
from sklearn.pipeline import Pipeline                             # noqa: E402
from sklearn.preprocessing import StandardScaler                  # noqa: E402

from plv_clone.models.xfp.rh3 import (                            # noqa: E402
    RH3_FEATS, TARGET, TRAIN_YEARS, EVAL_PA_MIN, ROS_PA_MIN,
    ROLLING_CSV, MULTIYR_CSV,
)
from rule9 import rule9_lift                                      # noqa: E402
from validate_inseason_discipline import attach_production_features  # noqa: E402

HOLDOUT = (2024, 2025)
MIN_TRAIN, MIN_TEST = 100, 30      # production cross_year_eval constants
OUT_JSON = (ROOT / 'data' / 'research' / 'validation_runs'
            / 'rh3_nonlinear_headroom_lgbm_2026-07-29_results.json')

# ---- THE DECLARED CELL: fixed params, frozen before the first fit ----------
LGBM_PARAMS = dict(
    n_estimators=400,
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=40,
    subsample=0.8,
    subsample_freq=1,       # without this LightGBM IGNORES subsample
    colsample_bytree=0.8,
    random_state=0,
    n_jobs=1,
    verbose=-1,
)


def ridge_factory():
    """Production learner, verbatim from engine.cross_year_eval_ridge."""
    return Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])


def lgbm_factory():
    return LGBMRegressor(**LGBM_PARAMS)


def build_frame() -> pd.DataFrame:
    """Real 22-feature production substrate (Rule 9), same path as
    validate_delta_grid.py."""
    for p in (ROLLING_CSV, MULTIYR_CSV):
        if not Path(p).exists():
            raise SystemExit(f'RULE 9: missing baseline input {p}')
    rolling = attach_production_features(pd.read_csv(ROLLING_CSV),
                                        pd.read_csv(MULTIYR_CSV))
    missing = [f for f in RH3_FEATS if f not in rolling.columns]
    if missing:
        raise SystemExit(f'RULE 9: baseline features absent from frame: {missing}')
    df = rolling.dropna(subset=list(RH3_FEATS) + [TARGET])
    df = df[(df['pa_to'] >= EVAL_PA_MIN)
            & (df['ros_pa'] >= ROS_PA_MIN)
            & (df['year'] != 2020)]
    return df.reset_index(drop=True)


def main() -> None:
    feats = list(RH3_FEATS)
    print('=== rh3 nonlinear headroom — ONE LightGBM cell (N1) ===')
    assert len(feats) == 22, (
        f'RH3_FEATS is {len(feats)}, expected 22 — production changed; '
        're-read the prereg before trusting this run.')
    print(f'RH3_FEATS: {len(feats)} (live import, asserted)')
    print(f'TARGET: {TARGET} | TRAIN_YEARS: {TRAIN_YEARS}')
    print(f'LGBM params: {LGBM_PARAMS}')

    df = build_frame()
    print(f'\nframe: {len(df)} rows | years {sorted(df.year.unique())}')

    per_year_ridge: dict = {}
    per_year_lgbm: dict = {}
    pooled = {'ridge': ([], []), 'lgbm': ([], [])}
    insample = {'ridge': [], 'lgbm': []}
    gains, splits, perms, coefs = [], [], [], []
    fold_n = {}

    for held in TRAIN_YEARS:
        train = df[df['year'] != held]
        test = df[df['year'] == held]
        if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
            print(f'  {held}: skipped (train={len(train)}, test={len(test)})')
            continue
        Xtr, ytr = train[feats].values, train[TARGET].values
        Xte, yte = test[feats].values, test[TARGET].values
        fold_n[held] = {'train': len(train), 'test': len(test)}

        out = {}
        for name, factory in (('ridge', ridge_factory), ('lgbm', lgbm_factory)):
            est = factory()
            est.fit(Xtr, ytr)
            pr = est.predict(Xte)
            r = float(np.corrcoef(pr, yte)[0, 1])
            mae = float(np.mean(np.abs(pr - yte)))
            r_in = float(np.corrcoef(est.predict(Xtr), ytr)[0, 1])
            out[name] = (est, r, mae, r_in)
            pooled[name][0].extend(pr.tolist())
            pooled[name][1].extend(yte.tolist())
            insample[name].append(r_in)

        # identical-rows guarantee (both arms saw the same fold)
        assert len(Xtr) == len(train) and len(Xte) == len(test)

        for name, store in (('ridge', per_year_ridge), ('lgbm', per_year_lgbm)):
            _, r, mae, _ = out[name]
            store[held] = {'r': round(r, 4), 'mae': round(mae, 6), 'n': len(test)}

        lg = out['lgbm'][0]
        gains.append(lg.booster_.feature_importance(importance_type='gain'))
        splits.append(lg.booster_.feature_importance(importance_type='split'))
        pi = permutation_importance(lg, Xte, yte, n_repeats=5,
                                    random_state=0,
                                    scoring='neg_mean_squared_error', n_jobs=1)
        perms.append(pi.importances_mean)
        rg = out['ridge'][0]
        coefs.append(np.abs(rg.named_steps['r'].coef_))

        print(f'  {held}: ridge r={out["ridge"][1]:+.4f}  '
              f'lgbm r={out["lgbm"][1]:+.4f}  '
              f'delta {out["lgbm"][1] - out["ridge"][1]:+.4f}  (n={len(test)})')

    def mean_r(store):
        return float(np.mean([v['r'] for v in store.values()]))

    def pooled_r(name):
        p, a = pooled[name]
        return float(np.corrcoef(p, a)[0, 1]), float(np.mean(np.abs(np.array(p) - np.array(a))))

    mr_ridge, mr_lgbm = mean_r(per_year_ridge), mean_r(per_year_lgbm)
    pr_ridge, mae_ridge = pooled_r('ridge')
    pr_lgbm, mae_lgbm = pooled_r('lgbm')

    res = rule9_lift(per_year_ridge, per_year_lgbm,
                     r_base=mr_ridge, r_full=mr_lgbm, holdout_years=HOLDOUT)

    print('\n--- HEADLINE (metric of record = mean per-year r) ---')
    print(f'  RidgeCV (production): mean r {mr_ridge:+.4f} | '
          f'pooled r {pr_ridge:+.4f} | pooled MAE {mae_ridge:.5f}')
    print(f'  LightGBM (fixed):     mean r {mr_lgbm:+.4f} | '
          f'pooled r {pr_lgbm:+.4f} | pooled MAE {mae_lgbm:.5f}')
    print(f'  LIFT (mean r): {res["lift"]:+.4f}   (bar >= +0.005)')
    print(f'  LIFT (pooled r): {pr_lgbm - pr_ridge:+.4f}')
    print(f'  sign consistency: {res["sign_match_years"]}/{res["n_total_years"]}'
          f'   (bar >= 5/7)')
    print(f'  holdout {HOLDOUT} mean lift: {res["holdout_lift"]:+.4f}   (bar > 0)')
    print(f'  per-year lift: {res["per_year_lift"]}')
    print(f'  pooled n: {len(pooled["ridge"][0])}')

    gate_effect = res['lift'] >= 0.005
    gate_sign = res['sign_match_years'] >= 5
    gate_hold = (res['holdout_lift'] or -1) > 0
    if gate_effect and gate_sign and gate_hold and res['lift'] >= 0.01:
        verdict = 'PASS'
    elif gate_effect and gate_sign and gate_hold:
        verdict = 'MARGINAL'
    else:
        verdict = 'REJECTED'
    print(f'\n  gates: effect={gate_effect} sign={gate_sign} holdout={gate_hold}')
    print(f'  VERDICT: {verdict}')

    print('\n--- overfit diagnostic (in-sample vs held-out mean r) ---')
    for name, mr in (('ridge', mr_ridge), ('lgbm', mr_lgbm)):
        ins = float(np.mean(insample[name]))
        print(f'  {name:<6} in-sample {ins:+.4f}  held-out {mr:+.4f}  '
              f'gap {ins - mr:+.4f}')

    print('\n--- DESCRIPTIVE feature importance (22 feats, mean over folds) ---')
    print('    (EXPLORATORY — does not authorize any RH3_FEATS change)')
    g = np.mean(gains, axis=0)
    imp = pd.DataFrame({
        'feature': feats,
        'lgbm_gain_pct': 100.0 * g / g.sum(),
        'lgbm_splits': np.mean(splits, axis=0),
        'perm_heldout_x1e5': 1e5 * np.mean(perms, axis=0),
        'ridge_abs_coef': np.mean(coefs, axis=0),
    }).sort_values('lgbm_gain_pct', ascending=False).reset_index(drop=True)
    imp.index = imp.index + 1
    with pd.option_context('display.width', 200,
                           'display.float_format', lambda v: f'{v:,.5f}'):
        print(imp.to_string())

    OUT_JSON.write_text(json.dumps({
        'signal': 'rh3_nonlinear_headroom_lgbm',
        'date': '2026-07-29',
        'cell': 'N1',
        'lgbm_params': LGBM_PARAMS,
        'n_feats': len(feats),
        'feats': feats,
        'target': TARGET,
        'frame_rows': int(len(df)),
        'pooled_n': len(pooled['ridge'][0]),
        'fold_n': fold_n,
        'per_year_ridge': per_year_ridge,
        'per_year_lgbm': per_year_lgbm,
        'mean_r_ridge': mr_ridge,
        'mean_r_lgbm': mr_lgbm,
        'pooled_r_ridge': pr_ridge,
        'pooled_r_lgbm': pr_lgbm,
        'pooled_mae_ridge': mae_ridge,
        'pooled_mae_lgbm': mae_lgbm,
        'rule9': res,
        'insample_mean_r': {k: float(np.mean(v)) for k, v in insample.items()},
        'importance': imp.to_dict(orient='records'),
        'gates': {'effect': bool(gate_effect), 'sign': bool(gate_sign),
                  'holdout': bool(gate_hold)},
        'verdict': verdict,
    }, indent=2), encoding='utf-8')
    print(f'\nwrote {OUT_JSON}')
    print('done.')


if __name__ == '__main__':
    main()
