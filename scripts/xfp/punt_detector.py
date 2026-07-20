"""punt_detector.py — flag weeks where opponent will be cap-light on SP starts.

If your weekly opponent's SP rotation only generates 5-6 starts this week
(vs the 10-start cap), they can't fully utilize their pitching cap. You
can punt cap-fill on your side too and use the saved roster spot to claim
hot hitters / streamers. Adds value when opponent has off-week scheduling.

Loads:
  - weekly_schedule_next_4w.json (MLB games per team for this week)
  - ESPN current matchup (who Ligers face this week)
  - both rosters' SP eligibility list

Computes: each team's expected SP starts this week = sum of probable SP
appearances in their roster across the week.

Output: data/outputs/punt_detector.json
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import json
import sys
import pandas as pd

from plv_clone.paths import ROOT  # single source for the repo root (was a hardcoded literal)
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'

from plv_clone.cap_math import SP_CAP as WEEKLY_SP_CAP  # BrownU 10-starts/week cap (single source)
from plv_clone.league_config import MY_TEAM_NAME


def main():
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    my_team = next(t for t in league.teams if t.team_name == MY_TEAM_NAME)

    # Find current matchup
    period = league.currentMatchupPeriod
    opp_team = None
    for m in my_team.schedule:
        if m.home_team.team_name == MY_TEAM_NAME:
            if m.home_team.team_id == my_team.team_id:
                # check if THIS matchup is current (winner=None, scores still moving)
                if getattr(m, 'winner', None) is None and getattr(m, 'home_final_score', 0) >= 0:
                    opp_team = m.away_team
                    break
    # Fallback: walk schedule list at index period-1
    if opp_team is None and len(my_team.schedule) >= period:
        m = my_team.schedule[period - 1]
        opp_team = m.away_team if m.home_team.team_name == MY_TEAM_NAME else m.home_team
    if opp_team is None:
        print('Could not identify current opponent'); return
    print(f'\nThis week: Ligers vs {opp_team.team_name} (matchup period {period})')

    # Load probable schedule
    sched = json.loads((OUT / 'weekly_schedule_next_4w.json').read_text(encoding='utf-8'))
    week_start = pd.Timestamp(date.today()).to_period('W-SUN').start_time
    week_end = week_start + timedelta(days=6)

    # For each team's SPs, count probable starts in [week_start, week_end]
    def count_sp_starts(team):
        sp_names = {p.name for p in team.roster
                    if 'SP' in (getattr(p, 'eligibleSlots', None) or [])}
        # Their MLB team abbreviations
        proteams = {p.proTeam for p in team.roster
                    if 'SP' in (getattr(p, 'eligibleSlots', None) or [])}
        starts = 0
        for mlb_team in proteams:
            mlb_team_norm = str(mlb_team).upper()
            for g in sched['by_team'].get(mlb_team_norm, []):
                if not (week_start.date() <= pd.Timestamp(g['date']).date() <= week_end.date()):
                    continue
                prob_name = g.get('home_probable_name') if g['home'] == mlb_team_norm else g.get('away_probable_name')
                if prob_name and prob_name in sp_names:
                    starts += 1
        return starts

    my_starts = count_sp_starts(my_team)
    opp_starts = count_sp_starts(opp_team)

    print(f'\n=== Current week SP-cap utilization ===')
    print(f'  Ligers SPs probable starts this week: {my_starts} / {WEEKLY_SP_CAP} cap')
    print(f'  {opp_team.team_name} SPs probable: {opp_starts} / {WEEKLY_SP_CAP}')

    advice = []
    if opp_starts <= 6:
        advice.append(f'OPPONENT IS CAP-LIGHT ({opp_starts}/10 starts). They can\'t '
                       f'max out their pitcher slate. **Their week-total ceiling is lower.**')
    if my_starts >= 10:
        advice.append(f'YOU ARE AT CAP ({my_starts}/10 starts). Any extra SP starts won\'t count.')
    if my_starts < 8:
        advice.append(f'YOU ARE UNDER CAP ({my_starts}/10). Stream a 2-start SP if you can.')
    diff = my_starts - opp_starts
    if diff >= 3:
        advice.append(f'You\'re projected for {diff} MORE SP starts than opponent — structural cap edge.')
    elif diff <= -3:
        advice.append(f'Opponent projected for {-diff} MORE SP starts — you may need to stream.')

    if not advice:
        advice.append('Both teams roughly equal on SP-cap utilization this week.')
    print()
    for a in advice:
        print(f'  ⚠ {a}')

    payload = {
        'period': period, 'opp_name': opp_team.team_name,
        'cap': WEEKLY_SP_CAP,
        'my_starts': my_starts, 'opp_starts': opp_starts,
        'week_start': str(week_start.date()), 'week_end': str(week_end.date()),
        'advice': advice,
    }
    with open(OUT / 'punt_detector.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'\nwrote punt_detector.json')


if __name__ == '__main__':
    main()
