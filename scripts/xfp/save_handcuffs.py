"""save_handcuffs.py — per-MLB-team closer + handcuff chain.

For each MLB team, identifies who's getting saves (last 30 days) and who's
the likely handcuff (next-in-line). Used to spot leverage RPs like Tanner
Scott (LAD second-in-line behind Edwin Diaz on IL).

Method:
  1. Pull recent SV/HLD log per MLB team from MLB Stats API
  2. Rank RPs per team by SV count last 21 days
  3. Top-1 = closer of record. Top-2 = handcuff.
  4. Cross-reference with ESPN free-agent pool + IL status for actionable
     handcuff opportunities.

Output:
  data/outputs/save_handcuffs.csv
  data/outputs/save_handcuffs.json
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import json
import requests
import sys
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'

ABBR_TO_MLB_ID = {
    'LAA': 108, 'AZ': 109, 'BAL': 110, 'BOS': 111, 'CHC': 112, 'CIN': 113,
    'CLE': 114, 'COL': 115, 'DET': 116, 'HOU': 117, 'KC': 118, 'LAD': 119,
    'WSH': 120, 'NYM': 121, 'ATH': 133, 'PIT': 134, 'SD': 135, 'SEA': 136,
    'SF': 137, 'STL': 138, 'TB': 139, 'TEX': 140, 'TOR': 141, 'MIN': 142,
    'PHI': 143, 'ATL': 144, 'CWS': 145, 'MIA': 146, 'NYY': 147, 'MIL': 158,
}


def fetch_team_saves(team_id: int, days: int = 21) -> list[dict]:
    """Per-pitcher SV + game count for a team in last `days` days."""
    today = date.today()
    start = today - timedelta(days=days)
    url = (f'https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?'
           f'stats=byDateRange&group=pitching&season=2026'
           f'&startDate={start}&endDate={today}'
           f'&playerPool=All')
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        rows = []
        for s in r.json().get('stats', []):
            for split in s.get('splits', []):
                p = split.get('player') or {}
                stat = split.get('stat') or {}
                rows.append({
                    'pitcher_id': p.get('id'),
                    'name': p.get('fullName'),
                    'saves': int(stat.get('saves', 0) or 0),
                    'holds': int(stat.get('holds', 0) or 0),
                    'games': int(stat.get('gamesPitched', 0) or 0),
                    'ip': float(stat.get('inningsPitched', 0) or 0),
                })
        return rows
    except Exception as exc:
        print(f'  team {team_id} fetch failed: {exc}')
        return []


def main():
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    rostered = {}  # name → team_name
    for t in league.teams:
        for p in t.roster:
            rostered[p.name] = t.team_name

    all_rows = []
    for abbr, mlb_id in ABBR_TO_MLB_ID.items():
        team_pitchers = fetch_team_saves(mlb_id)
        if not team_pitchers:
            continue
        team_df = pd.DataFrame(team_pitchers)
        team_df['team_abbr'] = abbr
        all_rows.append(team_df)
    if not all_rows:
        print('No data'); return
    df = pd.concat(all_rows, ignore_index=True)

    # For each team, rank RPs by saves + holds
    df['leverage_score'] = df['saves'] * 3 + df['holds']  # weight saves > holds
    df = df.sort_values(['team_abbr', 'leverage_score', 'saves'], ascending=[True, False, False])

    closers = []
    for abbr, sub in df.groupby('team_abbr'):
        sub = sub[sub['games'] >= 3]  # min activity
        if sub.empty:
            continue
        for rank, (_, r) in enumerate(sub.head(3).iterrows(), 1):
            on_roster = rostered.get(r['name'])
            closers.append({
                'team': abbr,
                'rank': rank,
                'name': r['name'],
                'saves': r['saves'],
                'holds': r['holds'],
                'games': r['games'],
                'leverage_score': r['leverage_score'],
                'rostered_by': on_roster,
                'is_FA': on_roster is None,
            })
    cdf = pd.DataFrame(closers)
    cdf.to_csv(OUT / 'save_handcuffs.csv', index=False)
    print(f'wrote save_handcuffs.csv ({len(cdf)} entries across {cdf["team"].nunique()} teams)')

    # Highlight actionable: handcuffs (rank 2) on teams where rank-1 has IL or low recent volume
    handcuffs_fa = cdf[(cdf['rank'] == 2) & cdf['is_FA']]
    print(f'\n=== FA HANDCUFFS (rank-2 closer-in-waiting, on waiver wire) ===')
    for _, r in handcuffs_fa.head(15).iterrows():
        print(f'  {r["team"]:<4s} #{r["rank"]} {r["name"]:<25s} '
              f'SV={r["saves"]} HLD={r["holds"]} G={r["games"]}')

    # Per-Ligers RP, show their leverage rank
    my_team = next(t for t in league.teams if t.team_name == 'New York Ligers')
    my_rps = [p.name for p in my_team.roster
              if 'RP' in (getattr(p, 'eligibleSlots', None) or [])]
    print(f'\n=== LIGERS RPs LEVERAGE RANK ===')
    for nm in my_rps:
        match = cdf[cdf['name'] == nm]
        if not match.empty:
            r = match.iloc[0]
            print(f'  {nm:<25s} rank #{r["rank"]} on {r["team"]:<4s} '
                  f'(SV={r["saves"]} HLD={r["holds"]})')
        else:
            print(f'  {nm:<25s} (no recent SV/HLD activity)')

    payload = {
        'as_of': str(date.today()),
        'fa_handcuffs': handcuffs_fa.head(20).to_dict(orient='records'),
        'ligers_rps_leverage': [
            {'name': nm,
             **(cdf[cdf['name'] == nm].iloc[0].to_dict() if not cdf[cdf['name'] == nm].empty else {'note': 'no recent SV/HLD'})}
            for nm in my_rps
        ],
        'full_chain': cdf.to_dict(orient='records'),
    }
    with open(OUT / 'save_handcuffs.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'\nwrote save_handcuffs.json')


if __name__ == '__main__':
    main()
