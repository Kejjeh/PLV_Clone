"""build_boom_stack_2024_poc.py — Phase 3 Agent 5 Part B.

Reconstruct a 3-component boom_stack proxy at split_day=90 for 2024 SPs
ONLY. Components:
  1. recform_hot  : recform_hot_z >= +0.5  (from Part A panel)
  2. skill_spike  : last-5-starts K% - season-to-date K% >= +3pp
                    AND last-5-starts BB% - season-to-date BB% <= -1pp
                    (computed leak-free from statcast)
  3. park_friendly: pitcher's HOME park's prior-year pf_wOBA <= 33rd pct
                    (proxy for pitcher-friendly; lower wOBA park = friendly)

opp_soft DEFERRED — needs per-start opponent xwOBA decomposition (the
biggest infra cost flagged in the Phase-3 deferral note).

Test: add boom_stack as feature to within-season blend, 2024 hold-out fold.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
PANEL_DIR = ROOT / 'data' / 'research' / 'historical_panel'

sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from build_recform_hot_retroactive import per_start_fp_proxy  # noqa
from fit_weight_blend_within_season import load_panel, fit_loyo  # noqa

YEAR = 2024
SPLIT_DAY = 90


def compute_skill_spike_2024() -> pd.DataFrame:
    """Return per-pitcher skill_spike flag at sd=90, 2024."""
    starts = per_start_fp_proxy(YEAR)
    starts = starts[starts['BF'] >= 15].copy()
    starts = starts.sort_values(['pitcher', 'game_date'])
    before = starts[starts['day_of_season'] < SPLIT_DAY]

    # Season-to-date K% / BB%
    season = before.groupby('pitcher', observed=True).agg(
        BF=('BF', 'sum'), K=('K', 'sum'), BB=('BB', 'sum'),
        starts=('BF', 'count'),
    ).reset_index()
    season['k_pct_to'] = season['K'] / season['BF']
    season['bb_pct_to'] = season['BB'] / season['BF']

    # Trailing 5
    trail = before.groupby('pitcher', observed=True).tail(5).groupby(
        'pitcher', observed=True).agg(
        BF=('BF', 'sum'), K=('K', 'sum'), BB=('BB', 'sum'),
        trail_starts=('BF', 'count'),
    ).reset_index()
    trail['k_pct_trail'] = trail['K'] / trail['BF']
    trail['bb_pct_trail'] = trail['BB'] / trail['BF']

    merged = season.merge(trail[['pitcher', 'k_pct_trail', 'bb_pct_trail', 'trail_starts']],
                          on='pitcher')
    merged = merged[merged['trail_starts'] >= 3].copy()
    merged['dk'] = merged['k_pct_trail'] - merged['k_pct_to']
    merged['dbb'] = merged['bb_pct_trail'] - merged['bb_pct_to']
    merged['skill_spike'] = ((merged['dk'] >= 0.03) & (merged['dbb'] <= -0.01)).astype(int)
    return merged[['pitcher', 'skill_spike']]


def compute_park_friendly_2024() -> pd.DataFrame:
    """Return per-pitcher park_friendly flag based on home park PRIOR year pf_wOBA."""
    pf = pd.read_csv(CACHE / 'park_factors_2018_2026.csv')
    pf_prev = pf[pf['year'] == YEAR - 1].copy()
    threshold = pf_prev['pf_wOBA'].quantile(0.33)
    pf_prev['park_friendly'] = (pf_prev['pf_wOBA'] <= threshold).astype(int)

    # Determine each pitcher's HOME team in 2024 from statcast
    sc = pd.read_parquet(CACHE / f'statcast_{YEAR}.parquet',
                          columns=['pitcher', 'home_team', 'inning_topbot'])
    sc = sc[sc['pitcher'].notna()].copy()
    # Pitcher's home team = home_team when inning_topbot == 'Top' (they're pitching for home)
    sc_home = sc[sc['inning_topbot'] == 'Top']
    home_team = sc_home.groupby('pitcher', observed=True)['home_team'].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else None
    ).reset_index().rename(columns={'home_team': 'team_abbr'})

    merged = home_team.merge(pf_prev[['team_abbr', 'park_friendly']], on='team_abbr', how='left')
    return merged[['pitcher', 'park_friendly']]


def main():
    print('=== boom_stack 2024 POC ===')

    # Component 1: recform_hot
    rec = pd.read_parquet(PANEL_DIR / 'recform_hot_retroactive.parquet')
    rec24 = rec[(rec['year'] == YEAR) & (rec['split_day'] == SPLIT_DAY)].copy()
    rec24['recform_hot'] = (rec24['recform_hot_z'] >= 0.5).astype(int)
    print(f'  recform_hot fires: {rec24["recform_hot"].sum()} / {len(rec24)}')

    # Component 2: skill_spike
    spike = compute_skill_spike_2024()
    print(f'  skill_spike fires: {spike["skill_spike"].sum()} / {len(spike)}')

    # Component 3: park_friendly
    park = compute_park_friendly_2024()
    print(f'  park_friendly fires: {park["park_friendly"].sum()} / {len(park)}')

    # Combine
    bs = rec24[['pitcher', 'recform_hot']].merge(
        spike, on='pitcher', how='outer').merge(
        park, on='pitcher', how='outer')
    for c in ['recform_hot', 'skill_spike', 'park_friendly']:
        bs[c] = bs[c].fillna(0).astype(int)
    bs['boom_stack_2024'] = bs[['recform_hot', 'skill_spike', 'park_friendly']].sum(axis=1)
    print(f'  boom_stack distribution:')
    print(bs['boom_stack_2024'].value_counts().sort_index().to_string())

    # === Hold-out test: 2024 fold of within-season blend ===
    sub, features = load_panel('SP', SPLIT_DAY)
    sub = sub.merge(bs[['pitcher', 'boom_stack_2024']], on='pitcher', how='left')
    # boom_stack only valid for year==2024 rows; set NaN elsewhere = 0
    sub['boom_stack_2024'] = np.where(sub['year'] == YEAR,
                                       sub['boom_stack_2024'].fillna(0), 0)

    train = sub[sub['year'] != YEAR]
    test = sub[sub['year'] == YEAR]
    print(f'\n  train n={len(train)}  test (2024) n={len(test)}')

    # Baseline: existing features only
    means = train[features].mean()
    stds = train[features].std().replace(0, 1)
    Xtr = ((train[features] - means) / stds).values
    Xte = ((test[features] - means) / stds).values
    ytr = train['_ros'].values
    yte = test['_ros'].values
    base = LinearRegression().fit(Xtr, ytr)
    r2_base = r2_score(yte, base.predict(Xte))
    print(f'  baseline 2024 hold-out R2 = {r2_base:.4f}')

    # +boom_stack
    feat2 = features + ['boom_stack_2024']
    means2 = train[feat2].mean()
    stds2 = train[feat2].std().replace(0, 1)
    Xtr2 = ((train[feat2] - means2) / stds2).values
    Xte2 = ((test[feat2] - means2) / stds2).values
    plus = LinearRegression().fit(Xtr2, ytr)
    r2_plus = r2_score(yte, plus.predict(Xte2))
    print(f'  +boom_stack 2024 hold-out R2 = {r2_plus:.4f}')
    print(f'  delta R2 = {r2_plus - r2_base:+.4f}')

    # Coef sign on boom_stack
    coef_bs = plus.coef_[-1]
    print(f'  boom_stack coefficient (standardized): {coef_bs:+.4f}')

    # Mean ROS FP by boom_stack bucket on 2024 test set
    test_plus = test.copy()
    test_plus['_actual'] = yte
    print(f'\n  Mean ROS FP per start by boom_stack on 2024 test set:')
    grp = test_plus.groupby('boom_stack_2024').agg(
        n=('_actual', 'count'),
        mean_ros=('_actual', 'mean'),
    ).round(3)
    print(grp.to_string())

    return {
        'n_train': len(train),
        'n_test_2024': len(test),
        'r2_baseline_2024': float(r2_base),
        'r2_plus_boom_stack_2024': float(r2_plus),
        'delta_r2': float(r2_plus - r2_base),
        'boom_stack_coef': float(coef_bs),
        'bs_dist': bs['boom_stack_2024'].value_counts().sort_index().to_dict(),
    }


if __name__ == '__main__':
    main()
