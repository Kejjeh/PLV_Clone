"""fa_move_planner_v2.py — slot-aware with IL activation accounting.

Every IL'd player on Ligers consumes a roster slot when activated.
If roster is full, each activation requires a drop. Pickup of a NEW
FA hitter requires a separate drop on TOP of any pending IL activations.

This version:
  1. Inventories full roster (hitter + pitcher, active + IL + BE)
  2. Counts available slots (roster cap vs used)
  3. Lists all Ligers IL'd players with expected return signal
  4. Computes net-slot-impact of each pending move
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import ast
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

HITTER_SLOTS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF',
                'DH', 'UTIL', 'MI', 'CI'}
IL_STATUSES = {'TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'DAY_TO_DAY',
                'INJURY_RESERVE', 'IL_60', 'IL_15', 'IL_10', 'DAY-TO-DAY',
                'OUT', 'PATERNITY', 'SUSPENSION'}


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z]+', '', s)


def main():
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    my_team = next(t for t in league.teams if t.team_name == 'New York Ligers')

    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rh['nk'] = rh['player_name'].map(_norm)
    rh_lkup = rh.drop_duplicates('nk').set_index('nk').to_dict('index')

    try:
        rp3 = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
        rp3['nk'] = rp3['player_name'].map(_norm)
        rp3_lkup = rp3.drop_duplicates('nk').set_index('nk').to_dict('index')
    except Exception:
        rp3_lkup = {}

    print(f'=== Ligers FULL ROSTER ({len(my_team.roster)} players) ===\n')

    active_hitters, bench_hitters, il_hitters = [], [], []
    active_pitchers, bench_pitchers, il_pitchers = [], [], []

    for p in my_team.roster:
        nk = _norm(p.name)
        slots = list(getattr(p, 'eligibleSlots', []) or [])
        is_hitter = bool(set(slots) & HITTER_SLOTS)
        injury = getattr(p, 'injuryStatus', 'ACTIVE')
        lineup_slot = getattr(p, 'lineupSlot', '?')
        prj = rh_lkup.get(nk, {}) if is_hitter else rp3_lkup.get(nk, {})
        rec = {
            'name': p.name,
            'pos': getattr(p, 'position', '?'),
            'slots': [s for s in slots if s != 'BE' and s != 'IL'],
            'ros': prj.get('expected_total_fp_remaining', 0) or 0,
            'injury': injury,
            'lineup_slot': lineup_slot,
        }
        on_il = (injury in IL_STATUSES) or (lineup_slot in ('IL', 'INJURY_RESERVE'))
        on_bench = (lineup_slot == 'BE')
        if is_hitter:
            (il_hitters if on_il else bench_hitters if on_bench else active_hitters).append(rec)
        else:
            (il_pitchers if on_il else bench_pitchers if on_bench else active_pitchers).append(rec)

    def show(title, group, show_ros=True):
        print(f'  --- {title} ({len(group)}) ---')
        for r in sorted(group, key=lambda x: -(x['ros'] or 0)):
            ros_s = f'RoS={r["ros"]:>6.1f}' if show_ros else ''
            print(f'    {r["name"]:<22s} {r["pos"]:<4s} slot={r["lineup_slot"]:<5s} '
                  f'inj={r["injury"]:<14s} {ros_s}')

    show('ACTIVE HITTERS', active_hitters)
    show('BENCHED HITTERS', bench_hitters)
    show('IL\'d HITTERS', il_hitters)
    show('ACTIVE PITCHERS', active_pitchers, show_ros=False)
    show('BENCHED PITCHERS', bench_pitchers, show_ros=False)
    show('IL\'d PITCHERS', il_pitchers, show_ros=False)

    # Roster slot accounting
    total = len(my_team.roster)
    il_total = len(il_hitters) + len(il_pitchers)
    active_total = len(active_hitters) + len(active_pitchers)
    bench_total = len(bench_hitters) + len(bench_pitchers)
    print(f'\n=== ROSTER SLOT INVENTORY ===')
    print(f'  Total players on roster: {total}')
    print(f'    Active: {active_total}')
    print(f'    Bench:  {bench_total}')
    print(f'    IL:     {il_total}')

    # ESPN BrownU likely has ~26 active + N IL slots. If total roster
    # is at cap, every IL activation needs a drop OR a bench-to-IL swap.

    # === MOVE IMPACT MODEL ===
    print(f'\n=== PENDING IL ACTIVATIONS (each costs 1 active/bench slot) ===')
    for r in sorted(il_hitters + il_pitchers, key=lambda x: -(x['ros'] or 0)):
        print(f'  {r["name"]:<22s} ({r["pos"]}) inj={r["injury"]:<14s}')

    print(f'\nIf each IL\'d Liger returns, must drop someone or move bench->IL.')
    print(f'Net hitter pickups require additional drops.')


if __name__ == '__main__':
    main()
