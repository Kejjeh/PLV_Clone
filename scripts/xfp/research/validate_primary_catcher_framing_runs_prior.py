"""validate_primary_catcher_framing_runs_prior.py

Candidate feature: prior-year framing runs of the SP's prior-year primary
catcher. Tests whether catcher framing skill (orthogonal to RP3_FEATS) adds
predictive lift to rp3.

Build path:
  1. catcher_framing_2017_2025.csv (per catcher × year framing_runs_per_100)
  2. sp_primary_catcher_2018_2025.csv (per pitcher × year modal catcher)
  3. For each (pitcher, year) row in rolling, look up the pitcher's
     prior-year (year-1) primary catcher, then that catcher's prior-year
     framing_runs_per_100. The "prior" both-shifts: forecasting RoS year T
     from the framing skill of the catcher that year T-1 caught most of
     this pitcher's pitches. NaN for rookies and pitchers whose prior-year
     primary catcher is missing a framing row.

Pre-registered: data/research/validation_runs/primary_catcher_framing_runs_prior_2026-05-24.md
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report

CACHE = Path('c:/Users/Joshua/plv_clone/data/research/xfp_cache')
FRAMING_CSV = CACHE / 'catcher_framing_2017_2025.csv'
PRIMARY_CSV = CACHE / 'sp_primary_catcher_2018_2025.csv'


def attach_primary_catcher_framing(rolling: pd.DataFrame) -> pd.DataFrame:
    fr = pd.read_csv(FRAMING_CSV)
    pc = pd.read_csv(PRIMARY_CSV)

    # Step 1: pitcher's PRIOR-year primary catcher.
    # i.e., for rolling row (pitcher P, year Y), grab pc[(P, Y-1)].primary_catcher.
    pc_prior = pc[['pitcher', 'year', 'primary_catcher', 'primary_catcher_pitches']].copy()
    pc_prior['year'] = pc_prior['year'] + 1
    pc_prior = pc_prior.rename(columns={
        'primary_catcher': 'prior_primary_catcher',
        'primary_catcher_pitches': 'prior_primary_catcher_pitches',
    })

    # Step 2: that catcher's framing in the SAME prior year (year-1).
    fr_prior = fr[['catcher_mlbam', 'year', 'framing_runs_per_100',
                   'shadow_pitches']].copy()
    fr_prior['year'] = fr_prior['year'] + 1  # use as prior for next-year forecast
    fr_prior = fr_prior.rename(columns={
        'catcher_mlbam': 'prior_primary_catcher',
        'framing_runs_per_100': 'primary_catcher_framing_runs_prior',
        'shadow_pitches': 'prior_primary_catcher_shadow_pitches',
    })

    out = rolling.merge(pc_prior, on=['pitcher', 'year'], how='left')
    out = out.merge(fr_prior, on=['prior_primary_catcher', 'year'], how='left')
    return out


def main():
    print('=== validate_primary_catcher_framing_runs_prior: candidate = prior-yr framing of prior-yr primary catcher ===')
    print('\nPreparing rolling SP substrate (production rp3 data-prep)...')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    rolling = attach_primary_catcher_framing(rolling)
    col = 'primary_catcher_framing_runs_prior'
    nn = rolling[col].notna().sum()
    print(f'  {col} non-null: {nn}/{len(rolling)} ({100*nn/len(rolling):.1f}%)')
    if nn == 0:
        print('  FATAL: zero non-null candidate values. Check merge keys / cache files.')
        sys.exit(1)
    mu = float(rolling[col].mean())
    print(f'  filling NaN with population mean: {mu:.4f} runs/100 (rookies / unmatched catchers)')

    # Sanity: per-year non-null
    py = rolling.groupby('year')[col].apply(lambda s: s.notna().sum())
    print(f'  per-year non-null:\n{py.to_string()}')

    result = evaluate_candidate(rolling, col, fill_value=mu, label=col)
    print_report(result)
    print(f'\nSUMMARY: {col} lift={result["lift"]:+.4f}  '
          f'sign={result["sign_match_years"]}/{result["n_total_years"]}  '
          f'holdout={result["holdout_lift"]:+.4f}')


if __name__ == '__main__':
    main()
