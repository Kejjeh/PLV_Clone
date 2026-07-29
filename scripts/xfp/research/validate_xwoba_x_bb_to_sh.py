"""validate_xwoba_x_bb_to_sh.py — interaction-term candidate for rp3.

Pre-registered: data/research/validation_runs/xwoba_x_bb_to_sh_2026-05-24.md

interaction = xwoba_per_pa_to_sh * bb_pct_to_sh
Expected coef sign: NEGATIVE (both factors are "bad" — product is badness²;
higher product -> lower FP/start).
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report


def main():
    print('=== validate_xwoba_x_bb_to_sh: interaction = xwoba_per_pa_to_sh * bb_pct_to_sh ===')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    col = 'xwoba_x_bb_to_sh'
    rolling[col] = rolling['xwoba_per_pa_to_sh'] * rolling['bb_pct_to_sh']
    nn = rolling[col].notna().sum()
    print(f'  {col} non-null: {nn}/{len(rolling)} ({100*nn/len(rolling):.1f}%)')
    mu = float(rolling[col].mean())

    result = evaluate_candidate(rolling, col, fill_value=mu, label=col)
    print_report(result)
    print(f'\nSUMMARY: {col} lift={result["lift"]:+.4f}  '
          f'sign={result["sign_match_years"]}/{result["n_total_years"]}  '
          f"holdout={result['holdout_lift']:+.4f}")


if __name__ == '__main__':
    main()
