"""
xfp_h7_pipeline.py — H7 gradient-boosting test on the expanded hitter pool.

Compendium §10.7 explicitly recommends tree models for talent projection.
H3-H6 established that linear Ridge + Statcast features hits a ceiling
around cross-year r ≈ 0.55. H7 tests whether XGBoost / LightGBM can find
non-linear interactions that push that ceiling.

Pool: H6 expanded (H2 features + Savant xwoba/xslg/xba/woba/slg/ba +
team_run_env_lag1 + bonus Statcast features that weren't in H2).

Decision gate: H7 ships if cross_year_r ≥ H2 + 0.01 AND |power_bias_hi| ≤ 1.0.
"""
from __future__ import annotations
import sys
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'

sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from xfp_h_eval import score_fn, fmt_result, TRAIN_MIN_PA, EVAL_MIN_PA, TRANSITIONS, power_bias_hi, team_context_bias
from xfp_h4_pipeline import add_team_run_env
from xfp_h6_pipeline import build_substrate_with_savant

H2_FEATS = [
    'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
    'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
    'sprint_speed', 'sb_per_pa',
]

# Expanded pool — everything that has signal
H7_POOL = list(set(H2_FEATS + [
    # Savant expected stats (H6)
    'sav_xwoba', 'sav_woba', 'sav_xslg', 'sav_slg', 'sav_xba', 'sav_ba',
    # Team environment (H4)
    'team_run_env_lag1',
    # Statcast contact-quality (H3)
    'xwoba_per_pa', 'xwoba_on_contact', 'barrel_pct', 'avg_ev', 'ev90',
    'c_plus_swstr', 'o_swing_pct', 'zone_pct',
    # H3 spray (kept even though they had low cross-year r — trees may find interactions)
    'pull_fb_pct', 'sweet_spot_pct',
]))


def cross_year_evaluate_model(df, feats, model_factory, label=''):
    """Same protocol as the linear cross_year_evaluate, but takes a model
    factory function returning a fresh sklearn-style estimator each transition.
    """
    preds_all, acts_all, res_rows = [], [], []
    for yr_train, yr_test in TRANSITIONS:
        train_pool = df[
            (df['year'] < yr_test) & (df['year'] != 2020)
            & (df['pa'] >= TRAIN_MIN_PA)
        ].dropna(subset=feats + ['fp_per_pa_actual'])
        if len(train_pool) < 50:
            continue
        train_year = df[(df['year'] == yr_train) & (df['pa'] >= TRAIN_MIN_PA)]
        test_year  = df[(df['year'] == yr_test ) & (df['pa'] >= EVAL_MIN_PA)]
        shared = set(train_year['batter']) & set(test_year['batter'])
        train_year = train_year[train_year['batter'].isin(shared)]
        test_year  = test_year [test_year ['batter'].isin(shared)].copy()

        test_meta = test_year[['batter','fp_per_pa_actual','hr_per_pa','team']].rename(
            columns={'hr_per_pa':'_hr_per_pa_test', 'team':'_team_test',
                     'fp_per_pa_actual':'_fp_per_pa_actual_test'})
        merged = test_meta.merge(train_year[['batter'] + feats], on='batter', how='inner') \
                          .dropna(subset=feats + ['_fp_per_pa_actual_test'])
        if len(merged) < 10:
            continue

        model = model_factory()
        model.fit(train_pool[feats].values, train_pool['fp_per_pa_actual'].values)
        merged['pred'] = model.predict(merged[feats].values)
        merged['transition'] = f'{yr_train}->{yr_test}'
        preds_all.extend(merged['pred'].tolist())
        acts_all.extend(merged['_fp_per_pa_actual_test'].tolist())
        res_rows.append(merged)

    if not res_rows:
        return {'r': np.nan, 'n': 0, 'label': label}
    res = pd.concat(res_rows, ignore_index=True)
    res['resid'] = res['pred'] - res['_fp_per_pa_actual_test']
    r = float(np.corrcoef(preds_all, acts_all)[0, 1])
    return {
        'r': round(r, 5),
        'power_bias_hi':     round(power_bias_hi(res), 4),
        'team_context_bias': round(team_context_bias(res), 4),
        'rmse': round(float(np.sqrt(np.mean(res['resid']**2))), 4),
        'mae':  round(float(np.mean(res['resid'].abs())), 4),
        'n':    len(res),
        'n_transitions': res['transition'].nunique(),
        'label': label,
    }


