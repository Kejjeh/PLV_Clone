"""validate_c_plus_swstr_last21.py — test raw L21 CSW as rp3 feature.

Pre-registered: data/research/validation_runs/c_plus_swstr_last21_2026-05-24.md
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report


def main():
    print('=== validate_c_plus_swstr_last21: candidate = raw L21 CSW per pitch ===')
    print('\nPreparing rolling SP substrate (production rp3 data-prep)...')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    col = 'c_plus_swstr_last21'
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
