import duckdb, pandas as pd, unicodedata
from plv_clone.projections import PROJECTIONS
con = duckdb.connect()

# Name join key — OWNER: plv_clone.utils.name_match.safe_name_key. Order-
# PRESERVING, space-separated ("kyle schwarber"), collapses curly-vs-straight
# apostrophes, C.J./CJ and hyphens. NEVER re-derive locally: a local copy
# mis-keyed Ryan O'Hearn's U+2019 apostrophe and printed an opponent's player
# as a FREE AGENT (2026-07-28). NOT join_key — that one sorts tokens and drops
# separators, which is a different (order-independent) key.
from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402

rp3 = PROJECTIONS.rp3()
def flip(s):
    if ',' in str(s):
        a,b = s.split(',',1)
        return f"{b.strip()} {a.strip()}"
    return s
rp3['display'] = rp3['player_name'].apply(flip)
rp3['key'] = rp3['display'].apply(_norm)
id_map = dict(zip(rp3['key'], rp3['pitcher']))

rookie_ids = {
    'Parker Messick': 800048, 'Trey Yesavage': 702056, 'Christian Scott': 681035,
    'Foster Griffin': 656492, 'Peter Lambert': 663567, 'Anthony Kay': 641743,
    'Brandon Sproat': 687075, 'Roki Sasaki': 808963, 'Tyler Phillips': 663969,
    'Andrew Painter': 691725,
}
for n, i in rookie_ids.items():
    id_map[_norm(n)] = i

rp3_lookup = {}
for _, r in rp3.iterrows():
    rp3_lookup[r['key']] = (int(r['rank']), r['xfp_rp3_per_start'])

targets = [
    ('Bryan Woo','AUTO','9'),('Drew Rasmussen','AUTO','19'),('Parker Messick','AUTO','26'),
    ('Trey Yesavage','PROB','48'),('Sonny Gray','PROB','37'),('Michael King','PROB','36'),
    ('Ryne Nelson','PROB','49'),('Christian Scott','PROB','64'),('Reid Detmers','PROB','61'),
    ('Ryan Weathers','PROB','34'),('Foster Griffin','PROB','68'),
    ('Framber Valdez','Q','42'),('Seth Lugo','Q','86'),('Bailey Ober','DNS','UR'),
]

SEASON_SQL = """
    SELECT
      COUNT(DISTINCT game_date) AS games,
      COUNT(*) AS pitches,
      AVG(CASE WHEN pitch_type IN ('FF','SI','FC') THEN release_speed END) AS fb_velo,
      SUM(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked','foul_tip') THEN 1 ELSE 0 END)*1.0 / NULLIF(COUNT(*),0) AS swstr_pct,
      SUM(CASE WHEN description IN ('called_strike','swinging_strike','swinging_strike_blocked','foul_tip') THEN 1 ELSE 0 END)*1.0 / NULLIF(COUNT(*),0) AS csw_pct,
      SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END)*1.0 / NULLIF(SUM(CASE WHEN events IS NOT NULL AND events <> '' THEN 1 ELSE 0 END),0) AS k_pct,
      SUM(CASE WHEN events IN ('walk','hit_by_pitch') THEN 1 ELSE 0 END)*1.0 / NULLIF(SUM(CASE WHEN events IS NOT NULL AND events <> '' THEN 1 ELSE 0 END),0) AS bb_pct,
      AVG(estimated_woba_using_speedangle) FILTER (WHERE events IS NOT NULL AND events <> '' AND launch_speed IS NOT NULL) AS xwoba_con,
      SUM(CASE WHEN launch_speed >= 95 THEN 1 ELSE 0 END)*1.0 / NULLIF(COUNT(*) FILTER (WHERE launch_speed IS NOT NULL),0) AS hardhit_pct
    FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
    WHERE pitcher = ? {extra}
"""

LAST_STARTS_SQL = """
    SELECT CAST(game_date AS DATE) AS gd,
           COUNT(*) AS pitches,
           AVG(CASE WHEN pitch_type IN ('FF','SI','FC') THEN release_speed END) AS fb_velo,
           SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
           SUM(CASE WHEN events IN ('walk','hit_by_pitch') THEN 1 ELSE 0 END) AS bb,
           SUM(CASE WHEN events IS NOT NULL AND events <> '' THEN 1 ELSE 0 END) AS bf,
           SUM(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked','foul_tip') THEN 1 ELSE 0 END)*1.0 / NULLIF(COUNT(*),0) AS swstr_pct,
           SUM(CASE WHEN events IN ('home_run') THEN 1 ELSE 0 END) AS hr
    FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
    WHERE pitcher = ?
    GROUP BY gd
    ORDER BY gd DESC LIMIT 4
"""

def fmt_pct(v):
    if pd.isna(v): return '   --'
    return f"{v*100:5.1f}%"
def fmt_velo(v):
    if pd.isna(v): return '   --'
    return f"{v:5.1f}"
def fmt_raw(v):
    if pd.isna(v): return '   --'
    return f"{v:.3f}"

for name, tier, pl_rank in targets:
    key = _norm(name)
    pid = id_map.get(key)
    if not pid:
        print(f"\n=== {name} ({tier}) PL#{pl_rank} | NO PID ===")
        continue
    season = con.execute(SEASON_SQL.format(extra=''), [pid]).df().iloc[0]
    l30 = con.execute(SEASON_SQL.format(extra="AND CAST(game_date AS DATE) >= DATE '2026-04-30'"), [pid]).df().iloc[0]
    games = con.execute(LAST_STARTS_SQL, [pid]).df()
    rp3r, rp3v = rp3_lookup.get(key, ('—','—'))
    print(f"\n=== {name} ({tier}) | PL#{pl_rank} | rp3 #{rp3r} ({rp3v if isinstance(rp3v,str) else f'{rp3v:.2f}'} fp/st) ===")
    print(f"  {'metric':10s} {'season':>9s}  {'L30d':>9s}")
    print(f"  {'games':10s} {int(season['games']):>9d}  {int(l30['games']):>9d}")
    print(f"  {'FB velo':10s} {fmt_velo(season['fb_velo']):>9s}  {fmt_velo(l30['fb_velo']):>9s}")
    print(f"  {'SwStr%':10s} {fmt_pct(season['swstr_pct']):>9s}  {fmt_pct(l30['swstr_pct']):>9s}")
    print(f"  {'CSW%':10s} {fmt_pct(season['csw_pct']):>9s}  {fmt_pct(l30['csw_pct']):>9s}")
    print(f"  {'K%':10s} {fmt_pct(season['k_pct']):>9s}  {fmt_pct(l30['k_pct']):>9s}")
    print(f"  {'BB%':10s} {fmt_pct(season['bb_pct']):>9s}  {fmt_pct(l30['bb_pct']):>9s}")
    print(f"  {'xwOBACON':10s} {fmt_raw(season['xwoba_con']):>9s}  {fmt_raw(l30['xwoba_con']):>9s}")
    print(f"  {'HardHit%':10s} {fmt_pct(season['hardhit_pct']):>9s}  {fmt_pct(l30['hardhit_pct']):>9s}")
    print(f"  Last starts:")
    for _, r in games.iterrows():
        print(f"    {r['gd']}  BF={int(r['bf']):2d} K={int(r['k']):2d} BB={int(r['bb']):d} HR={int(r['hr'])}  velo={fmt_velo(r['fb_velo'])}  swstr={fmt_pct(r['swstr_pct'])}")