def make_ridge():
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    return Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])


def make_xgb(max_depth=4, n_est=400, lr=0.04, subsample=0.85, colsample=0.85, reg_lambda=1.0):
    import xgboost as xgb
    return xgb.XGBRegressor(
        n_estimators=n_est, max_depth=max_depth, learning_rate=lr,
        subsample=subsample, colsample_bytree=colsample,
        reg_lambda=reg_lambda, random_state=42, verbosity=0,
        tree_method='hist',
    )


def make_lgbm(num_leaves=31, n_est=600, lr=0.04, min_child=20):
    import lightgbm as lgb
    return lgb.LGBMRegressor(
        n_estimators=n_est, num_leaves=num_leaves, learning_rate=lr,
        min_child_samples=min_child, subsample=0.85, colsample_bytree=0.85,
        random_state=42, verbosity=-1,
    )


def main():
    print('=== H7 — gradient boosting test ===\n')
    print('Building substrate with Savant + team_env...')
    df = build_substrate_with_savant()
    df = add_team_run_env(df)

    # Filter to features actually present (some may be missing from older years)
    feats_avail = [f for f in H7_POOL if f in df.columns]
    print(f'Pool size: {len(feats_avail)} features\n')

    df_pool = df.dropna(subset=feats_avail + ['fp_per_pa_actual']).copy()
    print(f'Rows after dropna: {len(df_pool)}')
    print(f'  ≥{TRAIN_MIN_PA} PA: {(df_pool["pa"] >= TRAIN_MIN_PA).sum()}')
    print(f'  ≥{EVAL_MIN_PA} PA: {(df_pool["pa"] >= EVAL_MIN_PA).sum()}\n')

    # Reference: H2 (Ridge on H2_FEATS) — native sample (no Savant restriction)
    print('--- Reference 1: H2 (Ridge, 13 features) on NATIVE sample ---')
    res_h2_native = cross_year_evaluate_model(df.dropna(subset=H2_FEATS + ['fp_per_pa_actual']),
                                                H2_FEATS, make_ridge, label='H2 Ridge (native)')
    s_h2_native = score_fn(res_h2_native['r'], res_h2_native['power_bias_hi'])
    print(f'  r={res_h2_native["r"]}  n={res_h2_native["n"]}  score={s_h2_native:.4f}\n')

    # Reference 2: H2 Ridge on the H7 (smaller) sample — apples-to-apples
    print('--- Reference 2: H2 (Ridge, 13 features) on H7 sample (apples-to-apples) ---')
    res_h2 = cross_year_evaluate_model(df_pool, H2_FEATS, make_ridge, label='H2 Ridge (H7 sample)')
    s_h2 = score_fn(res_h2['r'], res_h2['power_bias_hi'])
    print(f'  r={res_h2["r"]}  n={res_h2["n"]}  pwr_bias={res_h2["power_bias_hi"]:+.3f}  '
          f'team_bias={res_h2["team_context_bias"]:+.3f}  mae={res_h2["mae"]:.4f}  score={s_h2:.4f}\n')

    # Ridge on the expanded H7 pool (control — same model, more features)
    print('--- Ridge on expanded H7 pool (same sample) ---')
    res_ridge_expanded = cross_year_evaluate_model(df_pool, feats_avail, make_ridge, label='Ridge (expanded)')
    s_ridge_exp = score_fn(res_ridge_expanded['r'], res_ridge_expanded['power_bias_hi'])
    print(f'  r={res_ridge_expanded["r"]}  pwr_bias={res_ridge_expanded["power_bias_hi"]:+.3f}  '
          f'team_bias={res_ridge_expanded["team_context_bias"]:+.3f}  mae={res_ridge_expanded["mae"]:.4f}  '
          f'score={s_ridge_exp:.4f}  Δscore={s_ridge_exp-s_h2:+.4f}\n')

    # XGBoost — small grid
    print('--- XGBoost — small grid ---')
    xgb_results = []
    for max_depth in [3, 4, 5, 6]:
        for n_est in [300, 600]:
            for lr in [0.03, 0.05]:
                fac = lambda md=max_depth, ne=n_est, lr=lr: make_xgb(md, ne, lr)
                r = cross_year_evaluate_model(df_pool, feats_avail, fac,
                                                label=f'XGB d{max_depth} n{n_est} lr{lr}')
                s = score_fn(r['r'], r['power_bias_hi'])
                xgb_results.append((max_depth, n_est, lr, r, s))
                print(f'  d={max_depth} n={n_est} lr={lr}  r={r["r"]:.4f}  pwr_bias={r["power_bias_hi"]:+.3f}  '
                      f'mae={r["mae"]:.4f}  score={s:.4f}  Δ={s-s_h2:+.4f}')
    xgb_results.sort(key=lambda x: -x[4])
    best_xgb = xgb_results[0]
    print(f'\n  Best XGB: depth={best_xgb[0]} n_est={best_xgb[1]} lr={best_xgb[2]}  '
          f'r={best_xgb[3]["r"]}  score={best_xgb[4]:.4f}')
    print(f'  Top-3 XGB:')
    for md, ne, lr, r, s in xgb_results[:3]:
        print(f'    d={md} n={ne} lr={lr}  r={r["r"]:.4f}  score={s:.4f}')
    print()

    # LightGBM — small grid
    print('--- LightGBM — small grid ---')
    lgb_results = []
    for num_leaves in [15, 31, 63]:
        for n_est in [400, 800]:
            for lr in [0.03, 0.05]:
                fac = lambda nl=num_leaves, ne=n_est, lr=lr: make_lgbm(nl, ne, lr)
                r = cross_year_evaluate_model(df_pool, feats_avail, fac,
                                                label=f'LGBM lv{num_leaves} n{n_est} lr{lr}')
                s = score_fn(r['r'], r['power_bias_hi'])
                lgb_results.append((num_leaves, n_est, lr, r, s))
                print(f'  lv={num_leaves} n={n_est} lr={lr}  r={r["r"]:.4f}  pwr_bias={r["power_bias_hi"]:+.3f}  '
                      f'mae={r["mae"]:.4f}  score={s:.4f}  Δ={s-s_h2:+.4f}')
    lgb_results.sort(key=lambda x: -x[4])
    best_lgb = lgb_results[0]
    print(f'\n  Best LGBM: leaves={best_lgb[0]} n_est={best_lgb[1]} lr={best_lgb[2]}  '
          f'r={best_lgb[3]["r"]}  score={best_lgb[4]:.4f}')
    print()

    # Summary — apples-to-apples on the same sample (H7 pool dropna)
    print('=== Summary (apples-to-apples on H7-pool sample) ===')
    print(f'  H2 native (13 feats, larger sample):  r={res_h2_native["r"]:.4f}  n={res_h2_native["n"]}  score={s_h2_native:.4f}')
    print(f'  H2 on H7 sample (13 feats):           r={res_h2["r"]:.4f}  n={res_h2["n"]}  score={s_h2:.4f}')
    print(f'  Ridge expanded ({len(feats_avail)} feats):           r={res_ridge_expanded["r"]:.4f}  score={s_ridge_exp:.4f}  Δ={s_ridge_exp-s_h2:+.4f}')
    print(f'  Best XGBoost:                          r={best_xgb[3]["r"]:.4f}  score={best_xgb[4]:.4f}  Δ={best_xgb[4]-s_h2:+.4f}')
    print(f'  Best LightGBM:                         r={best_lgb[3]["r"]:.4f}  score={best_lgb[4]:.4f}  Δ={best_lgb[4]-s_h2:+.4f}')

    print()
    print('=== Decision gate (best gradient-boosting result) ===')
    best_gbdt = best_xgb if best_xgb[4] > best_lgb[4] else best_lgb
    best_gbdt_label = 'XGBoost' if best_xgb[4] > best_lgb[4] else 'LightGBM'
    target_r = res_h2['r'] + 0.01
    print(f'  Best model: {best_gbdt_label}')
    print(f'  cross_year_r {best_gbdt[3]["r"]:.4f} ≥ H2 + 0.01 = {target_r:.4f}? '
          f'{"PASS" if best_gbdt[3]["r"] >= target_r else "FAIL"}')
    print(f'  |power_bias_hi| {abs(best_gbdt[3]["power_bias_hi"]):.4f} ≤ 1.0? '
          f'{"PASS" if abs(best_gbdt[3]["power_bias_hi"]) <= 1.0 else "FAIL"}')
    print(f'  Score {best_gbdt[4]:.4f} > H2 {s_h2:.4f}? {"PASS" if best_gbdt[4] > s_h2 else "FAIL"}')


if __name__ == '__main__':
    main()
