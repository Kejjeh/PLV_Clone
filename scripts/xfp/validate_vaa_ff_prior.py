"""validate_vaa_ff_prior.py — re-validate prior-year four-seam Vertical
Approach Angle as a candidate rp3 feature.

Pre-registered: data/research/validation_runs/vaa_ff_prior_2026-05-23.md

Tests: does adding pitcher's prior-year mean four-seam VAA (degrees) to
RP3_FEATS beat the +0.005 lift gate?

Theory: flat fastballs (VAA closer to 0 / less negative) get more whiffs
up in the zone — the Strider/Skubal archetype. Not captured by raw
avg_velo_to or by any other current RP3 feature.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import (
    prep_rolling, attach_prior_year_feature, evaluate_candidate, print_report,
)

ROOT = Path(__file__).resolve().parents[2]
SP_STATCAST = ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_statcast_features_2015_2025.csv'


def main():
    print('=== validate_vaa_ff_prior: candidate = prior-year four-seam Vertical Approach Angle ===')

    print('\nPreparing rolling SP substrate (production rp3 data-prep)...')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    print(f'\nMerging prior-year vaa_ff from {SP_STATCAST.name}...')
    rolling = attach_prior_year_feature(
        rolling, str(SP_STATCAST),
        source_col='vaa_ff',
        new_col='vaa_ff_prior',
        min_gs=0,
    )
    nn = rolling['vaa_ff_prior'].notna().sum()
    print(f'  prior-year vaa_ff non-null on rolling: {nn}/{len(rolling)} ({100*nn/len(rolling):.1f}%)')
    print(f'  per-year non-null:')
    for y, n in rolling.dropna(subset=['vaa_ff_prior']).groupby('year').size().items():
        print(f'    {y}: {n}')

    mu = rolling['vaa_ff_prior'].mean()
    print(f'\n  filling NaN with population mean: {mu:.3f} degrees')

    result = evaluate_candidate(
        rolling, 'vaa_ff_prior',
        fill_value=float(mu),
        label='vaa_ff_prior',
    )
    print_report(result)

    print(f'\nSUMMARY: vaa_ff_prior lift={result["lift"]:+.4f}  '
          f'sign={result["sign_match_years"]}/{result["n_total_years"]}  '
          f"holdout={result['holdout_lift']:+.4f}")


if __name__ == '__main__':
    main()
