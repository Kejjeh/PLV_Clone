"""
Pull every team's roster into one CSV for league-wide /triangulate ranking.
Output: data/research/triangulate_universe/all_teams_roster.csv
Columns: player_name, player_id, position, bucket, team, lineup_slot, injured
"""
import sys, os, unicodedata
sys.path.insert(0, '.')
import pandas as pd
from app.espn_connector import _get_league

OUT = 'data/research/triangulate_universe/all_teams_roster.csv'
os.makedirs(os.path.dirname(OUT), exist_ok=True)

def classify_bucket(pos):
    p = str(pos).upper()
    if p == 'SP': return 'SP'
    if p == 'RP': return 'RP'
    if p in ('P','SP/RP','RP/SP'): return 'SP'
    return 'H'

league = _get_league()
rows = []
for team in league.teams:
    for p in team.roster:
        rows.append({
            'player_name': p.name,
            'player_id': p.playerId,
            'position': p.position,
            'bucket': classify_bucket(p.position),
            'team': team.team_name,
            'team_id': team.team_id,
            'lineup_slot': p.lineupSlot,
            'injured': p.injured,
        })
df = pd.DataFrame(rows)
df['category'] = df['team']  # so triangulate batch preserves it
df.to_csv(OUT, index=False)
print(f"Wrote {len(df)} rostered players across {df['team'].nunique()} teams to {OUT}")
print(df.groupby('team').size().to_string())
