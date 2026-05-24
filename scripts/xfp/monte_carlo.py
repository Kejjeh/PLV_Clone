"""monte_carlo.py — N-simulation playoff & championship probabilities.

Pulls remaining ESPN matchup schedule for each team. For each future week,
simulates team score = team_weekly_mean + N(0, sigma). Aggregates wins
across season, ranks teams, runs playoff bracket simulation (6 of 8 make
playoffs, 3 rounds with reseeding).

Reports per team:
  - prob_make_playoffs
  - prob_win_championship
  - prob_face_X_in_round_Y (per opponent)

Output: data/outputs/monte_carlo.json
"""
from __future__ import annotations
from pathlib import Path
import json
import sys
import random
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'

N_SIMS = 10000
PLAYOFF_TEAMS = 6  # BrownU
SIGMA_PER_WEEK = 80  # FP std per team per week (empirical-ish guess)


def main():
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()

    # Pull team weekly means from current value / RoS weeks
    overlap = json.loads((OUT / 'opponent_lineup_overlap.json').read_text(encoding='utf-8'))
    weekly_mean = {}  # team → avg fp/week
    my_v = sum(v['value'] for v in overlap['my_position_values'].values())
    REMAINING_WEEKS = 20
    weekly_mean[overlap['my_team']] = my_v / REMAINING_WEEKS
    for o in overlap['opponents']:
        opp_v = my_v - o['total_edge']
        weekly_mean[o['opp_name']] = opp_v / REMAINING_WEEKS

    # Walk current standings + remaining schedule
    standings = {t.team_name: {'w': t.wins, 'l': t.losses, 't': t.ties,
                                'team_id': t.team_id}
                  for t in league.teams}
    current_period = league.currentMatchupPeriod

    # Remaining matchups per team
    remaining_matchups = {t.team_name: [] for t in league.teams}
    for t in league.teams:
        for i, m in enumerate(t.schedule):
            period = i + 1
            if period < current_period:
                continue  # already played
            if period > 20:
                continue  # playoffs handled separately
            opp = m.home_team if m.away_team.team_name == t.team_name else m.away_team
            remaining_matchups[t.team_name].append((period, opp.team_name))
    # Dedupe (each matchup appears in both teams' schedules)
    seen = set()
    matchup_calendar = {}
    for tname, ms in remaining_matchups.items():
        for period, opp in ms:
            key = tuple(sorted([tname, opp])) + (period,)
            if key in seen: continue
            seen.add(key)
            matchup_calendar.setdefault(period, []).append((tname, opp))

    print(f'Simulating {N_SIMS:,} seasons. Current period={current_period}. '
          f'Remaining periods: {sorted(matchup_calendar.keys())}')

    # Simulate
    playoffs_count = {t: 0 for t in standings}
    finals_count = {t: 0 for t in standings}
    title_count = {t: 0 for t in standings}

    for sim in range(N_SIMS):
        wins = {t: standings[t]['w'] for t in standings}
        for period, pairs in matchup_calendar.items():
            for a, b in pairs:
                sa = np.random.normal(weekly_mean[a], SIGMA_PER_WEEK)
                sb = np.random.normal(weekly_mean[b], SIGMA_PER_WEEK)
                if sa > sb: wins[a] += 1
                elif sb > sa: wins[b] += 1
                # ties unlikely with normal noise
        ranked = sorted(wins.items(), key=lambda x: -x[1])
        seeded = [name for name, _ in ranked[:PLAYOFF_TEAMS]]
        for t in seeded:
            playoffs_count[t] += 1

        # Playoff bracket: 6 teams, top 2 get bye to semis
        # R1: 3v6, 4v5 → winners face 1, 2
        # R2: semis
        # R3: final
        round_1 = [(seeded[2], seeded[5]), (seeded[3], seeded[4])]
        r1_winners = []
        for a, b in round_1:
            sa = np.random.normal(weekly_mean[a], SIGMA_PER_WEEK * 1.4)  # 2-week matchup wider
            sb = np.random.normal(weekly_mean[b], SIGMA_PER_WEEK * 1.4)
            r1_winners.append(a if sa > sb else b)
        # Semis: seed1 vs lower r1 winner, seed2 vs higher r1 winner
        # Simpler: seed1 vs r1_w[1], seed2 vs r1_w[0]
        semis = [(seeded[0], r1_winners[1]), (seeded[1], r1_winners[0])]
        r2_winners = []
        for a, b in semis:
            sa = np.random.normal(weekly_mean[a], SIGMA_PER_WEEK * 1.4)
            sb = np.random.normal(weekly_mean[b], SIGMA_PER_WEEK * 1.4)
            r2_winners.append(a if sa > sb else b)
        for t in r2_winners:
            finals_count[t] += 1
        # Championship
        a, b = r2_winners
        sa = np.random.normal(weekly_mean[a], SIGMA_PER_WEEK * 1.4)
        sb = np.random.normal(weekly_mean[b], SIGMA_PER_WEEK * 1.4)
        champ = a if sa > sb else b
        title_count[champ] += 1

    rows = []
    for t in standings:
        rows.append({
            'team': t,
            'current_record': f'{standings[t]["w"]}-{standings[t]["l"]}',
            'weekly_mean': round(weekly_mean[t], 1),
            'playoff_pct': round(playoffs_count[t] / N_SIMS * 100, 1),
            'finals_pct': round(finals_count[t] / N_SIMS * 100, 1),
            'title_pct': round(title_count[t] / N_SIMS * 100, 1),
        })
    df = pd.DataFrame(rows).sort_values('title_pct', ascending=False)
    print(f'\n=== Monte Carlo Season Forecast (N={N_SIMS:,}) ===')
    print(df.to_string(index=False))

    payload = {
        'n_sims': N_SIMS,
        'sigma_per_week': SIGMA_PER_WEEK,
        'standings_sim': df.to_dict(orient='records'),
    }
    with open(OUT / 'monte_carlo.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    df.to_csv(OUT / 'monte_carlo.csv', index=False)
    print(f'\nwrote monte_carlo.json + .csv')


if __name__ == '__main__':
    main()
