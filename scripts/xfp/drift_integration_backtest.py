"""drift_integration_backtest.py — proper backtest: does drift adjustment
to FP/PA prediction beat raw cumulative FP/PA prediction?

Methodology:
  For each historical year (2018-2025, skip 2020), use a fixed mid-season
  cutoff (6 weeks). For each qualified hitter (≥50 pre, ≥100 post PA):

    1. Compute baseline FP/PA (skill proxy: TB+BB+HBP-K per PA) over
       full pre-cutoff window.
    2. Compute half-vs-half deltas for each of 7 component metrics
       (K%, BB%, whiff/swing, EV mean, EV p90, hard-hit%, barrel%).
    3. Compute ACTUAL post-cutoff FP/PA (the target).

  Then:
    - Train OLS on 2018-2023:
        post_fp_per_pa ~ α + β_0 × baseline + Σ β_m × delta_m
      where delta_m is half-vs-half change in metric m.
    - Test on 2024-2025 (cross-year r vs actual):
        Method A: predict using ONLY baseline (β_m=0)
        Method B: predict using baseline + ALL drift terms

  Win condition: Method B per-year cross-year r > Method A per-year r,
                  consistent across both holdout years.

  If passes, lock the β coefficients and save as `drift_integration_v1`.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
RES = ROOT / 'data' / 'research'

from scripts.xfp.rolling_skill_trend import (
    PA_EVENTS, SWINGS, WHIFFS, weekly_aggregate)
from scripts.xfp.validate_rolling_trend import load_year, skill_fp_per_pa

CUTOFF_W = 6
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
TEST_YEARS = [2024, 2025]
METRICS = ['k_pct', 'bb_pct', 'whiff_per_swing', 'ev_mean', 'ev_p90',
            'hard_hit_pct', 'barrel_pct']
MIN_PRE_PA = 50
MIN_POST_PA = 100


def build_panel(year_data):
    rows = []
    for year, df in year_data.items():
        if df.empty: continue
        season_start = df['game_date'].min()
        cutoff = season_start + pd.Timedelta(weeks=CUTOFF_W)
        midpoint = season_start + pd.Timedelta(weeks=CUTOFF_W/2)
        pre = df[df['game_date'] < cutoff]
        post = df[df['game_date'] >= cutoff]
        h1 = pre[pre['game_date'] < midpoint]
        h2 = pre[pre['game_date'] >= midpoint]

        pre_pa = pre[pre['is_pa']==1].groupby('batter').size()
        post_pa = post[post['is_pa']==1].groupby('batter').size()
        qual = set(pre_pa[pre_pa>=MIN_PRE_PA].index) & set(post_pa[post_pa>=MIN_POST_PA].index)
        if not qual: continue

        pre_grp = pre.groupby('batter')
        post_grp = post.groupby('batter')
        h1_grp = h1.groupby('batter') if not h1.empty else None
        h2_grp = h2.groupby('batter') if not h2.empty else None

        def metric_value(sub_pa, sub_full, metric):
            if metric == 'k_pct':
                return sub_pa['is_k'].sum() / len(sub_pa) * 100 if len(sub_pa) else np.nan
            if metric == 'bb_pct':
                return sub_pa['is_bb'].sum() / len(sub_pa) * 100 if len(sub_pa) else np.nan
            if metric == 'whiff_per_swing':
                sw = sub_full['is_swing'].sum()
                if sw == 0: return np.nan
                return sub_full['is_whiff'].sum() / sw * 100
            bbe = sub_full[sub_full['launch_speed'].notna()]
            if metric == 'ev_mean':
                return float(bbe['launch_speed'].mean()) if len(bbe) else np.nan
            if metric == 'ev_p90':
                return float(np.percentile(bbe['launch_speed'], 90)) if len(bbe) >= 10 else np.nan
            if metric == 'hard_hit_pct':
                return float((bbe['launch_speed'] >= 95).mean() * 100) if len(bbe) else np.nan
            if metric == 'barrel_pct':
                bbe_a = sub_full[sub_full['launch_speed'].notna() & sub_full['launch_angle'].notna()]
                if len(bbe_a) < 5: return np.nan
                return float(((bbe_a['launch_speed'] >= 98) & bbe_a['launch_angle'].between(26, 30)).mean() * 100)
            return np.nan

        for bid in qual:
            try:
                pb_full = pre_grp.get_group(bid)
                postb_full = post_grp.get_group(bid)
            except KeyError: continue
            pb_pa = pb_full[pb_full['is_pa']==1]
            postb_pa = postb_full[postb_full['is_pa']==1]
            # Baseline FP/PA over pre-cutoff (skill-only proxy)
            baseline_r, _ = skill_fp_per_pa(pb_full['events'])
            post_r, _ = skill_fp_per_pa(postb_full['events'])
            if pd.isna(baseline_r) or pd.isna(post_r): continue

            entry = {'year': year, 'batter': bid,
                     'baseline_fp_pa': baseline_r,
                     'post_fp_pa': post_r}
            try:
                h1b_full = h1_grp.get_group(bid) if h1_grp else None
                h2b_full = h2_grp.get_group(bid) if h2_grp else None
            except KeyError:
                h1b_full = h2b_full = None
            if h1b_full is None or h2b_full is None:
                continue
            h1b_pa = h1b_full[h1b_full['is_pa']==1]
            h2b_pa = h2b_full[h2b_full['is_pa']==1]
            # Compute deltas for each metric
            for m in METRICS:
                v1 = metric_value(h1b_pa, h1b_full, m)
                v2 = metric_value(h2b_pa, h2b_full, m)
                if pd.isna(v1) or pd.isna(v2):
                    entry[f'delta_{m}'] = np.nan
                else:
                    entry[f'delta_{m}'] = v2 - v1
            rows.append(entry)
    return pd.DataFrame(rows)


def main():
    print('Loading 2018-2025 data...')
    year_data = {}
    for y in TRAIN_YEARS + TEST_YEARS:
        print(f'  {y}...')
        year_data[y] = load_year(y)

    panel = build_panel(year_data)
    print(f'\nPanel size: {len(panel)} hitter-years')
    print(f'  Train (2018-2023): {len(panel[panel["year"].isin(TRAIN_YEARS)])}')
    print(f'  Test (2024-2025):  {len(panel[panel["year"].isin(TEST_YEARS)])}')

    # Save panel
    panel.to_csv(RES / 'drift_integration_panel.csv', index=False)

    # ============== Train OLS ==============
    delta_cols = [f'delta_{m}' for m in METRICS]
    train = panel[panel['year'].isin(TRAIN_YEARS)].dropna(subset=['baseline_fp_pa', 'post_fp_pa'] + delta_cols)
    print(f'\nTrain dropna sample: {len(train)} hitter-years')

    # Fit:  post_fp_pa = α + β_b × baseline + Σ β_m × delta_m
    X_train = train[['baseline_fp_pa'] + delta_cols].values
    y_train = train['post_fp_pa'].values
    X_aug = np.column_stack([np.ones(len(X_train)), X_train])
    # OLS via lstsq
    coefs, _, _, _ = np.linalg.lstsq(X_aug, y_train, rcond=None)
    alpha, beta_baseline = coefs[0], coefs[1]
    beta_drift = dict(zip(METRICS, coefs[2:]))

    print('\n=== OLS coefficients (trained on 2018-2023) ===')
    print(f'  Intercept α:      {alpha:+.5f}')
    print(f'  β_baseline:       {beta_baseline:+.5f}  (slope on cumulative FP/PA)')
    for m, b in beta_drift.items():
        print(f'  β_{m:<15s}: {b:+.5f}')

    # ============== Test ==============
    print('\n=== TEST per-year cross-year r (raw rh3-style vs drift-adjusted) ===')
    print(f'{"year":<6s} {"N":>5s} {"r_baseline_only":>16s} {"r_with_drift":>15s} {"gain":>8s}')

    overall_a, overall_b = [], []
    for y in TEST_YEARS:
        sub = panel[(panel['year']==y)].dropna(subset=['baseline_fp_pa', 'post_fp_pa'] + delta_cols)
        if len(sub) < 30: continue
        # Method A: baseline only (α=0 ignored, just regression of baseline alone)
        pred_a = sub['baseline_fp_pa'].values
        # Method B: full drift model
        X_test = sub[['baseline_fp_pa'] + delta_cols].values
        X_aug = np.column_stack([np.ones(len(X_test)), X_test])
        pred_b = X_aug @ coefs
        # Correlations against actual post_fp_pa
        actual = sub['post_fp_pa'].values
        r_a = float(np.corrcoef(pred_a, actual)[0,1])
        r_b = float(np.corrcoef(pred_b, actual)[0,1])
        overall_a.append(r_a); overall_b.append(r_b)
        print(f'  {y:<6d} {len(sub):>5d} {r_a:>16.4f} {r_b:>15.4f} {r_b-r_a:>+8.4f}')

    # Pooled (across all test years)
    test = panel[panel['year'].isin(TEST_YEARS)].dropna(subset=['baseline_fp_pa', 'post_fp_pa'] + delta_cols)
    pred_a = test['baseline_fp_pa'].values
    X_test = test[['baseline_fp_pa'] + delta_cols].values
    X_aug = np.column_stack([np.ones(len(X_test)), X_test])
    pred_b = X_aug @ coefs
    actual = test['post_fp_pa'].values
    r_a_pool = float(np.corrcoef(pred_a, actual)[0,1])
    r_b_pool = float(np.corrcoef(pred_b, actual)[0,1])
    print(f'  POOL  {len(test):>5d} {r_a_pool:>16.4f} {r_b_pool:>15.4f} {r_b_pool-r_a_pool:>+8.4f}')

    # ============== Verdict ==============
    print(f'\n=== VERDICT ===')
    n_win = sum(1 for a, b in zip(overall_a, overall_b) if b > a)
    print(f'  Drift-adjusted beat baseline in {n_win} of {len(overall_a)} test years')
    print(f'  Pooled r delta: {r_b_pool - r_a_pool:+.4f}')
    if r_b_pool > r_a_pool + 0.01:  # require meaningful gain
        print(f'  → PROMOTE drift integration to production (meaningful gain ≥ 0.01)')
    elif r_b_pool > r_a_pool:
        print(f'  → Marginal gain; consider promoting with caveat')
    else:
        print(f'  → DO NOT promote; drift integration does NOT improve FP/PA prediction')

    # Save coefficients
    coef_df = pd.DataFrame([{'name': k, 'beta': v} for k, v in
                              [('alpha', alpha), ('baseline_fp_pa', beta_baseline)] +
                              [(f'delta_{m}', beta_drift[m]) for m in METRICS]])
    coef_df.to_csv(RES / 'drift_integration_coefficients.csv', index=False)
    summary = {
        'r_baseline_pooled': r_a_pool,
        'r_with_drift_pooled': r_b_pool,
        'pooled_gain': r_b_pool - r_a_pool,
        'years_drift_won': n_win,
        'years_total': len(overall_a),
    }
    pd.DataFrame([summary]).to_csv(RES / 'drift_integration_summary.csv', index=False)
    print(f'\nwrote drift_integration_panel.csv, _coefficients.csv, _summary.csv')


if __name__ == '__main__':
    main()
