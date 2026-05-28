"""Career deep-dive: Spencer Arrighetti vs Logan Henderson vs Jared Jones."""
from __future__ import annotations
import pandas as pd
import duckdb
import unicodedata
pd.set_option('display.width', 260)
pd.set_option('display.max_columns', 40)

SP_MULTIYR = 'data/research/xfp_cache/sp_multiyr_2015_2025.csv'
ROLLING    = 'data/research/xfp_cache/rolling_pitchers_2018_2026.csv'
RP3_PROJ   = 'data/outputs/xfp_rp3_projections.csv'
PARQ_TMPL  = 'data/research/xfp_cache/statcast_{yr}.parquet'

NAMES = ['Spencer Arrighetti', 'Logan Henderson', 'Jared Jones']

def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c)).lower().strip()

# ---- ID resolution from sp_multiyr ----
mm = pd.read_csv(SP_MULTIYR)
print("Possible matches in sp_multiyr (2015-2025):")
for name in NAMES:
    nf = fold(name)
    cands = mm[mm['player_name'].fillna('').apply(fold).str.contains(nf, na=False)]
    rows = cands[['player_name','pitcher','year','gs']].drop_duplicates('pitcher').head(10)
    print(f"\n  {name}:")
    print(rows.to_string(index=False))

# Spencer Arrighetti debuted 2024 (Astros), Jared Jones debuted 2024 (Pirates),
# Logan Henderson is a recent 2025-2026 prospect — may not be in sp_multiyr at all.
# We'll resolve via Statcast directly if multiyr misses anyone.

# Resolved via pybaseball playerid_lookup
con = duckdb.connect()
ids = {
    'Spencer Arrighetti': 681293,  # debut 2024, Astros
    'Logan Henderson':    701656,  # debut 2025, Brewers
    'Jared Jones':        683003,  # debut 2024, Pirates (missed 2025 IL)
}
for name, pid in ids.items():
    print(f"  {name}: pitcher_id={pid}")

# =========================================================================
# Per-pitcher career summary
# =========================================================================
print("\n\n" + "="*90)
print("CAREER YEAR-BY-YEAR (sp_multiyr-style aggregates)")
print("="*90)

