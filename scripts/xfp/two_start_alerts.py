"""two_start_alerts.py — flag SPs scheduled for 2-start weeks in next 21 days.

Loads weekly_schedule_next_4w.json, buckets games by ISO Mon-Sun weeks
PER TEAM (since each MLB team's rotation drives SP start counts), then
for each Ligers SP (and FAs) counts probable starts per week.

A 2-start week is a roughly 19% league-average occurrence (17.8% empirically)
but knowing WHICH weeks they happen lets us stream the right ones.

Output:
  data/outputs/two_start_alerts.csv
  data/outputs/two_start_alerts.json
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json
import sys
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'


def main():
    sched_path = OUT / 'weekly_schedule_next_4w.json'
    if not sched_path.exists():
        print('Run weekly_schedule.py first'); return
    sched = json.loads(sched_path.read_text(encoding='utf-8'))

    # Walk all games; group by (probable_pitcher_id, iso_week_monday)
    # Each game appears in by_team for BOTH home & away — dedupe by gamePk.
    seen_pks = set()
    starts_by_pitcher_week = defaultdict(lambda: defaultdict(list))
    pitcher_names = {}
    for team, games in sched['by_team'].items():
        for g in games:
            gpk = g.get('gamePk')
            if gpk in seen_pks:
                continue
            seen_pks.add(gpk)
            for side in ['home', 'away']:
                pid = g.get(f'{side}_probable_id')
                pname = g.get(f'{side}_probable_name')
                if not pid:
                    continue
                week_key = (pd.Timestamp(g['date']).to_period('W-SUN')
                              .start_time.strftime('%Y-%m-%d'))
                starts_by_pitcher_week[pid][week_key].append({
                    'date': g['date'], 'team': team,
                    'opp': g['home'] if side == 'away' else g['away'],
                    'is_home': side == 'home',
                })
                pitcher_names[pid] = pname

    # Flatten + flag 2-start weeks
    rows = []
    for pid, weeks in starts_by_pitcher_week.items():
        for week, games in weeks.items():
            rows.append({
                'pitcher_id': pid,
                'pitcher_name': pitcher_names.get(pid),
                'week_start': week,
                'starts': len(games),
                'games': games,
            })
    df = pd.DataFrame(rows)
    two_start = df[df['starts'] >= 2].copy()
    print(f'Total probable starts mapped: {len(df)} pitcher-weeks')
    print(f'2-start weeks coming up: {len(two_start)} pitcher-weeks')

    # Filter to Ligers SPs + top-ros FAs
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    my_team = next(t for t in league.teams if t.team_name == 'New York Ligers')
    my_pids = {p.playerId: p.name for p in my_team.roster}
    # espn playerId is ESPN's, not MLB's. To match, build name lookup.
    my_names = {p.name for p in my_team.roster}

    df['on_ligers'] = df['pitcher_name'].isin(my_names)
    two_start_ligers = two_start[two_start['pitcher_name'].isin(my_names)]
    print(f'\nLIGERS SPs with 2-start weeks coming up:')
    if two_start_ligers.empty:
        print('  (none scheduled in next 4 weeks)')
    else:
        for _, r in two_start_ligers.iterrows():
            games_s = ', '.join(f'{g["date"]} vs {g["opp"]}' for g in r['games'])
            print(f'  {r["pitcher_name"]:<25s} week of {r["week_start"]}: {games_s}')

    # Top FAs with 2-start weeks (streamer alert)
    rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    rp_names = set(rp['player_name'].dropna())
    # Build FA set: in rp3 but not on any team
    rostered = set()
    for t in league.teams:
        for p in t.roster:
            rostered.add(p.name)
    fa_pitchers_with_2 = two_start[~two_start['pitcher_name'].isin(rostered)]
    # Cross-reference with rp3 for value
    rp_lookup = rp.set_index('player_name')['xfp_rp3_per_start'].to_dict()
    fa_pitchers_with_2 = fa_pitchers_with_2.copy()
    fa_pitchers_with_2['fp_per_start'] = fa_pitchers_with_2['pitcher_name'].apply(
        lambda n: rp_lookup.get(n, 0))
    fa_pitchers_with_2 = fa_pitchers_with_2.sort_values(
        ['week_start', 'fp_per_start'], ascending=[True, False])
    print(f'\nTOP FA STREAMERS WITH 2-START WEEKS:')
    for _, r in fa_pitchers_with_2.head(15).iterrows():
        games_s = ', '.join(f'{g["date"]} vs {g["opp"]}' for g in r['games'])
        print(f'  week {r["week_start"]}  {r["pitcher_name"]:<25s} '
              f'fp/start={r["fp_per_start"]:.2f}  {games_s}')

    df.to_csv(OUT / 'two_start_alerts.csv', index=False)
    payload = {
        'ligers_two_start': two_start_ligers.head(30).to_dict(orient='records'),
        'fa_two_start_streamers': fa_pitchers_with_2.head(30).to_dict(orient='records'),
    }
    with open(OUT / 'two_start_alerts.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'\nwrote two_start_alerts.csv + .json')


if __name__ == '__main__':
    main()
