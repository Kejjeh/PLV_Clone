"""run_decision_trend.py — in-season hitter swing-DECISION tracker.

Tracks plate-discipline / swing-decision metrics over time and flags real
approach changes. Window choice is EVIDENCE-BASED (decision_window_study.py,
2026-07-18, 13,939 obs / 483 players / 2024-2026):

  - Decision metrics are FAST-STABILIZING: even a 7d window carries real
    persistence signal beyond the hitter's own baseline (chase r=0.20,
    z-swing r=0.22, all FDR-pass), rising monotonically to r~0.36-0.42
    at 45d. There is no noise cliff: L7 = early hint, L21 = solid read.
  - Rule 13 HARD LIMIT: recent decision SHIFTS predict forward FP ~0.00
    beyond the FP level (all 20 cells null). This tracker detects
    APPROACH CHANGES — it never re-ranks anyone. Display/context only.

Primary window: L21 (solid read, repo convention). L7 shown as early hint.
Baseline: the hitter's own season-to-date BEFORE the window.

Usage:
  python scripts/xfp/run_decision_trend.py                  # my roster (live_rosters parquet)
  python scripts/xfp/run_decision_trend.py --names "A,B,C"  # any list
"""
from __future__ import annotations

import argparse
import glob
import sys

import numpy as np
import pandas as pd

STATCAST = 'data/research/xfp_cache/statcast_2026.parquet'
MY_TEAM = 'New York Ligers'

SWING = {'hit_into_play', 'foul', 'swinging_strike', 'swinging_strike_blocked',
         'foul_tip', 'foul_bunt', 'missed_bunt', 'bunt_foul_tip'}
# Cross-player spreads (2026 T1 panel) used to z-score deltas.
SPREAD = {'chase_pct': 6.5, 'z_swing_pct': 6.5, 'decision_gap': 8.0, 'swing_pct': 5.0}
GOOD_DIR = {'chase_pct': -1, 'z_swing_pct': +1, 'decision_gap': +1, 'swing_pct': 0}


def _metrics(g: pd.DataFrame) -> dict | None:
    iz, oz = int(g['inzone'].sum()), int(g['ozone'].sum())
    if iz < 15 or oz < 15:
        return None
    zsw = g.loc[g['inzone'], 'swing'].mean() * 100
    chase = g.loc[g['ozone'], 'swing'].mean() * 100
    return dict(n=len(g), chase_pct=chase, z_swing_pct=zsw,
                decision_gap=zsw - chase, swing_pct=g['swing'].mean() * 100)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--names', default=None, help='comma-separated hitter names')
    args = ap.parse_args()

    sc = pd.read_parquet(STATCAST, columns=['batter', 'game_date', 'description', 'zone'])
    sc['game_date'] = pd.to_datetime(sc['game_date'], errors='coerce')
    sc = sc.dropna(subset=['game_date'])
    sc['swing'] = sc['description'].isin(SWING)
    sc['inzone'] = sc['zone'].between(1, 9)
    sc['ozone'] = sc['zone'].between(11, 14)
    today = sc['game_date'].max()

    # resolve target hitters -> mlbam ids
    rosters = sorted(glob.glob('data/research/live_rosters_*.parquet'))
    roster = pd.read_parquet(rosters[-1]) if rosters else None
    if args.names:
        names = [n.strip() for n in args.names.split(',')]
    else:
        if roster is None:
            print('no live_rosters parquet; pass --names'); return 1
        mine = roster[roster['team_name'] == MY_TEAM]
        names = mine[~mine['position'].isin(['SP', 'RP'])]['player_name'].tolist()

    from plv_clone.utils.name_match import resolve_batter_id
    ids = {}
    for n in names:
        team = None
        if roster is not None:
            hit = roster[roster['player_name'] == n]
            if len(hit) == 1:
                team = hit.iloc[0]['pro_team']
        try:
            ids[n] = resolve_batter_id(n, team=team)
        except Exception:
            print(f'  ! could not resolve {n} — skipped', file=sys.stderr)

    print(f"DECISION TREND — L21 primary / L7 early hint / baseline = season pre-L21")
    print(f"data through {today.date()}  |  Rule 13: approach-change detector, never a ranker\n")
    hdr = (f"{'hitter':<22}{'win':>5}{'pitch':>6}{'chase%':>8}{'zSw%':>7}"
           f"{'gap':>7}{'Δchase':>8}{'Δgap':>7}  read")
    print(hdr); print('-' * len(hdr))

    for name, bid in ids.items():
        sub = sc[sc['batter'] == bid]
        if sub.empty:
            print(f"{name:<22}  — no 2026 pitches"); continue
        l21 = _metrics(sub[sub['game_date'] > today - pd.Timedelta(days=21)])
        l7 = _metrics(sub[sub['game_date'] > today - pd.Timedelta(days=7)])
        base = _metrics(sub[sub['game_date'] <= today - pd.Timedelta(days=21)])
        if l21 is None or base is None:
            print(f"{name:<22}  — insufficient window/baseline sample"); continue
        dch = l21['chase_pct'] - base['chase_pct']
        dgap = l21['decision_gap'] - base['decision_gap']
        z = max(abs(dch) / SPREAD['chase_pct'], abs(dgap) / SPREAD['decision_gap'])
        good = (dch < 0) or (dgap > 0)
        if z >= 0.75:
            read = 'APPROACH SHIFT ' + ('▲ better' if good else '▼ worse')
        elif z >= 0.4:
            read = 'drifting ' + ('▲' if good else '▼')
        else:
            read = 'stable'
        print(f"{name:<22}{'L21':>5}{l21['n']:>6}{l21['chase_pct']:>8.1f}"
              f"{l21['z_swing_pct']:>7.1f}{l21['decision_gap']:>7.1f}"
              f"{dch:>+8.1f}{dgap:>+7.1f}  {read}")
        if l7 is not None:
            d7 = l7['chase_pct'] - base['chase_pct']
            print(f"{'':<22}{'L7':>5}{l7['n']:>6}{l7['chase_pct']:>8.1f}"
                  f"{l7['z_swing_pct']:>7.1f}{l7['decision_gap']:>7.1f}"
                  f"{d7:>+8.1f}{'':>7}  (early hint)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
