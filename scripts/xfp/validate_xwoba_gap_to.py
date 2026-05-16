"""validate_xwoba_gap_to.py — re-validate the xwoba_gap_to signal against
the FULL rh3 production baseline (21 features).

Pre-registered: data/research/validation_runs/xwoba_gap_to_2026-05-16.md
Purpose: sanity-check the /validate-feature skill by reproducing the
+0.0016 lift number documented in the registry (NOT the inflated +0.006
from the original curated backtest).

Reuses the rh3 pipeline's data-prep + cross_year_eval to ensure the
exact production code path is exercised.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from xfp_rh3_pipeline import (
    ROLLING_CSV, MULTIYR_CSV, RH3_FEATS,
    SHRINK_SPEC_TO, SHRINK_SPEC_LAST21,
    build_prior_table, compute_population_means, apply_shrinkage,
    cross_year_eval, H2_LOCKED_CSV, XWOBA_RESID_CSV,
    PRIOR_K_PA, MARCEL_WEIGHTS, TRAIN_YEARS,
)

CANDIDATE = 'xwoba_gap_to'


def prep_rolling() -> pd.DataFrame:
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    print(f'rolling: {len(rolling)} rows | multiyr: {len(multiyr)} rows')

    prior = build_prior_table(multiyr, sorted(rolling['year'].unique().tolist()))
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')

    if H2_LOCKED_CSV.exists():
        h2_locked = pd.read_csv(H2_LOCKED_CSV)[['batter', 'lift_h2_aug150']]
        rolling = rolling.merge(h2_locked, on='batter', how='left')

    if XWOBA_RESID_CSV.exists():
        xw = pd.read_csv(XWOBA_RESID_CSV)[['batter', 'xwoba_residual_career']]
        rolling = rolling.merge(xw, on='batter', how='left')

    # career_stage feature (year - first MLB year)
    first_year = multiyr.groupby('batter')['year'].min().rename('first_year')
    rolling = rolling.merge(first_year, on='batter', how='left')
    rolling['career_stage'] = rolling['year'] - rolling['first_year']

    # xwoba_gap_to = within-season xwOBA-on-contact − actual wOBA per PA
    if 'xwoba_on_contact_to' in rolling.columns and 'woba_d_sum_to' in rolling.columns:
        rolling['actual_woba_per_pa_to'] = np.where(
            rolling['woba_d_sum_to'] > 0,
            rolling['woba_v_sum_to'] / rolling['woba_d_sum_to'],
            np.nan)
        rolling['xwoba_gap_to'] = (rolling['xwoba_on_contact_to']
                                     - rolling['actual_woba_per_pa_to']).fillna(0.0)
    else:
        rolling['xwoba_gap_to'] = 0.0

    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    pop_l21 = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)

    return rolling


def main():
    rolling = prep_rolling()

    missing = [f for f in RH3_FEATS if f not in rolling.columns]
    if missing:
        print(f'ERROR — missing features in rolling: {missing}')
        sys.exit(1)

    print(f'\n=== Test C: re-validate {CANDIDATE} ===')
    print(f'Production baseline: {len(RH3_FEATS)} features')
    print(f'Full set (with candidate): {sorted(RH3_FEATS)}')

    baseline_feats = [f for f in RH3_FEATS if f != CANDIDATE]
    print(f'\nBaseline (drops {CANDIDATE}): {len(baseline_feats)} features')

    print(f'\n--- Per-year cross_year r ---')
    print(f'\n  FULL (with {CANDIDATE}):')
    per_year_full, overall_full = cross_year_eval(rolling, RH3_FEATS)
    for yr, info in sorted(per_year_full.items()):
        print(f'    {yr}: r={info["r"]:+.4f} n={info["n"]}')
    print(f'    OVERALL: r={overall_full["r"]:+.4f} n={overall_full["n"]}')

    print(f'\n  BASELINE (drops {CANDIDATE}):')
    per_year_base, overall_base = cross_year_eval(rolling, baseline_feats)
    for yr, info in sorted(per_year_base.items()):
        print(f'    {yr}: r={info["r"]:+.4f} n={info["n"]}')
    print(f'    OVERALL: r={overall_base["r"]:+.4f} n={overall_base["n"]}')

    gain = overall_full['r'] - overall_base['r']
    print(f'\n  LIFT FROM {CANDIDATE}: r={gain:+.4f}  (n={overall_full["n"]})')

    # Per-year deltas
    print(f'\n  Per-year delta:')
    sign_match = 0; n_years = 0
    for yr in sorted(per_year_full.keys()):
        if yr in per_year_base:
            d = per_year_full[yr]['r'] - per_year_base[yr]['r']
            print(f'    {yr}: {d:+.4f}')
            n_years += 1
            if d > 0:
                sign_match += 1

    # Holdout assessment
    HOLDOUT = [2024, 2025]
    print(f'\n  Holdout years {HOLDOUT}:')
    holdout_full = [per_year_full[y]['r'] for y in HOLDOUT if y in per_year_full]
    holdout_base = [per_year_base[y]['r'] for y in HOLDOUT if y in per_year_base]
    if holdout_full and holdout_base:
        ho_gain = np.mean(holdout_full) - np.mean(holdout_base)
        print(f'    avg holdout gain: {ho_gain:+.4f}')

    print(f'\n  Sign consistency: {sign_match}/{n_years} years positive')

    # ALSO: joint v2 drop (matches the 2026-05-13 audit comparison)
    print(f'\n--- Joint v2 drop (xwoba_gap_to + career_stage), matches original audit ---')
    v2_joint = ['xwoba_gap_to', 'career_stage']
    base_joint = [f for f in RH3_FEATS if f not in v2_joint]
    print(f'  Baseline (19 features, drops v2 set): {sorted(base_joint)}')
    py_jb, ov_jb = cross_year_eval(rolling, base_joint)
    print(f'  Joint baseline OVERALL: r={ov_jb["r"]:+.4f}')
    print(f'  Full (21) OVERALL:      r={overall_full["r"]:+.4f}')
    gain_joint = overall_full['r'] - ov_jb['r']
    print(f'  Joint v2 LIFT: r={gain_joint:+.4f}')

    print(f'\n=== Gates ===')
    print(f'  (a) Effect size (lift ≥ +0.005?): {"PASS" if gain >= 0.005 else "FAIL/MARGINAL"} ({gain:+.4f})')
    print(f'  (b) Sign consistency (≥ 5 of 7?): {"PASS" if sign_match >= 5 else "FAIL"} ({sign_match}/{n_years})')
    if holdout_full and holdout_base:
        ho_pass = ho_gain > 0
        print(f'  (c) Holdout sign-match (+): {"PASS" if ho_pass else "FAIL"} ({ho_gain:+.4f})')


if __name__ == '__main__':
    main()
