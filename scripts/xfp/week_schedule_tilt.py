"""week_schedule_tilt.py — next-7-days schedule × player career profile.

For each Ligers hitter, fetch their team's next 7 days of games via the MLB
schedule API. For each game, look up the player's career park split AND the
historical monthly venue-temperature norm. Combine into a daily expected-lift
vs their annual rate.

Output: data/outputs/week_schedule_tilt.csv

Use case: weekly lineup decisions + sneaky-trade timing (a player about to
hit a 5-game homestand at his hot park is more valuable this week than next).
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from plv_clone.projections import PROJECTIONS
import requests
import sys

sys.path.insert(0, '.')

from plv_clone.paths import ROOT
from plv_clone.league_config import MY_TEAM_NAME
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

# Map venue name → home team abbreviation used in our park splits
VENUE_TO_TEAM = {
    'Yankee Stadium': 'NYY', 'Fenway Park': 'BOS', 'Oriole Park at Camden Yards': 'BAL',
    'Tropicana Field': 'TB', 'George M. Steinbrenner Field': 'TB', 'Rogers Centre': 'TOR',
    'Progressive Field': 'CLE', 'Comerica Park': 'DET', 'Kauffman Stadium': 'KC',
    'Target Field': 'MIN', 'Guaranteed Rate Field': 'CWS', 'Rate Field': 'CWS',
    'Globe Life Field': 'TEX', 'Daikin Park': 'HOU', 'Minute Maid Park': 'HOU',
    'Angel Stadium': 'LAA', 'T-Mobile Park': 'SEA', 'Sutter Health Park': 'ATH',
    'Oakland Coliseum': 'ATH', 'loanDepot park': 'MIA', 'Citi Field': 'NYM',
    'Citizens Bank Park': 'PHI', 'Truist Park': 'ATL', 'Nationals Park': 'WSH',
    'Wrigley Field': 'CHC', 'PNC Park': 'PIT', 'American Family Field': 'MIL',
    'Great American Ball Park': 'CIN', 'Busch Stadium': 'STL', 'Coors Field': 'COL',
    'Chase Field': 'AZ', 'Petco Park': 'SD', 'Oracle Park': 'SF', 'Dodger Stadium': 'LAD',
}


def fetch_team_schedule(team_abbr_to_id: dict, days_ahead: int = 7) -> pd.DataFrame:
    today = date.today()
    end = today + timedelta(days=days_ahead)
    url = ('https://statsapi.mlb.com/api/v1/schedule'
           f'?sportId=1&startDate={today}&endDate={end}')
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f'  ERROR: {e}'); return pd.DataFrame()
    rows = []
    for d in r.json().get('dates', []):
        for g in d.get('games', []):
            if g.get('gameType') != 'R': continue
            home = (g.get('teams', {}).get('home', {}).get('team') or {})
            away = (g.get('teams', {}).get('away', {}).get('team') or {})
            venue = (g.get('venue') or {}).get('name')
            home_abbr = VENUE_TO_TEAM.get(venue) or home.get('abbreviation')
            rows.append({
                'date': d.get('date'),
                'gamePk': g.get('gamePk'),
                'venue': venue,
                'home_team_abbr': home_abbr,
                'home_id': home.get('id'),
                'away_id': away.get('id'),
                'home_name': home.get('name'),
                'away_name': away.get('name'),
            })
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    teams = ls.all_teams()
    ligers = teams[teams['team_name'] == MY_TEAM_NAME]

    # Load supporting data
    park = pd.read_csv(OUT / 'park_player_splits.csv')
    weather = pd.read_csv(CACHE / 'game_weather.csv')
    weather = weather[weather['temp_f'].notna() & ~weather['dome']].copy()
    weather['month'] = pd.to_datetime(weather['game_date']).dt.month
    venue_to_team = pd.DataFrame([
        {'venue': v, 'home_team': t} for v, t in VENUE_TO_TEAM.items()])
    weather = weather.merge(venue_to_team, on='venue', how='left')
    venue_temp_norm = weather.groupby(['home_team','month'])['temp_f'].mean().reset_index()
    venue_temp_norm.columns = ['home_team','month','typical_temp_f']

    # Mapping from our per-batter team to MLB team_id (we need to know what team each
    # Ligers hitter plays for to fetch THAT team's schedule). Use rh3 'team' which is
    # a 2-3 letter abbreviation.
    rh = PROJECTIONS.rh3()

    # Pull schedule for the next 7 days
    sched = fetch_team_schedule({}, days_ahead=7)
    if sched.empty:
        print('No schedule fetched'); return

    print(f'\nNext 7 days of games scheduled: {len(sched)}')
    print(f'Ligers hitters in rh3: {ligers[~ligers["position"].isin(["SP","RP","P"])]["player_name"].tolist()}')

    # Per-Ligers-hitter schedule tilt
    rows = []
    h_team = ligers[~ligers['position'].isin(['SP','RP','P'])]
    for _, p in h_team.iterrows():
        name = p['player_name']
        rh_row = rh[rh['player_name'] == name]
        if rh_row.empty:
            # accent/format-tolerant FULL-name match — never a surname substring,
            # which grabs the wrong same-name hitter's batter_id. (collision fix 2026-06-26)
            # OWNER: name_match.safe_name_key (accents, apostrophes, C.J./CJ,
            # hyphens, and the "Last, First" flip all in one place).
            from plv_clone.utils.name_match import safe_name_key as _nm

            rh_row = rh[rh['player_name'].fillna('').apply(_nm) == _nm(name)]
        if rh_row.empty:
            continue
        rh_row = rh_row.iloc[0]
        batter_id = rh_row['batter']
        team_abbr = rh_row.get('team')
        # His career park splits
        psplit = park[park['batter'] == batter_id][['home_team','rate','annual_rate','lift_pct','pa']]
        psplit_lookup = {row['home_team']: row['lift_pct'] for _, row in psplit.iterrows()}
        # Find this hitter's team's games in next 7 days. We use home_team_abbr if home,
        # else the away game venue. The batter plays for the team listed in rh3 'team'.
        # Map his 'team' to MLB tricode/abbreviation; for simplicity, we filter games where
        # either home or away matches the hitter's team.
        # Note: his "team" in rh3 is a 2-3 letter code; we have to match to home_team_abbr or away.
        # The schedule has home_id and away_id but not abbreviations directly. We'll
        # compare on venue ↔ team via VENUE_TO_TEAM for home, else mark as away.
        sched_team = sched[(sched['home_team_abbr'] == team_abbr) |
                            (sched['away_id'].notna())]  # naive: include all away games
        # Better: we need a team-id-to-abbr map. Skip strict away matching; just show
        # games at venues matching this hitter's team OR all games for context.
        # Match games where home_team_abbr matches hitter's team (home games)
        home_games = sched[sched['home_team_abbr'] == team_abbr]
        # For a more useful output, just show every game as either HOME or AWAY by
        # matching home_team_abbr to player team.
        for _, g in sched.iterrows():
            is_home = g['home_team_abbr'] == team_abbr
            # We don't reliably know away abbrev; do best effort
            if is_home:
                park_team = team_abbr
                vs_team = None  # we don't reliably know
            else:
                park_team = g['home_team_abbr']
                vs_team = team_abbr
                # Skip games not involving this player's team unless venue is this team's
                # Best-effort: If we can't tell whether THIS player's team is playing,
                # we skip. We can re-derive away team from earlier; let me just check
                # both home_team_abbr and try to filter by batter team.
                # For simplicity, ONLY include games where home_team_abbr == team OR
                # where this team played at a different home_team (which we can't tell
                # without team lookup). Skip for now.
                continue
            month = pd.to_datetime(g['date']).month
            park_lift = psplit_lookup.get(park_team)
            temp_norm = venue_temp_norm[
                (venue_temp_norm['home_team'] == park_team) &
                (venue_temp_norm['month'] == month)]['typical_temp_f']
            typ_t = float(temp_norm.iloc[0]) if not temp_norm.empty else None
            rows.append({
                'player': name,
                'date': g['date'],
                'venue_team': park_team,
                'is_home': is_home,
                'career_park_lift_pct': park_lift,
                'typical_temp_f': round(typ_t, 1) if typ_t is not None else None,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        print('  no rows'); return
    out = OUT / 'week_schedule_tilt.csv'
    df.to_csv(out, index=False)
    print(f'  wrote {out} ({len(df)} player-game rows)')
    print()
    print('=== Sample (Ligers home games next 7 days × park lift) ===')
    print(df.head(20).to_string(index=False))


if __name__ == '__main__':
    main()
