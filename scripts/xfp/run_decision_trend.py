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

MEASUREMENT GATE (audit T19, 2026-08-01). Persistence (this study) and forward
RELIABILITY (`plv_clone.stabilization`, measured 2026-07-29) are different
questions, and only the second licenses printing a rate as a fact. Chase and
z-swing cross forward r=0.50 at **150** out-of-zone / in-zone pitches, so every
rendered rate whose denominator is short carries `SHORT_MARK` and the row earns
NO verdict — a marked number is descriptive, not decision-grade. Both legs of a
delta must clear the gate, since Δchase is `window − baseline`.

That gate also subsumes the study's own outer inclusion filters, which this
script had dropped while copying its inner 15/15 sanity guard. Measured on the
2026 panel (re-verified against data through 2026-07-31): of 411 baselines
clearing 150 OOZ + 150 IZ,
ZERO fall under the study's MIN_BASE_PITCH=300 (thinnest is 326), and every L21
window clearing the gate carries >= 305 pitches against the study's
`max(40, 3*w)` = 63. Re-deriving those literals here would add nothing but a
second copy of a threshold this repo already owns in one place.

Usage:
  python scripts/xfp/run_decision_trend.py                  # my roster (live_rosters parquet)
  python scripts/xfp/run_decision_trend.py --names "A,B,C"  # any list
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import numpy as np
import pandas as pd
from plv_clone import stabilization as _stab   # threshold OWNER — never inline a gate
from plv_clone.league_config import MY_TEAM_NAME, SEASON_YEAR
from plv_clone.paths import ROOT

# Anchored on the shared repo root (audit T45, 2026-08-01) — these were bare
# relative literals, so the tracker only ran from the repo root and hardcoded
# the season year.
STATCAST = ROOT / 'data' / 'research' / 'xfp_cache' / f'statcast_{SEASON_YEAR}.parquet'
ROSTER_DIR = ROOT / 'data' / 'research'
MY_TEAM = MY_TEAM_NAME

SWING = {'hit_into_play', 'foul', 'swinging_strike', 'swinging_strike_blocked',
         'foul_tip', 'foul_bunt', 'missed_bunt', 'bunt_foul_tip'}
# Cross-player spreads (2026 T1 panel) used to z-score deltas.
SPREAD = {'chase_pct': 6.5, 'z_swing_pct': 6.5, 'decision_gap': 8.0, 'swing_pct': 5.0}
GOOD_DIR = {'chase_pct': -1, 'z_swing_pct': +1, 'decision_gap': +1, 'swing_pct': 0}

# Marker appended to any rendered rate whose denominator is below the measured
# stabilization minimum (audit T19, 2026-08-01). The old code carried a bare
# inline `iz < 15 or oz < 15`, which is decision_window_study.py's INNER sanity
# guard — that study also declares MIN_BASE_PITCH / MIN_FWD_PITCH / max(40, 3*w)
# outer filters, and stabilization.py owns the forward-r crossing (150 OOZ / 150
# IZ pitches). A window under the minimum is descriptive, never decision-grade,
# so it renders marked and WITHOUT a verdict.
SHORT_MARK = '*'

# The default board's roster store is HAND-MAINTAINED — nothing in the repo
# writes live_rosters_*.parquet (the newest was 14 days old when audit T45 was
# filed). Past this bound the tracker refuses the default board rather than
# silently profiling a stale roster.
ROSTER_MAX_AGE_DAYS = 7


NIGHTLY_ROSTER_STORE = ROSTER_DIR / 'matchup_rosters_history.parquet'


def nightly_roster(today: date | None = None):
    """Newest snapshot from the store the nightly refresh ACTUALLY produces.

    ``matchup_rosters_history.parquet`` is appended by refresh step 0.5 every
    night; the legacy hand-maintained ``live_rosters_*.parquet`` files have no
    producer (review 2026-08-01 — reading only those killed the default board
    the moment they aged past the bound). Returns ``(frame, age_days)`` for the
    latest snapshot_date, or ``(None, None)`` when the store is absent.
    """
    if not NIGHTLY_ROSTER_STORE.exists():
        return None, None
    df = pd.read_parquet(NIGHTLY_ROSTER_STORE)
    if df.empty or 'snapshot_date' not in df.columns:
        return None, None
    latest = str(df['snapshot_date'].astype(str).max())
    try:
        stamp = date.fromisoformat(latest[:10])
    except ValueError:
        return None, None
    return (df[df['snapshot_date'].astype(str) == latest],
            ((today or date.today()) - stamp).days)


def latest_roster_snapshot(today: date | None = None):
    """Newest ``live_rosters_*.parquet`` as ``(path, age_days)``.

    ``(None, None)`` when the store is empty; ``(path, None)`` when the
    filename carries no parseable ISO datestamp.
    """
    files = sorted(ROSTER_DIR.glob('live_rosters_*.parquet'))
    if not files:
        return None, None
    p = files[-1]
    try:
        stamp = date.fromisoformat(p.stem.replace('live_rosters_', ''))
    except ValueError:
        return p, None
    return p, ((today or date.today()) - stamp).days


def _metrics(g: pd.DataFrame) -> dict | None:
    iz, oz = int(g['inzone'].sum()), int(g['ozone'].sum())
    if iz < 15 or oz < 15:   # inner sanity guard (decision_window_study.py:73)
        return None
    zsw = g.loc[g['inzone'], 'swing'].mean() * 100
    chase = g.loc[g['ozone'], 'swing'].mean() * 100
    return dict(n=len(g), n_iz=iz, n_ooz=oz, chase_pct=chase, z_swing_pct=zsw,
                decision_gap=zsw - chase, swing_pct=g['swing'].mean() * 100)


