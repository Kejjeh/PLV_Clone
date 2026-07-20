"""run_decision_gates.py — first-class pre-registered decision gates.

Codifies the pattern used all July (Messick post-break velo gate, Peralta 2H
gate, Canzone-vs-Mead earmark, Clemens PT watch): a roster decision is
pre-committed to a MEASURABLE condition, checked on a cadence, and pruned
once the decision executes. Previously these lived as hand-edited prose in
monday-morning Step 3c; this engine makes them stateful and self-pruning.

State: data/research/decision_gates.json (tracked — gates are durable).

Usage:
  python scripts/xfp/run_decision_gates.py check                # the Monday call
  python scripts/xfp/run_decision_gates.py list
  python scripts/xfp/run_decision_gates.py add --id messick-velo \
      --player "Parker Messick" --bucket SP --metric fb_velo_last_start \
      --cmp "<" --threshold 95.0 --decision "Messick is the 7/27 Fried cut" \
      --check-from 2026-07-20 --expires 2026-07-27 --notes "season norm 95.5+"
  python scripts/xfp/run_decision_gates.py resolve messick-velo
  python scripts/xfp/run_decision_gates.py remove <id>

Metrics (deliberately small; anything else -> --metric manual):
  fb_velo_last_start  mean FF/SI release_speed in the player's LAST start
                      (statcast_2026.parquet; only games >= check_from count)
  fp_lastN            mean BrownU FP over last N games (boxscore store,
                      bucket-aware SP/RP/H via lib/boom_bust)
  fp_last_start       last single-game FP (same source)
  games_lastN         appearances in the trailing N DAYS (PT watch)
  manual              criteria displayed verbatim, never auto-evaluated

Statuses: OPEN (awaiting data / before check_from) | TRIGGERED (condition
met -> execute the decision) | CLEARED (data present, condition false) |
EXPIRED. Rule 12: a gate's decision text never changes silently — edit via
remove+add with a new id.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from plv_clone.paths import ROOT

STATE = ROOT / 'data' / 'research' / 'decision_gates.json'
STATCAST = ROOT / 'data' / 'research' / 'xfp_cache' / 'statcast_2026.parquet'

_CMPS = {'<': lambda a, b: a < b, '<=': lambda a, b: a <= b,
         '>': lambda a, b: a > b, '>=': lambda a, b: a >= b}
METRICS = ('fb_velo_last_start', 'fp_lastN', 'fp_last_start', 'games_lastN', 'manual')


def _load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding='utf-8'))
    return {'gates': []}


def _save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def _resolve_mlbam(player: str, bucket: str):
    """Collision-safe id resolution via the canonical owners (Rule 10)."""
    from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
    try:
        if bucket == 'H':
            return resolve_batter_id(player)
        return resolve_pitcher_id(player)
    except Exception:
        return None


# ── metric measurers (each returns (value, asof_date) or (None, None)) ──────

def _fb_velo_last_start(mlbam: int, check_from: str | None):
    import pandas as pd
    if not STATCAST.exists():
        return None, None
    sc = pd.read_parquet(STATCAST, columns=['pitcher', 'game_date', 'pitch_type',
                                            'release_speed'])
    sub = sc[(sc['pitcher'] == int(mlbam))
             & (sc['pitch_type'].isin(('FF', 'SI')))].dropna(subset=['release_speed'])
    if sub.empty:
        return None, None
    sub = sub.assign(game_date=pd.to_datetime(sub['game_date']))
    last_day = sub['game_date'].max()
    if check_from and last_day.date() < date.fromisoformat(check_from):
        return None, None       # no qualifying start yet -> OPEN
    day = sub[sub['game_date'] == last_day]
    return round(float(day['release_speed'].mean()), 1), last_day.date().isoformat()


def _fp_series(mlbam: int, bucket: str):
    from lib.boom_bust import _load_box, _series_from_box
    kind = 'H' if bucket == 'H' else 'P'
    return _series_from_box(_load_box(kind), mlbam, bucket)


def _fp_lastN(mlbam: int, bucket: str, n: int):
    fps = _fp_series(mlbam, bucket)
    if not fps:
        return None, None
    tail = fps[-n:]
    if len(tail) < n:
        return None, None       # not enough post-registration games -> OPEN
    return round(sum(tail) / len(tail), 2), f'last {n} games'


def _fp_last_start(mlbam: int, bucket: str):
    fps = _fp_series(mlbam, bucket)
    if not fps:
        return None, None
    return round(fps[-1], 2), 'last game'


def _games_lastN(mlbam: int, bucket: str, days: int):
    import pandas as pd
    from lib.boom_bust import _load_box
    df = _load_box('H' if bucket == 'H' else 'P')
    if df is None or df.empty:
        return None, None
    sub = df[df['mlbam_id'] == int(mlbam)].assign(
        game_date=lambda d: pd.to_datetime(d['game_date']))
    if sub.empty:
        return 0, f'last {days}d'
    cutoff = pd.Timestamp(date.today()) - pd.Timedelta(days=days)
    return int((sub['game_date'] >= cutoff).sum()), f'last {days}d'


def _measure(g: dict):
    m = g['metric']
    if m == 'manual':
        return None, None
    mlbam, bucket = g.get('mlbam'), g.get('bucket', 'SP')
    if not mlbam:
        return None, None
    if m == 'fb_velo_last_start':
        return _fb_velo_last_start(mlbam, g.get('check_from'))
    if m == 'fp_lastN':
        return _fp_lastN(mlbam, bucket, int(g.get('window_n', 2)))
    if m == 'fp_last_start':
        return _fp_last_start(mlbam, bucket)
    if m == 'games_lastN':
        return _games_lastN(mlbam, bucket, int(g.get('window_n', 10)))
    return None, None


def _status(g: dict):
    today = date.today().isoformat()
    if g.get('resolved_at'):
        return 'RESOLVED', None, None
    if g.get('expires') and today > g['expires']:
        return 'EXPIRED', None, None
    if g.get('check_from') and today < g['check_from']:
        return 'OPEN', None, 'before check_from'
    if g['metric'] == 'manual':
        return 'OPEN', None, 'manual — evaluate by hand'
    try:
        val, asof = _measure(g)
    except Exception as e:
        return 'OPEN', None, f'measure error: {type(e).__name__}'
    if val is None:
        return 'OPEN', None, 'awaiting qualifying data'
    hit = _CMPS[g['cmp']](val, float(g['threshold']))
    return ('TRIGGERED' if hit else 'CLEARED'), val, asof


def cmd_check(_args) -> int:
    state = _load()
    live = [g for g in state['gates'] if not g.get('resolved_at')]
    if not live:
        print('No live decision gates. Add with: run_decision_gates.py add ...')
        return 0
    print(f"DECISION GATES — {date.today().isoformat()}  "
          f"(TRIGGERED = execute the decision; resolve <id> after acting)\n")
    hdr = f"{'id':<16}{'player':<20}{'status':<11}{'measured':<22}gate"
    print(hdr); print('-' * (len(hdr) + 24))
    for g in state['gates']:
        st, val, asof = _status(g)
        if st in ('RESOLVED',):
            continue
        cond = (g.get('criteria') or
                f"{g['metric']}({g.get('window_n', '')}) {g['cmp']} {g['threshold']}")
        meas = '—' if val is None else f"{val} ({asof})"
        print(f"{g['id']:<16}{g['player']:<20}{st:<11}{meas:<22}{cond}")
        print(f"{'':<16}→ {g['decision']}"
              + (f"   [expires {g['expires']}]" if g.get('expires') else ''))
        if g.get('notes'):
            print(f"{'':<16}  note: {g['notes']}")
    exp = [g['id'] for g in state['gates']
           if _status(g)[0] == 'EXPIRED' and not g.get('resolved_at')]
    if exp:
        print(f"\nEXPIRED (prune with resolve/remove): {', '.join(exp)}")
    return 0


def cmd_add(args) -> int:
    state = _load()
    if any(g['id'] == args.id for g in state['gates']):
        print(f"gate id '{args.id}' exists — remove it first (Rule 12: no silent edits)")
        return 1
    if args.metric not in METRICS:
        print(f'unknown metric {args.metric}; choose from {METRICS}')
        return 1
    mlbam = None
    if args.metric != 'manual':
        mlbam = _resolve_mlbam(args.player, args.bucket)
        if mlbam is None:
            print(f'could not resolve {args.player!r} ({args.bucket}) to an mlbam id '
                  f'— fix the name or use --metric manual')
            return 1
        if args.cmp not in _CMPS or args.threshold is None:
            print('non-manual gates need --cmp and --threshold')
            return 1
    g = {'id': args.id, 'player': args.player, 'bucket': args.bucket,
         'mlbam': mlbam, 'metric': args.metric, 'cmp': args.cmp,
         'threshold': args.threshold, 'window_n': args.n,
         'decision': args.decision, 'check_from': args.check_from,
         'expires': args.expires, 'notes': args.notes,
         'criteria': args.criteria,
         'created': datetime.now().isoformat(timespec='seconds')}
    state['gates'].append(g)
    _save(state)
    print(f"added gate {args.id} ({args.player}) → {args.decision}")
    return 0


def cmd_resolve(args) -> int:
    state = _load()
    for g in state['gates']:
        if g['id'] == args.id:
            g['resolved_at'] = datetime.now().isoformat(timespec='seconds')
            _save(state)
            print(f"resolved {args.id} — it will no longer appear in check")
            return 0
    print(f'no gate {args.id}')
    return 1


def cmd_remove(args) -> int:
    state = _load()
    n = len(state['gates'])
    state['gates'] = [g for g in state['gates'] if g['id'] != args.id]
    if len(state['gates']) == n:
        print(f'no gate {args.id}')
        return 1
    _save(state)
    print(f'removed {args.id}')
    return 0


def cmd_list(_args) -> int:
    state = _load()
    for g in state['gates']:
        tag = 'RESOLVED' if g.get('resolved_at') else 'live'
        print(f"{g['id']:<16}{g['player']:<20}{tag:<9}{g['decision']}")
    if not state['gates']:
        print('(no gates)')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check')
    sub.add_parser('list')
    a = sub.add_parser('add')
    a.add_argument('--id', required=True)
    a.add_argument('--player', required=True)
    a.add_argument('--bucket', choices=['H', 'SP', 'RP'], default='SP')
    a.add_argument('--metric', required=True)
    a.add_argument('--cmp', default=None)
    a.add_argument('--threshold', type=float, default=None)
    a.add_argument('--n', type=int, default=None,
                   help='window: games for fp_lastN, days for games_lastN')
    a.add_argument('--decision', required=True,
                   help='the roster decision this gate controls')
    a.add_argument('--check-from', dest='check_from', default=None)
    a.add_argument('--expires', default=None)
    a.add_argument('--notes', default=None)
    a.add_argument('--criteria', default=None,
                   help='manual gates: the criteria text displayed at check')
    r = sub.add_parser('resolve'); r.add_argument('id')
    rm = sub.add_parser('remove'); rm.add_argument('id')
    args = ap.parse_args()
    return {'check': cmd_check, 'list': cmd_list, 'add': cmd_add,
            'resolve': cmd_resolve, 'remove': cmd_remove}[args.cmd](args)


if __name__ == '__main__':
    raise SystemExit(main())
