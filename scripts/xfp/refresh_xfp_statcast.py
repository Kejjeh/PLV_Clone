"""refresh_xfp_statcast.py — update xfp_cache/statcast_{year}.parquet incrementally.

The xfp_cache parquet is built by build_sp_multiyr.py once and never refreshed
(it short-circuits if file exists). This script pulls only the missing
date range (from current max+1 day through today-2-day-lag) and appends.
"""
from __future__ import annotations
import argparse
import time
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

from plv_clone.paths import ROOT
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=date.today().year)
    ap.add_argument('--lag', type=int, default=2,
                    help='days behind today considered available (statcast lag)')
    args = ap.parse_args()

    path = CACHE / f'statcast_{args.year}.parquet'
    if not path.exists():
        print(f'No existing cache at {path} — run build_sp_multiyr.py for full pull')
        return

    existing = pd.read_parquet(path)
    existing['game_date'] = pd.to_datetime(existing['game_date'])
    last_date = existing['game_date'].max().date()
    available_through = date.today() - timedelta(days=args.lag)
    pull_start = last_date + timedelta(days=1)
    pull_end = available_through

    print(f'Existing cache: {len(existing):,} rows, max={last_date}')
    print(f'Pull window: {pull_start} → {pull_end}')

    if pull_start > pull_end:
        print('  cache already up to date')
        return

    import pybaseball as pb
    pb.cache.enable()

    t0 = time.time()
    print(f'  pulling pybaseball.statcast {pull_start} → {pull_end}...', flush=True)
    new_df = pb.statcast(start_dt=str(pull_start), end_dt=str(pull_end), verbose=False)
    new_df = new_df[new_df['game_type'] == 'R'].copy()
    print(f'  pulled {len(new_df):,} pitches in {time.time()-t0:.0f}s')

    if new_df.empty:
        print('  no new rows — likely off days')
        return

    # Align columns — keep intersection plus existing-only cols filled NaN
    new_df['game_date'] = pd.to_datetime(new_df['game_date'])
    new_cols = set(new_df.columns)
    old_cols = set(existing.columns)
    missing_in_new = old_cols - new_cols
    missing_in_old = new_cols - old_cols
    if missing_in_new:
        print(f'  cols in existing not in pull (will fill NaN): {len(missing_in_new)}')
        for c in missing_in_new:
            new_df[c] = pd.NA
    if missing_in_old:
        print(f'  cols in pull not in existing (will fill NaN): {len(missing_in_old)}')
        for c in missing_in_old:
            existing[c] = pd.NA
    # Align column order
    cols = existing.columns.tolist()
    new_df = new_df[cols]

    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.drop_duplicates(
        subset=['game_pk', 'at_bat_number', 'pitch_number'], keep='last'
    ) if 'game_pk' in combined.columns else combined

    print(f'  combined rows: {len(combined):,} (gain +{len(combined)-len(existing):,})')
    print(f'  new max date: {combined["game_date"].max().date()}')

    backup = path.with_suffix('.parquet.bak')
    if backup.exists(): backup.unlink()
    path.rename(backup)
    combined.to_parquet(path, index=False)
    print(f'  wrote {path}')
    print(f'  backup at {backup}')


if __name__ == '__main__':
    main()
