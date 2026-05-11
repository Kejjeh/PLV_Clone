"""weekly_schedule.py — shared MLB schedule fetcher with probable pitchers.

Pulls the next N weeks of MLB games. Used by playoff_ros, two_start_alerts,
and punt_detector.

Output:
  data/outputs/weekly_schedule_next_N.json
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import argparse
import json
import requests

ROOT = Path('c:/Users/Joshua/plv_clone')
OUT = ROOT / 'data' / 'outputs'

MLB_TEAM_ID_TO_ABBR = {
    108: 'LAA', 109: 'AZ', 110: 'BAL', 111: 'BOS', 112: 'CHC', 113: 'CIN',
    114: 'CLE', 115: 'COL', 116: 'DET', 117: 'HOU', 118: 'KC', 119: 'LAD',
    120: 'WSH', 121: 'NYM', 133: 'ATH', 134: 'PIT', 135: 'SD', 136: 'SEA',
    137: 'SF', 138: 'STL', 139: 'TB', 140: 'TEX', 141: 'TOR', 142: 'MIN',
    143: 'PHI', 144: 'ATL', 145: 'CWS', 146: 'MIA', 147: 'NYY', 158: 'MIL',
}


def fetch_schedule(start: date, end: date) -> dict:
    """Per-team list of games + probables in [start, end]."""
    url = (f'https://statsapi.mlb.com/api/v1/schedule?'
           f'sportId=1&startDate={start}&endDate={end}'
           f'&hydrate=probablePitcher')
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    by_team = {abbr: [] for abbr in MLB_TEAM_ID_TO_ABBR.values()}
    for d in r.json().get('dates', []):
        for g in d.get('games', []):
            if g.get('gameType') != 'R':
                continue
            home_id = g['teams']['home']['team']['id']
            away_id = g['teams']['away']['team']['id']
            home_abbr = MLB_TEAM_ID_TO_ABBR.get(home_id)
            away_abbr = MLB_TEAM_ID_TO_ABBR.get(away_id)
            home_prob = (g['teams']['home'].get('probablePitcher') or {})
            away_prob = (g['teams']['away'].get('probablePitcher') or {})
            game_rec = {
                'date': d['date'], 'gamePk': g['gamePk'],
                'venue': (g.get('venue') or {}).get('name'),
                'home': home_abbr, 'away': away_abbr,
                'home_probable_id': home_prob.get('id'),
                'home_probable_name': home_prob.get('fullName'),
                'away_probable_id': away_prob.get('id'),
                'away_probable_name': away_prob.get('fullName'),
            }
            if home_abbr:
                by_team[home_abbr].append({**game_rec, 'is_home': True})
            if away_abbr:
                by_team[away_abbr].append({**game_rec, 'is_home': False})
    return by_team


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weeks', type=int, default=4)
    args = ap.parse_args()
    start = date.today()
    end = start + timedelta(days=args.weeks * 7)
    sched = fetch_schedule(start, end)
    out_path = OUT / f'weekly_schedule_next_{args.weeks}w.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'start': str(start), 'end': str(end),
                   'by_team': sched}, f, separators=(',', ':'))
    total_games = sum(len(v) for v in sched.values())
    print(f'wrote {out_path}: {total_games} team-game-rows across '
          f'{sum(1 for v in sched.values() if v)} teams in {args.weeks} weeks')


if __name__ == '__main__':
    main()
