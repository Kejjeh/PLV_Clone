"""validate_weighted_catcher_framing_to.py

Candidate feature: `weighted_catcher_framing_to` — n-pitches-weighted framing
runs/100 of the SP's PRIOR-year per-start catchers (each start contributes
the catcher of record for that start, weighted by pitch count).

Replaces the modal-catcher proxy (`primary_catcher_framing_runs_prior`) which
was REJECTED at Δr -0.0001. The per-start exposure tracks within-season
catcher swaps, platoons, trades and IL replacements that the modal version
collapses away. If the receiver-quality signal is real, this is where it
surfaces; if this also rejects, the catcher dimension is confirmed dead in
rp3 (drift_swstr + c_plus_swstr_to_sh fully absorb the K-rate consequence).

Build path:
  1. scripts/xfp/build_sp_per_start_catcher.py →
     `data/research/xfp_cache/sp_per_start_catcher_2018_2025.csv`
     `data/research/xfp_cache/sp_weighted_catcher_framing_2018_2025.csv`
  2. For rolling row (pitcher P, year Y), grab the year-(Y-1) row from
     the weighted cache. NaN for rookies / pitchers without a prior-year
     start row → filled with population mean.

Pre-registered: data/research/validation_runs/weighted_catcher_framing_to_2026-05-24.md
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report

CACHE = Path('c:/Users/Joshua/plv_clone/data/research/xfp_cache')
WEIGHTED_CSV = CACHE / 'sp_weighted_catcher_framing_2018_2025.csv'
ROS_SCHED_CSV = CACHE / 'ros_schedule_features_2018_2026.csv'

CANDIDATE = 'weighted_catcher_framing_to'


def attach_ros_schedule(rolling: pd.DataFrame) -> pd.DataFrame:
    """Mirror the merge in rp3.main() so RP3_FEATS resolves cleanly.

    prep_rolling() does NOT include this feature (it lives in main() in
    production rp3.py). Without it, evaluate_candidate fails because
    'ros_opp_xwoba_weighted' is in RP3_FEATS.
    """
    if not ROS_SCHED_CSV.exists():
        raise FileNotFoundError(f'Missing {ROS_SCHED_CSV}')
    sched = pd.read_csv(ROS_SCHED_CSV)[
        ['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']
    ]
    out = rolling.merge(sched, on=['pitcher', 'year', 'split_day'], how='left')
    yr_mean = out.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
    out['ros_opp_xwoba_weighted'] = out['ros_opp_xwoba_weighted'].fillna(yr_mean)
    out['ros_opp_xwoba_weighted'] = out['ros_opp_xwoba_weighted'].fillna(
        out['ros_opp_xwoba_weighted'].mean()
    )
    return out


def attach_weighted_catcher_framing(rolling: pd.DataFrame) -> pd.DataFrame:
    src = pd.read_csv(WEIGHTED_CSV)
    src = src[['pitcher', 'year',
               'weighted_catcher_framing_runs_per_100', 'n_starts']].copy()
    # Year T value used as prior for year T+1 → shift +1
    src['year'] = src['year'] + 1
    src = src.rename(columns={
        'weighted_catcher_framing_runs_per_100': CANDIDATE,
        'n_starts': 'prior_yr_n_starts_for_catcher_weight',
    })
    return rolling.merge(src, on=['pitcher', 'year'], how='left')


def main():
    print('=== validate_weighted_catcher_framing_to: per-start replacement of modal proxy ===')
    print('\nPreparing rolling SP substrate (production rp3 data-prep)...')
    rolling = prep_rolling()
    print(f'  rolling rows: {len(rolling)}')

    rolling = attach_ros_schedule(rolling)
    rolling = attach_weighted_catcher_framing(rolling)
    nn = rolling[CANDIDATE].notna().sum()
    print(f'  {CANDIDATE} non-null: {nn}/{len(rolling)} '
          f'({100*nn/len(rolling):.1f}%)')
    if nn == 0:
        print('  FATAL: zero non-null candidate values. Check merge keys / cache files.')
        sys.exit(1)
    mu = float(rolling[CANDIDATE].mean())
    print(f'  filling NaN with population mean: {mu:.4f} runs/100 (rookies / unmatched)')

    py = rolling.groupby('year')[CANDIDATE].apply(lambda s: s.notna().sum())
    print(f'  per-year non-null:\n{py.to_string()}')

    result = evaluate_candidate(rolling, CANDIDATE, fill_value=mu, label=CANDIDATE)
    print_report(result)
    print(f'\nSUMMARY: {CANDIDATE} lift={result["lift"]:+.4f}  '
          f'sign={result["sign_match_years"]}/{result["n_total_years"]}  '
          f'holdout={result["holdout_lift"]:+.4f}')
    print(f'  vs modal proxy baseline (-0.0001): '
          f'delta = {result["lift"] - (-0.0001):+.4f}')


if __name__ == '__main__':
    main()