def career_table_via_statcast(pid: int) -> pd.DataFrame:
    rows = []
    for yr in range(2024, 2027):
        pq = PARQ_TMPL.format(yr=yr)
        try:
            r = con.execute(f"""
                WITH pa_level AS (
                    SELECT pitcher, game_pk, at_bat_number, batter,
                           MAX(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS is_k,
                           MAX(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS is_bb,
                           MAX(CASE WHEN events='hit_by_pitch' THEN 1 ELSE 0 END) AS is_hbp,
                           MAX(estimated_woba_using_speedangle) AS xwoba_pa,
                           MAX(CASE WHEN events IN ('single','double','triple','home_run',
                                                     'field_out','strikeout','force_out',
                                                     'grounded_into_double_play','fielders_choice_out',
                                                     'hit_by_pitch','walk','sac_fly','field_error')
                                THEN 1 ELSE 0 END) AS is_pa_end
                    FROM read_parquet('{pq}')
                    WHERE pitcher = {pid}
                    GROUP BY pitcher, game_pk, at_bat_number, batter
                ),
                pitch_level AS (
                    SELECT COUNT(*) AS pitches,
                           SUM(CASE WHEN description IN ('swinging_strike','foul_tip','missed_bunt') THEN 1 ELSE 0 END) AS swstr,
                           SUM(CASE WHEN description IN ('called_strike') THEN 1 ELSE 0 END) AS cstr,
                           SUM(CASE WHEN description IN ('swinging_strike','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt') THEN 1 ELSE 0 END) AS swings,
                           SUM(CASE WHEN zone BETWEEN 1 AND 9 THEN 1 ELSE 0 END) AS in_zone,
                           SUM(CASE WHEN zone NOT BETWEEN 1 AND 9 AND description IN ('swinging_strike','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt') THEN 1 ELSE 0 END) AS o_swings,
                           SUM(CASE WHEN zone NOT BETWEEN 1 AND 9 THEN 1 ELSE 0 END) AS o_pitches,
                           AVG(CASE WHEN pitch_type IN ('FF','FT','SI') THEN release_speed END) AS avg_velo_fb,
                           AVG(release_speed) AS avg_velo,
                           AVG(release_extension) AS avg_ext,
                           AVG(CASE WHEN pitch_type IN ('FF') THEN pfx_z*12 END) AS avg_pfxz_ff
                    FROM read_parquet('{pq}')
                    WHERE pitcher = {pid}
                )
                SELECT (SELECT COUNT(DISTINCT game_pk) FROM read_parquet('{pq}') WHERE pitcher={pid}) AS gs,
                       (SELECT COUNT(*) FROM pa_level WHERE is_pa_end=1) AS tbf,
                       (SELECT SUM(is_k)*1.0/COUNT(*) FROM pa_level WHERE is_pa_end=1) AS k_pct,
                       (SELECT SUM(is_bb)*1.0/COUNT(*) FROM pa_level WHERE is_pa_end=1) AS bb_pct,
                       (SELECT AVG(xwoba_pa) FROM pa_level WHERE is_pa_end=1) AS xwoba_pa,
                       p.pitches, p.swstr, p.cstr, p.swings, p.in_zone, p.o_swings, p.o_pitches,
                       p.swstr*1.0/p.pitches AS swstr_pct,
                       (p.swstr+p.cstr)*1.0/p.pitches AS csw_pct,
                       p.in_zone*1.0/p.pitches AS zone_pct,
                       p.o_swings*1.0/NULLIF(p.o_pitches,0) AS chase_pct,
                       p.avg_velo_fb, p.avg_velo, p.avg_ext, p.avg_pfxz_ff
                FROM pitch_level p
            """).df()
            r['year'] = yr
            rows.append(r)
        except Exception as e:
            print(f"  [{yr}] query failed: {e}")
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

for name, pid in ids.items():
    print(f"\n=== {name} (pitcher_id={pid}) ===")
    t = career_table_via_statcast(pid)
    if t.empty:
        print("  (no data)")
        continue
    # Drop years where the pitcher didn't appear
    t = t[t['gs'] > 0].copy()
    for c in ['k_pct','bb_pct','xwoba_pa','swstr_pct','csw_pct','zone_pct','chase_pct']:
        if c in t.columns: t[c] = t[c].round(3)
    for c in ['avg_velo_fb','avg_velo','avg_ext','avg_pfxz_ff']:
        if c in t.columns: t[c] = t[c].round(2)
    show = ['year','gs','tbf','k_pct','bb_pct','xwoba_pa','swstr_pct','csw_pct','zone_pct','chase_pct',
            'avg_velo_fb','avg_velo','avg_ext','avg_pfxz_ff']
    print(t[show].to_string(index=False))

# =========================================================================
# Pitch arsenal — usage% and per-pitch whiff% by year
# =========================================================================
print("\n\n" + "="*90)
print("PITCH ARSENAL TRAJECTORY (usage% + whiff/swing by year, per pitch_type)")
print("="*90)
for name, pid in ids.items():
    print(f"\n--- {name} ---")
    rows = []
    for yr in (2024, 2025, 2026):
        pq = PARQ_TMPL.format(yr=yr)
        try:
            r = con.execute(f"""
                SELECT pitch_type,
                       COUNT(*) AS n,
                       COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS usage_pct,
                       AVG(release_speed) AS velo,
                       AVG(pfx_z*12) AS pfx_z_in,
                       AVG(release_extension) AS ext,
                       SUM(CASE WHEN description IN ('swinging_strike','foul_tip','missed_bunt') THEN 1 ELSE 0 END)
                         * 1.0 / NULLIF(SUM(CASE WHEN description IN ('swinging_strike','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt') THEN 1 ELSE 0 END), 0) AS whiff_per_swing,
                       AVG(estimated_woba_using_speedangle) AS xwoba_pa
                FROM read_parquet('{pq}')
                WHERE pitcher = {pid} AND pitch_type IS NOT NULL
                GROUP BY pitch_type
                HAVING COUNT(*) >= 20
                ORDER BY n DESC
            """).df()
            r['year'] = yr
            rows.append(r)
        except Exception as e:
            pass
    if not rows:
        print("  (none)")
        continue
    arsenal = pd.concat(rows, ignore_index=True)
    arsenal = arsenal[['year','pitch_type','n','usage_pct','velo','pfx_z_in','ext','whiff_per_swing','xwoba_pa']]
    for c in ['usage_pct','whiff_per_swing','xwoba_pa']:
        arsenal[c] = arsenal[c].round(3)
    for c in ['velo','pfx_z_in','ext']:
        arsenal[c] = arsenal[c].round(2)
    arsenal = arsenal.sort_values(['year','n'], ascending=[True, False])
    print(arsenal.to_string(index=False))

