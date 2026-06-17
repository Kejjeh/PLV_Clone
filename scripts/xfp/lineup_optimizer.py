"""lineup_optimizer.py — weekly SP-cap-aware start optimizer.

Pulls Ligers SPs + next-7-day MLB schedule. For each SP, identifies probable
start dates (via MLB Stats API probablePitcher field + 5-day rotation
fallback). Projects fp per start using rp3 (matchup-adjusted if available).
Identifies cap-binding situations (>10 projected starts in week) and
recommends which lowest-EV starts to bench.

Background: BrownU league caps SP scoring at the first 10 starts per week.
Beyond 10, additional starts don't count. The optimizer flags weeks where
we're projected to have more than 10 starts so we can bench the worst ones.

Outputs:
  - data/outputs/lineup_optimizer_weekly.csv (per-start expected fp table)
  - data/outputs/lineup_optimizer.json       (dashboard JSON)

Usage:
    python scripts/xfp/lineup_optimizer.py
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import json
import sys
import unicodedata
import re

import pandas as pd
import requests

sys.path.insert(0, '.')

from plv_clone.paths import ROOT  # single source for the repo root (was a hardcoded literal)
OUT = ROOT / 'data' / 'outputs'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

from plv_clone.cap_math import SP_CAP, cap_excess_starts  # single source for the SP-cap rule
WEEK_CAP_SP_STARTS = SP_CAP  # BrownU 10-starts/week cap (was a local literal)

# MLB team_id → tricode mapping
TEAM_ID_TO_ABBR = {
    108: 'LAA', 109: 'AZ', 110: 'BAL', 111: 'BOS', 112: 'CHC', 113: 'CIN',
    114: 'CLE', 115: 'COL', 116: 'DET', 117: 'HOU', 118: 'KC', 119: 'LAD',
    120: 'WSH', 121: 'NYM', 133: 'ATH', 134: 'PIT', 135: 'SD', 136: 'SEA',
    137: 'SF', 138: 'STL', 139: 'TB', 140: 'TEX', 141: 'TOR', 142: 'MIN',
    143: 'PHI', 144: 'ATL', 145: 'CWS', 146: 'MIA', 147: 'NYY', 158: 'MIL',
}


def _strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


def _norm(s):
    """Normalize a name to a sorted-words key so 'Last, First' == 'First Last'."""
    s = _strip_accents(str(s)).lower()
    s = re.sub(r'[,]+', ' ', s)
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def fetch_week_schedule(days_ahead: int = 7) -> pd.DataFrame:
    today = date.today()
    end = today + timedelta(days=days_ahead - 1)
    url = (f'https://statsapi.mlb.com/api/v1/schedule?'
           f'sportId=1&startDate={today}&endDate={end}'
           f'&hydrate=probablePitcher')
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    rows = []
    for d in r.json().get('dates', []):
        for g in d.get('games', []):
            if g.get('gameType') != 'R':
                continue
            home = g['teams']['home']['team']
            away = g['teams']['away']['team']
            home_prob = g['teams']['home'].get('probablePitcher') or {}
            away_prob = g['teams']['away'].get('probablePitcher') or {}
            rows.append({
                'date': d['date'],
                'gamePk': g['gamePk'],
                'home_id': home['id'], 'home_abbr': TEAM_ID_TO_ABBR.get(home['id']),
                'away_id': away['id'], 'away_abbr': TEAM_ID_TO_ABBR.get(away['id']),
                'home_probable_id': home_prob.get('id'),
                'home_probable_name': home_prob.get('fullName'),
                'away_probable_id': away_prob.get('id'),
                'away_probable_name': away_prob.get('fullName'),
            })
    return pd.DataFrame(rows)


def main():
    from plv_clone.league_state import LeagueState
    teams = LeagueState().all_teams()
    ligers = teams[teams['team_name'] == 'New York Ligers']
    sps = ligers[ligers['position'].isin(['SP', 'P'])][['player_name', 'pro_team']]
    print(f'Ligers SPs: {len(sps)}')
    print(sps['player_name'].tolist())

    # Pull next-7-day schedule
    sched = fetch_week_schedule(days_ahead=7)
    print(f'\nWeek schedule: {len(sched)} games')

    # Load rp3 projections + name normalization
    rp3 = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    rp3['name_key'] = rp3['player_name'].map(_norm)
    # Dedupe by name_key — keep first (highest-rank duplicate)
    rp3 = rp3.drop_duplicates('name_key', keep='first')
    rp3_lookup = rp3.set_index('name_key')[['pitcher', 'xfp_rp3_per_start',
                                              'schedule_factor', 'xfp_rp3_per_start_sched']].to_dict('index')

    # For each SP, find their probable starts in week
    rows = []
    for _, sp in sps.iterrows():
        name = sp['player_name']
        nm = _norm(name)
        # Try direct match in probables (handles "Last, First" vs "First Last")
        for _, g in sched.iterrows():
            for side in ['home', 'away']:
                pname = g.get(f'{side}_probable_name')
                if not pname:
                    continue
                if _norm(pname) == nm:
                    # Find matching rp3 row
                    rp = rp3_lookup.get(nm) or {}
                    fp_base = rp.get('xfp_rp3_per_start')
                    fp_adj = rp.get('xfp_rp3_per_start_sched') or fp_base
                    rows.append({
                        'date': g['date'],
                        'pitcher': name,
                        'team_abbr': g[f'{side}_abbr'],
                        'opp_team_abbr': g['away_abbr'] if side == 'home' else g['home_abbr'],
                        'is_home': side == 'home',
                        'gamePk': g['gamePk'],
                        'xfp_per_start': fp_base,
                        'xfp_per_start_sched': fp_adj,
                    })

    starts = pd.DataFrame(rows).sort_values('date')

    if starts.empty:
        # Fallback: probables aren't published far ahead; use rotation cadence
        print('\nNo MLB probables matched. Using 5-day cadence fallback from rp3 schedule_factor.')
        # We'll project each rostered SP with one start in the week using their projection
        rp_l = rp3.merge(sps, left_on='player_name', right_on='player_name', how='inner')
        for _, r in rp_l.iterrows():
            rows.append({
                'date': 'TBD',
                'pitcher': r['player_name'],
                'team_abbr': r.get('team'),
                'opp_team_abbr': None,
                'is_home': None,
                'gamePk': None,
                'xfp_per_start': r['xfp_rp3_per_start'],
                'xfp_per_start_sched': r.get('xfp_rp3_per_start_sched') or r['xfp_rp3_per_start'],
            })
        starts = pd.DataFrame(rows)

    # Ensure numeric, fall back to base fp if sched-adj missing, or league average (~10) if all missing
    starts['xfp_per_start_sched'] = starts['xfp_per_start_sched'].fillna(starts['xfp_per_start'])
    starts['xfp_per_start_sched'] = starts['xfp_per_start_sched'].fillna(10.0)
    starts['xfp_per_start'] = starts['xfp_per_start'].fillna(starts['xfp_per_start_sched'])

    # Rank globally by xfp_per_start_sched, descending (display column).
    starts['rank'] = starts['xfp_per_start_sched'].rank(ascending=False, method='min').astype(int)
    # Cap which starts count via the canonical planning cap (cap_math): start the
    # best SP_CAP by projected FP, bench the rest. cap_excess_starts takes EXACTLY
    # the top SP_CAP (stable tie-break) — unlike rank<=cap, which over-counts when
    # ties straddle the boundary.
    _excess = cap_excess_starts(starts['xfp_per_start_sched'].tolist(), WEEK_CAP_SP_STARTS)
    starts['count_toward_cap'] = [i not in _excess for i in range(len(starts))]
    starts['decision'] = starts['count_toward_cap'].map(lambda x: 'START' if x else 'BENCH (cap)')

    total = len(starts)
    capped = starts['count_toward_cap'].sum()
    sum_count = starts.loc[starts['count_toward_cap'], 'xfp_per_start_sched'].sum()
    sum_total = starts['xfp_per_start_sched'].sum()
    benched_total = sum_total - sum_count

    print(f'\n=== Lineup Optimizer Summary ===')
    print(f'  Total projected SP starts this week: {total}')
    print(f'  Cap: {WEEK_CAP_SP_STARTS}')
    print(f'  Counting toward score: {capped}')
    if total > WEEK_CAP_SP_STARTS:
        print(f'  *** OVER CAP by {total - WEEK_CAP_SP_STARTS} starts ***')
        print(f'  Bench-loss without optimizing: {benched_total:.1f} fp (lowest ranked auto-skipped)')
    else:
        print(f'  Under cap by {WEEK_CAP_SP_STARTS - total}. All starts count.')
    print(f'  Expected counting-score fp this week: {sum_count:.1f}')

    print(f'\n=== Per-start ranking ===')
    cols = ['date', 'pitcher', 'team_abbr', 'opp_team_abbr', 'is_home',
            'xfp_per_start', 'xfp_per_start_sched', 'rank', 'decision']
    print(starts[cols].to_string(index=False))

    starts.to_csv(OUT / 'lineup_optimizer_weekly.csv', index=False)
    print(f'\nwrote {OUT / "lineup_optimizer_weekly.csv"}')

    payload = {
        'as_of': str(date.today()),
        'cap': WEEK_CAP_SP_STARTS,
        'total_starts': int(total),
        'counting_starts': int(capped),
        'expected_counting_fp': round(float(sum_count), 1),
        'bench_loss_if_unoptimized': round(float(benched_total), 1),
        'starts': starts[cols].to_dict(orient='records'),
    }
    with open(OUT / 'lineup_optimizer.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'wrote {OUT / "lineup_optimizer.json"}')


if __name__ == '__main__':
    main()
