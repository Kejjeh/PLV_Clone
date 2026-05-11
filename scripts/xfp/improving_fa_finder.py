"""improving_fa_finder.py — intersect rolling-skill-trend with ESPN FA pool.

Surfaces TRUE free agents (not on any team) whose underlying skills are
trending UP over recent weeks. Combines:
  - rolling_skill_trend.json (IMPROVING flag per player)
  - ESPN free_agents (verified availability + percent_owned)
  - xfp_rh3_projections (RoS value + eligibility for slot fit)

Outputs the top actionable improving FAs ranked by:
  - Eligible slot fit on Ligers' weakest positions (C / UTIL / OF5)
  - RoS projection value
  - Roster % (higher = more urgent claim)
  - Skill-trend flags count (more positive flags = stronger improvement)
"""
from __future__ import annotations
from pathlib import Path
import json
import sys
import unicodedata
import re
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z]+', '', s)


def main():
    # Load rolling-skill data
    skill = json.loads((OUT / 'rolling_skill_trend.json').read_text(encoding='utf-8'))
    improving = [r for r in skill['results']
                  if r.get('trend') in ('IMPROVING', 'slight_up')]
    name_to_skill = {_norm(r['name']): r for r in improving}
    print(f'Skill-improving universe (IMPROVING + slight_up): {len(improving)}')

    # Pull ESPN free agents
    from app import espn_connector as ec
    league = ec._get_league()
    rostered = set()
    for t in league.teams:
        for p in t.roster:
            rostered.add(_norm(p.name))
    fas = league.free_agents(size=500)
    fa_info = []
    for fa in fas:
        nk = _norm(fa.name)
        if nk in rostered:
            continue
        if nk not in name_to_skill:
            continue
        # This player is BOTH a FA and improving
        sk = name_to_skill[nk]
        fa_info.append({
            'name': fa.name,
            'nk': nk,
            'position': getattr(fa, 'position', '?'),
            'proTeam': getattr(fa, 'proTeam', '?'),
            'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0),
            'eligibleSlots': list(getattr(fa, 'eligibleSlots', []) or []),
            'trend': sk['trend'],
            'flags': sk.get('flags', []),
            'n_pos_flags': sum(1 for f in sk.get('flags', []) if f.startswith('+')),
        })

    # Attach rh3 projection
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rh['nk'] = rh['player_name'].map(_norm)
    proj = rh.drop_duplicates('nk').set_index('nk')[[
        'xfp_rh3_per_pa', 'expected_total_fp_remaining', 'signal',
        'replacement_delta', 'primary_position'
    ]].to_dict('index')

    for fa in fa_info:
        p = proj.get(fa['nk'], {})
        fa['xfp_per_pa'] = p.get('xfp_rh3_per_pa', 0)
        fa['ros_fp'] = p.get('expected_total_fp_remaining', 0)
        fa['signal'] = p.get('signal', '—')
        fa['repl_delta'] = p.get('replacement_delta', 0)
        fa['primary_pos'] = p.get('primary_position', '?')

    fa_info.sort(key=lambda x: -(x['ros_fp'] or 0))

    print(f'\nTrue FAs from IMPROVING/slight_up universe: {len(fa_info)}')

    print(f'\n=== TOP IMPROVING FREE AGENTS (sorted by RoS, all are skill-trending up) ===')
    print(f'{"PLAYER":<25s} {"POS":<5s} {"%OWN":>6s} {"RoS":>7s} {"SIG":>5s} {"#+":>3s}  FLAGS')
    for fa in fa_info[:30]:
        flags_s = ', '.join(fa['flags'][:5])
        print(f'  {fa["name"]:<25s} {fa["position"]:<5s} {fa["pct_owned"]:>5.0f}% '
              f'{fa["ros_fp"]:>7.1f} {fa["signal"]:>5s} {fa["n_pos_flags"]:>3d}  {flags_s}')

    # Save
    pd.DataFrame(fa_info).to_csv(OUT.parent / 'research' / 'improving_fa.csv', index=False)
    print(f'\nwrote data/research/improving_fa.csv')


if __name__ == '__main__':
    main()
