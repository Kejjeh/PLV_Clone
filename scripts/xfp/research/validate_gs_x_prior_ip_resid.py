"""validate_gs_x_prior_ip_resid.py — interaction-term candidate for rp3.

Pre-registered: data/research/validation_runs/gs_x_prior_ip_resid_2026-05-24.md

interaction = gs_to * prior_ip_resid
  prior_ip_resid = prior-year ip_per_start (sp_multiyr, gs>=5) MINUS cohort mean
  NaN prior filled with 0 (mean residual) -> interaction contribution = 0
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import (
    prep_rolling, evaluate_candidate, print_report, attach_prior_year_feature,
)
from plv_clone.models.xfp.rp3 import MULTIYR_CSV


def main():
    print('=== validate_gs_x_prior_ip_resid: interaction = gs_to * prior_ip_resid ===')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    # Build prior_ip_per_start by attaching prior-year ip_per_start
    rolling = attach_prior_year_feature(
        rolling,
        source_csv=str(MULTIYR_CSV),
        source_col='ip_per_start',
        new_col='prior_ip_per_start',
        min_gs=5,
    )
    nn_prior = rolling['prior_ip_per_start'].notna().sum()
    print(f'  prior_ip_per_start coverage: {nn_prior}/{len(rolling)} ({100*nn_prior/len(rolling):.1f}%)')

    # Residual = prior IP/start − cohort mean (computed on the qualifying rows)
    cohort_mean = float(rolling['prior_ip_per_start'].mean())
    print(f'  cohort mean prior ip_per_start: {cohort_mean:.3f}')
    rolling['prior_ip_resid'] = rolling['prior_ip_per_start'] - cohort_mean
    rolling['prior_ip_resid'] = rolling['prior_ip_resid'].fillna(0.0)

    col = 'gs_x_prior_ip_resid'
    rolling[col] = rolling['gs_to'] * rolling['prior_ip_resid']
    nn = rolling[col].notna().sum()
    print(f'  {col} non-null: {nn}/{len(rolling)} ({100*nn/len(rolling):.1f}%)')
    print(f'  {col} range: [{rolling[col].min():.3f}, {rolling[col].max():.3f}], mean={rolling[col].mean():.3f}')

    result = evaluate_candidate(rolling, col, fill_value=0.0, label=col)
    print_report(result)
    print(f'\nSUMMARY: {col} lift={result["lift"]:+.4f}  '
          f'sign={result["sign_match_years"]}/{result["n_total_years"]}  '
          f"holdout={result['holdout_lift']:+.4f}")


if __name__ == '__main__':
    main()
