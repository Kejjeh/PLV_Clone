"""eval_screenshot_fas.py — evaluate specific FA list against rh3 + drift signal.

Reads the FA names from the 2026-05-12 screenshot and outputs:
  - rh3 RoS (validated cross-year r=0.62)
  - drift signal summary (v4-validated within-season skill shift)
  - position eligibility from ESPN
  - verdict
"""
from __future__ import annotations
from pathlib import Path
import sys
import unicodedata
import re
import pandas as pd
import numpy as np

from plv_clone.projections import PROJECTIONS
from plv_clone.paths import ROOT, OUTPUTS as OUT
sys.path.insert(0, str(ROOT))

FAS_FROM_SCREENSHOT = [
    'Hunter Goodman',
    'Matt Chapman',
    'Teoscar Hernandez',
    'Eugenio Suarez',
    'Max Muncy',
    'Ivan Herrera',
    'Willy Adames',
    'Chandler Simpson',
    'Jeremy Pena',
    'Yainer Diaz',
    'Marcus Semien',
    'Michael Busch',
    'Dillon Dingler',
    'Xander Bogaerts',
    'Jose Caballero',
    'Ceddanne Rafaela',
    'Bryson Stott',
    'Isaac Paredes',
    'Brandon Marsh',
    'Kyle Stowers',
    'Caleb Durbin',
]


# Name join key — OWNER: plv_clone.utils.name_match.join_key (order-independent,
# so "Fried, Max" == "Max Fried"). NEVER re-derive locally: 127 local copies
# drifted apart and mis-keyed Ryan O'Hearn's curly apostrophe (2026-07-28).
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402


def drift_summary(row):
    """Translate per-metric deltas into a +/- summary of skill direction."""
    if pd.isna(row.get('k_pct_delta')):
        return 'no_drift_data', 0
    # Skill direction: + per improvement, - per decline
    score = 0
    notes = []
    # K%: lower is better
    if pd.notna(row['k_pct_delta']):
        if row['k_pct_delta'] <= -3: score += 1; notes.append(f'K%↓{abs(row["k_pct_delta"]):.0f}')
        elif row['k_pct_delta'] >= 3: score -= 1; notes.append(f'K%↑{row["k_pct_delta"]:.0f}')
    # EV90: higher is better, strongest validated
    if pd.notna(row['ev_p90_delta']):
        if row['ev_p90_delta'] >= 3: score += 1; notes.append(f'EV90↑{row["ev_p90_delta"]:.1f}')
        elif row['ev_p90_delta'] <= -3: score -= 1; notes.append(f'EV90↓{abs(row["ev_p90_delta"]):.1f}')
    # whiff/swing: lower is better
    if pd.notna(row['whiff_per_swing_delta']):
        if row['whiff_per_swing_delta'] <= -3: score += 1; notes.append(f'whiff↓{abs(row["whiff_per_swing_delta"]):.0f}')
        elif row['whiff_per_swing_delta'] >= 3: score -= 1; notes.append(f'whiff↑{row["whiff_per_swing_delta"]:.0f}')
    # barrel%: higher better
    if pd.notna(row['barrel_pct_delta']):
        if row['barrel_pct_delta'] >= 2: score += 1; notes.append(f'brl↑{row["barrel_pct_delta"]:.1f}')
        elif row['barrel_pct_delta'] <= -2: score -= 1; notes.append(f'brl↓{abs(row["barrel_pct_delta"]):.1f}')
    return ', '.join(notes) if notes else 'flat', score


def main():
    rh3 = PROJECTIONS.rh3()
    rh3['_nk'] = rh3['player_name'].map(_norm)
    drift = pd.read_csv(OUT / 'skill_drift_2026.csv')
    drift['_nk'] = drift['name'].map(_norm)

    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    # NOTE: size=1500 was the pre-refactor cap. LeagueState bakes size=2000
    # internally per ADR-0004 — call espn-api League directly because
    # downstream code needs raw player objects (eligibleSlots, percent_owned).
    fas = league.free_agents(size=2000)
    fa_by_nk = {_norm(f.name): f for f in fas}
    rostered = set()
    for t in league.teams:
        for p in t.roster:
            rostered.add(_norm(p.name))

    print(f'{"="*120}')
    print(f'  FA EVAL (screenshot list) — rh3 RoS + validated drift signal')
    print(f'{"="*120}\n')

    print(f'  {"PLAYER":<22s} {"POS":<6s} {"%own":>5s} {"on_team":<12s} '
          f'{"rh3_RoS":>8s} {"signal":<6s} {"drift_score":>4s}  drift_notes')

    results = []
    for name in FAS_FROM_SCREENSHOT:
        nk = _norm(name)
        # 1. rh3 lookup
        rh_match = rh3[rh3['_nk'] == nk]
        rh_row = rh_match.iloc[0].to_dict() if not rh_match.empty else {}
        # 2. drift
        dr_match = drift[drift['_nk'] == nk]
        if not dr_match.empty:
            dr_row = dr_match.iloc[0]
            notes, score = drift_summary(dr_row)
        else:
            notes, score = 'no_drift_data', 0
        # 3. ESPN status
        fa = fa_by_nk.get(nk)
        if fa is None:
            on_team = 'NOT IN FA POOL'
            pos = '?'
            slots_s = ''
        elif nk in rostered:
            on_team = 'ROSTERED'
            pos = getattr(fa, 'position', '?')
            slots_s = ''
        else:
            on_team = 'FA'
            pos = getattr(fa, 'position', '?')
            slots = list(getattr(fa, 'eligibleSlots', []) or [])
            slots_s = ','.join(s for s in slots if s not in ('BE', 'IL'))
        pct_owned = float(getattr(fa, 'percent_owned', 0) or 0) if fa else 0
        ros = rh_row.get('expected_total_fp_remaining', 0) or 0
        signal = rh_row.get('signal', '?')
        results.append({
            'name': name, 'pos': pos, 'pct_owned': pct_owned,
            'on_team': on_team, 'rh3_ros': ros, 'signal': signal,
            'drift_score': score, 'drift_notes': notes, 'slots': slots_s,
        })

    # Sort by rh3 RoS desc
    results.sort(key=lambda r: -r['rh3_ros'])

    for r in results:
        print(f'  {r["name"]:<22s} {r["pos"]:<6s} {r["pct_owned"]:>4.0f}% '
              f'{r["on_team"]:<12s} {r["rh3_ros"]:>8.1f} {r["signal"]:<6s} '
              f'{r["drift_score"]:>+4d}  {r["drift_notes"]}')

    pd.DataFrame(results).to_csv(OUT / 'screenshot_fa_eval.csv', index=False)
    print(f'\nwrote {OUT / "screenshot_fa_eval.csv"}')


if __name__ == '__main__':
    main()
