"""integrate_rh3_v2_backtest.py — proper rh3 v2 backtest.

Uses the SAME substrate (rolling_hitters_2018_2026.csv) and SAME training/
target setup as the production rh3 pipeline. Adds two new features:

  • xwoba_gap_to = xwoba_on_contact_to − (woba_v_sum_to/woba_d_sum_to)
    The luck regression signal validated as H3 (+0.077 r in standalone
    test); want to see how much it improves the FULL rh3 model.

  • career_stage = year − first MLB year (proxy for career trajectory)
    Validated as H5 (+0.017 r in standalone test).

Bar: if rh3 v2 cross-year r > rh3 v1 r by ≥ +0.005 (the same gate v1
itself used), promote to production.
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

ROLLING_CSV = CACHE / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = CACHE / 'hitters_multiyr_2015_2026.csv'

TARGET = 'ros_full_fp_per_pa'
EVAL_PA_MIN = 50
ROS_PA_MIN = 100
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]

# Existing rh3 features (per xfp_rh3_pipeline.py:88)
RH3_V1_FEATS = [
    'iso_to_sh', 'k_pct_to_sh', 'hr_per_pa_to_sh', 'hard_hit_pct_to_sh',
    'contact_pct_to_sh', 'whiff_pct_to_sh', 'swstr_pct_to_sh', 'bb_pct_to_sh',
    'chase_pct_to_sh', 'in_play_pct_to_sh', 'sb_per_pa_to_sh',
    'xwoba_per_pa_to_sh', 'barrel_pct_to_sh',
    'prior_fp_per_pa', 'prior_pa_eff', 'pa_to', 'split_day',
    'lift_h2_aug150', 'xwoba_residual_career',
]
RH3_V2_FEATS = RH3_V1_FEATS + ['xwoba_gap_to', 'career_stage']

SHRINK_SPEC_TO = {
    'k_pct_to':         ('pa_to',     60),
    'bb_pct_to':        ('pa_to',    120),
    'hr_per_pa_to':     ('pa_to',    170),
    'iso_to':           ('ab_to',    160),
    'sb_per_pa_to':     ('pa_to',    300),
    'xwoba_per_pa_to':  ('pa_to',    300),
    'contact_pct_to':   ('swing_to', 100),
    'whiff_pct_to':     ('swing_to', 100),
    'swstr_pct_to':     ('pitches_to', 300),
    'hard_hit_pct_to':  ('bip_to',    50),
    'barrel_pct_to':    ('bip_to',    50),
    'chase_pct_to':     ('out_zone_to', 400),
    'in_play_pct_to':   ('pitches_to', 300),
}


def main():
    print('Loading substrate...')
    df = pd.read_csv(ROLLING_CSV)
    multi = pd.read_csv(MULTIYR_CSV)
    print(f'  rolling: {len(df)} rows, multiyr: {len(multi)} rows')

    # Build career_stage
    first_year = multi.groupby('batter')['year'].min().to_dict()
    df['career_stage'] = df.apply(lambda r: r['year'] - first_year.get(r['batter'], r['year']),
                                    axis=1)

    # Build xwoba_gap_to: xwoba_on_contact_to - actual_wOBA_per_PA
    if 'xwoba_on_contact_to' in df.columns and 'woba_d_sum_to' in df.columns:
        df['actual_woba_per_pa'] = np.where(
            df['woba_d_sum_to'] > 0,
            df['woba_v_sum_to'] / df['woba_d_sum_to'],
            np.nan)
        df['xwoba_gap_to'] = df['xwoba_on_contact_to'] - df['actual_woba_per_pa']
    else:
        df['xwoba_gap_to'] = np.nan
    print(f'  xwoba_gap_to non-null: {df["xwoba_gap_to"].notna().sum()}/{len(df)}')

    # Make sure derived denominators exist
    if 'ab_to' not in df.columns:
        df['ab_to'] = df['pa_to'] - df['bb_to'] - df.get('hbp_to', 0)
    if 'out_zone_to' not in df.columns:
        df['out_zone_to'] = (df['pitches_to'] - df['in_zone_to']).clip(lower=0)

    # Apply shrinkage on cumulative-to-date rates
    # Use train-year (non-2020) means
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

    # Bring in prior_fp_per_pa from existing rh3 output
    print('Building prior (Marcel weighted from multiyr)...')
    PRIOR_K_PA = 200
    MARCEL_WEIGHTS = (5, 4, 3)
    by_yr = {y: multi[multi['year'] == y].set_index('batter') for y in multi['year'].unique()}
    league_mean_by_year = (multi[multi['pa'] >= 200]
                            .groupby('year')['fp_per_pa_actual'].mean().to_dict())
    all_batters = set()
    for d in by_yr.values():
        all_batters.update(d.index)
    prior_rows = []
    for tgt in TRAIN_YEARS:
        offsets_use = []
        for off, w in zip([1, 2, 3], MARCEL_WEIGHTS):
            y = tgt - off
            if y in by_yr and y != 2020:
                offsets_use.append((y, w))
        league_mu = league_mean_by_year.get(tgt, np.nanmean(list(league_mean_by_year.values())))
        for b in all_batters:
            num = 0.0; denom = 0.0
            for y, w in offsets_use:
                df_y = by_yr[y]
                if b in df_y.index:
                    row = df_y.loc[b]
                    if isinstance(row, pd.DataFrame): row = row.iloc[0]
                    pa = float(row.get('pa', 0) or 0)
                    fp = float(row.get('fp_per_pa_actual', np.nan))
                    if pa >= 50 and not np.isnan(fp):
                        num += w * pa * fp
                        denom += w * pa
            prior = (num + PRIOR_K_PA * league_mu) / (denom + PRIOR_K_PA)
            prior_rows.append({'batter': b, 'year': tgt,
                               'prior_fp_per_pa': prior,
                               'prior_pa_eff': denom / max(sum(w for _, w in offsets_use), 1)})
    prior_df = pd.DataFrame(prior_rows)
    df = df.merge(prior_df, on=['batter', 'year'], how='left')

    # Bring in lift_h2 and xwoba_residual from their CSVs
    h2_csv = OUT / 'seasonality_h2_locked.csv'
    if h2_csv.exists():
        h2 = pd.read_csv(h2_csv)
        if 'lift_h2_aug150' in h2.columns:
            df = df.merge(h2[['batter', 'lift_h2_aug150']], on='batter', how='left')
    if 'lift_h2_aug150' not in df.columns:
        df['lift_h2_aug150'] = 0.0
    xres_csv = OUT / 'hitter_xwoba_residual.csv'
    if xres_csv.exists():
        xres = pd.read_csv(xres_csv)
        if 'xwoba_residual_career' in xres.columns:
            df = df.merge(xres[['batter', 'xwoba_residual_career']], on='batter', how='left')
    if 'xwoba_residual_career' not in df.columns:
        df['xwoba_residual_career'] = 0.0

    # Cross-year evaluation
    print('\n=== Cross-year evaluation ===')
    print(f'{"":<22s} {"V1 r":>8s} {"V2 r":>8s} {"gain":>8s}')

    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline

    def cross_eval(feats):
        eval_df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)].copy()
        eval_df = eval_df.dropna(subset=feats + [TARGET])
        preds_all, acts_all = [], []
        per_year = {}
        for held in TRAIN_YEARS:
            train = eval_df[eval_df['year'] != held]
            test = eval_df[eval_df['year'] == held]
            if len(train) < 100 or len(test) < 30: continue
            pipe = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pipe.fit(train[feats].values, train[TARGET].values)
            preds = pipe.predict(test[feats].values)
            r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
            per_year[held] = r
            preds_all.extend(preds.tolist()); acts_all.extend(test[TARGET].tolist())
        overall = float(np.corrcoef(preds_all, acts_all)[0, 1])
        return overall, per_year

    r_v1, py_v1 = cross_eval(RH3_V1_FEATS)
    r_v2, py_v2 = cross_eval(RH3_V2_FEATS)

    print(f'  OVERALL r            {r_v1:>8.4f} {r_v2:>8.4f} {r_v2-r_v1:>+8.4f}')
    for y in sorted(py_v1.keys()):
        r1 = py_v1.get(y, np.nan); r2 = py_v2.get(y, np.nan)
        gain = r2 - r1
        print(f'  {y} held-out         {r1:>8.4f} {r2:>8.4f} {gain:>+8.4f}')

    # Verdict
    gain_overall = r_v2 - r_v1
    print(f'\n=== VERDICT ===')
    print(f'  rh3 v1 cross-year r: {r_v1:.4f}')
    print(f'  rh3 v2 cross-year r: {r_v2:.4f}')
    print(f'  Gain: {gain_overall:+.4f}')
    if gain_overall >= 0.005:
        print(f'  PROMOTE — gain ≥ +0.005 bar')
    elif gain_overall >= 0:
        print(f'  Marginal positive gain; consider integration with caveat')
    else:
        print(f'  REJECT — v2 does not improve')

    # Save details for examination
    pd.DataFrame([{
        'feature_set': 'v1', 'overall_r': r_v1,
    }, {
        'feature_set': 'v2 (v1 + xwoba_gap + career_stage)', 'overall_r': r_v2,
    }]).to_csv(RES / 'rh3_v2_backtest_summary.csv', index=False)


if __name__ == '__main__':
    main()
