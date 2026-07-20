"""validate_fp_per_start_last21.py — test raw L21 FP/start as rp3 feature.

Pre-registered: data/research/validation_runs/fp_per_start_last21_2026-05-28.md

RP3_FEATS contains fp_per_start_to (cumulative) but no L21d FP level and no
delta_fp. This script tests whether adding the L21d FP level as a composite
recency anchor adds incremental lift on top of the existing 23-feature
production baseline.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report


def main():
    print('=== validate_fp_per_start_last21: candidate = raw L21 FP/start (composite recency anchor) ===')
    print('\nPreparing rolling SP substrate (production rp3 data-prep)...')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    # Attach ros_opp_xwoba_weighted (in RP3_FEATS, not added by prep_rolling)
    from plv_clone.models.xfp.rp3 import ROS_SCHED_CSV
    if ROS_SCHED_CSV.exists():
        sched = pd.read_csv(ROS_SCHED_CSV)[['pitcher','year','split_day','ros_opp_xwoba_weighted']]
        rolling = rolling.merge(sched, on=['pitcher','year','split_day'], how='left')
        ym = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
        rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(ym)
        rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(
            rolling['ros_opp_xwoba_weighted'].mean())
        print('  ros_opp_xwoba_weighted joined OK')
    else:
        raise FileNotFoundError(f'Missing {ROS_SCHED_CSV}')

    col = 'fp_per_start_last21'
    nn = rolling[col].notna().sum()
    print(f'  {col} non-null: {nn}/{len(rolling)} ({100*nn/len(rolling):.1f}%)')
    mu = float(rolling[col].mean())
    print(f'  filling NaN with population mean: {mu:.4f}')

    result = evaluate_candidate(rolling, col, fill_value=mu, label=col)
    print_report(result)
    print(f'\nSUMMARY: {col} lift={result["lift"]:+.4f}  '
          f'sign={result["sign_match_years"]}/{result["n_total_years"]}  '
          f"holdout={result['holdout_lift']:+.4f}")


if __name__ == '__main__':
    main()
