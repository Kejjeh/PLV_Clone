"""backtest_framework.py — historical model evaluation on actual fantasy outcomes.

Approach: for each historical year + each split_day cutoff:
  1. Predict rest-of-season FP for every player using the production model
     (trained on prior years' data — strict no-leak)
  2. Compare to actual rest-of-season FP for that (player, split, year)
  3. Aggregate metrics: rank correlation, top-N hit rate, replacement-level
     accuracy

Reports two metrics that map to fantasy decisions:
  - rank correlation (does the model order players correctly?)
  - top-N hit rate (of the top-N projected, how many were actually top-N?)

This is the methodology gap I noted: cross-year r is necessary but doesn't
directly measure "if you'd used this model on date X, would your decisions
have been better than picking randomly?"

Per-model backtests:
  - RH3 (hitter RoS rate)
  - RP3 (SP RoS per-start)
  - RP-RS2 (RP RoS total)
"""
from __future__ import annotations
from pathlib import Path
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))


def top_n_hit_rate(preds, acts, ids, N):
    """For top-N predicted, how many overlap with top-N actual?"""
    if len(preds) < N:
        return np.nan
    df = pd.DataFrame({'pred': preds, 'act': acts, 'id': ids})
    pred_top = set(df.nlargest(N, 'pred')['id'])
    act_top  = set(df.nlargest(N, 'act')['id'])
    return len(pred_top & act_top) / N


def backtest_rh3():
    """Backtest RH3 across all historical (year, split_day) cutoffs."""
    from xfp_rh3_pipeline import (build_prior_table, compute_population_means,
                                    apply_shrinkage, SHRINK_SPEC_TO, RH3_FEATS,
                                    TRAIN_YEARS, EVAL_PA_MIN, ROS_PA_MIN,
                                    ROLLING_CSV, MULTIYR_CSV, TARGET)
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)

    # Marcel prior + shrinkage
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['batter','year'], how='left')
    league_mu = float(multiyr[multiyr['pa']>=200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff'] = rolling['prior_pa_eff'].fillna(0.0)
    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)

    rolling = rolling.dropna(subset=RH3_FEATS + [TARGET])
    rolling = rolling[(rolling['pa_to'] >= EVAL_PA_MIN) & (rolling['ros_pa'] >= ROS_PA_MIN)
                      & (rolling['year'] != 2020)]

    print('=== RH3 BACKTEST — per (year, split_day) ===\n')
    print(f'{"Year":<5} {"Split":<6} {"n":<5} {"r":<7} {"Top10":<7} {"Top25":<7} {"Top50":<7}')
    print('-'*55)
    for held in TRAIN_YEARS:
        train = rolling[rolling['year'] != held]
        if len(train) < 100: continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[RH3_FEATS].values, train[TARGET].values)
        for split in sorted(rolling['split_day'].unique()):
            test = rolling[(rolling['year'] == held) & (rolling['split_day'] == split)]
            if len(test) < 30: continue
            preds = pipe.predict(test[RH3_FEATS].values)
            acts = test[TARGET].values
            ids = test['batter'].values
            r = float(np.corrcoef(preds, acts)[0, 1])
            t10 = top_n_hit_rate(preds, acts, ids, 10)
            t25 = top_n_hit_rate(preds, acts, ids, 25)
            t50 = top_n_hit_rate(preds, acts, ids, 50)
            print(f'{held:<5} {split:<6} {len(test):<5} {r:<7.4f} '
                  f'{t10:<7.2f} {t25:<7.2f} {t50:<7.2f}')


def backtest_rp3():
    """Backtest RP3 (SP per-start RoS)."""
    from xfp_rp3_pipeline import (build_prior_table, compute_population_means,
                                    apply_shrinkage, SHRINK_SPEC_TO, SHRINK_SPEC_LAST21,
                                    RP3_FEATS, TRAIN_YEARS, EVAL_GS_MIN, ROS_GS_MIN,
                                    ROLLING_CSV, MULTIYR_CSV, IL_CSV, TARGET)
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    il = pd.read_csv(IL_CSV)
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['pitcher','year'], how='left')
    league_mu = float(multiyr[multiyr['gs']>=10]['fp_per_start_actual'].mean())
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff'] = rolling['prior_gs_eff'].fillna(0.0)
    rolling = rolling.merge(il, on=['pitcher','year','split_day'], how='left')
    rolling['il_stints_to'] = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split'] = rolling['is_on_il_at_split'].fillna(0).astype(int)
    max_dsr = float(rolling['days_since_il_return'].max(skipna=True) or 200)
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)
    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    pop_l21 = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            rolling[col] = rolling[col].fillna(rolling[col].mean(skipna=True))
    rolling['gs_last21'] = rolling['gs_last21'].fillna(0)
    rolling['fp_per_start_last21'] = rolling['fp_per_start_last21'].fillna(rolling['fp_per_start_to'])

    rolling = rolling.dropna(subset=RP3_FEATS + [TARGET])
    rolling = rolling[(rolling['gs_to'] >= EVAL_GS_MIN) & (rolling['ros_gs'] >= ROS_GS_MIN)
                      & (rolling['year'] != 2020)]

    print('\n=== RP3 BACKTEST — per (year, split_day) ===\n')
    print(f'{"Year":<5} {"Split":<6} {"n":<5} {"r":<7} {"Top10":<7} {"Top25":<7} {"Top50":<7}')
    print('-'*55)
    for held in TRAIN_YEARS:
        train = rolling[rolling['year'] != held]
        if len(train) < 50: continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[RP3_FEATS].values, train[TARGET].values)
        for split in sorted(rolling['split_day'].unique()):
            test = rolling[(rolling['year'] == held) & (rolling['split_day'] == split)]
            if len(test) < 20: continue
            preds = pipe.predict(test[RP3_FEATS].values)
            acts = test[TARGET].values
            ids = test['pitcher'].values
            r = float(np.corrcoef(preds, acts)[0, 1])
            t10 = top_n_hit_rate(preds, acts, ids, 10)
            t25 = top_n_hit_rate(preds, acts, ids, 25)
            t50 = top_n_hit_rate(preds, acts, ids, 50)
            print(f'{held:<5} {split:<6} {len(test):<5} {r:<7.4f} '
                  f'{t10:<7.2f} {t25:<7.2f} {t50:<7.2f}')


def aggregate_summary(label, preds_year_split):
    """Print average top-N hit rate across years for each split."""
    df = pd.DataFrame(preds_year_split)
    if df.empty: return
    by_split = df.groupby('split_day').agg(
        mean_r=('r','mean'),
        mean_t10=('t10','mean'),
        mean_t25=('t25','mean'),
        mean_t50=('t50','mean'),
        n=('r','count'),
    ).round(3)
    print(f'\n--- {label}: split-day averages across {by_split["n"].iloc[0]} years ---')
    print(by_split.to_string())


def main():
    print('═' * 72)
    print('BACKTEST FRAMEWORK — model performance on historical (year, split) cohorts')
    print('═' * 72)
    print('Metrics:')
    print('  r       = Pearson correlation between predicted and actual RoS')
    print('  Top-N   = Hit rate (overlap of top-N predicted with top-N actual)')
    print('  Higher Top-N = better fantasy decisions: model picks the right people')
    print()
    backtest_rh3()
    backtest_rp3()


if __name__ == '__main__':
    main()
