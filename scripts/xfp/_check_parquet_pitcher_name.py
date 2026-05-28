import duckdb
con = duckdb.connect()
cols = con.execute("DESCRIBE SELECT * FROM read_parquet('data/research/xfp_cache/statcast_2025.parquet') LIMIT 1").df()
print('2025 parquet columns:', cols['column_name'].tolist())

# Look for any pitcher name field
name_cols = [c for c in cols['column_name'] if 'name' in c.lower() or 'pitcher' in c.lower()]
print('candidates:', name_cols)

# Try searching for Henderson, Logan via known patterns
for yr in (2025, 2026):
    print(f'\n=== 2025-2026 distinct pitchers with name containing Henderson ===')
    try:
        # Most Statcast parquets have player_name = pitcher when it's a pitching event
        r = con.execute(f"""
            SELECT DISTINCT pitcher
            FROM read_parquet('data/research/xfp_cache/statcast_{yr}.parquet')
            WHERE pitcher IS NOT NULL
            LIMIT 0
        """).df()
        # Now try a name lookup via player_name (which can vary)
        # Statcast convention: 'player_name' is the BATTER. There's no pitcher_name column.
        # We need to use pybaseball or MLB Stats API. Easier: try the 'fielder' fields or check the
        # rolling_pitchers cache which has been built per pitcher.
    except Exception as e:
        print(f'  err: {e}')

# Easier: try pybaseball playerid_lookup
try:
    from pybaseball import playerid_lookup
    for name in [('Henderson', 'Logan'), ('Arrighetti', 'Spencer'), ('Jones', 'Jared')]:
        r = playerid_lookup(name[0], name[1])
        print(f'\n{name}:')
        print(r[['name_first','name_last','key_mlbam','mlb_played_first','mlb_played_last']].to_string(index=False))
except Exception as e:
    print(f'pybaseball failed: {e}')
con.close()
