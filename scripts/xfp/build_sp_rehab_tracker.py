"""
Build the SP rehab tracker — implementation of /sp-rehab-tracker skill.

Scans all 8 league rosters for IL'd SPs, pulls their 2026 MiLB Statcast via
Baseball Savant minors filter, compares to pre-injury MLB baseline from
sp_multiyr_2015_2025, and produces a tiered verdict per pitcher.
"""
from __future__ import annotations
import os, sys, io, time
import urllib.request
import unicodedata
import pandas as pd
import numpy as np
from datetime import date

pd.set_option('display.width', 260)
pd.set_option('display.max_columns', 40)

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
# league_state migration 2026-07-04: get_my_roster_with_injuries was imported
# but never used; all_teams() is now a schema superset of get_all_teams().
from plv_clone.league_state import default_state


def get_all_teams():
    return default_state().all_teams()

SP_MULTIYR  = 'data/research/xfp_cache/sp_multiyr_2015_2025.csv'
MLBAM_CACHE = 'data/research/xfp_cache/sp_mlbam_resolved.csv'
OUT_TPL     = 'data/research/sp_rehab_tracker_{date}.csv'
PARQ_TMPL   = 'data/research/xfp_cache/statcast_{yr}.parquet'

PITCHER_POS = {'SP', 'RP', 'P'}

# Watchlist: FA / dropped SPs known to be IL'd that need MiLB tracking too.
# These won't appear in get_all_teams() but matter for buy-low scans.
FA_WATCHLIST = {
    'Jared Jones': 683003,   # Pirates, TJ recovery 2025-26
}


def fb_baseline_from_parquet(mlbam: int, year: int) -> dict | None:
    """Compute FB-only avg velo + K%/BB%/SwStr% baseline from prior MLB year Statcast."""
    pq = PARQ_TMPL.format(yr=year)
    if not os.path.exists(pq):
        return None
    import duckdb
    con = duckdb.connect()
    try:
        r = con.execute(f"""
            WITH px AS (
                SELECT pitcher, pitch_type, description, events,
                       release_speed, game_pk, at_bat_number,
                       CASE WHEN pitch_type IN ('FF','FT','SI') THEN release_speed END AS fb_velo
                FROM read_parquet('{pq}')
                WHERE pitcher = {mlbam}
            ),
            pa AS (
                SELECT game_pk, at_bat_number,
                       MAX(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
                       MAX(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
                       MAX(CASE WHEN events IS NOT NULL AND events!='' THEN 1 ELSE 0 END) AS pa_end
                FROM px GROUP BY game_pk, at_bat_number
            )
            SELECT
                AVG(fb_velo) AS fb_velo,
                COUNT(*) AS pitches,
                SUM(CASE WHEN description IN ('swinging_strike','foul_tip') THEN 1 ELSE 0 END)*1.0/COUNT(*) AS swstr_pct,
                (SELECT SUM(k)*1.0/NULLIF(SUM(pa_end),0) FROM pa) AS k_pct,
                (SELECT SUM(bb)*1.0/NULLIF(SUM(pa_end),0) FROM pa) AS bb_pct
            FROM px
        """).fetchone()
        con.close()
        if r is None or r[0] is None:
            return None
        return {'fb_velo': r[0], 'pitches': r[1],
                'swstr_pct': r[2], 'k_pct': r[3], 'bb_pct': r[4], 'year': year}
    except Exception:
        con.close()
        return None


def most_recent_mlb_game_date(mlbam: int, year: int = 2026) -> 'pd.Timestamp | None':
    pq = PARQ_TMPL.format(yr=year)
    if not os.path.exists(pq):
        return None
    import duckdb
    con = duckdb.connect()
    try:
        r = con.execute(f"""
            SELECT MAX(game_date) FROM read_parquet('{pq}') WHERE pitcher = {mlbam}
        """).fetchone()
        con.close()
        return pd.Timestamp(r[0]) if r and r[0] else None
    except Exception:
        con.close()
        return None

def fold(s):
    if pd.isna(s): return ''
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c)).lower().strip()


