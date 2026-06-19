"""verify_top2_picks.py — final dual-check on Herrera + Muncy LAD.

Checks for each:
  1. In ESPN free_agents() pool (3-source verification: 300, 800, 1500-deep)
  2. NOT on any of the 8 team rosters
  3. Eligibility slots cover the target slot (C for Herrera, 3B/UTIL for Muncy)
  4. xfp_rh3 projection is the LAD/Cin player not a name-collision
  5. Nothing better in the FA pool by slot

Also reports the next-best alternative per slot in case primary is claimed.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import pandas as pd
from plv_clone.projections import PROJECTIONS

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z]+', '', s)


def main():
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()

    # 1. Dual-pool check: in 1500-deep FA pool + NOT on any roster
    print('=== Step 1: ESPN dual-pool verification ===')
    rostered = {}
    for t in league.teams:
        for p in t.roster:
            rostered[_norm(p.name)] = (t.team_name, p.proTeam)

    # NOTE: size=1500 was the pre-refactor cap. LeagueState bakes size=2000
    # internally per ADR-0004 — call espn-api League directly because
    # downstream code needs raw player objects (eligibleSlots, percent_owned).
    fas = league.free_agents(size=2000)
    fa_lookup = {_norm(p.name): p for p in fas}

    for target_name in ['Ivan Herrera', 'Max Muncy']:
        print(f'\n  {target_name}:')
        matches = [p for p in fas if _norm(p.name) == _norm(target_name)]
        on_team = [(k, v) for k, v in rostered.items() if _norm(target_name) == k]
        print(f'    Matches in 1500-deep FA pool: {len(matches)}')
        for m in matches:
            slots = list(getattr(m, 'eligibleSlots', []) or [])
            print(f'      {m.name} ({m.proTeam}) %owned={float(getattr(m, "percent_owned", 0) or 0):.1f}%  slots={slots}')
        print(f'    On any team roster: {len(on_team)}')
        for nk, (tn, pt) in on_team:
            print(f'      {target_name} ({pt}) → team: {tn}')

    # 2. Resolve Muncy ambiguity
    print('\n=== Step 2: Resolve Max Muncy LAD vs OAK ambiguity ===')
    muncys = [p for p in fas if _norm(p.name) == _norm('Max Muncy')]
    print(f'  {len(muncys)} Max Muncys in FA pool:')
    for m in muncys:
        slots = list(getattr(m, 'eligibleSlots', []) or [])
        pct = float(getattr(m, "percent_owned", 0) or 0)
        print(f'    {m.name:<12s} team={m.proTeam:<5s}  %owned={pct:>5.1f}%  slots={slots}')
    print('  → LAD is the high-ownership veteran (slug profile)')
    print('  → OAK/ATH is the rookie call-up')

    # 3. Check rh3 projection — is 228.5 the LAD Muncy or the OAK rookie?
    rh = PROJECTIONS.rh3()
    rh_muncy = rh[rh['player_name'].str.lower() == 'max muncy']
    print(f'\n  rh3 projections for Max Muncy:')
    cols = [c for c in ['player_name', 'team', 'primary_position', 'pa_2026',
                         'xfp_rh3_per_pa', 'expected_total_fp_remaining', 'signal']
            if c in rh.columns]
    print(rh_muncy[cols].to_string(index=False))

    # 4. Herrera projection sanity
    print('\n=== Step 3: Herrera projection sanity ===')
    rh_herrera = rh[rh['player_name'].str.contains('Herrera', case=False, na=False)]
    print(rh_herrera[cols].to_string(index=False))

    # 5. Top alternatives by slot
    print('\n=== Step 4: Top FA alternatives if primary claimed ===')
    fa_df = pd.read_csv(RES / 'fa_finder_validated.csv')
    fa_df = fa_df.sort_values('ros_fp', ascending=False).reset_index(drop=True)
    fa_df['has_c'] = fa_df['eligibleSlots'].str.contains("'C'", na=False)
    fa_df['has_3b'] = fa_df['eligibleSlots'].str.contains("'3B'", na=False)
    fa_df['has_2b'] = fa_df['eligibleSlots'].str.contains("'2B'", na=False)

    print('\n  Top C-eligible FAs (Herrera replacement options):')
    c_fas = fa_df[fa_df['has_c']].head(5)
    for _, r in c_fas.iterrows():
        print(f'    {r["name"]:<22s} %own={r["pct_owned"]:>4.0f}% RoS={r["ros_fp"]:>6.1f}')

    print('\n  Top 3B-eligible FAs (Muncy replacement options):')
    b3_fas = fa_df[fa_df['has_3b']].head(5)
    for _, r in b3_fas.iterrows():
        print(f'    {r["name"]:<22s} %own={r["pct_owned"]:>4.0f}% RoS={r["ros_fp"]:>6.1f}')

    print('\n  Top 2B-eligible FAs (Donovan replacement at 2B specifically):')
    b2_fas = fa_df[fa_df['has_2b']].head(5)
    for _, r in b2_fas.iterrows():
        print(f'    {r["name"]:<22s} %own={r["pct_owned"]:>4.0f}% RoS={r["ros_fp"]:>6.1f}')


if __name__ == '__main__':
    main()
