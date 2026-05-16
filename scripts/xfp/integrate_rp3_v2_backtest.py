"""integrate_rp3_v2_backtest.py — SP drift integration backtest.

Add 6 within-season drift features (last_21_day_rate − cumulative_to_date_rate)
to the rp3 SP model. Backtest cross-year r.

Drift features added (from H1 validation):
  delta_velo, delta_swstr, delta_k_pct, delta_bb_pct, delta_chase, delta_zone

Bar: r gain ≥ +0.005 to promote.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

ROLLING_CSV = CACHE / 'rolling_pitchers_2018_2026.csv'
SP_MULTIYR = CACHE / 'sp_multiyr_2015_2025.csv'

TARGET = 'ros_fp_per_start'
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]

RP3_V1_FEATS = [
    'k_pct_to_sh', 'bb_pct_to_sh', 'swstr_pct_to_sh', 'c_plus_swstr_to_sh',
    'xwoba_per_pa_to_sh', 'zone_pct_to_sh',
    'z_swing_pct_to_sh', 'o_swing_pct_to_sh',
    'avg_velo_to',
    'fp_per_start_to', 'gs_to',
    'prior_fp_per_start',
    'split_day',
]
DRIFT_FEATS = ['delta_velo', 'delta_swstr', 'delta_k_pct', 'delta_bb_pct',
                'delta_chase', 'delta_zone']
RP3_V2_FEATS = RP3_V1_FEATS + DRIFT_FEATS

SHRINK_SPEC_TO = {
    'k_pct_to':       ('tbf_to',     70),
    'bb_pct_to':      ('tbf_to',    170),
    'swstr_pct_to':   ('pitches_to', 300),
    'c_plus_swstr_to':('pitches_to', 300),
    'xwoba_per_pa_to':('tbf_to',    250),
    'zone_pct_to':    ('pitches_to', 300),
    'z_swing_pct_to': ('in_zone_to', 200),
    'o_swing_pct_to': ('pitches_to', 300),
}


def main():
    print('Loading rolling pitchers substrate...')
    df = pd.read_csv(ROLLING_CSV)
    print(f'  {len(df)} rows')

    # Build drift features (last_21 - cumulative_to_date)
    df['delta_velo'] = df['avg_velo_last21'] - df['avg_velo_to']
    df['delta_swstr'] = df['swstr_pct_last21'] - df['swstr_pct_to']
    df['delta_k_pct'] = df['k_pct_last21'] - df['k_pct_to']
    df['delta_bb_pct'] = df['bb_pct_last21'] - df['bb_pct_to']
    df['delta_chase'] = df['o_swing_pct_last21'] - df['o_swing_pct_to']
    df['delta_zone'] = df['zone_pct_last21'] - df['zone_pct_to']

    for col in DRIFT_FEATS:
        print(f'  {col}: {df[col].notna().sum()}/{len(df)} non-null')

    # Apply shrinkage
    sub_train = df[df['year'].isin([y for y in TRAIN_YEARS if y != 2020])]
    pop_means = {}
    for rate_col, (denom_col, _k) in SHRINK_SPEC_TO.items():
        if rate_col not in sub_train.columns or denom_col not in sub_train.columns:
            pop_means[rate_col] = float(sub_train.get(rate_col, pd.Series([0])).mean(skipna=True) or 0.0)
            continue
        d = sub_train[[rate_col, denom_col]].dropna()
        d = d[d[denom_col] > 0]
        if d.empty:
            pop_means[rate_col] = float(sub_train[rate_col].mean(skipna=True) or 0.0)
        else:
            pop_means[rate_col] = float((d[rate_col] * d[denom_col]).sum() / d[denom_col].sum())
    for rate_col, (denom_col, k) in SHRINK_SPEC_TO.items():
        n = df[denom_col].astype(float)
        obs = df[rate_col].astype(float)
        mean = pop_means[rate_col]
        df[rate_col + '_sh'] = (n.fillna(0.0) * obs.fillna(mean) + k * mean) / (n.fillna(0.0) + k)

    # Build prior from sp_multiyr
    print('Building prior (Marcel from sp_multiyr)...')
    multi = pd.read_csv(SP_MULTIYR)
    by_yr = {y: multi[multi['year'] == y].set_index('pitcher') for y in multi['year'].unique()}
    league_mean_by_year = (multi[multi['gs'] >= 5].groupby('year')['fp_per_start_actual'].mean().to_dict())
    PRIOR_K_GS = 10
    MARCEL = (5, 4, 3)
    all_p = set()
    for d in by_yr.values():
        all_p.update(d.index)
    rows = []
    for tgt in TRAIN_YEARS:
        offsets_use = []
        for off, w in zip([1, 2, 3], MARCEL):
            y = tgt - off
            if y in by_yr and y != 2020:
                offsets_use.append((y, w))
        league_mu = league_mean_by_year.get(tgt, np.nanmean(list(league_mean_by_year.values())))
        for p in all_p:
            num = 0.0; denom = 0.0
            for y, w in offsets_use:
                d = by_yr[y]
                if p in d.index:
                    row = d.loc[p]
                    if isinstance(row, pd.DataFrame): row = row.iloc[0]
                    gs = float(row.get('gs', 0) or 0)
                    fp = float(row.get('fp_per_start_actual', np.nan))
                    if gs >= 3 and not np.isnan(fp):
                        num += w * gs * fp
                        denom += w * gs
            prior = (num + PRIOR_K_GS * league_mu) / (denom + PRIOR_K_GS)
            rows.append({'pitcher': p, 'year': tgt, 'prior_fp_per_start': prior})
    prior_df = pd.DataFrame(rows)
    df = df.merge(prior_df, on=['pitcher', 'year'], how='left')

    # Cross-year evaluation
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline

    def cross_eval(feats):
        eval_df = df[(df['gs_to'] >= 3) & (df['ros_gs'] >= 3) & (df['year'] != 2020)].copy()
        eval_df = eval_df.dropna(subset=feats + [TARGET])
        per_year, preds_all, acts_all = {}, [], []
        for held in TRAIN_YEARS:
            train = eval_df[eval_df['year'] != held]
            test = eval_df[eval_df['year'] == held]
            if len(train) < 50 or len(test) < 20: continue
            pipe = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pipe.fit(train[feats].values, train[TARGET].values)
            preds = pipe.predict(test[feats].values)
            r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
            per_year[held] = r
            preds_all.extend(preds.tolist()); acts_all.extend(test[TARGET].tolist())
        overall = float(np.corrcoef(preds_all, acts_all)[0, 1])
        return overall, per_year, len(preds_all)

    print('\n=== Cross-year evaluation ===')
    print(f'{"":<22s} {"V1 r":>8s} {"V2 r":>8s} {"gain":>8s}')
    r_v1, py_v1, n1 = cross_eval(RP3_V1_FEATS)
    r_v2, py_v2, n2 = cross_eval(RP3_V2_FEATS)
    print(f'  OVERALL (n={n1}/{n2}) {r_v1:>8.4f} {r_v2:>8.4f} {r_v2-r_v1:>+8.4f}')
    for y in sorted(py_v1.keys()):
        r1 = py_v1.get(y, np.nan); r2 = py_v2.get(y, np.nan)
        print(f'  {y} held-out         {r1:>8.4f} {r2:>8.4f} {r2-r1:>+8.4f}')

    gain = r_v2 - r_v1
    print(f'\n=== VERDICT ===')
    print(f'  rp3 v1 r: {r_v1:.4f}')
    print(f'  rp3 v2 r: {r_v2:.4f}')
    print(f'  Gain: {gain:+.4f}')
    if gain >= 0.005:
        print(f'  PROMOTE — gain ≥ +0.005')
    elif gain >= 0:
        print(f'  Marginal positive gain')
    else:
        print(f'  REJECT — no gain')

    pd.DataFrame([{'feature_set': 'v1', 'overall_r': r_v1},
                    {'feature_set': 'v2', 'overall_r': r_v2}]).to_csv(
        RES / 'rp3_v2_backtest_summary.csv', index=False)


if __name__ == '__main__':
    main()
