"""Quick YoY comparison: Suárez, Teoscar Hernández, Spencer Steer, Trent Grisham."""
import pandas as pd
import duckdb
import numpy as np

pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 30)

MULTIYR = 'data/research/xfp_cache/hitters_multiyr_2015_2026.csv'
PARQ_26 = 'data/research/xfp_cache/statcast_2026.parquet'

df = pd.read_csv(MULTIYR)

# Find IDs
def find(name_frag):
    m = df[df['player_name'].fillna('').str.contains(name_frag, case=False, na=False)]
    ids = m[['player_name','batter']].drop_duplicates('batter')
    return ids

print("ID lookup:")
for frag in ['Eugenio', 'Teoscar', 'Spencer Steer', 'Trent Grisham']:
    print(f"  {frag}: {find(frag).head(3).to_dict('records')}")

PLAYERS = {
    'Suárez':   553993,
    'Teoscar':  606192,
    'Steer':    668715,   # confirm below
    'Grisham':  663757,
}

# Confirm and fix IDs if necessary
for name in ['Spencer Steer','Trent Grisham']:
    m = find(name)
    print(f"  resolved {name}: {m.to_dict('records')}")

# Career YoY table
cols = ['year','pa','xwoba_per_pa','xwoba_on_contact','ev90','hard_hit_pct','barrel_pct',
        'k_pct','bb_pct','chase_pct','whiff_pct','hr_per_pa','iso',
        'avg_swing_speed','squared_up_rate','blast_rate','fp_per_pa_actual']

for name, pid in PLAYERS.items():
    sub = df[df['batter'] == pid].sort_values('year')
    if sub.empty:
        print(f"\n!! {name} (pid={pid}) not found")
        continue
    print(f"\n================ {name} ({pid}) — career YoY ================")
    out = sub[cols].copy()
    for c in cols:
        if c in ('year','pa'): continue
        out[c] = out[c].round(3)
    print(out.to_string(index=False))

# L21d snapshot from Statcast 2026
print("\n================ L21d snapshots (2026) ================")
con = duckdb.connect()
last_date = con.execute(f"SELECT MAX(game_date) FROM read_parquet('{PARQ_26}')").fetchone()[0]
print(f"Most recent game_date in 2026 parquet: {last_date}")

PA_EVENTS = "('single','double','triple','home_run','field_out','strikeout','force_out','grounded_into_double_play','fielders_choice_out','hit_by_pitch','walk','sac_fly','sac_bunt','field_error','double_play','triple_play','catcher_interf')"

for name, pid in PLAYERS.items():
    q = f"""
        WITH last_date AS (SELECT MAX(game_date) AS md FROM read_parquet('{PARQ_26}'))
        SELECT
          COUNT(DISTINCT (game_pk, at_bat_number)) AS pa_l21,
          AVG(CASE WHEN events IN {PA_EVENTS} THEN estimated_woba_using_speedangle END) AS xwoba_pa,
          AVG(CASE WHEN events IS NOT NULL AND events != '' AND launch_speed IS NOT NULL
                   THEN estimated_woba_using_speedangle END) AS xwoba_con,
          AVG(launch_speed) AS avg_ev,
          SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
          SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
          SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
          SUM(CASE WHEN description IN ('swinging_strike','foul_tip','missed_bunt') THEN 1 ELSE 0 END)*1.0
            / NULLIF(SUM(CASE WHEN description IN ('swinging_strike','foul_tip','missed_bunt',
                                                    'foul','hit_into_play') THEN 1 ELSE 0 END),0)
            AS whiff_per_swing
        FROM read_parquet('{PARQ_26}'), last_date
        WHERE batter = {pid}
          AND game_date >= last_date.md - INTERVAL '21 days'
    """
    r = con.execute(q).fetchone()
    pa, xw, xc, ev, hr, k, bb, w = r
    if pa is None or pa == 0:
        print(f"  {name}: NO L21d data")
        continue
    print(f"  {name}: PA={pa}  xwOBA={xw:.3f}  xwOBACON={xc if xc is None else round(xc,3)}  EV={ev if ev is None else round(ev,1)}  HR={hr}  K={k}  BB={bb}  whiff/swing={w if w is None else round(w,3)}")

con.close()

# Year-over-year deltas (key)
print("\n================ Key YoY deltas (2025 → 2026 STD) ================")
for name, pid in PLAYERS.items():
    sub = df[df['batter']==pid].set_index('year')
    if 2025 not in sub.index or 2026 not in sub.index:
        continue
    r25, r26 = sub.loc[2025], sub.loc[2026]
    print(f"\n{name}:")
    print(f"  PA: 2025={int(r25['pa'])}  2026={int(r26['pa'])}")
    for c in ['xwoba_per_pa','xwoba_on_contact','ev90','hard_hit_pct','barrel_pct',
              'k_pct','bb_pct','chase_pct','whiff_pct','hr_per_pa','iso','fp_per_pa_actual']:
        if c not in r25.index or c not in r26.index:
            continue
        v25, v26 = r25[c], r26[c]
        if pd.isna(v25) or pd.isna(v26):
            continue
        delta = v26 - v25
        arrow = '↑' if delta > 0 else '↓'
        print(f"  {c:24s} 2025={v25:.3f}  2026={v26:.3f}  Δ={delta:+.3f} {arrow}")
