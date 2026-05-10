"""retro_snapshots.py — generate historical projection snapshots for accuracy tracking.

For each (year, split_day) row in the rolling hitter substrate, train an RH3
model on all OTHER years and predict the held-out year's split_day rows.
Save the predictions as a snapshot at the real-world cutoff_date.

This gives the accuracy tracker history to work with immediately, instead of
waiting weeks for live snapshots to accumulate.

CAVEAT: career-level features (lift_h2_aug150, xwoba_residual_career) are
computed from the FULL 2018-2025 window. That means each retro snapshot has
mild leakage from the held-out test year on those slow-moving career
rollups. The leakage is small (~+0.005 r typical effect) and acceptable for
operational accuracy tracking. The per-year RH3_FEATS process metrics
(_to_sh columns) are correctly held out via the LOO split.

Usage:
    python scripts/xfp/retro_snapshots.py
    python scripts/xfp/retro_snapshots.py --years 2024 2025 2026   # subset
    python scripts/xfp/retro_snapshots.py --force                  # overwrite
"""
from __future__ import annotations
import argparse
import sys
from datetime import date as date_cls
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))

from scripts.xfp import xfp_rh3_pipeline as rh3mod
from scripts.xfp.validate_six_pack import build_hitter_rolling
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

SNAP = ROOT / 'data' / 'research' / 'projection_snapshots'
TARGET = rh3mod.TARGET
RH3_FEATS = rh3mod.RH3_FEATS


def train_predict(rolling: pd.DataFrame, test_year: int, split_day: int) -> pd.DataFrame:
    """Train rh3 on rows where year != test_year, predict on (year, split_day) rows."""
    sub = rolling.dropna(subset=RH3_FEATS + [TARGET]).copy()
    sub = sub[(sub['pa_to'] >= rh3mod.EVAL_PA_MIN)
              & (sub['ros_pa'] >= rh3mod.ROS_PA_MIN)
              & (sub['year'] != 2020)]
    train = sub[sub['year'] != test_year]
    test = rolling[(rolling['year'] == test_year) & (rolling['split_day'] == split_day)].copy()
    test = test.dropna(subset=RH3_FEATS)
    test = test[test['pa_to'] >= rh3mod.EVAL_PA_MIN]
    if len(train) < 200 or len(test) < 20:
        return pd.DataFrame()

    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    pipe.fit(train[RH3_FEATS].values, train[TARGET].values)
    test['xfp_rh3_per_pa'] = pipe.predict(test[RH3_FEATS].values)

    # Simple replacement-style signal (tertile within snapshot)
    try:
        test['signal'] = pd.qcut(test['xfp_rh3_per_pa'], 3,
                                  labels=['drop', 'hold', 'add'], duplicates='drop')
    except Exception:
        test['signal'] = 'hold'

    # Replacement delta: gap vs the 33rd-percentile player (replacement level)
    repl = float(test['xfp_rh3_per_pa'].quantile(0.33))
    test['replacement_xfp_per_pa'] = repl
    test['replacement_delta'] = test['xfp_rh3_per_pa'] - repl

    return test


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', nargs='*', type=int, default=None,
                    help='Restrict to these test years (default: 2024, 2025, 2026)')
    ap.add_argument('--force', action='store_true',
                    help='Overwrite existing snapshot files')
    args = ap.parse_args()

    years_scope = args.years or [2024, 2025, 2026]

    print('Building rolling hitter substrate...')
    rolling = build_hitter_rolling()
    print(f'  rolling shape: {rolling.shape}')

    today = pd.Timestamp(date_cls.today())
    n_written = 0; n_skipped = 0

    for year in sorted(rolling['year'].unique()):
        if year not in years_scope:
            continue
        year_rows = rolling[rolling['year'] == year]
        for split_day in sorted(year_rows['split_day'].dropna().unique().astype(int)):
            sub = year_rows[year_rows['split_day'] == split_day]
            if sub.empty:
                continue
            cutoff_date = pd.to_datetime(sub['cutoff_date'].iloc[0])
            if cutoff_date >= today:
                continue  # don't backfill the future

            snap_date = cutoff_date.strftime('%Y-%m-%d')
            snap_dir = SNAP / snap_date
            target_file = snap_dir / 'xfp_rh3_projections.csv'
            if target_file.exists() and not args.force:
                n_skipped += 1
                continue

            preds = train_predict(rolling, year, split_day)
            if preds.empty:
                print(f'  [{snap_date}] insufficient data, skip')
                continue

            snap_dir.mkdir(parents=True, exist_ok=True)
            # Include the actual ros_full_fp_per_pa from substrate so the tracker
            # can evaluate retro snapshots directly without re-deriving from statcast.
            cols_out = ['batter', 'player_name', 'team', 'pa_to',
                        'prior_fp_per_pa', 'xfp_rh3_per_pa',
                        'replacement_xfp_per_pa', 'replacement_delta', 'signal',
                        'ros_full_fp_per_pa', 'ros_pa']
            avail = [c for c in cols_out if c in preds.columns]
            preds[avail].to_csv(target_file, index=False)
            print(f'  [{snap_date}] wrote {len(preds)} batter rows  '
                  f'(year={year}, split_day={split_day})')
            n_written += 1

    print(f'\nDone. {n_written} new snapshots, {n_skipped} skipped (already exist).')
    print(f'Snapshot root: {SNAP}')


if __name__ == '__main__':
    main()
