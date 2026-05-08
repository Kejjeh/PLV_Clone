"""test_two_stage_total.py — RH3 rate x Ridge PA vs RH3 rate x naive PA, on TOTAL FP."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT / 'scripts/xfp'))
from xfp_rht1_pipeline import (build_prior_table, build_lineup_lag, compute_pop_means,
                                apply_shrinkage, SHRINK_SPEC_TO, TRAIN_YEARS,
                                EVAL_PA_MIN, ROS_PA_MIN, SEASON_DAYS, lineup_change_mask,
                                MULTIYR_CSV, ROLLING_CSV, RH3_RATE_FEATS)

PA_FEATS = [
    'pa_to', 'lineup_spot_to', 'started_pct_to', 'pa_per_started_game_to',
    'lineup_spot_lag1', 'started_pct_lag1', 'pa_lag1', 'split_day',
]


def loo_combined(df, feats_rate, feats_pa=None, naive_pa=False):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.copy()
    df['ros_total_fp'] = df['ros_pa'] * df['ros_full_fp_per_pa']
    cols_needed = feats_rate + (feats_pa if feats_pa else []) + ['ros_full_fp_per_pa', 'ros_pa', 'ros_total_fp']
    df = df.dropna(subset=cols_needed)
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    preds, acts, idx = [], [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30: continue
        rate_pipe = Pipeline([('sc', StandardScaler()),
                              ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        rate_pipe.fit(train[feats_rate].values, train['ros_full_fp_per_pa'].values)
        rate_pred = rate_pipe.predict(test[feats_rate].values)
        if naive_pa:
            pa_pace = test['pa_to'].values / np.maximum(test['split_day'].values, 1)
            pa_pred = pa_pace * np.maximum(SEASON_DAYS - test['split_day'].values, 0)
        else:
            pa_pipe = Pipeline([('sc', StandardScaler()),
                                ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pa_pipe.fit(train[feats_pa].values, train['ros_pa'].values)
            pa_pred = pa_pipe.predict(test[feats_pa].values)
        total_pred = rate_pred * pa_pred
        preds.extend(total_pred.tolist()); acts.extend(test['ros_total_fp'].tolist())
        idx.extend(test.index.tolist())
    return np.array(preds), np.array(acts), np.array(idx)


def metric(p, a, idx, mask=None):
    if mask is not None:
        keep = mask.reindex(idx).fillna(False).values
        p = p[keep]; a = a[keep]
    if len(p) < 30: return None
    r = float(np.corrcoef(p, a)[0,1])
    mae = float(np.mean(np.abs(p-a)))
    return {'r': round(r,4), 'mae': round(mae,1), 'n': len(p)}


def main():
    rolling = pd.read_csv(ROLLING_CSV); multiyr = pd.read_csv(MULTIYR_CSV)
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['batter','year'], how='left')
    league_mu = float(multiyr[multiyr['pa']>=200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff'] = rolling['prior_pa_eff'].fillna(0.0)
    ll = build_lineup_lag(rolling)
    rolling = rolling.merge(ll, left_on=['batter','year'], right_on=['batter','year_target'], how='left').drop(columns=['year_target'], errors='ignore')
    pop_lineup = float(rolling['lineup_spot_to'].mean())
    rolling['lineup_spot_lag1'] = rolling['lineup_spot_lag1'].fillna(pop_lineup)
    rolling['started_pct_lag1'] = rolling['started_pct_lag1'].fillna(0.0)
    rolling['lineup_spot_to'] = rolling['lineup_spot_to'].fillna(pop_lineup)
    rolling['started_pct_to'] = rolling['started_pct_to'].fillna(0.0)
    rolling['pa_per_started_game_to'] = rolling['pa_per_started_game_to'].fillna(rolling['pa_per_started_game_to'].mean())
    pa_lag = multiyr[['batter','year','pa']].rename(columns={'pa':'pa_lag1'}); pa_lag['year_target']=pa_lag['year']+1
    rolling = rolling.merge(pa_lag[['batter','year_target','pa_lag1']], left_on=['batter','year'],
                             right_on=['batter','year_target'], how='left').drop(columns=['year_target'], errors='ignore')
    rolling['pa_lag1'] = rolling['pa_lag1'].fillna(rolling['pa_lag1'].mean())
    pop_to = compute_pop_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)

    p1, a1, i1 = loo_combined(rolling, RH3_RATE_FEATS, naive_pa=True)
    p2, a2, i2 = loo_combined(rolling, RH3_RATE_FEATS, feats_pa=PA_FEATS, naive_pa=False)
    m1 = metric(p1, a1, i1); m2 = metric(p2, a2, i2)
    print('=== Total FP: rate x naive_PA vs rate x ridge_PA ===\n')
    print(f'{"Approach":<28} {"r":<8} {"MAE":<7} {"n":<6}')
    print('-'*55)
    print(f'{"RH3 rate x NAIVE PA":<28} {m1["r"]:<8} {m1["mae"]:<7} {m1["n"]:<6}')
    print(f'{"RH3 rate x RIDGE PA":<28} {m2["r"]:<8} {m2["mae"]:<7} {m2["n"]:<6}')
    print(f'Delta = r:{m2["r"]-m1["r"]:+.4f}  MAE:{m2["mae"]-m1["mae"]:+.1f}')

    lc = lineup_change_mask(rolling)
    m1_lc = metric(p1, a1, i1, lc); m2_lc = metric(p2, a2, i2, lc)
    print(f'\n--- Lineup-change subset ---')
    print(f'{"RH3 x NAIVE":<28} {m1_lc["r"]:<8} {m1_lc["mae"]:<7} {m1_lc["n"]:<6}')
    print(f'{"RH3 x RIDGE PA":<28} {m2_lc["r"]:<8} {m2_lc["mae"]:<7} {m2_lc["n"]:<6}')
    print(f'Delta = r:{m2_lc["r"]-m1_lc["r"]:+.4f}  MAE:{m2_lc["mae"]-m1_lc["mae"]:+.1f}')


if __name__ == '__main__':
    main()
