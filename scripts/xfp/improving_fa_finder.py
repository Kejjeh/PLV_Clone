"""improving_fa_finder.py — TRUE FAs ranked by validated RoS projection.

Methodology (post-validation 2026-05-11):
  - PRIMARY ranker: xfp_rh3 RoS (validated cross-year r=0.62)
  - Trend flag used as a NEGATIVE filter only: drop DECLINING players
    (the only side of the trend signal with empirically meaningful
     rest-of-season effect; IMPROVING does NOT add signal beyond RoS)
  - See feedback_rolling_trend_short_horizon_only.md and
    scripts/xfp/validate_rolling_trend.py for the empirical backing.

Outputs:
  - Top FAs by RoS, with trend as informational context
  - data/research/fa_finder_validated.csv
"""
from __future__ import annotations
from pathlib import Path
import json
import sys
import unicodedata
import re
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z]+', '', s)


def main():
    # Load rolling-skill data — INFORMATIONAL ONLY (validation v3 showed
    # the flag is not robust across cutoff/horizon combos; partial r ≤ +0.03
    # everywhere and reverses at early cutoffs). DO NOT use as a filter or
    # co-ranker. See feedback_rolling_trend_short_horizon_only.md.
    skill = json.loads((OUT / 'rolling_skill_trend.json').read_text(encoding='utf-8'))
    name_to_skill = {_norm(r['name']): r for r in skill['results']}
    print(f'Universe with trend data (for info column only): {len(name_to_skill)}')

    # Pull ESPN free agents
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    rostered = set()
    for t in league.teams:
        for p in t.roster:
            rostered.add(_norm(p.name))
    # NOTE: size=500 was the pre-refactor cap. LeagueState bakes size=2000
    # internally per ADR-0004 — call the espn-api League directly here
    # because downstream code needs raw player objects (eligibleSlots, etc.).
    fas = league.free_agents(size=2000)

    # Attach rh3 projection (the validated cross-year r=0.62 ranker)
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rh['nk'] = rh['player_name'].map(_norm)
    proj = rh.drop_duplicates('nk').set_index('nk')[[
        'xfp_rh3_per_pa', 'expected_total_fp_remaining', 'signal',
        'replacement_delta', 'primary_position'
    ]].to_dict('index')

    fa_info = []
    for fa in fas:
        nk = _norm(fa.name)
        if nk in rostered:
            continue
        p = proj.get(nk, {})
        if not p:
            continue  # no validated RoS projection — skip
        sk = name_to_skill.get(nk, {})
        flags = sk.get('flags', [])
        fa_info.append({
            'name': fa.name,
            'nk': nk,
            'position': getattr(fa, 'position', '?'),
            'proTeam': getattr(fa, 'proTeam', '?'),
            'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0),
            'eligibleSlots': list(getattr(fa, 'eligibleSlots', []) or []),
            'trend': sk.get('trend', 'no_data'),
            'flags': flags,
            'n_pos_flags': sum(1 for f in flags if f.startswith('+')),
            'n_neg_flags': sum(1 for f in flags if f.startswith('-')),
            'xfp_per_pa': p.get('xfp_rh3_per_pa', 0),
            'ros_fp': p.get('expected_total_fp_remaining', 0),
            'signal': p.get('signal', '—'),
            'repl_delta': p.get('replacement_delta', 0),
            'primary_pos': p.get('primary_position', '?'),
        })

    # PRIMARY RANK: validated rh3 RoS (sole ranker; trend is info only)
    fa_info.sort(key=lambda x: -(x['ros_fp'] or 0))

    print(f'\nTrue FAs with RoS projection: {len(fa_info)}')

    print(f'\n=== TOP FREE AGENTS — ranked by xfp_rh3 RoS (validated, sole ranker) ===')
    print(f'  Trend column is INFO ONLY (no validated decision use at this cutoff)')
    print(f'\n{"PLAYER":<25s} {"POS":<6s} {"%OWN":>6s} {"RoS":>7s} {"SIG":>5s} {"TREND":<12s} FLAGS')
    for fa in fa_info[:30]:
        flags_s = ', '.join(fa['flags'][:4])
        print(f'  {fa["name"]:<25s} {fa["position"]:<6s} {fa["pct_owned"]:>5.0f}% '
              f'{fa["ros_fp"]:>7.1f} {fa["signal"]:>5s} {fa["trend"]:<12s} {flags_s}')

    # Save
    pd.DataFrame(fa_info).to_csv(OUT.parent / 'research' / 'fa_finder_validated.csv', index=False)
    print(f'\nwrote data/research/fa_finder_validated.csv')


if __name__ == '__main__':
    main()
