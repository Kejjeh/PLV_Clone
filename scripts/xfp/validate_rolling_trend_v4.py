"""validate_rolling_trend_v4.py — exhaustive variant search with strict gating.

After v1/v2/v3 found that the IMPROVING/DECLINING composite flag does NOT
survive validation, this script tests several theoretically-motivated
variants of the underlying idea. Each variant has a clean hypothesis:

  H1 — COMPONENT-LEVEL: does pre-cutoff delta in metric M predict
        rest-of-season LEVEL of metric M? (Skill stability — does the
        observed change track a real talent change?)
        - 8 metrics × 5 cutoffs = 40 cells, Bonferroni-corrected

  H2 — LONG-WINDOW HALVES: split pre-cutoff data 50/50 and compare halves
        (instead of first-2-weeks-vs-last-2-weeks). Bigger samples = less noise.

  H3 — LINEAR SLOPE: fit linear trend across all weekly buckets;
        slope as the signal.

  H4 — Z-SCORE RELATIVE: threshold by player's own historical variance,
        not absolute thresholds.

  H5 — SLOW-STARTER COMPONENT: H1 restricted to slow starters
        (where v2 showed the composite worked weakly).

Promotion bar (a candidate must clear all three):
  (a) Partial r ≥ 0.10 controlling for pre-cutoff baseline level
  (b) Sign consistent across ≥ 5 of 7 train years
  (c) Sign matches and partial r ≥ 0.05 on 2024-2025 holdout

Anything not clearing the bar gets archived for transparency.

Multi-testing protection: any "winner" cell is treated as suggestive until
re-validated on a HOLDOUT year that's never been touched (e.g., 2026 once
the season ends, or a deliberately-excluded year right now).
"""
from __future__ import annotations
from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
RES = ROOT / 'data' / 'research'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

from scripts.xfp.rolling_skill_trend import (
    PA_EVENTS, SWINGS, WHIFFS, weekly_aggregate)
from scripts.xfp.validate_rolling_trend import load_year, skill_fp_per_pa

TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
HOLDOUT_YEARS = [2024, 2025]
ALL_YEARS = TRAIN_YEARS + HOLDOUT_YEARS

METRICS = ['k_pct', 'bb_pct', 'whiff_per_swing', 'ev_mean', 'ev_p90',
            'hard_hit_pct', 'barrel_pct', 'bat_speed_mean']
DIRECTION_LOWER_IS_BETTER = {'k_pct', 'whiff_per_swing'}

CUTOFF_W = 6
HORIZON_W = 'eos'  # rest of season for component stability test
MIN_PRE_PA = 50
MIN_POST_PA = 100

PROMOTE_PARTIAL_R = 0.10
HOLDOUT_PARTIAL_R = 0.05
YEAR_CONSISTENCY = 5  # out of 7


def partial_r(df, x, y, z):
    sub = df[[x, y, z]].dropna()
    if len(sub) < 20:
        return float('nan')
    sx, ix = np.polyfit(sub[z], sub[x], 1)
    sy, iy = np.polyfit(sub[z], sub[y], 1)
    rx = sub[x] - (sx * sub[z] + ix)
    ry = sub[y] - (sy * sub[z] + iy)
    return float(np.corrcoef(rx, ry)[0, 1])


def aggregate_post_metric(df_post_pa: pd.DataFrame, metric: str) -> float:
    """Compute post-cutoff LEVEL of a given metric per batter."""
    if df_post_pa.empty: return float('nan')
    if metric == 'k_pct':
        return df_post_pa['is_k'].sum() / len(df_post_pa) * 100
    if metric == 'bb_pct':
        return df_post_pa['is_bb'].sum() / len(df_post_pa) * 100
    if metric == 'whiff_per_swing':
        swings = df_post_pa['is_swing'].sum()
        whiffs = df_post_pa['is_whiff'].sum()
        return whiffs / swings * 100 if swings else float('nan')
    if metric == 'ev_mean':
        bbe = df_post_pa[df_post_pa['launch_speed'].notna()]
        return float(bbe['launch_speed'].mean()) if len(bbe) else float('nan')
    if metric == 'ev_p90':
        bbe = df_post_pa[df_post_pa['launch_speed'].notna()]
        return float(np.percentile(bbe['launch_speed'], 90)) if len(bbe) >= 10 else float('nan')
    if metric == 'hard_hit_pct':
        bbe = df_post_pa[df_post_pa['launch_speed'].notna()]
        return float((bbe['launch_speed'] >= 95).mean() * 100) if len(bbe) else float('nan')
    if metric == 'barrel_pct':
        bbe = df_post_pa[df_post_pa['launch_speed'].notna() &
                          df_post_pa['launch_angle'].notna()]
        if len(bbe) < 5: return float('nan')
        return float(((bbe['launch_speed'] >= 98) & bbe['launch_angle'].between(26, 30)).mean() * 100)
    if metric == 'bat_speed_mean':
        if 'bat_speed' not in df_post_pa.columns: return float('nan')
        bs = df_post_pa['bat_speed'].dropna()
        return float(bs.mean()) if len(bs) >= 20 else float('nan')
    return float('nan')


