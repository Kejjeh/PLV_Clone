"""_rp3_validation_harness.py — shared data-prep helpers for rp3 v3
candidate-feature validation scripts.

Centralises the production data-prep + Marcel prior + shrinkage + drift
features so each validate_<signal>.py only has to add the candidate
column and run cross_year_eval.

Mirrors the prep flow in src/plv_clone/models/xfp/rp3.py main(). If the
production prep changes, this file must change too.
"""
from __future__ import annotations
import warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np

import sys as _sys
from plv_clone.paths import ROOT as _ROOT
_sys.path.insert(0, str(_ROOT))
from scripts.xfp.lib.rule9 import rule9_lift  # position-agnostic Rule-9 scoring

from plv_clone.models.xfp.rp3 import (
    RP3_FEATS, cross_year_eval, ROLLING_CSV, MULTIYR_CSV, IL_CSV,
    ROS_SCHED_CSV, SHRINK_SPEC_TO, SHRINK_SPEC_LAST21, build_prior_table,
    compute_population_means, apply_shrinkage, TRAIN_YEARS,
)


def _cye(df: pd.DataFrame, feats: list[str]):
    """Tolerant unpack of rp3.cross_year_eval.

    2026-07-04 the production signature grew a third return value (the
    per-prediction residual detail frame for CI fitting). The harness only
    needs (per_year, overall); this shim keeps every validate_<signal>.py
    working across both signatures.
    """
    out = cross_year_eval(df, feats)
    return out[0], out[1]


def prep_rolling() -> pd.DataFrame:
    """Reproduce production rp3 data-prep so cross_year_eval matches.

    Returns the rolling DataFrame with:
      - Marcel prior merged (prior_fp_per_start, prior_gs_eff)
      - IL features merged + imputed
      - Shrinkage applied (_sh columns)
      - 6 drift features (delta_velo / swstr / k_pct / bb_pct / chase / zone)

    The expected cross_year_r on this DataFrame with RP3_FEATS is 0.5509
    (matches production rp3.main()).
    """
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    il = pd.read_csv(IL_CSV)

    # Marcel prior
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff'] = rolling['prior_gs_eff'].fillna(0.0)

    # IL
    rolling = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    rolling['il_stints_to'] = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split'] = rolling['is_on_il_at_split'].fillna(0).astype(int)
    max_dsr = float(rolling['days_since_il_return'].max(skipna=True) or 200)
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)

    # Shrinkage
    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    pop_l21 = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)

    # Drift features (already in RP3_FEATS)
    rolling['delta_velo']    = rolling['avg_velo_last21']   - rolling['avg_velo_to']
    rolling['delta_swstr']   = rolling['swstr_pct_last21']  - rolling['swstr_pct_to']
    rolling['delta_k_pct']   = rolling['k_pct_last21']      - rolling['k_pct_to']
    rolling['delta_bb_pct']  = rolling['bb_pct_last21']     - rolling['bb_pct_to']
    rolling['delta_chase']   = rolling['o_swing_pct_last21']- rolling['o_swing_pct_to']
    rolling['delta_zone']    = rolling['zone_pct_last21']   - rolling['zone_pct_to']
    for c in ('delta_velo', 'delta_swstr', 'delta_k_pct', 'delta_bb_pct',
              'delta_chase', 'delta_zone'):
        rolling[c] = rolling[c].fillna(0.0)

    # RoS schedule-strength feature — in RP3_FEATS since 2026-05-24 but this
    # prep was never updated, so baselines silently dropped every row at the
    # dropna(feats) step (audit 2026-07-09). Merge mirrors rp3.main().
    if not ROS_SCHED_CSV.exists():
        raise FileNotFoundError(
            f'Missing required RoS schedule cache: {ROS_SCHED_CSV}. '
            'Run scripts/xfp/build_ros_schedule_features.py.')
    sched_xw = pd.read_csv(ROS_SCHED_CSV)[
        ['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']
    ]
    rolling = rolling.merge(sched_xw, on=['pitcher', 'year', 'split_day'], how='left')
    year_means = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
    rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(year_means)
    rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(
        rolling['ros_opp_xwoba_weighted'].mean()
    )

    return rolling


