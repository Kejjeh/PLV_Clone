"""build_boom_stack_sd30_test.py — Phase 3 follow-up Agent B.

Re-test the Agent-5 boom_stack POC at split_day=30 instead of 90 to see
whether the absorbed-signal issue at sd=90 was a noise-floor artifact.

Hypothesis: at sd=90, season-to-date `_to` features have already absorbed
most of the signal boom_stack carries. At sd=30 those `_to` features are
noisy (5-6 starts), so a 5-game-rolling boom_stack might add real lift.

3-component boom_stack at sd=30 (opp_soft DEFERRED — needs decision-time
park + opp_xwOBA):
  1. recform_hot  : trailing-5 fp_proxy/BF z-score >= +0.5
  2. skill_spike  : trailing-5 K% - season-to-date K% >= +3pp
                    AND trailing-5 BB% - season-to-date BB% <= -1pp
  3. park_friendly: pitcher's HOME park's prior-year pf_wOBA <= 33rd pct

Train 2018-2023 ex-2020, hold-out 2024.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from build_recform_hot_retroactive import per_start_fp_proxy, SP_START_BF_MIN, TRAILING_N  # noqa
from fit_weight_blend_within_season import load_panel  # noqa

YEAR = 2024
SPLIT_DAY = 30
MIN_TRAIL_STARTS_SD30 = 3  # at sd=30 most SPs have 3-6 starts


def compute_recform_sd30(year: int) -> pd.DataFrame:
    """Leak-free trailing-5 fp_proxy/BF z-score at sd=30."""
    starts = per_start_fp_proxy(year)
    starts = starts[starts['BF'] >= SP_START_BF_MIN].copy()
    starts = starts.sort_values(['pitcher', 'game_date'])
    before = starts[starts['day_of_season'] < SPLIT_DAY]

    recform = before.groupby('pitcher', observed=True).tail(TRAILING_N).groupby(
        'pitcher', observed=True).agg(
        trail_bf=('BF', 'sum'),
        trail_fp=('fp_proxy', 'sum'),
        trail_starts=('BF', 'count'),
    ).reset_index()
    recform = recform[recform['trail_starts'] >= MIN_TRAIL_STARTS_SD30].copy()
    recform['recform_fp_per_bf'] = recform['trail_fp'] / recform['trail_bf']
    mu = recform['recform_fp_per_bf'].mean()
    sd_pop = recform['recform_fp_per_bf'].std(ddof=0)
    recform['recform_hot_z'] = (recform['recform_fp_per_bf'] - mu) / (sd_pop if sd_pop > 0 else 1)
    recform['recform_hot'] = (recform['recform_hot_z'] >= 0.5).astype(int)
    return recform[['pitcher', 'recform_hot', 'recform_hot_z', 'trail_starts']]


def compute_skill_spike_sd30(year: int) -> pd.DataFrame:
    starts = per_start_fp_proxy(year)
    starts = starts[starts['BF'] >= SP_START_BF_MIN].copy()
    starts = starts.sort_values(['pitcher', 'game_date'])
    before = starts[starts['day_of_season'] < SPLIT_DAY]

    season = before.groupby('pitcher', observed=True).agg(
        BF=('BF', 'sum'), K=('K', 'sum'), BB=('BB', 'sum'),
        starts=('BF', 'count'),
    ).reset_index()
    season['k_pct_to'] = season['K'] / season['BF']
    season['bb_pct_to'] = season['BB'] / season['BF']

    trail = before.groupby('pitcher', observed=True).tail(TRAILING_N).groupby(
        'pitcher', observed=True).agg(
        BF=('BF', 'sum'), K=('K', 'sum'), BB=('BB', 'sum'),
        trail_starts=('BF', 'count'),
    ).reset_index()
    trail['k_pct_trail'] = trail['K'] / trail['BF']
    trail['bb_pct_trail'] = trail['BB'] / trail['BF']

    merged = season.merge(
        trail[['pitcher', 'k_pct_trail', 'bb_pct_trail', 'trail_starts']],
        on='pitcher')
    merged = merged[merged['trail_starts'] >= MIN_TRAIL_STARTS_SD30].copy()
    merged['dk'] = merged['k_pct_trail'] - merged['k_pct_to']
    merged['dbb'] = merged['bb_pct_trail'] - merged['bb_pct_to']
    merged['skill_spike'] = ((merged['dk'] >= 0.03) & (merged['dbb'] <= -0.01)).astype(int)
    return merged[['pitcher', 'skill_spike']]


def compute_park_friendly(year: int) -> pd.DataFrame:
    pf = pd.read_csv(CACHE / 'park_factors_2018_2026.csv')
    pf_prev = pf[pf['year'] == year - 1].copy()
    threshold = pf_prev['pf_wOBA'].quantile(0.33)
    pf_prev['park_friendly'] = (pf_prev['pf_wOBA'] <= threshold).astype(int)

    sc = pd.read_parquet(CACHE / f'statcast_{year}.parquet',
                         columns=['pitcher', 'home_team', 'inning_topbot'])
    sc = sc[sc['pitcher'].notna()].copy()
    sc_home = sc[sc['inning_topbot'] == 'Top']
    home_team = sc_home.groupby('pitcher', observed=True)['home_team'].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else None
    ).reset_index().rename(columns={'home_team': 'team_abbr'})

    merged = home_team.merge(pf_prev[['team_abbr', 'park_friendly']],
                             on='team_abbr', how='left')
    return merged[['pitcher', 'park_friendly']]


def bootstrap_delta_r2(yte, pred_base, pred_plus, n_boot=2000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(yte)
    deltas = []
    yte = np.asarray(yte); pred_base = np.asarray(pred_base); pred_plus = np.asarray(pred_plus)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            d = r2_score(yte[idx], pred_plus[idx]) - r2_score(yte[idx], pred_base[idx])
        except Exception:
            continue
        deltas.append(d)
    deltas = np.array(deltas)
    return float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5)), float(deltas.mean())


def main():
    print(f'=== boom_stack 2024 POC @ split_day={SPLIT_DAY} ===\n')

    rec = compute_recform_sd30(YEAR)
    print(f'  recform_hot fires:  {int(rec["recform_hot"].sum())} / {len(rec)}')

    spike = compute_skill_spike_sd30(YEAR)
    print(f'  skill_spike fires:  {int(spike["skill_spike"].sum())} / {len(spike)}')

    park = compute_park_friendly(YEAR)
    print(f'  park_friendly fires: {int(park["park_friendly"].sum())} / {len(park)}')

    bs = rec[['pitcher', 'recform_hot']].merge(
        spike, on='pitcher', how='outer').merge(
        park, on='pitcher', how='outer')
    for c in ['recform_hot', 'skill_spike', 'park_friendly']:
        bs[c] = bs[c].fillna(0).astype(int)
    bs['boom_stack_sd30'] = bs[['recform_hot', 'skill_spike', 'park_friendly']].sum(axis=1)
    print('\n  boom_stack_sd30 distribution:')
    print(bs['boom_stack_sd30'].value_counts().sort_index().to_string())

    # === Hold-out test ===
    sub, features = load_panel('SP', SPLIT_DAY)
    sub = sub.merge(bs[['pitcher', 'boom_stack_sd30']], on='pitcher', how='left')
    sub['boom_stack_sd30'] = np.where(sub['year'] == YEAR,
                                      sub['boom_stack_sd30'].fillna(0), 0)

    train = sub[sub['year'] != YEAR]
    test = sub[sub['year'] == YEAR]
    print(f'\n  train n={len(train)}  test (2024) n={len(test)}')

    means = train[features].mean()
    stds = train[features].std().replace(0, 1)
    Xtr = ((train[features] - means) / stds).values
    Xte = ((test[features] - means) / stds).values
    ytr = train['_ros'].values
    yte = test['_ros'].values
    base = LinearRegression().fit(Xtr, ytr)
    pred_base = base.predict(Xte)
    r2_base = r2_score(yte, pred_base)
    print(f'\n  baseline 2024 hold-out R2 = {r2_base:.4f}')

    feat2 = features + ['boom_stack_sd30']
    means2 = train[feat2].mean()
    stds2 = train[feat2].std().replace(0, 1)
    Xtr2 = ((train[feat2] - means2) / stds2).values
    Xte2 = ((test[feat2] - means2) / stds2).values
    plus = LinearRegression().fit(Xtr2, ytr)
    pred_plus = plus.predict(Xte2)
    r2_plus = r2_score(yte, pred_plus)
    print(f'  +boom_stack 2024 hold-out R2 = {r2_plus:.4f}')
    delta = r2_plus - r2_base
    print(f'  delta R2 = {delta:+.4f}')

    coef_bs = plus.coef_[-1]
    print(f'  boom_stack coefficient (standardized): {coef_bs:+.4f}')

    lo, hi, mean_d = bootstrap_delta_r2(yte, pred_base, pred_plus)
    print(f'  bootstrap 95% CI for delta R2: [{lo:+.4f}, {hi:+.4f}]  (mean {mean_d:+.4f})')

    test_plus = test.copy()
    test_plus['_actual'] = yte
    print('\n  Mean ROS FP per start by boom_stack_sd30 on 2024 test set:')
    grp = test_plus.groupby('boom_stack_sd30').agg(
        n=('_actual', 'count'),
        mean_ros=('_actual', 'mean'),
        std_ros=('_actual', 'std'),
    ).round(3)
    print(grp.to_string())

    result = {
        'split_day': SPLIT_DAY,
        'year': YEAR,
        'n_train': int(len(train)),
        'n_test_2024': int(len(test)),
        'r2_baseline_2024': float(r2_base),
        'r2_plus_boom_stack_2024': float(r2_plus),
        'delta_r2': float(delta),
        'delta_r2_ci95': [lo, hi],
        'boom_stack_coef_std': float(coef_bs),
        'bs_dist': {int(k): int(v) for k, v in bs['boom_stack_sd30'].value_counts().sort_index().to_dict().items()},
        'per_stack_2024_holdout': grp.reset_index().to_dict(orient='records'),
    }
    out_json = OUT_DIR / 'weight_blend_boom_sd30_2026-06-04.json'
    out_json.write_text(json.dumps(result, indent=2))
    print(f'\nWrote {out_json}')
    return result


if __name__ == '__main__':
    main()
