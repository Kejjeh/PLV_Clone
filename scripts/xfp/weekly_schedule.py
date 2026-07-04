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

from plv_clone.mlb_stats import get_schedule
from plv_clone.paths import ROOT
OUT = ROOT / 'data' / 'outputs'

MLB_TEAM_ID_TO_ABBR = {
    108: 'LAA', 109: 'AZ', 110: 'BAL', 111: 'BOS', 112: 'CHC', 113: 'CIN',
    114: 'CLE', 115: 'COL', 116: 'DET', 117: 'HOU', 118: 'KC', 119: 'LAD',
    120: 'WSH', 121: 'NYM', 133: 'ATH', 134: 'PIT', 135: 'SD', 136: 'SEA',
    137: 'SF', 138: 'STL', 139: 'TB', 140: 'TEX', 141: 'TOR', 142: 'MIN',
    143: 'PHI', 144: 'ATL', 145: 'CWS', 146: 'MIA', 147: 'NYY', 158: 'MIL',
}


def fetch_schedule(start: date, end: date) -> dict:
    """Per-team list of games + probables in [start, end].

    Delegates the raw fetch to the mlb_stats.get_schedule owner (item 9,
    2026-07-04) and maps team ids via this module's own MLB_TEAM_ID_TO_ABBR so
    the JSON output (consumed by playoff_ros / two_start_alerts / punt_detector)
    is unchanged. Regular-season games only (gameType 'R').
    """
    games = get_schedule(start, end)

    by_team = {abbr: [] for abbr in MLB_TEAM_ID_TO_ABBR.values()}
    for g in games:
        if g.get('game_type') != 'R':
            continue
        home_abbr = MLB_TEAM_ID_TO_ABBR.get(g.get('home_id'))
        away_abbr = MLB_TEAM_ID_TO_ABBR.get(g.get('away_id'))
        game_rec = {
            'date': g['date'], 'gamePk': g['game_pk'],
            'venue': g.get('venue_name'),
            'home': home_abbr, 'away': away_abbr,
            'home_probable_id': g.get('home_probable_id'),
            'home_probable_name': g.get('home_probable_name'),
            'away_probable_id': g.get('away_probable_id'),
            'away_probable_name': g.get('away_probable_name'),
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