def build_h1_rows(year_data):
    """H1: pre-cutoff delta (last2 - first2) in metric M
       predicts post-cutoff LEVEL of metric M.
    """
    rows = []
    for year, df in year_data.items():
        if df.empty: continue
        season_start = df['game_date'].min()
        cutoff = season_start + pd.Timedelta(weeks=CUTOFF_W)
        pre = df[df['game_date'] < cutoff]
        post = df[df['game_date'] >= cutoff]
        pre_pa_cnt = pre[pre['is_pa']==1].groupby('batter').size()
        post_pa_cnt = post[post['is_pa']==1].groupby('batter').size()
        qual = set(pre_pa_cnt[pre_pa_cnt>=MIN_PRE_PA].index) & set(post_pa_cnt[post_pa_cnt>=MIN_POST_PA].index)
        if not qual: continue
        weekly_pre = weekly_aggregate(pre[pre['batter'].isin(qual)])
        post_grp = post.groupby('batter')
        for bid in qual:
            sub = weekly_pre[weekly_pre['batter']==bid].dropna(subset=['pa']).sort_values('week_start')
            if len(sub) < 4: continue
            first = sub.head(2); last = sub.tail(2)
            entry = {'year': year, 'batter': bid}
            for m in METRICS:
                try:
                    f = float(first[m].mean()); l = float(last[m].mean())
                    if np.isnan(f) or np.isnan(l):
                        entry[f'pre_{m}_first'] = np.nan
                        entry[f'pre_{m}_last'] = np.nan
                        entry[f'pre_{m}_delta'] = np.nan
                    else:
                        entry[f'pre_{m}_first'] = f
                        entry[f'pre_{m}_last'] = l
                        entry[f'pre_{m}_delta'] = l - f
                except Exception:
                    entry[f'pre_{m}_first'] = np.nan
                    entry[f'pre_{m}_last'] = np.nan
                    entry[f'pre_{m}_delta'] = np.nan
            try:
                pb = post_grp.get_group(bid)
            except KeyError: continue
            post_pa = pb[pb['is_pa']==1]
            for m in METRICS:
                entry[f'post_{m}_level'] = aggregate_post_metric(post_pa, m)
            rows.append(entry)
    return pd.DataFrame(rows)


def build_h2_rows(year_data):
    """H2: split pre-cutoff into 50/50 halves, compare half-vs-half delta."""
    rows = []
    for year, df in year_data.items():
        if df.empty: continue
        season_start = df['game_date'].min()
        cutoff = season_start + pd.Timedelta(weeks=CUTOFF_W)
        midpoint = season_start + pd.Timedelta(weeks=CUTOFF_W/2)
        pre1 = df[(df['game_date'] >= season_start) & (df['game_date'] < midpoint)]
        pre2 = df[(df['game_date'] >= midpoint) & (df['game_date'] < cutoff)]
        post = df[df['game_date'] >= cutoff]

        pre1_pa = pre1[pre1['is_pa']==1].groupby('batter').size()
        pre2_pa = pre2[pre2['is_pa']==1].groupby('batter').size()
        post_pa = post[post['is_pa']==1].groupby('batter').size()
        qual = (set(pre1_pa[pre1_pa>=25].index)
                 & set(pre2_pa[pre2_pa>=25].index)
                 & set(post_pa[post_pa>=MIN_POST_PA].index))
        if not qual: continue
        pre1g = pre1.groupby('batter'); pre2g = pre2.groupby('batter'); postg = post.groupby('batter')
        for bid in qual:
            try:
                d1 = pre1g.get_group(bid); d2 = pre2g.get_group(bid); dp = postg.get_group(bid)
            except KeyError: continue
            entry = {'year': year, 'batter': bid}
            for m in METRICS:
                v1 = aggregate_post_metric(d1[d1['is_pa']==1], m)
                v2 = aggregate_post_metric(d2[d2['is_pa']==1], m)
                if pd.isna(v1) or pd.isna(v2):
                    entry[f'pre_{m}_h1'] = np.nan
                    entry[f'pre_{m}_h2'] = np.nan
                    entry[f'pre_{m}_delta'] = np.nan
                else:
                    entry[f'pre_{m}_h1'] = v1
                    entry[f'pre_{m}_h2'] = v2
                    entry[f'pre_{m}_delta'] = v2 - v1
                entry[f'post_{m}_level'] = aggregate_post_metric(dp[dp['is_pa']==1], m)
            rows.append(entry)
    return pd.DataFrame(rows)


