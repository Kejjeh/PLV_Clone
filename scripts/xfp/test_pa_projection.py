"""test_pa_projection.py — does a lineup-aware PA model beat naive pa_pace?

If lineup features improve PA projection specifically (not the rate side),
we can use a 2-stage architecture: RH3 rate × RH-PA1 volume = total FP.

This isolates the volume question from the rate question.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT / 'scripts/xfp'))
from xfp_rht1_pipeline import (build_prior_table, build_lineup_lag, compute_pop_means,
                                apply_shrinkage, SHRINK_SPEC_TO, TRAIN_YEARS,
                                EVAL_PA_MIN, ROS_PA_MIN, SEASON_DAYS, lineup_change_mask,
                                MULTIYR_CSV, ROLLING_CSV)

# PA-only target
PA_TARGET = 'ros_pa'

# Two PA models to compare:
# 1. NAIVE: ros_pa = pa_to * (SEASON_DAYS - split_day) / split_day
# 2. RIDGE: predict ros_pa from lineup + history features

PA_FEATS = [
    'pa_to', 'lineup_spot_to', 'started_pct_to', 'pa_per_started_game_to',
    'lineup_spot_lag1', 'started_pct_lag1', 'pa_lag1', 'split_day',
]


def naive_pa_loo(df):
    df = df.dropna(subset=['pa_to', 'split_day', 'ros_pa']).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    preds, acts, idx = [], [], []
    for held in TRAIN_YEARS:
        test = df[df['year'] == held]
        if len(test) < 30:
            continue
        pa_pace = test['pa_to'] / np.maximum(test['split_day'], 1)
        pred = pa_pace * np.maximum(SEASON_DAYS - test['split_day'], 0)
        preds.extend(pred.tolist()); acts.extend(test['ros_pa'].tolist())
        idx.extend(test.index.tolist())
    return np.array(preds), np.array(acts), np.array(idx)


def ridge_pa_loo(df):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=PA_FEATS + ['ros_pa']).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    preds, acts, idx = [], [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[PA_FEATS].values, train[PA_TARGET].values)
        p = pipe.predict(test[PA_FEATS].values)
        preds.extend(p.tolist()); acts.extend(test[PA_TARGET].tolist())
        idx.extend(test.index.tolist())
    return np.array(preds), np.array(acts), np.array(idx)


def metric(preds, acts, idx, mask=None):
    if mask is not None:
        keep = mask.reindex(idx).fillna(False).values
        preds = preds[keep]; acts = acts[keep]
        if len(preds) < 30: return None
    r = float(np.corrcoef(preds, acts)[0, 1])
    mae = float(np.mean(np.abs(preds - acts)))
    return {'r': round(r, 4), 'mae': round(mae, 1), 'n': len(preds)}


def main():
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    rolling['ros_total_fp'] = rolling['ros_pa'] * rolling['ros_full_fp_per_pa']

    # Set up features (mirror RH-T1 setup)
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff']    = rolling['prior_pa_eff'].fillna(0.0)
    lineup_lag = build_lineup_lag(rolling)
    rolling = rolling.merge(lineup_lag, left_on=['batter','year'],
                             right_on=['batter','year_target'], how='left').drop(columns=['year_target'], errors='ignore')
    pop_lineup_spot = float(rolling['lineup_spot_to'].mean())
    rolling['lineup_spot_lag1'] = rolling['lineup_spot_lag1'].fillna(pop_lineup_spot)
    rolling['started_pct_lag1'] = rolling['started_pct_lag1'].fillna(0.0)
    rolling['lineup_spot_to'] = rolling['lineup_spot_to'].fillna(pop_lineup_spot)
    rolling['started_pct_to'] = rolling['started_pct_to'].fillna(0.0)
    rolling['pa_per_started_game_to'] = rolling['pa_per_started_game_to'].fillna(rolling['pa_per_started_game_to'].mean())
    pa_lag = multiyr[['batter','year','pa']].rename(columns={'pa':'pa_lag1'})
    pa_lag['year_target'] = pa_lag['year'] + 1
    rolling = rolling.merge(pa_lag[['batter','year_target','pa_lag1']],
                             left_on=['batter','year'], right_on=['batter','year_target'],
                             how='left').drop(columns=['year_target'], errors='ignore')
    rolling['pa_lag1'] = rolling['pa_lag1'].fillna(rolling['pa_lag1'].mean())

    print('=== PA projection: naive vs lineup-aware Ridge ===\n')
    naive_p, naive_a, naive_idx = naive_pa_loo(rolling)
    ridge_p, ridge_a, ridge_idx = ridge_pa_loo(rolling)

    print(f'{"Approach":<22} {"r":<8} {"MAE":<7} {"n":<6}')
    print('-'*45)
    nm = metric(naive_p, naive_a, naive_idx)
    rm = metric(ridge_p, ridge_a, ridge_idx)
    print(f'{"NAIVE (pa_pace × days)":<22} {nm["r"]:<8} {nm["mae"]:<7} {nm["n"]:<6}')
    print(f'{"Ridge (lineup + lag)":<22} {rm["r"]:<8} {rm["mae"]:<7} {rm["n"]:<6}')
    print(f'\nΔ ridge - naive: r={rm["r"]-nm["r"]:+.4f}  MAE={rm["mae"]-nm["mae"]:+.1f}')

    lc_mask = lineup_change_mask(rolling)
    print(f'\n--- Lineup-change subset (n={lc_mask.sum()}) ---')
    nm_lc = metric(naive_p, naive_a, naive_idx, mask=lc_mask)
    rm_lc = metric(ridge_p, ridge_a, ridge_idx, mask=lc_mask)
    if nm_lc and rm_lc:
        print(f'{"NAIVE":<22} {nm_lc["r"]:<8} {nm_lc["mae"]:<7} {nm_lc["n"]:<6}')
        print(f'{"Ridge":<22} {rm_lc["r"]:<8} {rm_lc["mae"]:<7} {rm_lc["n"]:<6}')
        print(f'Δ on lineup-change: r={rm_lc["r"]-nm_lc["r"]:+.4f}  MAE={rm_lc["mae"]-nm_lc["mae"]:+.1f}')


if __name__ == '__main__':
    main()
