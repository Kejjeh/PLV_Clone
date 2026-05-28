"""Two tasks:
1. Check Suárez 2026 game log + IL stints
2. Pull user roster hitters, compute YoY trajectory + recency for each
"""
import pandas as pd
import duckdb
import sys
pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 30)

PARQ_26 = 'data/research/xfp_cache/statcast_2026.parquet'
MULTIYR = 'data/research/xfp_cache/hitters_multiyr_2015_2026.csv'

# ===== Task 1: Suárez game log + IL =====
print("="*80)
print("SUÁREZ 2026 GAME LOG (batter=553993)")
print("="*80)
con = duckdb.connect()
gl = con.execute(f"""
    SELECT game_date,
           COUNT(DISTINCT (game_pk, at_bat_number)) AS pa,
           SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
           SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
           AVG(launch_speed) AS avg_ev,
           MAX(launch_speed) AS max_ev,
           AVG(CASE WHEN events IS NOT NULL AND events != ''
                    THEN estimated_woba_using_speedangle END) AS xwoba_pa
    FROM read_parquet('{PARQ_26}')
    WHERE batter = 553993
    GROUP BY game_date
    ORDER BY game_date
""").df()
print(gl.to_string(index=False))
print(f"\nFirst game: {gl['game_date'].min()}   Last game: {gl['game_date'].max()}")
print(f"Total games played: {len(gl)}")
print(f"Total PA: {gl['pa'].sum()}")

# Gap analysis — detect IL stints from game-date gaps > 10 days
gl['game_date'] = pd.to_datetime(gl['game_date'])
gl = gl.sort_values('game_date').reset_index(drop=True)
gl['gap_days'] = gl['game_date'].diff().dt.days
print("\nGame-date gaps > 7 days (possible IL stints):")
gaps = gl[gl['gap_days'] > 7]
if len(gaps):
    print(gaps[['game_date','gap_days']].to_string(index=False))
else:
    print("  None")
print()

# ===== Task 2: roster hitter YoY =====
print("="*80)
print("USER ROSTER — pulling live")
print("="*80)
sys.path.insert(0, 'c:/Users/Joshua/plv_clone')
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
print(f"Roster size: {len(roster)}")
HITTER_POSITIONS = {'C','1B','2B','3B','SS','OF','DH','MI','CI','UTIL','LF','CF','RF'}
hitters = roster[roster['position'].isin(HITTER_POSITIONS)].copy()
print(f"\nHitters on roster ({len(hitters)}):")
print(hitters[['player_name','player_id','position','lineup_slot','injured','injury_status']].to_string(index=False))

# Resolve player IDs (ESPN player_id ≠ MLBAM batter id)
df = pd.read_csv(MULTIYR)
# Build a fuzzy lookup: name → batter id (most recent year)
df_recent = df.sort_values('year', ascending=False).drop_duplicates('player_name')[['player_name','batter']]
name_to_bid = dict(zip(df_recent['player_name'].str.strip().str.lower(),
                       df_recent['batter']))

def resolve(name):
    norm = name.strip().lower()
    if norm in name_to_bid:
        return name_to_bid[norm]
    # try ascii fold for accents
    import unicodedata
    ascii_norm = ''.join(c for c in unicodedata.normalize('NFKD', norm) if not unicodedata.combining(c))
    for k, v in name_to_bid.items():
        k_ascii = ''.join(c for c in unicodedata.normalize('NFKD', k) if not unicodedata.combining(c))
        if k_ascii == ascii_norm:
            return v
    return None

print("\nResolving roster hitter IDs...")
hitters['mlbam'] = hitters['player_name'].apply(resolve)
print(hitters[['player_name','position','mlbam']].to_string(index=False))

# ===== YoY trajectory for each rostered hitter =====
print("\n" + "="*80)
print("YOY TRAJECTORY — each rostered hitter")
print("="*80)
cols = ['year','pa','xwoba_per_pa','xwoba_on_contact','ev90','hard_hit_pct','barrel_pct',
        'k_pct','bb_pct','chase_pct','whiff_pct','hr_per_pa','iso','fp_per_pa_actual']

# Compact summary: career-best xwOBACON, 2024/2025/2026 row, recent gap
summary_rows = []
for _, h in hitters.iterrows():
    name = h['player_name']
    pid = h['mlbam']
    if pid is None or pd.isna(pid):
        print(f"\n!! {name} — no MLBAM match")
        continue
    sub = df[df['batter'] == int(pid)].sort_values('year')
    if sub.empty:
        print(f"\n!! {name} (mlbam={pid}) — empty multiyr")
        continue
    print(f"\n--- {name} ({h['position']}, mlbam={int(pid)}) ---")
    out = sub[cols].copy()
    for c in cols:
        if c in ('year','pa'): continue
        out[c] = out[c].round(3)
    print(out.to_string(index=False))

    # Build summary row: career xwOBACON peak, 25/26 deltas
    s25 = sub[sub['year']==2025].iloc[0] if (sub['year']==2025).any() else None
    s26 = sub[sub['year']==2026].iloc[0] if (sub['year']==2026).any() else None
    peak_xwobacon = sub['xwoba_on_contact'].max()
    peak_year = int(sub.loc[sub['xwoba_on_contact'].idxmax(),'year']) if not sub['xwoba_on_contact'].isna().all() else None
    summary_rows.append({
        'player': name, 'pos': h['position'],
        'peak_xwobacon': round(peak_xwobacon,3) if pd.notna(peak_xwobacon) else None,
        'peak_year': peak_year,
        'xw25': round(s25['xwoba_per_pa'],3) if s25 is not None else None,
        'xwc25': round(s25['xwoba_on_contact'],3) if s25 is not None else None,
        'pa26': int(s26['pa']) if s26 is not None else 0,
        'xw26': round(s26['xwoba_per_pa'],3) if s26 is not None else None,
        'xwc26': round(s26['xwoba_on_contact'],3) if s26 is not None else None,
        'fp_pa26': round(s26['fp_per_pa_actual'],3) if s26 is not None else None,
        'd_xwc': round((s26['xwoba_on_contact'] - s25['xwoba_on_contact']),3) if (s25 is not None and s26 is not None) else None,
    })

print("\n" + "="*80)
print("ROSTER HITTER YOY SUMMARY (sorted by 2026 xwOBA)")
print("="*80)
sdf = pd.DataFrame(summary_rows)
sdf = sdf.sort_values('xw26', ascending=False, na_position='last')
print(sdf.to_string(index=False))
