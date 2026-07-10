"""_rprs2_validation_harness.py — shared data-prep helpers for rprs2
candidate-feature validation scripts.

Mirrors the prep + evaluation flow in src/plv_clone/models/xfp/rprs2.py
main(). rprs2 needs no extra prep beyond reading the rolling CSV (unlike
rp3's Marcel/IL/shrinkage stack) — its lag1 features are pre-built and
mean-imputed inside rolling_relievers_2018_2026.csv. If the production
prep changes, this file must change too.

Structural pattern follows scripts/xfp/_rp3_validation_harness.py.
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

from plv_clone.models.xfp.rprs2 import (
    FEATS_RPRS2, BASE_FEATS, TRAIN_YEARS, TARGET, EVAL_G_MIN,
    ROLLING_CSV, cross_year_eval, role_change_mask, _masked_overall,
)

LEVERAGE_CSV = _ROOT / 'data' / 'research' / 'xfp_cache' / 'fangraphs_rp_leverage_2018_2026.csv'


def prep_rolling() -> pd.DataFrame:
    """Reproduce production rprs2 data-prep so cross_year_eval matches.

    Production main() reads the rolling CSV directly with no further
    feature engineering (all *_to and *_lag1 columns are pre-built), so
    this is a plain read. Kept as a function so validation scripts stay
    insulated if rprs2 ever grows a prep stage.
    """
    return pd.read_csv(ROLLING_CSV)


def attach_leverage_lag1(rolling: pd.DataFrame) -> pd.DataFrame:
    """Merge prior-year FanGraphs leverage features onto the rolling panel.

    Joins fangraphs_rp_leverage_2018_2026.csv (keyed by mlbam `mlb_id`,
    season) on (pitcher, year-1). Adds three candidate columns, each
    mean-imputed with the population mean of OBSERVED lag values (global
    scalar, matching the rolling-builder's own lag1 imputation pattern —
    e.g. g_lag1 sentinel 45.4249):

      pli_lag1          prior-year pLI
      gmli_lag1         prior-year gmLI
      sd_md_per_g_lag1  prior-year (shutdowns - meltdowns) / g

    Also adds `has_lev_lag1` (0/1) for DIAGNOSTIC reporting only — it is
    NOT a declared candidate feature (has-prior structure is already
    carried by role_*_lag1 dummies).
    """
    lev = pd.read_csv(LEVERAGE_CSV)
    lev = lev.dropna(subset=['mlb_id', 'season']).copy()
    lev['mlb_id'] = lev['mlb_id'].astype(int)
    lev['season'] = lev['season'].astype(int)
    assert not lev.duplicated(['mlb_id', 'season']).any(), \
        'duplicate (mlb_id, season) keys in leverage file'

    lev['sd_md_per_g'] = (lev['shutdowns'] - lev['meltdowns']) / lev['g'].replace(0, np.nan)
    src = lev[['mlb_id', 'season', 'pli', 'gmli', 'sd_md_per_g']].rename(columns={
        'mlb_id': 'pitcher',
        'pli': 'pli_lag1',
        'gmli': 'gmli_lag1',
        'sd_md_per_g': 'sd_md_per_g_lag1',
    })
    # Shift to next year: season T values serve as PRIOR for outcome year T+1
    src['year'] = src['season'] + 1
    src = src.drop(columns=['season'])

    out = rolling.merge(src, on=['pitcher', 'year'], how='left')
    out['has_lev_lag1'] = out['pli_lag1'].notna().astype(int)
    for c in ('pli_lag1', 'gmli_lag1', 'sd_md_per_g_lag1'):
        out[c] = out[c].fillna(out[c].mean())
    return out


def evaluate_candidate(
    rolling: pd.DataFrame,
    candidate_cols: list[str] | str,
    *,
    label: str | None = None,
    baseline_extra: list[str] | None = None,
) -> dict:
    """Rule-9 lift test vs the FULL production FEATS_RPRS2 baseline, plus
    rprs2's stratified role-change-subset check.

    candidate_cols may be one column or several (for the redundancy step).
    baseline_extra lets the redundancy step use FEATS_RPRS2 + best_cell as
    the baseline.

    Returns dict with: r_baseline, r_full, lift, per_year_lift,
    sign_match_years, n_total_years, holdout_lift, rc_r_baseline,
    rc_r_full, rc_lift, n (pooled rows).
    """
    if isinstance(candidate_cols, str):
        candidate_cols = [candidate_cols]
    label = label or '+'.join(candidate_cols)

    base_feats = FEATS_RPRS2 + (baseline_extra or [])
    full_feats = base_feats + candidate_cols

    for c in full_feats:
        if c not in rolling.columns:
            raise ValueError(f'{c} not in rolling DataFrame columns')

    rc_mask = role_change_mask(rolling)

    py_base, ov_base, det_base = cross_year_eval(rolling, base_feats)
    rc_base = _masked_overall(det_base, rc_mask)
    py_full, ov_full, det_full = cross_year_eval(rolling, full_feats)
    rc_full = _masked_overall(det_full, rc_mask)

    # Sample-alignment guard: mean-imputed candidates must not change n
    assert ov_base['n'] == ov_full['n'], \
        f'sample drift: baseline n={ov_base["n"]} vs full n={ov_full["n"]}'

    r9 = rule9_lift(py_base, py_full, r_base=ov_base['r'], r_full=ov_full['r'])

    return {
        'candidate': label,
        'n': ov_base['n'],
        'r_baseline': round(ov_base['r'], 4),
        'r_full': round(ov_full['r'], 4),
        'lift': round(r9['lift'], 4),
        'per_year_baseline': {y: info['r'] for y, info in sorted(py_base.items())},
        'per_year_full': {y: info['r'] for y, info in sorted(py_full.items())},
        'per_year_lift': r9['per_year_lift'],
        'sign_match_years': r9['sign_match_years'],
        'n_total_years': r9['n_total_years'],
        'holdout_lift': round(r9['holdout_lift'], 4) if r9['holdout_lift'] is not None else None,
        'rc_n': rc_base['n'],
        'rc_r_baseline': rc_base['r'],
        'rc_r_full': rc_full['r'],
        'rc_lift': round(rc_full['r'] - rc_base['r'], 4)
                   if pd.notna(rc_full['r']) and pd.notna(rc_base['r']) else None,
    }


def print_report(result: dict, gate: float = 0.005) -> None:
    """Standardised gate report (rprs2 feature-addition variant)."""
    print(f"\n=== Candidate: {result['candidate']} ===")
    print(f"  Baseline (FEATS_RPRS2 stack): r={result['r_baseline']}  n={result['n']}")
    print(f"  Full (+ candidate):           r={result['r_full']}")
    print(f"  LIFT = {result['lift']:+.4f}  (gate: >= +{gate:.3f})")
    print(f"  Per-year lift:")
    for y, d in result['per_year_lift'].items():
        print(f"    {y}: {d:+.4f}")
    print(f"  Sign consistency: {result['sign_match_years']}/{result['n_total_years']} years positive")
    print(f"  Holdout (2024-2025) avg lift: {result['holdout_lift']:+.4f}")
    print(f"  Role-change subset (n={result['rc_n']}): "
          f"r {result['rc_r_baseline']} -> {result['rc_r_full']}  "
          f"delta {result['rc_lift']:+.4f}")
    print(f"  Gates:")
    print(f"    (1) overall lift >= +{gate:.3f}?  "
          f"{'PASS' if result['lift'] >= gate else 'FAIL'} ({result['lift']:+.4f})")
    print(f"    (2) role-change no regression?  "
          f"{'PASS' if (result['rc_lift'] is not None and result['rc_lift'] >= 0.0) else 'FAIL'} "
          f"({result['rc_lift']:+.4f})")
    print(f"    (3) sign >= 5 of {result['n_total_years']}?          "
          f"{'PASS' if result['sign_match_years'] >= 5 else 'FAIL'} "
          f"({result['sign_match_years']}/{result['n_total_years']})")
    ho = result['holdout_lift']
    print(f"    (4) holdout 2024-25 > 0?        "
          f"{'PASS' if (ho is not None and ho > 0) else 'FAIL'} ({ho:+.4f})")