# =========================================================================
# Recent form (last 5 starts each)
# =========================================================================
print("\n\n" + "="*90)
print("RECENT FORM (last 5 starts in 2026 if available)")
print("="*90)
for name, pid in ids.items():
    print(f"\n--- {name} ---")
    pq = PARQ_TMPL.format(yr=2026)
    try:
        r = con.execute(f"""
            WITH game_agg AS (
                SELECT game_date, game_pk, pitcher,
                       COUNT(*) AS pitches,
                       SUM(CASE WHEN description IN ('swinging_strike','foul_tip') THEN 1 ELSE 0 END) AS swstr,
                       SUM(CASE WHEN description IN ('swinging_strike','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt') THEN 1 ELSE 0 END) AS swings,
                       AVG(CASE WHEN pitch_type IN ('FF','FT','SI') THEN release_speed END) AS avg_velo_fb,
                       AVG(release_extension) AS ext
                FROM read_parquet('{pq}')
                WHERE pitcher = {pid}
                GROUP BY game_date, game_pk, pitcher
            ),
            pa_agg AS (
                SELECT game_date, game_pk,
                       COUNT(DISTINCT (game_pk, at_bat_number)) AS tbf,
                       SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
                       SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
                       SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
                       AVG(CASE WHEN events IS NOT NULL AND events!='' THEN estimated_woba_using_speedangle END) AS xwoba_pa
                FROM read_parquet('{pq}')
                WHERE pitcher = {pid}
                GROUP BY game_date, game_pk
            )
            SELECT g.game_date, g.pitches, g.swstr, g.swings,
                   g.swstr*1.0/g.swings AS whiff_swing,
                   g.swstr*1.0/g.pitches AS swstr_pct,
                   g.avg_velo_fb, g.ext,
                   p.tbf, p.k, p.bb, p.hr, p.xwoba_pa
            FROM game_agg g
            JOIN pa_agg p USING (game_date, game_pk)
            ORDER BY g.game_date DESC
            LIMIT 5
        """).df()
        if r.empty:
            print("  (no 2026 starts)")
            continue
        for c in ['whiff_swing','swstr_pct','xwoba_pa']:
            r[c] = r[c].round(3)
        for c in ['avg_velo_fb','ext']:
            r[c] = r[c].round(2)
        print(r.to_string(index=False))
    except Exception as e:
        print(f"  query failed: {e}")

# =========================================================================
# Current rp3 projection
# =========================================================================
print("\n\n" + "="*90)
print("CURRENT rp3 PROJECTION (latest snapshot)")
print("="*90)
rp3 = pd.read_csv(RP3_PROJ)
for name, pid in ids.items():
    row = rp3[rp3['pitcher'] == pid].sort_values('split_day', ascending=False).head(1)
    if row.empty:
        print(f"  {name}: no rp3 row")
        continue
    cols = ['player_name','split_day','xfp_rp3_per_start','prior_fp_per_start','gs_to',
            'fp_per_start_to','fp_per_start_last21','recency_form_gap','signal','rank']
    avail = [c for c in cols if c in row.columns]
    print(f"\n  {name}:")
    print(row[avail].to_string(index=False))

con.close()
print("\nDone.")
