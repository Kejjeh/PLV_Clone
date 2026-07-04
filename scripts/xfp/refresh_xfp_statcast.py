"""refresh_xfp_statcast.py — update xfp_cache/statcast_{year}.parquet incrementally.

The xfp_cache parquet is built by build_sp_multiyr.py once and never refreshed
(it short-circuits if file exists). Each run does two passes:

1. Tail pull — the missing date range (current max+1 day through today-lag).
2. Gap repair — the gf bridge (build_statcast_gf_bridge.py) writes provisional
   rows for recent days, which advances max(game_date) past any day it failed
   on, so the tail pull alone never revisits holes. Compare per-day game_pks
   against the MLB schedule API (regular-season Final games) and re-pull any
   date with missing games.
"""
from __future__ import annotations
import argparse
import time
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

from plv_clone.paths import ROOT
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

SCHEDULE_URL = ('https://statsapi.mlb.com/api/v1/schedule'
                '?sportId=1&gameType=R&startDate={start}&endDate={end}')


def final_game_pks_by_date(start: date, end: date) -> dict:
    """Regular-season Final game_pks per date ('YYYY-MM-DD') from the MLB schedule API."""
    import requests
    js = requests.get(SCHEDULE_URL.format(start=start, end=end), timeout=60).json()
    out = {}
    for d in js.get('dates', []):
        pks = {g['gamePk'] for g in d.get('games', [])
               if g.get('status', {}).get('codedGameState') == 'F'}
        if pks:
            out[d['date']] = pks
    return out


def date_ranges(days: list) -> list:
    """Group sorted dates into consecutive (start, end) ranges."""
    days = sorted(days)
    ranges = []
    run_start = prev = days[0]
    for d in days[1:]:
        if (d - prev).days == 1:
            prev = d
        else:
            ranges.append((run_start, prev))
            run_start = prev = d
    ranges.append((run_start, prev))
    return ranges


def pull_range(start: str, end: str) -> pd.DataFrame:
    import pybaseball as pb
    pb.cache.enable()
    t0 = time.time()
    print(f'  pulling pybaseball.statcast {start} → {end}...', flush=True)
    df = pb.statcast(start_dt=start, end_dt=end, verbose=False)
    df = df[df['game_type'] == 'R'].copy()
    print(f'  pulled {len(df):,} pitches in {time.time()-t0:.0f}s')
    return df


def align_columns(new_df: pd.DataFrame, base: pd.DataFrame):
    """Fill NaN for column-set differences in both directions; match base order."""
    new_df['game_date'] = pd.to_datetime(new_df['game_date'])
    missing_in_new = set(base.columns) - set(new_df.columns)
    missing_in_base = set(new_df.columns) - set(base.columns)
    if missing_in_new:
        print(f'  cols in existing not in pull (will fill NaN): {len(missing_in_new)}')
        for c in missing_in_new:
            new_df[c] = pd.NA
    if missing_in_base:
        print(f'  cols in pull not in existing (will fill NaN): {len(missing_in_base)}')
        for c in missing_in_base:
            base[c] = pd.NA
    return new_df[base.columns.tolist()], base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=date.today().year)
    ap.add_argument('--lag', type=int, default=2,
                    help='days behind today considered available (statcast lag)')
    ap.add_argument('--no-repair', action='store_true',
                    help='skip the schedule-vs-cache gap scan')
    args = ap.parse_args()

    path = CACHE / f'statcast_{args.year}.parquet'
    if not path.exists():
        print(f'No existing cache at {path} — run build_sp_multiyr.py for full pull')
        return

    combined = pd.read_parquet(path)
    combined['game_date'] = pd.to_datetime(combined['game_date'])
    n_start = len(combined)
    last_date = combined['game_date'].max().date()
    available_through = date.today() - timedelta(days=args.lag)
    pull_start = last_date + timedelta(days=1)
    pull_end = available_through
    changed = False

    print(f'Existing cache: {n_start:,} rows, max={last_date}')
    print(f'Pull window: {pull_start} → {pull_end}')

    # 1. Tail pull
    if pull_start > pull_end:
        print('  tail already up to date')
    else:
        new_df = pull_range(str(pull_start), str(pull_end))
        if new_df.empty:
            print('  no new rows — likely off days')
        else:
            new_df, combined = align_columns(new_df, combined)
            combined = pd.concat([combined, new_df], ignore_index=True)
            changed = True

    # 2. Gap repair
    if not args.no_repair:
        scan_start = date(args.year, 3, 1)
        scan_end = min(pull_end, date(args.year, 11, 30))
        sched = {}
        if scan_end >= scan_start:
            try:
                sched = final_game_pks_by_date(scan_start, scan_end)
            except Exception as e:
                print(f'  gap scan skipped (schedule API error: {e})')
        if sched:
            games = combined[['game_pk', 'game_date']].drop_duplicates()
            games['d'] = games['game_date'].dt.strftime('%Y-%m-%d')
            have = games.groupby('d')['game_pk'].agg(set).to_dict()
            deficient = [date.fromisoformat(d) for d, pks in sched.items()
                         if pks - have.get(d, set())]
            if not deficient:
                print(f'  gap scan: no missing games {scan_start} → {scan_end}')
            else:
                print(f'  gap scan: {len(deficient)} day(s) with missing games: '
                      f'{[str(d) for d in sorted(deficient)]}')
                for lo, hi in date_ranges(deficient):
                    rep = pull_range(str(lo), str(hi))
                    if rep.empty:
                        continue
                    rep, combined = align_columns(rep, combined)
                    # Drop any prior (partial/provisional) rows for the games
                    # being re-pulled so phantom rows can't linger or double-count.
                    repull_pks = set(rep['game_pk'].unique())
                    combined = combined[~combined['game_pk'].isin(repull_pks)]
                    combined = pd.concat([combined, rep], ignore_index=True)
                    changed = True

    if not changed:
        print('  cache already up to date — nothing written')
        return

    if 'game_pk' in combined.columns:
        combined = combined.drop_duplicates(
            subset=['game_pk', 'at_bat_number', 'pitch_number'], keep='last')

    print(f'  combined rows: {len(combined):,} (gain +{len(combined)-n_start:,})')
    print(f'  new max date: {combined["game_date"].max().date()}')

    backup = path.with_suffix('.parquet.bak')
    if backup.exists():
        backup.unlink()
    path.rename(backup)
    combined.to_parquet(path, index=False)
    print(f'  wrote {path}')
    print(f'  backup at {backup}')


if __name__ == '__main__':
    main()