def attach_prior_year_feature(
    rolling: pd.DataFrame,
    source_csv: str,
    source_col: str,
    new_col: str,
    *,
    min_gs: int = 5,
) -> pd.DataFrame:
    """Merge a prior-year column from a (pitcher, year) source CSV.

    Each row gets the prior-year (year - 1) value of `source_col` from
    `source_csv` joined on pitcher. Pitchers without a prior-year row
    (rookies / IL all year) get NaN, which the validation script must
    fill with a sentinel before passing to cross_year_eval.

    Parameters
    ----------
    rolling : the prepared rolling DataFrame from prep_rolling()
    source_csv : absolute path to a CSV with at least (pitcher, year, source_col)
    source_col : the column name in source CSV to pull
    new_col : the name to give the merged column in rolling
    min_gs : if source CSV has a 'gs' column, require ≥ this many starts
             for the source row to count (filters out cup-of-coffee garbage)
    """
    src = pd.read_csv(source_csv)
    keep_cols = ['pitcher', 'year', source_col]
    if 'gs' in src.columns:
        src = src[src['gs'] >= min_gs]
    src = src[keep_cols].rename(columns={source_col: new_col})
    src = src.dropna(subset=[new_col]).copy()
    # Shift to next year: a value at year T is used as PRIOR for year T+1
    src['year'] = src['year'] + 1
    return rolling.merge(src, on=['pitcher', 'year'], how='left')


def evaluate_candidate(
    rolling: pd.DataFrame,
    candidate_col: str,
    *,
    fill_value: float | None = None,
    label: str | None = None,
) -> dict:
    """Run the standard Rule 9 lift test: full RP3_FEATS vs full + candidate.

    Returns dict with keys:
      r_baseline, r_full, lift, per_year_baseline, per_year_full,
      sign_match_years, n_total_years, holdout_lift, n_full, n_baseline
    """
    label = label or candidate_col
    df = rolling.copy()

    if fill_value is not None and candidate_col in df.columns:
        df[candidate_col] = df[candidate_col].fillna(fill_value)

    if candidate_col not in df.columns:
        raise ValueError(f"{candidate_col} not in rolling DataFrame columns")

    # Baseline: full production RP3_FEATS
    py_base, ov_base = _cye(df, RP3_FEATS)
    py_full, ov_full = _cye(df, RP3_FEATS + [candidate_col])
    # Rule-9 lift scoring (position-agnostic) lives in lib/rule9.
    r9 = rule9_lift(py_base, py_full, r_base=ov_base['r'], r_full=ov_full['r'])

    return {
        'candidate': label,
        'r_baseline': round(ov_base['r'], 4),
        'r_full': round(ov_full['r'], 4),
        'lift': round(r9['lift'], 4),
        'n_baseline': ov_base['n'],
        'n_full': ov_full['n'],
        'per_year_baseline': {y: info['r'] for y, info in sorted(py_base.items())},
        'per_year_full': {y: info['r'] for y, info in sorted(py_full.items())},
        'per_year_lift': r9['per_year_lift'],
        'sign_match_years': r9['sign_match_years'],
        'n_total_years': r9['n_total_years'],
        'holdout_lift': round(r9['holdout_lift'], 4) if r9['holdout_lift'] is not None else None,
    }


def print_report(result: dict, gate: float = 0.005) -> None:
    """Print a standardised report from evaluate_candidate output."""
    print(f"\n=== Candidate: {result['candidate']} ===")
    print(f"  Baseline (RP3_FEATS, {len(RP3_FEATS)} feats): r={result['r_baseline']} n={result['n_baseline']}")
    print(f"  Full     (+ candidate, {len(RP3_FEATS)+1} feats): r={result['r_full']} n={result['n_full']}")
    print(f"  LIFT = {result['lift']:+.4f}  (gate: ≥ +{gate:.3f})")
    print(f"\n  Per-year lift (full - baseline):")
    for y, d in result['per_year_lift'].items():
        marker = '+' if d > 0 else '-'
        print(f"    {y}: {d:+.4f}  {marker}")
    print(f"\n  Sign consistency: {result['sign_match_years']}/{result['n_total_years']} years positive")
    if result['holdout_lift'] is not None:
        print(f"  Holdout (2024-2025) avg lift: {result['holdout_lift']:+.4f}")
    print(f"\n  Gates:")
    print(f"    (a) Lift ≥ +{gate:.3f}? {'PASS' if result['lift'] >= gate else 'FAIL/MARGINAL'} ({result['lift']:+.4f})")
    print(f"    (b) Sign ≥ 5 of 7?      {'PASS' if result['sign_match_years'] >= 5 else 'FAIL'} ({result['sign_match_years']}/{result['n_total_years']})")
    if result['holdout_lift'] is not None:
        ho_pass = result['holdout_lift'] > 0
        print(f"    (c) Holdout sign +?     {'PASS' if ho_pass else 'FAIL'} ({result['holdout_lift']:+.4f})")
