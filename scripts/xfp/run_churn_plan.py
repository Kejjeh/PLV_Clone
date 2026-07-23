"""run_churn_plan.py — multi-step roster-churn planner + execution verifier.

Codifies the weekly loop ("drop A for B before B's start locks, then add C
after C pitches") AND closes the gap that cost a banked start on 2026-07-19:
the planned Soriano→Bradish→Bennett churn silently never executed, and
nothing checked. `plan` turns the sequence into an ordered checklist with ET
deadlines; `verify` reconciles the plan against the LIVE roster and calls
out EXECUTED / PENDING-WAIVER / PARTIAL / PENDING / MISSED per step.
PENDING-WAIVER = drop confirmed executed but the add hasn't cleared and the
drop is <48h old (the add is likely still inside BrownU's ~24-48h waiver
window). A condition with no posted probable prints "deadline unresolved —
re-verify when <player>'s next probable posts" rather than a bare PENDING.

Usage:
  python scripts/xfp/run_churn_plan.py plan \
      --move "drop Jose Soriano add Kyle Bradish ; before-start-of Kyle Bradish" \
      --move "drop Kyle Bradish add Jake Bennett ; after-start-of Kyle Bradish"
  python scripts/xfp/run_churn_plan.py verify            # latest plan
  python scripts/xfp/run_churn_plan.py verify --plan data/research/churn_plans/plan_X.json

Move syntax: "[drop NAME] [add NAME] [; before-start-of NAME | ; after-start-of NAME]"
Conditions resolve to the named pitcher's NEXT probable start (pitcher_schedule
cache first, MLB statsapi for the first-pitch TIME): before → deadline = first
pitch ET; after → earliest-safe-time = first pitch + 4h.

House rules baked in: 4 true RPs is a FLOOR (a plan that drops an RP without
adding one is refused); BrownU drops sit on ~24-48h waivers (faab=False) —
noted per drop; forced-drop cascades belong in /forced-drop-planner.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pandas as pd

from plv_clone.paths import ROOT
from plv_clone.league_config import MY_TEAM_NAME

PLAN_DIR = ROOT / 'data' / 'research' / 'churn_plans'
SCHED_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'pitcher_schedule_2026.csv'
ET = ZoneInfo('America/New_York')


def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower().strip()


def _resolve(name: str):
    """(mlbam, kind) via the collision-safe owners; pitcher first, then batter;
    falls back to a normalized FULL-name match against the projection CSVs
    ("Last, First" flipped via the canonical helper) — never last-name contains."""
    from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
    try:
        pid = resolve_pitcher_id(name)
        if pid:
            return int(pid), 'P'
    except Exception:
        pass
    try:
        bid = resolve_batter_id(name)
        if bid:
            return int(bid), 'H'
    except Exception:
        pass
    from lib.bucket_dispatch import _flip_lastfirst
    key = _norm(name)
    for csv, id_col, kind in (
            (ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv', 'pitcher', 'P'),
            (ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv', 'pitcher', 'P'),
            (ROOT / 'data' / 'outputs' / 'xfp_rh3_projections.csv', 'batter', 'H')):
        if not csv.exists():
            continue
        try:
            df = pd.read_csv(csv)
            name_col = 'player_name' if 'player_name' in df.columns else 'name_api'
            hits = df[df[name_col].astype(str).map(
                lambda s: _norm(_flip_lastfirst(s))) == key]
            if len(hits) == 1:
                return int(hits.iloc[0][id_col]), kind
        except Exception:
            continue
    return None, None


def _next_start(name: str, mlbam: int | None):
    """Next probable start for a pitcher: (date, first_pitch_et|None, opp)."""
    if not SCHED_CSV.exists():
        return None
    sc = pd.read_csv(SCHED_CSV, usecols=['game_date', 'pitcher', 'pitcher_name',
                                         'team', 'opp_team_abbrev'])
    today = datetime.now(ET).date().isoformat()
    if mlbam is not None:
        sub = sc[(sc['pitcher'] == mlbam) & (sc['game_date'] >= today)]
    else:
        key = _norm(name)
        sub = sc[(sc['pitcher_name'].map(_norm) == key) & (sc['game_date'] >= today)]
    if sub.empty:
        return None
    row = sub.sort_values('game_date').iloc[0]
    first_pitch = _first_pitch_et(str(row['team']), str(row['game_date']))
    return {'date': str(row['game_date']), 'first_pitch_et': first_pitch,
            'opp': str(row['opp_team_abbrev'])}


def _first_pitch_et(team_name: str, game_date: str):
    """First-pitch ET via MLB statsapi (fail-soft to None → date-only deadline)."""
    import requests
    try:
        teams = requests.get('https://statsapi.mlb.com/api/v1/teams',
                             params={'sportId': 1}, timeout=15).json().get('teams', [])
        tid = next((t['id'] for t in teams if t.get('name') == team_name), None)
        if tid is None:
            return None
        games = requests.get('https://statsapi.mlb.com/api/v1/schedule',
                             params={'sportId': 1, 'teamId': tid, 'date': game_date},
                             timeout=15).json()
        for d in games.get('dates', []):
            for g in d.get('games', []):
                iso = g.get('gameDate')
                if iso:
                    dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET)
                    return dt.isoformat(timespec='minutes')
    except Exception:
        pass
    return None


_MOVE_RE = re.compile(r'(?:drop\s+(?P<drop>.+?))?\s*(?:add\s+(?P<add>.+?))?\s*$',
                      re.IGNORECASE)


def _parse_move(raw: str) -> dict:
    if ';' in raw:
        action, cond = [p.strip() for p in raw.split(';', 1)]
    else:
        action, cond = raw.strip(), None
    m = _MOVE_RE.match(action)
    drop = (m.group('drop') or '').strip() or None
    add = (m.group('add') or '').strip() or None
    if not drop and not add:
        raise SystemExit(f'unparseable move: {raw!r}')
    when = None
    if cond:
        cm = re.match(r'(before|after)-start-of\s+(.+)', cond, re.IGNORECASE)
        if not cm:
            raise SystemExit(f'unparseable condition: {cond!r} '
                             f'(use before-start-of NAME / after-start-of NAME)')
        when = {'type': cm.group(1).lower(), 'player': cm.group(2).strip()}
    return {'drop': drop, 'add': add, 'when': when}


def _rp_floor_guard(moves: list[dict]) -> None:
    """4 true RPs is a FLOOR: refuse a plan whose drops include an RP without a
    same-plan RP add (roles via detect-time kind + rprs2 membership heuristic)."""
    from lib.pitcher_role import detect_pitcher_role  # noqa: F401  (documented owner)
    rprs2 = ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv'
    rp_ids = set()
    if rprs2.exists():
        try:
            rp_ids = set(pd.read_csv(rprs2, usecols=['pitcher'])['pitcher'].astype(int))
        except Exception:
            rp_ids = set()
    dropped_rp = [mv['drop'] for mv in moves
                  if mv.get('drop_id') and mv['drop_id'] in rp_ids and mv['drop_kind'] == 'P']
    added_rp = [mv['add'] for mv in moves
                if mv.get('add_id') and mv['add_id'] in rp_ids and mv['add_kind'] == 'P']
    if dropped_rp and len(added_rp) < len(dropped_rp):
        raise SystemExit(
            f"REFUSED: plan drops RP(s) {dropped_rp} without matching RP add(s) — "
            f"Josh's standing rule: 4 true RPs is a FLOOR; RP drops are only "
            f"RP-for-RP upgrades (CLAUDE.md 2026-07-18).")


def cmd_plan(args) -> int:
    moves = [_parse_move(raw) for raw in args.move]
    for i, mv in enumerate(moves, 1):
        mv['seq'] = i
        for side in ('drop', 'add'):
            if mv[side]:
                pid, kind = _resolve(mv[side])
                mv[f'{side}_id'], mv[f'{side}_kind'] = pid, kind
                if pid is None:
                    print(f'  ⚠ could not resolve {mv[side]!r} — deadlines still '
                          f'computed, verify will match by name')
        if mv['when']:
            wid, _ = _resolve(mv['when']['player'])
            nxt = _next_start(mv['when']['player'], wid)
            mv['when']['start'] = nxt
            if nxt is None:
                print(f"  ⚠ no probable start found for {mv['when']['player']} — "
                      f"condition recorded without a clock")
            else:
                fp = nxt['first_pitch_et']
                if mv['when']['type'] == 'before':
                    mv['deadline_et'] = fp or f"{nxt['date']} (lineup lock — time unknown)"
                else:
                    if fp:
                        dt = datetime.fromisoformat(fp) + timedelta(hours=4)
                        mv['earliest_et'] = dt.isoformat(timespec='minutes')
                    else:
                        mv['earliest_et'] = f"{nxt['date']} evening (time unknown)"
    _rp_floor_guard(moves)

    plan = {'created': datetime.now(ET).isoformat(timespec='seconds'),
            'team': MY_TEAM_NAME, 'moves': moves}
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    path = PLAN_DIR / f"plan_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(plan, indent=2), encoding='utf-8')

    print(f"\nCHURN PLAN — {plan['created']}  (saved {path.name})")
    print('=' * 72)
    for mv in moves:
        parts = []
        if mv['drop']:
            parts.append(f"DROP {mv['drop']}")
        if mv['add']:
            parts.append(f"ADD {mv['add']}")
        line = f"{mv['seq']}. " + ' → '.join(parts)
        print(line)
        if mv.get('deadline_et'):
            print(f"     ⏰ BEFORE first pitch: {mv['deadline_et']} "
                  f"({mv['when']['player']} vs {mv['when']['start']['opp']})")
        if mv.get('earliest_et'):
            print(f"     ⏰ NOT BEFORE: {mv['earliest_et']} "
                  f"(after {mv['when']['player']}'s start)")
        if mv['drop']:
            print(f"     ♻ waiver note: {mv['drop']} sits on ~24-48h waivers "
                  f"(claim-back window if this goes sideways)")
    print("\nSP moves change weekly cap math — run /cap-check for the banked "
          "count. Verify execution later with: run_churn_plan.py verify")
    return 0


def cmd_verify(args) -> int:
    if args.plan:
        path = Path(args.plan)
    else:
        cands = sorted(glob.glob(str(PLAN_DIR / 'plan_*.json')))
        if not cands:
            print('no saved churn plans')
            return 1
        path = Path(cands[-1])
    plan = json.loads(path.read_text(encoding='utf-8'))

    from plv_clone.league_state import default_state
    teams = default_state().all_teams()
    mine = set(teams.loc[teams['team_name'] == MY_TEAM_NAME, 'player_name'].map(_norm))
    anywhere = set(teams['player_name'].map(_norm))
    now = datetime.now(ET)

    try:
        plan_created = datetime.fromisoformat(plan['created'])
    except (KeyError, ValueError):
        plan_created = None

    print(f"CHURN VERIFY — {now.isoformat(timespec='minutes')}  vs {path.name}")
    print('=' * 72)
    any_missed = False
    for mv in plan['moves']:
        drop_done = mv['drop'] is not None and _norm(mv['drop']) not in mine
        add_done = mv['add'] is not None and _norm(mv['add']) in mine
        checks = [c for c in (drop_done if mv['drop'] else None,
                              add_done if mv['add'] else None) if c is not None]
        deadline = mv.get('deadline_et')
        past = False
        deadline_dt = None
        if deadline and not deadline.endswith(')'):
            try:
                deadline_dt = datetime.fromisoformat(deadline)
                past = deadline_dt < now
            except ValueError:
                past = False
        # Deadline unresolved = the move HAS a start-condition but plan-time
        # found no posted probable for the condition player (no clock at all).
        unresolved = (mv.get('when') is not None
                      and mv['when'].get('start') is None
                      and not deadline and not mv.get('earliest_et'))
        # PENDING-WAIVER: drop confirmed executed but the add hasn't cleared,
        # and the drop is recent enough (<48h) that the ADD target may simply
        # still be inside BrownU's ~24-48h waiver window (faab=False). We
        # don't log drop-execution timestamps, so the best available proxy is
        # the moment the drop became due/possible: the move deadline if past,
        # else plan creation time.
        in_waiver_window = False
        if drop_done and mv['add'] and not add_done:
            ref = deadline_dt if (deadline_dt is not None and past) else plan_created
            if ref is not None:
                in_waiver_window = (now - ref) < timedelta(hours=48)
        if all(checks):
            status = 'EXECUTED ✓'
        elif in_waiver_window:
            status = 'PENDING-WAIVER ⏳'
        elif any(checks):
            status = 'PARTIAL ◐'
        elif past:
            status, any_missed = 'MISSED ✗', True
        else:
            status = 'PENDING …'
        desc = ' → '.join(p for p in (f"drop {mv['drop']}" if mv['drop'] else None,
                                      f"add {mv['add']}" if mv['add'] else None) if p)
        print(f"{mv['seq']}. [{status}] {desc}"
              + (f"   (deadline was {deadline})" if past else
                 f"   (deadline {deadline})" if deadline else ''))
        if status == 'PENDING-WAIVER ⏳':
            print(f"     ⏳ drop confirmed off roster; {mv['add']} not yet mine — "
                  f"likely clearing BrownU's ~24-48h waivers. Re-verify after the "
                  f"window; if still missing, treat as PARTIAL and re-plan.")
        if status.startswith('PENDING') and unresolved:
            print(f"     ⏰ deadline unresolved — re-verify when "
                  f"{mv['when']['player']}'s next probable posts")
        if mv['add'] and not add_done and _norm(mv['add']) in anywhere:
            owner = teams.loc[teams['player_name'].map(_norm) == _norm(mv['add']),
                              'team_name'].iloc[0]
            print(f"     ⚠ {mv['add']} is now on {owner} — add no longer possible")
    if any_missed and SCHED_CSV.exists():
        today = now.date().isoformat()
        sc = pd.read_csv(SCHED_CSV, usecols=['game_date', 'pitcher_name'])
        later = sc[sc['game_date'] > today]['pitcher_name'].head(8).tolist()
        if later:
            print(f"\nSalvage: upcoming probables to re-plan around: {', '.join(later)}"
                  f"\n(run /streamer-precision-board for ranked alternatives)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--move', action='append', required=True,
                   help='"[drop NAME] [add NAME] [; before-start-of NAME | ; after-start-of NAME]"')
    v = sub.add_parser('verify')
    v.add_argument('--plan', default=None)
    args = ap.parse_args()
    return {'plan': cmd_plan, 'verify': cmd_verify}[args.cmd](args)


if __name__ == '__main__':
    raise SystemExit(main())
