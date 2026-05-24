"""validate_pitch_entropy_prior.py — re-validate prior-year pitch-mix
entropy as a candidate rp3 feature.

Pre-registered: data/research/validation_runs/pitch_entropy_prior_2026-05-23.md

Tests: does adding pitcher's prior-year Shannon entropy of pitch-type
distribution to RP3_FEATS beat the +0.005 lift gate?

Theory: higher entropy = more unpredictable mix = more whiffs / weaker
contact, above-and-beyond the stuff features already in RP3_FEATS.
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
    print('=== validate_pitch_entropy_prior: candidate = prior-year pitch-mix Shannon entropy ===')

    print('\nPreparing rolling SP substrate (production rp3 data-prep)...')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    print(f'\nMerging prior-year pitch_entropy from {SP_STATCAST.name}...')
    # sp_statcast_features has no 'gs' col — min_gs filter is a no-op there,
    # the attach helper handles that path.
    rolling = attach_prior_year_feature(
        rolling, str(SP_STATCAST),
        source_col='pitch_entropy',
        new_col='pitch_entropy_prior',
        min_gs=0,
    )
    nn = rolling['pitch_entropy_prior'].notna().sum()
    print(f'  prior-year pitch_entropy non-null on rolling: {nn}/{len(rolling)} ({100*nn/len(rolling):.1f}%)')
    print(f'  per-year non-null:')
    for y, n in rolling.dropna(subset=['pitch_entropy_prior']).groupby('year').size().items():
        print(f'    {y}: {n}')

    mu = rolling['pitch_entropy_prior'].mean()
    print(f'\n  filling NaN with population mean: {mu:.3f} bits')

    result = evaluate_candidate(
        rolling, 'pitch_entropy_prior',
        fill_value=float(mu),
        label='pitch_entropy_prior',
    )
    print_report(result)

    print(f'\nSUMMARY: pitch_entropy_prior lift={result["lift"]:+.4f}  '
          f'sign={result["sign_match_years"]}/{result["n_total_years"]}  '
          f"holdout={result['holdout_lift']:+.4f}")


if __name__ == '__main__':
    main()
