"""run_second_half_splits.py — career pre/post All-Star splits in BrownU FP terms.

The Peralta-vs-Soriano lens (2026-07-18), generalized: for every player on the
roster (+ named extras), pull CAREER pre-ASG vs post-ASG splits from the MLB
Stats API (`careerStatSplits`, sitCodes preas/posas — one call per half) and
express both halves in BrownU FP per unit (hitters FP/g, SP FP/start, RP FP/app).

ROLE RULE (CLAUDE.md gotcha #8 — the reason this script exists as a skill):
pitchers are bucketed by `detect_pitcher_role()` (eligible_slots + gamesStarted),
NEVER by ESPN's `.position` tag. Detmers (ESPN "RP", true SP) is the canonical case.

Δ(2H−1H) is a career TENDENCY, not a projection — Rule 13 context lens. It
never moves rh3/rp3/rprs2.

Usage:
  python scripts/xfp/run_second_half_splits.py                       # my roster
  python scripts/xfp/run_second_half_splits.py --extra "A,B,C"       # + FA names
  python scripts/xfp/run_second_half_splits.py --names "A,B" --no-roster
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd
import requests

import os
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path[:0] = [_ROOT, os.path.join(_ROOT, 'scripts', 'xfp')]

API = 'https://statsapi.mlb.com/api/v1'


def _search_id(name: str) -> tuple[int, str] | None:
    """MLB API people search — accent/spelling tolerant. Returns (id, position)."""
    r = requests.get(f'{API}/people/search', params={'names': name}, timeout=20).json()
    for p in r.get('people', []):
        if p.get('active'):
            return p['id'], p.get('primaryPosition', {}).get('abbreviation', '?')
    ppl = r.get('people', [])
    return (ppl[0]['id'], ppl[0].get('primaryPosition', {}).get('abbreviation', '?')) if ppl else None


def _split(pid: int, group: str, code: str) -> dict | None:
    r = requests.get(f'{API}/people/{pid}/stats',
                     params={'stats': 'careerStatSplits', 'group': group,
                             'sitCodes': code}, timeout=20).json()
    for st in r.get('stats', []):
        for s in st.get('splits', []):
            if s.get('split', {}).get('code') == code:
                return s.get('stat', {})
    return None


def _ip_thirds(ip) -> float:
    ip = float(ip or 0)
    w = int(ip)
    f = round(ip - w, 1)
    return w + (f == 0.1) / 3 + (f == 0.2) * 2 / 3


def _pitch_fp(s: dict) -> float:
    return (s.get('strikeOuts', 0) + _ip_thirds(s.get('inningsPitched', 0)) * 3.3
            - s.get('hits', 0) - 2 * s.get('earnedRuns', 0)
            - s.get('baseOnBalls', 0) - s.get('hitBatsmen', 0)
            + 5 * s.get('saves', 0) + 2 * s.get('holds', 0))


def _hit_fp(s: dict) -> float:
    return (s.get('runs', 0) + s.get('totalBases', 0) + s.get('rbi', 0)
            + s.get('baseOnBalls', 0) + s.get('hitByPitch', 0)
            + s.get('stolenBases', 0) - s.get('strikeOuts', 0))


def _pct(n, d):
    return 100 * n / d if d else float('nan')


def player_row(name: str, pid: int, kind: str, role: str, owner: str) -> dict | None:
    group = 'hitting' if kind == 'H' else 'pitching'
    pre, post = _split(pid, group, 'preas'), _split(pid, group, 'posas')
    if not pre or not post:
        return None
    row = dict(player=name, role=role, owner=owner)
    if kind == 'H':
        for tag, s in (('1H', pre), ('2H', post)):
            g = s.get('gamesPlayed', 0)
            pa = s.get('plateAppearances', 0)
            row[f'{tag}_g'] = g
            row[f'{tag}_fpg'] = _hit_fp(s) / g if g else float('nan')
            row[f'{tag}_ops'] = float(s.get('ops', 0) or 0)
            row[f'{tag}_k'] = _pct(s.get('strikeOuts', 0), pa)
        row['d_fpg'] = row['2H_fpg'] - row['1H_fpg']
    else:
        for tag, s in (('1H', pre), ('2H', post)):
            gs, g = s.get('gamesStarted', 0), s.get('gamesPlayed', 0)
            unit = gs if role == 'SP' else g
            bf = s.get('battersFaced', 0)
            row[f'{tag}_n'] = unit
            row[f'{tag}_fp'] = _pitch_fp(s) / unit if unit else float('nan')
            row[f'{tag}_era'] = float(s.get('era', 0) or 0)
            row[f'{tag}_kbb'] = (_pct(s.get('strikeOuts', 0), bf)
                                 - _pct(s.get('baseOnBalls', 0), bf))
        row['d_fp'] = row['2H_fp'] - row['1H_fp']
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--extra', default='', help='comma-separated extra names (tagged FA/EXT)')
    ap.add_argument('--names', default='', help='explicit list instead of roster (implies --no-roster; add --with-roster to keep both)')
    ap.add_argument('--no-roster', action='store_true')
    ap.add_argument('--with-roster', action='store_true',
                    help='with --names: ALSO include the roster sweep')
    args = ap.parse_args()

    # QA fix 2026-07-20: --names previously ALSO dumped the whole roster
    # (one focused 2-pitcher compare pulled ~26 extra API sweeps). --names now
    # means "just these names" unless --with-roster is explicit.
    skip_roster = args.no_roster or (bool(args.names.strip()) and not args.with_roster)

    from lib.pitcher_role import detect_pitcher_role
    targets = []  # (name, kind H/P, role, owner)
    if not skip_roster:
        from app.espn_connector import get_my_roster_with_injuries
        my = get_my_roster_with_injuries()
        for _, r in my.iterrows():
            if r['position'] in ('SP', 'RP'):
                try:
                    role = detect_pitcher_role(r)
                except Exception:
                    role = r['position']
                targets.append((r['player_name'], 'P', role, 'MINE'))
            else:
                targets.append((r['player_name'], 'H', r['position'], 'MINE'))
    for n in [x.strip() for x in (args.extra + ',' + args.names).split(',') if x.strip()]:
        targets.append((n, '?', '?', 'FA/EXT'))

    rows = []
    for name, kind, role, owner in targets:
        found = _search_id(name)
        if not found:
            print(f'  ! no MLB id for {name}', file=sys.stderr)
            continue
        pid, pos = found
        if kind == '?':
            kind = 'P' if pos in ('P', 'SP', 'RP', 'TWP') else 'H'
            role = pos if kind == 'H' else None
            if kind == 'P':
                try:
                    role = detect_pitcher_role(None, mlbam_id=pid)
                except Exception:
                    role = 'SP'
        row = player_row(name, pid, kind, role, owner)
        if row is None:
            print(f'  ! no career splits for {name}', file=sys.stderr)
            continue
        row['kind'] = kind
        rows.append(row)

    df = pd.DataFrame(rows)
    pd.set_option('display.float_format', lambda v: f'{v:,.2f}')

    hit = df[df['kind'] == 'H'].copy()
    if len(hit):
        hit['pos_grp'] = hit['role'].map(lambda p: {'C': '1_C', '1B': '2_CI', '3B': '2_CI',
                                                    '2B': '3_MI', 'SS': '3_MI'}.get(p, '4_OF/DH'))
        hit = hit.sort_values(['pos_grp', 'd_fpg'], ascending=[True, False])
        print('\n=== HITTERS — career pre-ASG vs post-ASG (BrownU FP/g) ===')
        cols = ['player', 'role', 'owner', '1H_g', '1H_fpg', '2H_g', '2H_fpg',
                'd_fpg', '1H_ops', '2H_ops', '1H_k', '2H_k']
        print(hit[cols].to_string(index=False))
    for role in ('SP', 'RP'):
        sub = df[(df['kind'] == 'P') & (df['role'] == role)].sort_values('d_fp', ascending=False)
        if not len(sub):
            continue
        unit = 'FP/start' if role == 'SP' else 'FP/app'
        print(f'\n=== {role}s — career pre-ASG vs post-ASG (BrownU {unit}) ===')
        cols = ['player', 'owner', '1H_n', '1H_fp', '2H_n', '2H_fp', 'd_fp',
                '1H_era', '2H_era', '1H_kbb', '2H_kbb']
        print(sub[cols].to_string(index=False))
    out = 'data/outputs/second_half_splits.csv'
    df.to_csv(out, index=False)
    print(f'\nledger -> {out}')
    print('Rule 13: career-tendency lens; Δ never moves rh3/rp3/rprs2.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
