"""accuracy_tracker.py — compare past projection snapshots to actual fp earned.

For each (snapshot_date, player) in data/research/projection_snapshots/, look up
that player's actual fp_per_pa accumulated SINCE the snapshot date using current
statcast data. Compute:
  - per-snapshot r (predicted vs actual)
  - per-snapshot MAE
  - bias for high-projected vs low-projected players
  - per-signal accuracy (e.g., did BUY-LOW calls actually outperform their pre-call rate?)

Output:
  data/research/accuracy_tracker_summary.csv — one row per snapshot
  prints per-snapshot table + cumulative-mean

Usage:
    python scripts/xfp/accuracy_tracker.py
    python scripts/xfp/accuracy_tracker.py --signal slump   # restrict to slump module
"""
from __future__ import annotations
import argparse
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
SNAP = ROOT / 'data' / 'research' / 'projection_snapshots'
RES = ROOT / 'data' / 'research'

MIN_PA_FOR_EVAL = 20  # need at least this many PA AFTER snapshot to evaluate batter

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


def load_actual_fp(year: int, since_date: pd.Timestamp) -> pd.DataFrame:
    """Per batter, fp_per_pa accumulated from since_date to end of statcast data."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=['game_date', 'batter', 'events'])
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[(df['game_date'] >= since_date) & df['events'].isin(PA_EVENTS)]
    if df.empty:
        return pd.DataFrame()
    df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
    df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
    df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
    df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    df['core_fp'] = df['tb'] + df['bb'] + df['hbp'] - df['k']
    df['pa'] = 1
    agg = df.groupby('batter', as_index=False).agg(
        actual_pa=('pa', 'sum'), actual_core_fp=('core_fp', 'sum'))
    agg['actual_core_fp_per_pa'] = agg['actual_core_fp'] / agg['actual_pa']
    return agg


def evaluate_snapshot(snap_date: str) -> dict | None:
    """Compare projections on snap_date to actual fp/PA outcome.

    Two-mode evaluation:
      A) RETRO snapshots: file already contains ros_full_fp_per_pa (true target
         matching the projection's scale). Use directly. Most accurate.
      B) LIVE snapshots: compute core_fp from statcast since snap_date.
         Approximate (misses R/RBI/SB) but works for future fills.
    """
    snap_dir = SNAP / snap_date
    rh_path = snap_dir / 'xfp_rh3_projections.csv'
    if not rh_path.exists():
        return None
    rh = pd.read_csv(rh_path)
    since = pd.Timestamp(snap_date)
    year = since.year

    # Mode A: retro snapshot with embedded actual target
    if 'ros_full_fp_per_pa' in rh.columns and rh['ros_full_fp_per_pa'].notna().sum() >= 10:
        merged = rh[rh['ros_full_fp_per_pa'].notna() & rh['ros_pa'].fillna(0).ge(50)].copy()
        if len(merged) < 10:
            return None
        pred = merged['xfp_rh3_per_pa']
        act = merged['ros_full_fp_per_pa']
        mode = 'retro_substrate'
    else:
        # Mode B: live snapshot — derive from statcast going forward
        actual = load_actual_fp(year, since)
        if actual.empty:
            return None
        merged = rh.merge(actual, on='batter', how='inner')
        merged = merged[merged['actual_pa'] >= MIN_PA_FOR_EVAL]
        if len(merged) < 10:
            return None
        pred = merged['xfp_rh3_per_pa']
        act = merged['actual_core_fp_per_pa']
        mode = 'live_statcast'
    r = float(np.corrcoef(pred, act)[0, 1])
    mae = float(np.mean(np.abs(pred - act)))

    # Bias: high-projected vs low-projected players (residual quartile gap)
    merged['resid'] = pred - act
    q_lo = merged['xfp_rh3_per_pa'].quantile(0.25)
    q_hi = merged['xfp_rh3_per_pa'].quantile(0.75)
    bias_top = float(merged[merged['xfp_rh3_per_pa'] >= q_hi]['resid'].mean())
    bias_bot = float(merged[merged['xfp_rh3_per_pa'] <= q_lo]['resid'].mean())

    # Signal accuracy: did "add" players outperform "drop" players?
    actual_col = 'ros_full_fp_per_pa' if mode == 'retro_substrate' else 'actual_core_fp_per_pa'
    if 'signal' in merged.columns:
        add_act = merged[merged['signal'] == 'add'][actual_col].mean()
        drop_act = merged[merged['signal'] == 'drop'][actual_col].mean()
        signal_gap = float(add_act - drop_act) if pd.notna(add_act) and pd.notna(drop_act) else np.nan
    else:
        signal_gap = np.nan

    # Slump module: did BUY-LOW (slump_pct_rank low + bounce_pct high) outperform their pre-call rate?
    slump_lift = np.nan
    if 'slump_pct_rank' in merged.columns and 'slump_bounce_pct' in merged.columns:
        buy_low = merged[(merged['slump_pct_rank'].fillna(50) <= 25)
                         & (merged['slump_bounce_pct'].fillna(0) >= 70)]
        if len(buy_low) >= 5 and 'prior_fp_per_pa' in buy_low.columns:
            slump_lift = float(buy_low[actual_col].mean() - buy_low['prior_fp_per_pa'].mean())

    mean_pa = float(merged['ros_pa'].mean()) if 'ros_pa' in merged.columns else (
        float(merged['actual_pa'].mean()) if 'actual_pa' in merged.columns else np.nan)
    return {
        'snap_date': snap_date,
        'mode': mode,
        'n_batters': len(merged),
        'mean_pa_window': round(mean_pa, 1) if not np.isnan(mean_pa) else None,
        'r': round(r, 4),
        'mae': round(mae, 4),
        'bias_top_quartile': round(bias_top, 4),
        'bias_bot_quartile': round(bias_bot, 4),
        'add_vs_drop_actual_gap': round(signal_gap, 4) if not np.isnan(signal_gap) else None,
        'buy_low_bounce_lift': round(slump_lift, 4) if not np.isnan(slump_lift) else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--signal', choices=['slump', 'add_drop'], help='Restrict to one signal type')
    args = ap.parse_args()

    if not SNAP.exists():
        print(f'No snapshot directory at {SNAP}. Run snapshot_projections.py first.')
        return
    snap_dates = sorted([d.name for d in SNAP.iterdir() if d.is_dir()])
    if not snap_dates:
        print(f'No snapshots in {SNAP}. Run snapshot_projections.py first.')
        return

    print(f'Evaluating {len(snap_dates)} snapshots:')
    rows = []
    for sd in snap_dates:
        res = evaluate_snapshot(sd)
        if res is None:
            print(f'  {sd}: insufficient data')
            continue
        rows.append(res)
        print(f"  {sd} [{res['mode']:>14s}]: n={res['n_batters']:>3}, r={res['r']:+.4f}, mae={res['mae']:.4f}, "
              f"bias_top={res['bias_top_quartile']:+.4f}, bias_bot={res['bias_bot_quartile']:+.4f}, "
              f"add−drop_gap={res['add_vs_drop_actual_gap'] if res['add_vs_drop_actual_gap'] is not None else 'n/a'}")

    if rows:
        out = pd.DataFrame(rows)
        out.to_csv(RES / 'accuracy_tracker_summary.csv', index=False)
        print(f'\nWrote {RES / "accuracy_tracker_summary.csv"}')

        print('\n=== Cumulative model accuracy ===')
        print(f'  mean r across {len(rows)} snapshots: {out["r"].mean():+.4f}')
        print(f'  mean MAE: {out["mae"].mean():.4f}')
        print(f'  bias top-quartile (over/under-projection): {out["bias_top_quartile"].mean():+.4f}')
        print(f'  bias bottom-quartile: {out["bias_bot_quartile"].mean():+.4f}')
        if out['add_vs_drop_actual_gap'].notna().any():
            print(f'  add vs drop gap (positive = good): {out["add_vs_drop_actual_gap"].mean():+.4f}')


if __name__ == '__main__':
    main()