def resolve_mlbam(name: str, multiyr_lookup: dict, cache: dict) -> int | None:
    """Resolve name → MLBAM. Collision-safe deep resolver first
    (name_match.resolve_id consults KNOWN_PITCHER_COLLISIONS), then the
    sp_multiyr name index, then pybaseball."""
    if name in cache and cache[name]:
        return int(cache[name])
    # Collision-safe deep resolver first — never silently grab the wrong
    # same-name pitcher. Safe-fails to None on an ambiguous collision (no team
    # hint here), in which case we fall through to the legacy index + pybaseball.
    try:
        from plv_clone.utils.name_match import resolve_id as _resolve_id
        pid = _resolve_id(name, kind="pitcher")
        if pid:
            cache[name] = int(pid)
            return int(pid)
    except Exception:
        pass
    nf = fold(name)
    # sp_multiyr names are "Last, First" — build both formats
    parts = name.strip().split()
    if len(parts) >= 2:
        last = parts[-1]
        first = ' '.join(parts[:-1])
        last_first_norm = fold(f"{last}, {first}")
        if last_first_norm in multiyr_lookup:
            mlbam = multiyr_lookup[last_first_norm]
            cache[name] = mlbam
            return int(mlbam)
    # Try direct
    if nf in multiyr_lookup:
        mlbam = multiyr_lookup[nf]
        cache[name] = mlbam
        return int(mlbam)
    # Fallback to pybaseball
    try:
        from pybaseball import playerid_lookup
        if len(parts) >= 2:
            r = playerid_lookup(parts[-1], ' '.join(parts[:-1]))
            if len(r) and 'key_mlbam' in r.columns:
                # Pick most recent MLB-active match
                r = r[r['mlb_played_last'].notna()].sort_values('mlb_played_last', ascending=False)
                if len(r):
                    mlbam = int(r.iloc[0]['key_mlbam'])
                    cache[name] = mlbam
                    return mlbam
    except Exception as e:
        print(f"    pybaseball lookup failed for {name}: {e}")
    return None


