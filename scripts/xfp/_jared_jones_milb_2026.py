"""Jared Jones 2026 MiLB rehab — velo and command check."""
import pandas as pd
import sys
pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 30)

JONES_MLBAM = 683003

# Try pybaseball Statcast minors
print("Trying pybaseball.statcast_pitcher (MLB-only):")
try:
    from pybaseball import statcast_pitcher
    df = statcast_pitcher('2026-03-01', '2026-05-27', JONES_MLBAM)
    print(f"  MLB statcast rows for Jones 2026: {len(df)}")
    if len(df):
        print(df[['game_date','pitch_type','release_speed','description','events']].head(20))
except Exception as e:
    print(f"  err: {e}")

# pybaseball minor league
print("\nTrying pybaseball.statcast_minor_league_pitcher:")
try:
    from pybaseball import statcast_minor_league_pitcher
    df = statcast_minor_league_pitcher('2026-03-01', '2026-05-27', JONES_MLBAM)
    print(f"  MiLB statcast rows: {len(df)}")
    if len(df):
        print(df.head())
except Exception as e:
    print(f"  err: {e}")

# Try the API call directly via savant URL — minor league savant exists
print("\nTrying baseballsavant minor-league CSV download:")
try:
    import urllib.request, io
    # Savant supports minor-league filter via &game_type=L (AAA) etc.
    url = (
        "https://baseballsavant.mlb.com/statcast_search/csv?"
        "all=true"
        "&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
        "&hfGT=R%7CPO%7CS%7C&hfC=&hfSea=2026%7C&hfSit=&player_type=pitcher"
        f"&hfOuts=&opponent=&pitcher_throws=&batter_stands=&hfSA=&game_date_gt=&game_date_lt="
        f"&hfInfield=&team=&position=&hfOutfield=&hfRO=&home_road=&hfFlag=&hfPull=&metric_1="
        f"&hfInn=&min_pitches=0&min_results=0&group_by=name&sort_col=pitches&player_event_sort=api_p_release_speed"
        f"&sort_order=desc&min_pas=0&pitchers_lookup%5B%5D={JONES_MLBAM}&minors=true&type=details"
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    df = pd.read_csv(io.BytesIO(data))
    print(f"  rows: {len(df)}")
    if len(df):
        print(f"  cols: {df.columns.tolist()[:30]}")
        print(df.head(3))
        # Save
        df.to_csv('data/research/jared_jones_milb_2026.csv', index=False)
        print(f"\n  saved to data/research/jared_jones_milb_2026.csv")
except Exception as e:
    print(f"  err: {e}")

# Try MLB Stats API for rehab game log
print("\nTrying MLB Stats API for game log:")
try:
    import urllib.request, json
    # statsapi gives full per-game pitching log
    url = f"https://statsapi.mlb.com/api/v1/people/{JONES_MLBAM}/stats?stats=gameLog&season=2026&group=pitching&sportId=11,12,13,14,16"
    # sportId 11=AAA, 12=AA, 13=A+, 14=A, 16=Rookie
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    splits = d.get('stats', [{}])[0].get('splits', [])
    print(f"  Game log entries (MiLB): {len(splits)}")
    rows = []
    for s in splits:
        stat = s.get('stat', {})
        rows.append({
            'date': s.get('date'),
            'team': s.get('team', {}).get('name'),
            'opp': s.get('opponent', {}).get('name'),
            'league': s.get('league', {}).get('name') if 'league' in s else None,
            'ip': stat.get('inningsPitched'),
            'h': stat.get('hits'),
            'r': stat.get('runs'),
            'er': stat.get('earnedRuns'),
            'bb': stat.get('baseOnBalls'),
            'k': stat.get('strikeOuts'),
            'hr': stat.get('homeRuns'),
            'pitches': stat.get('numberOfPitches'),
            'strikes': stat.get('strikes'),
            'era': stat.get('era'),
            'whip': stat.get('whip'),
        })
    if rows:
        gl = pd.DataFrame(rows).sort_values('date')
        print(gl.to_string(index=False))
        gl.to_csv('data/research/jared_jones_milb_gamelog_2026.csv', index=False)
        print("\n  saved to data/research/jared_jones_milb_gamelog_2026.csv")
    # Also pull MLB level (sportId=1)
    url2 = f"https://statsapi.mlb.com/api/v1/people/{JONES_MLBAM}/stats?stats=gameLog&season=2026&group=pitching&sportId=1"
    req2 = urllib.request.Request(url2, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req2, timeout=30) as r:
        d2 = json.loads(r.read())
    splits2 = d2.get('stats',[{}])[0].get('splits', [])
    print(f"\n  MLB-level entries: {len(splits2)}")
except Exception as e:
    print(f"  err: {e}")