def sample_is_decision_grade(m: dict) -> bool:
    """True when BOTH swing-decision denominators clear their registered minimum.

    Thresholds come from `plv_clone.stabilization` (measured forward-r >= 0.50
    crossings), never from a literal here.
    """
    return bool(_stab.is_sufficient(m['n_ooz'], 'chase', 'H')
                and _stab.is_sufficient(m['n_iz'], 'zswing', 'H'))


def _num(val: float, ok: bool, width: int, sign: str = '') -> str:
    """Right-aligned rate, marked when its sample is below the minimum."""
    s = f'{val:{sign}.1f}' + ('' if ok else SHORT_MARK)
    return f'{s:>{width}}'


def _mlb_search(name):
    """Accent-tolerant fallback: MLB people/search (fix 2026-07-18 —
    resolve_batter_id missed accented FAs like Peña/Suárez).

    Module-level (was a closure inside main()) so a test can neutralise the
    network call; behavior is unchanged — it closed over nothing.
    """
    import requests
    try:
        r = requests.get('https://statsapi.mlb.com/api/v1/people/search',
                         params={'names': name}, timeout=15).json()
        for p in r.get('people', []):
            if p.get('active') and p.get('primaryPosition', {}).get('abbreviation') not in ('P',):
                return p['id']
    except Exception:
        pass
    return None


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

    # resolve target hitters -> mlbam ids. The nightly store is primary; the
    # legacy live_rosters_* file is only a fallback. UNKNOWN age (an undatable
    # snapshot) counts as stale — treating it as fresh silently reopens the
    # stale-roster hole the bound exists for (review 2026-08-01).
    roster, snap_age = nightly_roster()
    snap = NIGHTLY_ROSTER_STORE if roster is not None else None
    if roster is None:
        snap, snap_age = latest_roster_snapshot()
        roster = pd.read_parquet(snap) if snap is not None else None
    stale = roster is not None and (snap_age is None
                                    or snap_age > ROSTER_MAX_AGE_DAYS)
    if args.names:
        names = [n.strip() for n in args.names.split(',')]
        if stale:
            print(f'  ! roster snapshot {snap.name} is {snap_age} days old '
                  f'(bound {ROSTER_MAX_AGE_DAYS}d) — team hints may be wrong',
                  file=sys.stderr)
    else:
        if roster is None:
            print('no live_rosters parquet; pass --names'); return 1
        if stale:
            age_s = ('of unknown age (no parseable datestamp)'
                     if snap_age is None else f'{snap_age} days old')
            print(f'REFUSING default board: newest roster snapshot {snap.name} is '
                  f'{age_s} (freshness bound {ROSTER_MAX_AGE_DAYS}d). '
                  f'Pass --names, or run the nightly refresh (step 0.5 writes '
                  f'{NIGHTLY_ROSTER_STORE.name}).', file=sys.stderr)
            return 2
        mine = roster[roster['team_name'] == MY_TEAM]
        names = mine[~mine['position'].isin(['SP', 'RP'])]['player_name'].tolist()

    from plv_clone.utils.name_match import resolve_batter_id

    have = set(sc['batter'].unique())
    ids = {}
    for n in names:
        team = None
        if roster is not None:
            hit = roster[roster['player_name'] == n]
            if len(hit) == 1:
                team = hit.iloc[0]['pro_team']
        bid = None
        try:
            bid = resolve_batter_id(n, team=team)
        except Exception:
            bid = None
        if bid is None or bid not in have:
            alt = _mlb_search(n)
            if alt is not None and alt in have:
                bid = alt
        if bid is None:
            print(f'  ! could not resolve {n} — skipped', file=sys.stderr)
        else:
            ids[n] = bid

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
        # A verdict is a CLAIM. It requires both legs of the comparison to be
        # measurable at the registered minimum; otherwise the row still renders
        # (marked) but says the sample is short instead of naming a direction.
        ok21 = sample_is_decision_grade(l21) and sample_is_decision_grade(base)
        if not ok21:
            read = 'sample short — below stabilization min'
        else:
            z = max(abs(dch) / SPREAD['chase_pct'], abs(dgap) / SPREAD['decision_gap'])
            good = (dch < 0) or (dgap > 0)
            if z >= 0.75:
                read = 'APPROACH SHIFT ' + ('▲ better' if good else '▼ worse')
            elif z >= 0.4:
                read = 'drifting ' + ('▲' if good else '▼')
            else:
                read = 'stable'
        w21 = sample_is_decision_grade(l21)
        print(f"{name:<22}{'L21':>5}{l21['n']:>6}{_num(l21['chase_pct'], w21, 8)}"
              f"{_num(l21['z_swing_pct'], w21, 7)}{_num(l21['decision_gap'], w21, 7)}"
              f"{_num(dch, ok21, 8, '+')}{_num(dgap, ok21, 7, '+')}  {read}")
        if l7 is not None:
            d7 = l7['chase_pct'] - base['chase_pct']
            w7 = sample_is_decision_grade(l7)
            hint = '(early hint)' if w7 else '(early hint — below min)'
            print(f"{'':<22}{'L7':>5}{l7['n']:>6}{_num(l7['chase_pct'], w7, 8)}"
                  f"{_num(l7['z_swing_pct'], w7, 7)}{_num(l7['decision_gap'], w7, 7)}"
                  f"{_num(d7, w7, 8, '+')}{'':>7}  {hint}")

    print(f"\n  {SHORT_MARK} below the measured stabilization minimum — "
          f"{_stab.describe('chase', 'H')}; {_stab.describe('zswing', 'H')}")
    print("    (owner: src/plv_clone/stabilization.py — a marked number is "
          "descriptive, NOT decision-grade, and earns no verdict)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