def pull_milb(mlbam: int, start: str, end: str) -> pd.DataFrame:
    """Pull 2026 MiLB Statcast for a pitcher via Savant minors filter."""
    url = (
        "https://baseballsavant.mlb.com/statcast_search/csv?all=true"
        "&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
        "&hfGT=R%7CPO%7CS%7C&hfC=&hfSea=2026%7C&hfSit=&player_type=pitcher"
        f"&hfOuts=&opponent=&pitcher_throws=&batter_stands=&hfSA="
        f"&game_date_gt={start}&game_date_lt={end}"
        "&hfInfield=&team=&position=&hfOutfield=&hfRO=&home_road=&hfFlag="
        "&hfPull=&metric_1=&hfInn=&min_pitches=0&min_results=0&group_by=name"
        "&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
        f"&min_pas=0&pitchers_lookup%5B%5D={mlbam}&minors=true&type=details"
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        return pd.read_csv(io.BytesIO(data))
    except Exception as e:
        print(f"    pull failed for {mlbam}: {e}")
        return pd.DataFrame()


def score_rehab(milb_df: pd.DataFrame, prior_row: pd.Series | None) -> dict:
    """Compute deltas + verdict from MiLB pitches vs prior MLB baseline."""
    out = {'milb_pitches': 0, 'outings': 0, 'last_outing': None,
           'fb_velo': None, 'fb_max': None, 'milb_k_pct': None, 'milb_bb_pct': None,
           'milb_swstr': None, 'milb_csw': None,
           'velo_delta': None, 'k_delta': None, 'bb_delta': None, 'swstr_delta': None,
           'workload_curve': None, 'days_gap_max': None,
           'verdict': 'NO DATA'}
    if milb_df.empty:
        return out
    df = milb_df.copy()
    df['game_date'] = pd.to_datetime(df['game_date'])
    out['milb_pitches'] = len(df)
    out['outings'] = df['game_pk'].nunique()
    out['last_outing'] = df['game_date'].max().date().isoformat()

    fb = df[df['pitch_type'].isin(['FF','FT','SI'])]
    if len(fb):
        out['fb_velo'] = round(fb['release_speed'].mean(), 2)
        out['fb_max']  = round(fb['release_speed'].max(), 2)

    # PA-level outcomes
    pa = df.dropna(subset=['at_bat_number'])
    pa_grp = pa.groupby(['game_pk','at_bat_number'])['events'].apply(
        lambda x: x.dropna().iloc[0] if len(x.dropna()) else ''
    ).reset_index().rename(columns={'events':'event'})
    total_pa = (pa_grp['event'] != '').sum()
    if total_pa:
        k = (pa_grp['event'] == 'strikeout').sum()
        bb = (pa_grp['event'] == 'walk').sum()
        out['milb_k_pct']  = round(k / total_pa, 3)
        out['milb_bb_pct'] = round(bb / total_pa, 3)

    out['milb_swstr'] = round((df['description'].isin(['swinging_strike','foul_tip','missed_bunt'])).sum() / len(df), 3)
    out['milb_csw']   = round((df['description'].isin(['called_strike','swinging_strike','foul_tip'])).sum() / len(df), 3)

    # Workload curve
    counts = df.groupby('game_date').size().sort_index()
    out['workload_curve'] = ' → '.join(f"{d.strftime('%m/%d')}:{n}" for d, n in counts.items())
    if len(counts) > 1:
        gaps = (counts.index.to_series().diff().dt.days.fillna(0)).max()
        out['days_gap_max'] = int(gaps)

    # Deltas vs prior
    if prior_row is not None:
        prior_velo  = prior_row.get('avg_velo')
        prior_k     = prior_row.get('k_pct')
        prior_bb    = prior_row.get('bb_pct')
        prior_swstr = prior_row.get('swstr_pct')
        if pd.notna(prior_velo) and out['fb_velo']:
            out['velo_delta']  = round(out['fb_velo']  - float(prior_velo), 2)
        if pd.notna(prior_k) and out['milb_k_pct']:
            out['k_delta']     = round(out['milb_k_pct']  - float(prior_k), 3)
        if pd.notna(prior_bb) and out['milb_bb_pct']:
            out['bb_delta']    = round(out['milb_bb_pct'] - float(prior_bb), 3)
        if pd.notna(prior_swstr) and out['milb_swstr']:
            out['swstr_delta'] = round(out['milb_swstr'] - float(prior_swstr), 3)

    # Verdict logic
    if out['milb_pitches'] < 80:
        out['verdict'] = 'WORKLOAD-ONLY'
    elif (out['velo_delta'] is not None and out['velo_delta'] >= 1.0
          and out['swstr_delta'] is not None and out['swstr_delta'] >= 0.01
          and out['k_delta'] is not None and out['k_delta'] >= 0):
        out['verdict'] = 'AHEAD'
    elif (out['velo_delta'] is not None and out['velo_delta'] < -1.0
          or (out['swstr_delta'] is not None and out['swstr_delta'] < -0.02)):
        out['verdict'] = 'BEHIND'
    elif (out['velo_delta'] is not None and abs(out['velo_delta']) <= 1.0):
        out['verdict'] = 'ON TRACK'
    else:
        out['verdict'] = 'UNCERTAIN'
    return out


def main():
    print("=== SP rehab tracker ===\n")

    # Step 1: identify IL'd SPs across all 8 rosters
    print("Pulling all 8 team rosters...")
    rosters = get_all_teams()
    print(f"  rosters shape: {rosters.shape}  cols: {list(rosters.columns)}")
    pitchers = rosters[rosters['position'].isin(PITCHER_POS)].copy()
    ild = pitchers[(pitchers['injured'] == True) | (~pitchers['injury_status'].isin(['ACTIVE', None, '']))].copy()
    print(f"\nIL'd pitchers across all rosters: {len(ild)}")

    # Augment with FA watchlist
    fa_rows = []
    for name, mlbam in FA_WATCHLIST.items():
        if name in set(ild['player_name']):
            continue
        fa_rows.append({
            'player_name': name, 'player_id': None,
            'position': 'SP', 'pro_team': None,
            'team_name': 'FA (watchlist)', 'lineup_slot': None,
            'injured': True, 'injury_status': 'IL (FA)',
            'owner': None, 'team_id': None,
        })
    if fa_rows:
        ild = pd.concat([ild, pd.DataFrame(fa_rows)], ignore_index=True)
        print(f"Augmented with {len(fa_rows)} FA-watchlist SPs (total: {len(ild)})")

    print(ild[['player_name','position','team_name','lineup_slot','injured','injury_status']].to_string(index=False))

    if ild.empty:
        print("\nNo IL'd pitchers to track. Done.")
        return

    # Step 2: resolve MLBAM IDs
    print("\nResolving MLBAM IDs...")
    multiyr = pd.read_csv(SP_MULTIYR)
    multiyr_lookup = (multiyr.sort_values('year', ascending=False)
                     .drop_duplicates('player_name')
                     .assign(__nf=lambda d: d['player_name'].apply(fold))
                     .set_index('__nf')['pitcher'].to_dict())

    # Load resolved cache
    cache = {}
    if os.path.exists(MLBAM_CACHE):
        cdf = pd.read_csv(MLBAM_CACHE)
        cache = dict(zip(cdf['name'], cdf['mlbam']))
        print(f"  loaded {len(cache)} from cache")

    # Pre-fill from FA_WATCHLIST (overrides cache lookup miss)
    for name, mlbam in FA_WATCHLIST.items():
        cache[name] = mlbam

    for _, p in ild.iterrows():
        name = p['player_name']
        if name in cache and cache[name]:
            continue
        mlbam = resolve_mlbam(name, multiyr_lookup, cache)
        if mlbam:
            print(f"  {name} → {mlbam}")
        else:
            print(f"  {name} → UNRESOLVED")

    # Persist cache
    cache_df = pd.DataFrame([{'name': k, 'mlbam': v} for k, v in cache.items() if v])
    cache_df.to_csv(MLBAM_CACHE, index=False)

    # Step 3+4+5: pull MiLB + baseline + score each
    print("\nPulling MiLB rehab data + scoring...")
    today = date.today().isoformat()
    rows = []
    for _, p in ild.iterrows():
        name = p['player_name']
        mlbam = cache.get(name)
        if not mlbam:
            rows.append({**{'name': name, 'pos': p['position'], 'team': p['team_name'],
                          'injury': p['injury_status'], 'mlbam': None}, **{'verdict': 'NO MLBAM'}})
            continue
        print(f"  {name} (mlbam={mlbam})...")
        milb = pull_milb(int(mlbam), start='2026-03-01', end=today)

        # Filter MiLB to post-IL window: if the pitcher has MLB starts in 2026,
        # only count MiLB outings AFTER their most recent MLB game (the rehab assignment).
        # If no 2026 MLB outings exist, the entire 2026 MiLB output IS the rehab.
        last_mlb = most_recent_mlb_game_date(int(mlbam), 2026)
        rehab_window_note = None
        if last_mlb is not None and not milb.empty:
            milb['game_date'] = pd.to_datetime(milb['game_date'])
            pre = len(milb)
            milb = milb[milb['game_date'] > last_mlb].copy()
            rehab_window_note = f"filtered to post-{last_mlb.date()} (pre-filter: {pre}, post-IL: {len(milb)})"

        # FB-specific baseline from prior-year Statcast parquet
        # Pick the most recent year with MLB data for this pitcher
        fb_prior = None
        prior_year_used = None
        for yr in (2025, 2024, 2023):
            r = fb_baseline_from_parquet(int(mlbam), yr)
            if r and r.get('pitches', 0) >= 200:
                fb_prior = r
                prior_year_used = yr
                break

        # sp_multiyr fallback for K%/BB% if FB baseline missing
        prior_rows = multiyr[multiyr['pitcher'] == mlbam].sort_values('year', ascending=False)
        prior_sp = prior_rows.iloc[0] if len(prior_rows) else None

        # Build a synthetic prior row with FB-specific velo + sp_multiyr K/BB/swstr
        if fb_prior:
            prior = pd.Series({
                'avg_velo': fb_prior['fb_velo'],           # FB-only, not overall
                'k_pct':    fb_prior['k_pct'],
                'bb_pct':   fb_prior['bb_pct'],
                'swstr_pct': fb_prior['swstr_pct'],
            })
            prior_year = prior_year_used
        else:
            prior = prior_sp
            prior_year = int(prior_sp['year']) if prior_sp is not None else None

        score = score_rehab(milb, prior)
        score.update({
            'name': name, 'pos': p['position'], 'team': p['team_name'],
            'injury': p['injury_status'], 'mlbam': int(mlbam),
            'prior_year': prior_year,
            'prior_fb_velo': round(float(prior['avg_velo']), 2) if prior is not None and pd.notna(prior.get('avg_velo')) else None,
            'prior_k':    round(float(prior['k_pct']), 3)   if prior is not None and pd.notna(prior.get('k_pct')) else None,
            'prior_bb':   round(float(prior['bb_pct']), 3)  if prior is not None and pd.notna(prior.get('bb_pct')) else None,
            'prior_swstr': round(float(prior['swstr_pct']), 3) if prior is not None and pd.notna(prior.get('swstr_pct')) else None,
            'rehab_window': rehab_window_note,
        })
        rows.append(score)
        time.sleep(0.5)  # be polite to Savant

    out = pd.DataFrame(rows)
    out_path = OUT_TPL.format(date=today)
    out.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}  ({len(out)} pitchers scored)")

    # Step 7: ranked output
    TIER_ORDER = ['AHEAD', 'ON TRACK', 'UNCERTAIN', 'WORKLOAD-ONLY', 'BEHIND', 'NO DATA', 'NO MLBAM']
    print("\n" + "="*120)
    print(f"=== SP REHAB TRACKER  ({today}) ===")
    print("="*120)
    show = ['name','team','pos','injury','outings','milb_pitches','last_outing',
            'fb_velo','fb_max','prior_fb_velo','velo_delta',
            'milb_k_pct','prior_k','k_delta',
            'milb_bb_pct','prior_bb','bb_delta',
            'milb_swstr','prior_swstr','swstr_delta',
            'workload_curve','prior_year','verdict']
    for tier in TIER_ORDER:
        t = out[out['verdict'] == tier]
        if t.empty: continue
        print(f"\n--- {tier} ({len(t)}) ---")
        print(t[show].to_string(index=False))

    # Step 8: action callouts
    print("\n" + "="*120)
    print("ACTION CALLOUTS")
    print("="*120)

    mine = out[out['team'].str.contains('Ligers', case=False, na=False)]
    other = out[~out['team'].str.contains('Ligers', case=False, na=False) & (out['team'] != 'FA (watchlist)')]
    fa_watch = out[out['team'] == 'FA (watchlist)']

    print("\nBuy-low watch (AHEAD on OTHER rosters — owners may be selling):")
    blw = other[other['verdict'] == 'AHEAD']
    if blw.empty:
        print("  (none)")
    else:
        print(blw[['name','team','injury','velo_delta','k_delta','swstr_delta','last_outing']].to_string(index=False))

    print("\nMy roster IL'd SPs:")
    if mine.empty:
        print("  (none on IL)")
    else:
        print(mine[['name','pos','injury','outings','fb_velo','velo_delta','workload_curve','verdict']].to_string(index=False))

    print("\nFaders (BEHIND on my roster — drop watch on activation):")
    f = mine[mine['verdict'] == 'BEHIND']
    if f.empty:
        print("  (none)")
    else:
        print(f[['name','injury','velo_delta','swstr_delta','workload_curve']].to_string(index=False))

    print("\nFA watchlist (dropped/IL SPs):")
    if fa_watch.empty:
        print("  (none)")
    else:
        print(fa_watch[['name','injury','outings','fb_velo','prior_fb_velo','velo_delta','milb_k_pct','k_delta','workload_curve','verdict']].to_string(index=False))

    print("\nAwaiting data (NO DATA / WORKLOAD-ONLY across the league):")
    aw = out[out['verdict'].isin(['NO DATA','WORKLOAD-ONLY'])]
    if aw.empty:
        print("  (none)")
    else:
        print(aw[['name','team','injury','outings','milb_pitches','workload_curve']].to_string(index=False))


if __name__ == '__main__':
    main()
