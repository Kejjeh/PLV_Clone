"""PART 1 — empirical stabilization curves for BAT-TRACKING metrics.

Pre-registered: data/research/validation_runs/bat_speed_stabilization_and_delta_2026-07-29.md

Method mirrors scripts/xfp/validate_cutoff_stabilization.py exactly: forward
reliability r(metric over the first N units of a season, metric over the REST of
that same season), bucketed by N, with the r>=0.50 / r>=0.70 crossings
interpolated between straddling buckets.

Why it is needed: bat speed is the only hitter process metric with validated
incremental forward-FP signal (2026-06-26), yet its sample gate was never
measured on our data — `plv_clone.stabilization.LITERATURE_ONLY` carries
bat_speed at 30 swings (a borrowed Savant-guidance number, flagged as not ours)
and `lib/trend_signal` gates at 80/200 swings (hand-picked). This script
replaces both with a measured value.

Substrate: data/research/bat_speed_daily.parquet (one row per batter-game_date;
built by scripts/xfp/build_bat_speed_daily.py). Daily rows are collapsed with
SWING-COUNT WEIGHTS, so `mean_bat_speed` and `fast_swing_rate` reconstruct
exactly. `p90_bat_speed` is NOT count-additive — its curve is a swing-weighted
mean of daily p90s and is reported as APPROXIMATE (declared secondary).

Usage:
    python scripts/xfp/validate_bat_speed_stabilization.py
    python scripts/xfp/validate_bat_speed_stabilization.py --drop-provisional
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

STORE = ROOT / 'data' / 'research' / 'bat_speed_daily.parquet'

# metric -> (daily numerator column expression, label)
# All three are turned into swing-count-weighted sums so the cumulative and
# rest-of-season aggregates are exact (p90 excepted — see module docstring).
METRICS = ['mean_bat_speed', 'fast_swing_rate', 'p90_bat_speed']
APPROX = {'p90_bat_speed'}

BUCKET_EDGES = np.arange(25, 626, 25)
SNAPSHOT_EVERY = 7          # calendar-day stride for snapshots within a season
REST_FLOOR_SWINGS = 100     # rest-of-season sample needed for a valid pair
MIN_PLAYER_SEASONS = 200    # per-bucket floor (declared)


def load(drop_provisional: bool = False) -> pd.DataFrame:
    d = pd.read_parquet(STORE)
    d['game_date'] = pd.to_datetime(d['game_date'])
    d['year'] = d['game_date'].dt.year
    if drop_provisional:
        before = len(d)
        d = d[d['provisional_share'].fillna(0.0) <= 0.0]
        print(f'  dropped {before - len(d)} provisional batter-days '
              f'({(before - len(d)) / before:.2%})')
    for m in METRICS:
        d[m] = pd.to_numeric(d[m], errors='coerce')
    d['n_swings'] = pd.to_numeric(d['n_swings'], errors='coerce')
    d = d[d['n_swings'].notna() & (d['n_swings'] > 0)]
    # weighted sums (exact for mean/rate; approximate for p90)
    for m in METRICS:
        d['_w_' + m] = d[m] * d['n_swings']
    return d.sort_values(['batter', 'year', 'game_date']).reset_index(drop=True)


def build_snapshots(d: pd.DataFrame) -> pd.DataFrame:
    """One row per (batter, season, snapshot day): to-date vs rest-of-season."""
    wcols = ['_w_' + m for m in METRICS]
    g = d.groupby(['batter', 'year'], sort=False)
    cum = g[['n_swings'] + wcols].cumsum()
    tot = g[['n_swings'] + wcols].transform('sum')
    day_idx = (d['game_date'] - g['game_date'].transform('min')).dt.days

    snap = pd.DataFrame({
        'batter': d['batter'].values,
        'year': d['year'].values,
        'day_idx': day_idx.values,
        'sw_to': cum['n_swings'].values,
        'sw_rest': (tot['n_swings'] - cum['n_swings']).values,
    })
    for m in METRICS:
        snap[m + '_to'] = cum['_w_' + m].values / cum['n_swings'].values
        snap[m + '_rest'] = ((tot['_w_' + m].values - cum['_w_' + m].values)
                             / np.maximum(snap['sw_rest'].values, 1))
    # weekly stride: keep the last game-day within each 7-day block
    snap['block'] = snap['day_idx'] // SNAPSHOT_EVERY
    snap = snap.groupby(['batter', 'year', 'block'], as_index=False).tail(1)
    return snap[snap['sw_rest'] >= REST_FLOOR_SWINGS].reset_index(drop=True)


def curve(snap: pd.DataFrame, metric: str):
    to, rest = snap[metric + '_to'], snap[metric + '_rest']
    ok = to.notna() & rest.notna()
    s = snap[ok]
    to, rest = to[ok], rest[ok]
    key = (s['batter'].astype(str) + '_' + s['year'].astype(str))
    mids, rs, ns, nps = [], [], [], []
    for lo, hi in zip(BUCKET_EDGES[:-1], BUCKET_EDGES[1:]):
        sel = (s['sw_to'] >= lo) & (s['sw_to'] < hi)
        n_ps = key[sel].nunique()
        if n_ps < MIN_PLAYER_SEASONS:
            continue
        r = float(np.corrcoef(to[sel], rest[sel])[0, 1])
        mids.append((lo + hi) / 2)
        rs.append(r)
        ns.append(int(sel.sum()))
        nps.append(int(n_ps))
    return mids, rs, ns, nps


def crossing(mids, rs, level: float):
    for i in range(len(rs)):
        if rs[i] >= level:
            if i == 0:
                return mids[0], True          # already above at first bucket
            x0, x1, y0, y1 = mids[i - 1], mids[i], rs[i - 1], rs[i]
            return x0 + (level - y0) * (x1 - x0) / (y1 - y0), False
    return None, False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--drop-provisional', action='store_true',
                    help='declared robustness check: exclude gf-bridge days')
    ap.add_argument('--fine', action='store_true',
                    help='POST-HOC descriptive resolution only: 5-swing edges '
                         'below 50. The declared grid starts at 25 and bat '
                         'speed is already r>0.8 there, so this only locates '
                         'where the crossing actually is. Changes no verdict.')
    args = ap.parse_args()
    if args.fine:
        global BUCKET_EDGES
        BUCKET_EDGES = np.arange(5, 56, 5)

    print(f'store: {STORE.relative_to(ROOT)}')
    d = load(args.drop_provisional)
    print(f'  {len(d):,} batter-days | {d["batter"].nunique()} batters | '
          f'seasons {sorted(d["year"].unique())} | {int(d["n_swings"].sum()):,} swings')
    ps = d.groupby(['batter', 'year'])['n_swings'].sum()
    print(f'  {len(ps):,} player-seasons; season swings quantiles '
          f'p25={ps.quantile(.25):.0f} p50={ps.quantile(.5):.0f} '
          f'p75={ps.quantile(.75):.0f} p95={ps.quantile(.95):.0f}')

    snap = build_snapshots(d)
    print(f'  snapshots (weekly stride, rest >= {REST_FLOOR_SWINGS} swings): '
          f'{len(snap):,} from '
          f'{snap.groupby(["batter", "year"]).ngroups:,} player-seasons')

    results = {}
    for m in METRICS:
        mids, rs, ns, nps = curve(snap, m)
        results[m] = (mids, rs, ns, nps)
        c50, at_first_50 = crossing(mids, rs, 0.50)
        c70, _ = crossing(mids, rs, 0.70)
        tag = ' (APPROX)' if m in APPROX else ''
        print(f'\n=== {m}{tag} ===')
        print(f'{"swings":>8} {"fwd r":>7} {"n snap":>8} {"n pl-szn":>9}')
        for x, r, n, p in zip(mids, rs, ns, nps):
            print(f'{int(x):>8} {r:>+7.3f} {n:>8} {p:>9}')
        f50 = 'never' if c50 is None else (
            f'{c50:.0f} swings' + (' (already >=.50 in first bucket)'
                                   if at_first_50 else ''))
        f70 = 'never in-window' if c70 is None else f'{c70:.0f} swings'
        print(f'  r>=0.50 at: {f50}')
        print(f'  r>=0.70 at: {f70}')
        if c50 is not None:
            print(f'  EMPIRICAL MINIMUM (ceil 25): '
                  f'{int(np.ceil(c50 / 25) * 25)} swings')

    print('\n--- registry-ready summary ---')
    for m in METRICS:
        mids, rs, _, _ = results[m]
        c50, _ = crossing(mids, rs, 0.50)
        c70, _ = crossing(mids, rs, 0.70)
        if c50 is None:
            print(f'  {m:<16} NEVER STABILIZES in-window')
        else:
            hc = 'never' if c70 is None else f'{int(np.ceil(c70 / 25) * 25)}'
            print(f'  {m:<16} min {int(np.ceil(c50 / 25) * 25):>4} swings '
                  f'(r>=.50) | r>=.70 at {hc}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
