"""fa_move_planner.py — slot-aware FA upgrade plan for Ligers."""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import ast
import pandas as pd

from plv_clone.projections import PROJECTIONS
from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

HITTER_SLOTS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF',
                'DH', 'UTIL', 'MI', 'CI'}


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z]+', '', s)


def _parse_slots(s):
    """eligibleSlots in FA csv is stored as a stringified Python list."""
    if isinstance(s, list): return s
    if not isinstance(s, str) or not s.startswith('['): return []
    try:
        return ast.literal_eval(s)
    except Exception:
        return []


def main():
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    my_team = next(t for t in league.teams if t.team_name == 'New York Ligers')

    rh = PROJECTIONS.rh3()
    rh['nk'] = rh['player_name'].map(_norm)
    rh_lkup = rh.drop_duplicates('nk').set_index('nk').to_dict('index')

    hitters = []
    for p in my_team.roster:
        nk = _norm(p.name)
        prj = rh_lkup.get(nk, {})
        slots = list(getattr(p, 'eligibleSlots', []) or [])
        hitter_slots = [s for s in slots if s in HITTER_SLOTS]
        if not hitter_slots:
            continue
        hitters.append({
            'name': p.name,
            'pos': getattr(p, 'position', '?'),
            'slots': hitter_slots,
            'ros': prj.get('expected_total_fp_remaining', 0) or 0,
            'sig': prj.get('signal', '—'),
            'injury': getattr(p, 'injuryStatus', 'ACTIVE'),
        })
    hitters.sort(key=lambda x: -x['ros'])

    print(f'=== Ligers HITTERS ({len(hitters)}) ranked by RoS ===')
    print(f'{"#":>2s} {"PLAYER":<22s} {"POS":<5s} {"RoS":>7s} {"SIG":>5s} {"INJ":<10s}  SLOTS')
    for i, h in enumerate(hitters, 1):
        slots_s = ','.join(h['slots'][:6])
        print(f'  {i:>2d} {h["name"]:<22s} {h["pos"]:<5s} {h["ros"]:>7.1f} '
              f'{h["sig"]:>5s} {h["injury"]:<10s}  {slots_s}')

    # Weakest 5
    weakest = sorted(hitters, key=lambda x: x['ros'])[:5]
    print(f'\n--- WEAKEST 5 LIGERS HITTERS (drop candidates) ---')
    for h in weakest:
        print(f'  {h["name"]:<22s} RoS={h["ros"]:>6.1f}  slots={",".join(h["slots"][:4])}  inj={h["injury"]}')

    # Top FAs
    fa = pd.read_csv(RES / 'fa_finder_validated.csv')
    fa = fa.sort_values('ros_fp', ascending=False).reset_index(drop=True)
    fa['slots_parsed'] = fa['eligibleSlots'].map(_parse_slots)

    print(f'\n--- TOP-15 FAs ranked by validated RoS ---')
    print(f'{"#":>2s} {"PLAYER":<22s} {"POS":<5s} {"%OWN":>5s} {"RoS":>7s} {"SIG":>5s}  SLOTS')
    for i in range(min(15, len(fa))):
        r = fa.iloc[i]
        slots_s = ','.join([s for s in r['slots_parsed'] if s in HITTER_SLOTS])
        print(f'  {i+1:>2d} {r["name"]:<22s} {r["position"]:<5s} {r["pct_owned"]:>4.0f}% '
              f'{r["ros_fp"]:>7.1f} {r["signal"]:>5s}  {slots_s}')

    # Swap impact: for each top FA, find the lowest-RoS Liger whose slots overlap
    print(f'\n--- SWAP IMPACT (drop lowest-RoS Liger whose slot the FA can fill) ---')
    print(f'  {"FA":<22s} {"FA_RoS":>7s}  {"BEST_DROP":<22s} {"DROP_RoS":>8s}  NET_GAIN')
    for i in range(min(15, len(fa))):
        r = fa.iloc[i]
        fa_slots = {s for s in r['slots_parsed'] if s in HITTER_SLOTS}
        if not fa_slots:
            continue
        # Restrict drop candidates to ACTIVE Ligers whose slots overlap
        candidates = [h for h in hitters
                       if set(h['slots']) & fa_slots
                       and h['injury'] in ('ACTIVE', 'NORMAL')]
        if not candidates:
            print(f'  {r["name"]:<22s} {r["ros_fp"]:>7.1f}  (no slot-overlap on roster)')
            continue
        drop = sorted(candidates, key=lambda x: x['ros'])[0]
        net = r['ros_fp'] - drop['ros']
        print(f'  {r["name"]:<22s} {r["ros_fp"]:>7.1f}  {drop["name"]:<22s} '
              f'{drop["ros"]:>8.1f}  {net:>+8.1f}')


if __name__ == '__main__':
    main()