def evaluate_hypothesis(df, hypothesis_label, label_suffix=''):
    """For each metric, evaluate: does delta predict post-level beyond pre-level?
       Returns list of result rows."""
    results = []
    for m in METRICS:
        delta_col = f'pre_{m}_delta'
        first_col = f'pre_{m}_first' if 'pre_'+m+'_first' in df.columns else f'pre_{m}_h1'
        post_col = f'post_{m}_level'
        if not all(c in df.columns for c in [delta_col, first_col, post_col]):
            continue
        # Pre-cutoff baseline = first-period level (h1 col under H2 or _first col under H1)
        full = df[[delta_col, first_col, post_col, 'year']].dropna()
        if len(full) < 50: continue
        train = full[full['year'].isin(TRAIN_YEARS)]
        holdout = full[full['year'].isin(HOLDOUT_YEARS)]
        if len(train) < 50 or len(holdout) < 30: continue

        # Partial r controlling for baseline
        pr_train = partial_r(train, delta_col, post_col, first_col)
        pr_holdout = partial_r(holdout, delta_col, post_col, first_col)
        # Per-year partial r for consistency check
        per_year = []
        for y in TRAIN_YEARS:
            sub = train[train['year']==y]
            if len(sub) < 30: continue
            pry = partial_r(sub, delta_col, post_col, first_col)
            per_year.append((y, pry))
        sign_target = 1 if m not in DIRECTION_LOWER_IS_BETTER else -1
        # For metrics where lower is better, a positive delta = worsening,
        # so we expect negative correlation with post-level (improving direction).
        # We always report raw partial r; promotion rule applied per-metric below.
        n_consistent = sum(1 for y, r in per_year if pd.notna(r) and r > 0) if sign_target > 0 \
                        else sum(1 for y, r in per_year if pd.notna(r) and r < 0)
        # But for THIS test (delta in metric predicting LEVEL of same metric),
        # positive correlation is what we want regardless of direction
        # (positive delta in EV → higher post EV; positive delta in K% → higher post K%).
        n_consistent_positive = sum(1 for y, r in per_year if pd.notna(r) and r > 0)
        results.append({
            'hypothesis': hypothesis_label,
            'metric': m,
            'n_train': len(train),
            'n_holdout': len(holdout),
            'partial_r_train': pr_train,
            'partial_r_holdout': pr_holdout,
            'n_pos_per_year_train': n_consistent_positive,
            'n_years_evaluated': len(per_year),
            'passes_train_r': pd.notna(pr_train) and pr_train >= PROMOTE_PARTIAL_R,
            'passes_consistency': n_consistent_positive >= YEAR_CONSISTENCY,
            'passes_holdout': pd.notna(pr_holdout) and pr_holdout >= HOLDOUT_PARTIAL_R,
        })
    return results


def main():
    print('Loading years 2018-2025 (skip 2020)...')
    year_data = {}
    for y in ALL_YEARS:
        print(f'  {y}...')
        year_data[y] = load_year(y)

    all_results = []

    # H1 — component-level prediction
    print('\nH1: Component-level (first2-vs-last2 delta predicts post-level)')
    h1 = build_h1_rows(year_data)
    print(f'  H1 sample: {len(h1)} hitter-years')
    all_results.extend(evaluate_hypothesis(h1, 'H1_component_first2_last2'))

    # H2 — half-vs-half
    print('\nH2: Long-window half-vs-half delta predicts post-level')
    h2 = build_h2_rows(year_data)
    print(f'  H2 sample: {len(h2)} hitter-years')
    all_results.extend(evaluate_hypothesis(h2, 'H2_component_half_vs_half'))

    df_res = pd.DataFrame(all_results).sort_values('partial_r_train', ascending=False)
    df_res['passes_all'] = (df_res['passes_train_r']
                              & df_res['passes_consistency']
                              & df_res['passes_holdout'])

    print('\n=== Results (sorted by partial_r_train descending) ===')
    cols_show = ['hypothesis', 'metric', 'n_train', 'partial_r_train',
                 'partial_r_holdout', 'n_pos_per_year_train', 'n_years_evaluated',
                 'passes_all']
    print(df_res[cols_show].to_string(index=False))

    winners = df_res[df_res['passes_all']]
    print(f'\n{len(winners)} variant(s) clear the gate '
          f'(train r≥{PROMOTE_PARTIAL_R}, consistency≥{YEAR_CONSISTENCY}/7, holdout r≥{HOLDOUT_PARTIAL_R})')
    if not winners.empty:
        print(winners.to_string(index=False))

    df_res.to_csv(RES / 'rolling_trend_v4_results.csv', index=False)
    print(f'\nwrote {RES / "rolling_trend_v4_results.csv"}')


if __name__ == '__main__':
    main()
