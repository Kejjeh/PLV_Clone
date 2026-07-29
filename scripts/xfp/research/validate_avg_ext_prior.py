"""validate_avg_ext_prior.py — re-validate prior-year extension (avg_ext)
as a candidate rp3 feature.

Pre-registered: data/research/validation_runs/avg_ext_prior_2026-05-23.md

Tests: does adding pitcher's prior-year mean release-extension (in feet)
to RP3_FEATS beat the +0.005 lift gate?

Theory: extension is a stable mechanical trait that drives perceived
velocity / pitch tunneling on top of raw avg_velo_to, and is not in
the current RP3_FEATS list.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Make harness importable
sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import (
    prep_rolling, attach_prior_year_feature, evaluate_candidate, print_report,
)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
SP_MULTIYR = ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv'


def main():
    print('=== validate_avg_ext_prior: candidate = prior-year mean release extension ===')

    print('\nPreparing rolling SP substrate (production rp3 data-prep)...')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    print(f'\nMerging prior-year avg_ext from {SP_MULTIYR.name}...')
    rolling = attach_prior_year_feature(
        rolling, str(SP_MULTIYR),
        source_col='avg_ext',
        new_col='avg_ext_prior',
        min_gs=5,
    )
    nn = rolling['avg_ext_prior'].notna().sum()
    print(f'  prior-year avg_ext non-null on rolling: {nn}/{len(rolling)} ({100*nn/len(rolling):.1f}%)')
    print(f'  per-year non-null:')
    for y, n in rolling.dropna(subset=['avg_ext_prior']).groupby('year').size().items():
        print(f'    {y}: {n}')

    # Fill missing with population mean so cross_year_eval doesn't drop rows
    mu = rolling['avg_ext_prior'].mean()
    print(f'\n  filling NaN with population mean: {mu:.3f} feet')

    result = evaluate_candidate(
        rolling, 'avg_ext_prior',
        fill_value=float(mu),
        label='avg_ext_prior',
    )
    print_report(result)

    # Print summary line for easy grep in commit
    print(f'\nSUMMARY: avg_ext_prior lift={result["lift"]:+.4f}  '
          f'sign={result["sign_match_years"]}/{result["n_total_years"]}  '
          f"holdout={result['holdout_lift']:+.4f}")


if __name__ == '__main__':
    main()
