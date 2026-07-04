"""
build_hitters_multiyr.py — multi-year hitter substrate for the xFP H model.

Reads cached Statcast pitch-by-pitch parquets at
data/research/xfp_cache/statcast_{year}.parquet (built by build_sp_multiyr.py),
aggregates per-(batter, year), and joins MLB Stats API counting stats (R, RBI,
SB, sprint speed) to get the full FP/PA target.

Output schema (one row per batter-year):
    batter, player_name, year, team,
    pa, ab, bip, in_zone, out_zone,
    swing, contact, swstr, called_strike,
    z_swing, z_contact, o_swing,
    bb, k, hbp, h, b1, b2, b3, hr, tb,
    sb, r, rbi,                                  # from MLB Stats API
    avg_ev, hard_hit_n, barrel_n,
    xwoba_bip, woba_v_sum, woba_d_sum, xwoba_per_pa,
    swing_pct, contact_pct, swstr_pct, c_plus_swstr,
    zone_pct, o_swing_pct, z_swing_pct, z_contact_pct,
    chase_pct, whiff_pct, in_play_pct,
    hard_hit_pct, barrel_pct,
    k_pct, bb_pct, hbp_pct, hr_per_pa, iso, sb_per_pa, r_per_pa, rbi_per_pa,
    sprint_speed,
    fp_per_pa_actual, core_fp_per_pa_actual, fp_total

The xFP H model trains on (rate features) -> fp_per_pa_actual cross-year.
"""
from __future__ import annotations
import os, sys, time, warnings, json
from pathlib import Path
from typing import Iterable
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
CACHE.mkdir(parents=True, exist_ok=True)
MODELS = ROOT / 'data' / 'models'
OUTPUTS = ROOT / 'data' / 'outputs'
OUT_CSV = CACHE / 'hitters_multiyr_2015_2026.csv'
COUNTING_CACHE = CACHE / 'hitter_counting_stats_{year}.json'  # MLB API season totals
SPRINT_CACHE = CACHE / 'sprint_speed_{year}.csv'

YEARS = list(range(2015, 2027))  # 2015..2026

# ── Statcast description sets (mirror build_sp_multiyr.py) ────────────────────
SWING_DESC = {'swinging_strike','swinging_strike_blocked','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt'}
SWSTR_DESC = {'swinging_strike','swinging_strike_blocked','foul_tip','missed_bunt'}
CALLED_STRIKE_DESC = {'called_strike'}

# ── Event sets (mirror src/plv_clone/fantasy/hitter_points.py) ────────────────
K_EVENTS  = {'strikeout', 'strikeout_double_play', 'strikeout_triple_play'}
BB_EVENTS = {'walk', 'intent_walk'}
H_EVENTS  = {'single', 'double', 'triple', 'home_run'}
SB_EVENTS = {'stolen_base_2b', 'stolen_base_3b', 'stolen_base_home'}
TB_MAP = {'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}
NON_PA = SB_EVENTS | {
    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
    'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
    'wild_pitch', 'passed_ball', 'balk',
}

# ── ESPN scoring constants (mirror data/models/league_scoring.json) ──────────
SCORE = {'r': 1.0, 'tb': 1.0, 'rbi': 1.0, 'bb': 1.0, 'hbp': 1.0, 'sb': 1.0, 'k': -1.0}



def _cache_fresh_enough(cache_path, year) -> bool:
    """Immutable (completed) years: any cache is valid. The IN-PROGRESS season:
    cache must be from today, else refetch (audit 2026-07-04: the 2026 counting
    stats froze for 15 days and silently fed rh3 training targets; sprint speed
    was 59 days stale). Fetch failures still fall back to the stale cache via
    the existing try/except."""
    from datetime import date, datetime
    t = date.today()
    cur = t.year if t.month >= 3 else t.year - 1
    if int(year) < cur:
        return True
    return datetime.fromtimestamp(cache_path.stat().st_mtime).date() >= t


def aggregate_year(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Per-batter season aggregates from one year of pitch-by-pitch Statcast."""
    d = df.copy()
    desc = d['description'].fillna('')
    ev = d['events'].fillna('')

    d['in_zone']  = (d['zone'] >= 1) & (d['zone'] <= 9)
    d['out_zone'] = (d['zone'] >= 11) & (d['zone'] <= 14)
    d['is_swing'] = desc.isin(SWING_DESC)
    d['is_swstr'] = desc.isin(SWSTR_DESC)
    d['is_contact'] = d['is_swing'] & ~d['is_swstr']
    d['is_called_strike'] = desc == 'called_strike'
    d['z_swing']   = d['is_swing']   & d['in_zone']
    d['z_contact'] = d['is_contact'] & d['in_zone']
    d['o_swing']   = d['is_swing']   & d['out_zone']

    d['is_pa_end'] = ev != ''
    d['is_k']      = ev.isin(K_EVENTS)
    d['is_bb']     = ev.isin(BB_EVENTS)
    d['is_hbp']    = ev == 'hit_by_pitch'
    d['is_h']      = ev.isin(H_EVENTS)
    d['is_hr']     = ev == 'home_run'
    d['is_1b']     = ev == 'single'
    d['is_2b']     = ev == 'double'
    d['is_3b']     = ev == 'triple'
    d['is_sb']     = ev.isin(SB_EVENTS)
    # PA = PA-ending event AND not a non-PA tracking event (SB, pickoff, etc.)
    d['is_pa']     = d['is_pa_end'] & ~ev.isin(NON_PA)
    d['is_bip']    = d['is_pa'] & ~d['is_k'] & ~d['is_bb'] & ~d['is_hbp']
    d['tb']        = ev.map(TB_MAP).fillna(0).astype(int)

    # Batted-ball quality (compendium-aligned)
    ls = pd.to_numeric(d.get('launch_speed'), errors='coerce')
    la = pd.to_numeric(d.get('launch_angle'), errors='coerce')
    d['hard_hit'] = (ls >= 95) & d['is_bip']
    if 'launch_speed_angle' in d.columns:
        d['barrel'] = (pd.to_numeric(d['launch_speed_angle'], errors='coerce') == 6) & d['is_bip']
    else:
        d['barrel'] = (ls >= 98) & la.between(26, 30) & d['is_bip']
    # Sweet Spot% — BBE with LA in [8, 32]° (compendium §3, §10.1)
    d['sweet_spot'] = la.between(8, 32) & d['is_bip']
    # Stash launch_speed values restricted to BIP for EV90 quantile aggregation
    d['ls_bip'] = ls.where(d['is_bip'])

    # Spray angle for Pull/Cent/Oppo (compendium §3 — uses Statcast horizontal angle).
    # Approximation: hc_x / hc_y are field coordinates; compute angle from home plate.
    # Convention: home plate ≈ (125.42, 198.27); arctan2 of (hc_x − 125.42, 198.27 − hc_y).
    # For a RHB, negative angles = pull (LF), positive = oppo (RF). Flip for LHB.
    if 'hc_x' in d.columns and 'hc_y' in d.columns and 'stand' in d.columns:
        hcx = pd.to_numeric(d['hc_x'], errors='coerce')
        hcy = pd.to_numeric(d['hc_y'], errors='coerce')
        spray_rad = np.arctan2(hcx - 125.42, 198.27 - hcy)
        spray_deg = np.degrees(spray_rad)  # − = LF, 0 = CF, + = RF
        # Flip LHB so positive = pull-side regardless of handedness
        sign = np.where(d['stand'] == 'L', 1.0, -1.0)
        d['spray_pull_deg'] = spray_deg * sign  # positive = pull, negative = oppo
        # Bin: pull (>15°), cent (-15..15), oppo (<-15°)
        d['is_pull'] = (d['spray_pull_deg'] >  15) & d['is_bip']
        d['is_cent'] = (d['spray_pull_deg'].between(-15, 15)) & d['is_bip']
        d['is_oppo'] = (d['spray_pull_deg'] < -15) & d['is_bip']
        # Pulled fly balls (LA 20-35°) — what compendium calls out for HR projection
        d['is_pull_fb'] = d['is_pull'] & la.between(20, 35)
    else:
        d['is_pull'] = False
        d['is_cent'] = False
        d['is_oppo'] = False
        d['is_pull_fb'] = False

    # xwOBA on contact (BIP-only) and per-PA xwOBA (research-doc convention)
    xwoba_con = pd.to_numeric(d.get('estimated_woba_using_speedangle'), errors='coerce')
    d['xwoba_con_val'] = xwoba_con.where(d['is_bip'])
    woba_v = pd.to_numeric(d.get('woba_value'), errors='coerce')
    woba_d = pd.to_numeric(d.get('woba_denom'), errors='coerce')
    d['woba_v_pa'] = woba_v
    bip_with_xwoba = d['is_bip'] & xwoba_con.notna()
    d.loc[bip_with_xwoba, 'woba_v_pa'] = xwoba_con[bip_with_xwoba]
    d['woba_d_pa'] = woba_d

    # Batter team — derive from inning_topbot (top of inning = away team batting)
    if 'inning_topbot' in d.columns and 'home_team' in d.columns and 'away_team' in d.columns:
        d['_batter_team'] = np.where(d['inning_topbot'] == 'Top', d['away_team'], d['home_team'])
    else:
        d['_batter_team'] = ''

    g = d.groupby('batter')
    agg = g.agg(
        pitches      =('batter','size'),
        pa           =('is_pa','sum'),
        bip          =('is_bip','sum'),
        in_zone      =('in_zone','sum'),
        out_zone     =('out_zone','sum'),
        swing        =('is_swing','sum'),
        contact      =('is_contact','sum'),
        swstr        =('is_swstr','sum'),
        called_strike=('is_called_strike','sum'),
        z_swing      =('z_swing','sum'),
        z_contact    =('z_contact','sum'),
        o_swing      =('o_swing','sum'),
        bb           =('is_bb','sum'),
        k            =('is_k','sum'),
        hbp          =('is_hbp','sum'),
        h            =('is_h','sum'),
        b1           =('is_1b','sum'),
        b2           =('is_2b','sum'),
        b3           =('is_3b','sum'),
        hr           =('is_hr','sum'),
        tb           =('tb','sum'),
        sb           =('is_sb','sum'),
        avg_ev       =('launch_speed','mean'),
        hard_hit_n   =('hard_hit','sum'),
        barrel_n     =('barrel','sum'),
        sweet_spot_n =('sweet_spot','sum'),
        pull_n       =('is_pull','sum'),
        cent_n       =('is_cent','sum'),
        oppo_n       =('is_oppo','sum'),
        pull_fb_n    =('is_pull_fb','sum'),
        xwoba_bip    =('xwoba_con_val','mean'),
        woba_v_sum   =('woba_v_pa','sum'),
        woba_d_sum   =('woba_d_pa','sum'),
    ).reset_index()
    # EV90 — 90th-percentile launch_speed on BIP (compendium §3, §10.1).
    # Computed separately because pandas .agg doesn't support quantile cleanly here.
    ev90 = (d[d['is_bip']].dropna(subset=['ls_bip'])
              .groupby('batter')['ls_bip']
              .quantile(0.90)
              .rename('ev90')).reset_index()
    agg = agg.merge(ev90, on='batter', how='left')

    # Player names + team modes
    name_map = d.dropna(subset=['player_name']).groupby('batter')['player_name'].first()
    agg['player_name'] = agg['batter'].map(name_map)
    team_map = (d[d['_batter_team'] != '']
                .groupby('batter')['_batter_team']
                .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else ''))
    agg['team'] = agg['batter'].map(team_map).fillna('')
    agg['year'] = year

    # Derived rate columns
    agg['xwoba_per_pa']  = agg['woba_v_sum'] / agg['woba_d_sum'].replace(0, np.nan)
    agg['xwoba_on_contact'] = agg['xwoba_bip']
    agg['swing_pct']     = agg['swing'] / agg['pitches']
    agg['contact_pct']   = agg['contact'] / agg['swing'].replace(0, np.nan)
    agg['swstr_pct']     = agg['swstr'] / agg['pitches']
    agg['c_plus_swstr']  = (agg['called_strike'] + agg['swstr']) / agg['pitches']
    agg['zone_pct']      = agg['in_zone'] / agg['pitches']
    agg['o_swing_pct']   = agg['o_swing'] / agg['out_zone'].replace(0, np.nan)
    agg['z_swing_pct']   = agg['z_swing'] / agg['in_zone'].replace(0, np.nan)
    agg['z_contact_pct'] = agg['z_contact'] / agg['z_swing'].replace(0, np.nan)
    # Chase rate is the same as o_swing_pct (kept for naming compatibility with PLV pipeline)
    agg['chase_pct']     = agg['o_swing_pct']
    # Whiff rate per swing (canonical Statcast definition)
    agg['whiff_pct']     = agg['swstr'] / agg['swing'].replace(0, np.nan)
    agg['in_play_pct']   = agg['bip'] / agg['pitches']
    agg['hard_hit_pct']  = agg['hard_hit_n'] / agg['bip'].replace(0, np.nan)
    agg['barrel_pct']    = agg['barrel_n'] / agg['bip'].replace(0, np.nan)
    # Compendium-aligned new rates
    agg['sweet_spot_pct']= agg['sweet_spot_n'] / agg['bip'].replace(0, np.nan)
    agg['pull_pct']      = agg['pull_n'] / agg['bip'].replace(0, np.nan)
    agg['cent_pct']      = agg['cent_n'] / agg['bip'].replace(0, np.nan)
    agg['oppo_pct']      = agg['oppo_n'] / agg['bip'].replace(0, np.nan)
    agg['pull_fb_pct']   = agg['pull_fb_n'] / agg['bip'].replace(0, np.nan)
    agg['k_pct']         = agg['k'] / agg['pa'].replace(0, np.nan)
    agg['bb_pct']        = agg['bb'] / agg['pa'].replace(0, np.nan)
    agg['hbp_pct']       = agg['hbp'] / agg['pa'].replace(0, np.nan)
    agg['hr_per_pa']     = agg['hr'] / agg['pa'].replace(0, np.nan)
    agg['sb_per_pa']     = agg['sb'] / agg['pa'].replace(0, np.nan)
    agg['ab']            = agg['pa'] - agg['bb'] - agg['hbp']  # approx; ignores SF/SH (small)
    agg['iso']           = (agg['tb'] - agg['h']) / agg['ab'].replace(0, np.nan)

    return agg


# ── MLB Stats API: per-year R/RBI/SB season totals ────────────────────────────

def fetch_counting_stats(year: int) -> pd.DataFrame:
    """One row per batter with R, RBI, SB, AB, PA totals for the season.

    Pulled from MLB Stats API /stats?group=hitting endpoint, cached as JSON.
    """
    cache_path = CACHE / f'hitter_counting_stats_{year}.json'
    if cache_path.exists() and _cache_fresh_enough(cache_path, year):
        try:
            data = json.loads(cache_path.read_text())
            df = pd.DataFrame(data)
            print(f'  [{year}] counting stats cached: {len(df)} batters', flush=True)
            return df
        except Exception as exc:
            print(f'  [{year}] cache read failed ({exc}); refetching', flush=True)

    import requests
    rows: list[dict] = []
    offset = 0
    page_size = 200
    while True:
        url = (
            'https://statsapi.mlb.com/api/v1/stats'
            f'?stats=season&group=hitting&season={year}&playerPool=ALL'
            f'&limit={page_size}&offset={offset}'
        )
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f'  [{year}] counting stats fetch failed at offset {offset}: {exc}', flush=True)
            break
        splits = resp.json().get('stats', [{}])[0].get('splits', [])
        if not splits:
            break
        for s in splits:
            p = s.get('player', {}) or {}
            stat = s.get('stat', {}) or {}
            pid = p.get('id')
            if not pid:
                continue
            rows.append({
                'batter': int(pid),
                # Canonical batter name — Statcast's player_name column is the
                # pitcher, not the batter, so we resolve names from MLB Stats API.
                'mlb_name': p.get('fullName'),
                'mlb_pa':  int(stat.get('plateAppearances', 0) or 0),
                'mlb_ab':  int(stat.get('atBats', 0) or 0),
                'mlb_r':   int(stat.get('runs', 0) or 0),
                'mlb_rbi': int(stat.get('rbi', 0) or 0),
                'mlb_sb':  int(stat.get('stolenBases', 0) or 0),
                'mlb_h':   int(stat.get('hits', 0) or 0),
                'mlb_hr':  int(stat.get('homeRuns', 0) or 0),
                'mlb_bb':  int(stat.get('baseOnBalls', 0) or 0),
                'mlb_k':   int(stat.get('strikeOuts', 0) or 0),
                'mlb_hbp': int(stat.get('hitByPitch', 0) or 0),
            })
        offset += page_size
        if len(splits) < page_size:
            break
        time.sleep(0.2)

    df = pd.DataFrame(rows)
    if not df.empty:
        cache_path.write_text(json.dumps(rows))
        print(f'  [{year}] counting stats fetched + cached: {len(df)} batters', flush=True)
    else:
        print(f'  [{year}] no counting stats returned', flush=True)
    return df


def fetch_sprint_speed(year: int) -> pd.DataFrame:
    """Per-batter sprint speed (ft/s) from Baseball Savant. Cached as CSV."""
    cache_path = CACHE / f'sprint_speed_{year}.csv'
    if cache_path.exists() and _cache_fresh_enough(cache_path, year):
        df = pd.read_csv(cache_path)
        print(f'  [{year}] sprint cached: {len(df)} batters', flush=True)
        return df

    import requests
    url = (
        'https://baseballsavant.mlb.com/leaderboard/sprint_speed'
        f'?year={year}&min=10&csv=true'
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))
    except Exception as exc:
        print(f'  [{year}] sprint fetch failed: {exc}', flush=True)
        return pd.DataFrame(columns=['batter', 'sprint_speed'])

    # Savant uses player_id; map to int
    pid_col = next((c for c in df.columns if c.lower() in ('player_id', 'mlb_id')), None)
    speed_col = next((c for c in df.columns if 'sprint' in c.lower() and 'speed' in c.lower()), None)
    if pid_col is None or speed_col is None:
        print(f'  [{year}] sprint columns not found ({list(df.columns)})', flush=True)
        return pd.DataFrame(columns=['batter', 'sprint_speed'])

    out = df[[pid_col, speed_col]].rename(columns={pid_col: 'batter', speed_col: 'sprint_speed'})
    out['batter'] = pd.to_numeric(out['batter'], errors='coerce').astype('Int64')
    out['sprint_speed'] = pd.to_numeric(out['sprint_speed'], errors='coerce')
    out = out.dropna(subset=['batter']).copy()
    out['batter'] = out['batter'].astype(int)
    out.to_csv(cache_path, index=False)
    print(f'  [{year}] sprint fetched + cached: {len(out)} batters', flush=True)
    return out


# ── Build pipeline ────────────────────────────────────────────────────────────

def build():
    print('=== build_hitters_multiyr ===', flush=True)
    frames = []
    for yr in YEARS:
        sc_path = CACHE / f'statcast_{yr}.parquet'
        if not sc_path.exists():
            print(f'\n--- year {yr} --- SKIP (no statcast parquet)', flush=True)
            continue
        print(f'\n--- year {yr} ---', flush=True)
        raw = pd.read_parquet(sc_path)
        print(f'  [{yr}] statcast: {len(raw):,} pitches', flush=True)
        season = aggregate_year(raw, yr)

        # Counting stats merge (fp_per_pa target depends on R, RBI, SB)
        counts = fetch_counting_stats(yr)
        if not counts.empty:
            season = season.merge(counts, on='batter', how='left')
            # Prefer MLB Stats API totals where present (cleaner than Statcast event aggregation)
            season['r']   = season['mlb_r'].fillna(0).astype(int)
            season['rbi'] = season['mlb_rbi'].fillna(0).astype(int)
            # Use MLB Stats API SB count as authoritative when available; falls back to Statcast events
            season['sb_total'] = season['mlb_sb'].fillna(season['sb']).astype(int)
            season['sb'] = season['sb_total']
            season = season.drop(columns=['sb_total'])
            # Recompute sb_per_pa now that we have the authoritative MLB-API SB count
            # (Statcast `events` column doesn't fire on SBs because they aren't
            # PA-ending events, so the in-aggregate sb_per_pa was always 0.)
            season['sb_per_pa'] = season['sb'] / season['pa'].replace(0, np.nan)
            # Canonical batter name from MLB API replaces Statcast's player_name
            # (Statcast's player_name is the pitcher, not the batter).
            if 'mlb_name' in season.columns:
                season['player_name'] = season['mlb_name'].fillna(season['player_name'])
        else:
            season['r'] = 0
            season['rbi'] = 0

        # Sprint speed
        sprint = fetch_sprint_speed(yr)
        if not sprint.empty:
            season = season.merge(sprint, on='batter', how='left')
        else:
            season['sprint_speed'] = np.nan

        # FanGraphs bat-tracking (only 2026 currently exists)
        fg_path = OUTPUTS / f'fangraphs_batters_{yr}.csv'
        if fg_path.exists():
            try:
                fg = pd.read_csv(fg_path)
                keep = {
                    'mlb_id':             'batter',
                    'avg_bat_speed':      'avg_swing_speed',
                    'blast_swing_pct':    'blast_rate',
                    'squared_up_swing_pct':'squared_up_rate',
                }
                cols = {src: dst for src, dst in keep.items() if src in fg.columns}
                if cols:
                    fg_sub = fg[list(cols.keys())].rename(columns=cols)
                    fg_sub['batter'] = pd.to_numeric(fg_sub['batter'], errors='coerce').astype('Int64')
                    for c in ('blast_rate', 'squared_up_rate'):
                        if c in fg_sub.columns:
                            v = pd.to_numeric(fg_sub[c], errors='coerce')
                            if v.dropna().max() and v.dropna().max() > 1.5:
                                fg_sub[c] = (v / 100.0).round(4)
                    fg_sub = fg_sub.dropna(subset=['batter']).copy()
                    fg_sub['batter'] = fg_sub['batter'].astype(int)
                    season = season.merge(fg_sub, on='batter', how='left')
                    print(f'  [{yr}] merged FG bat-tracking: {fg_sub.shape[0]} matches', flush=True)
            except Exception as exc:
                print(f'  [{yr}] FG merge failed: {exc}', flush=True)

        # Final per-PA target (vector-safe; pa==0 yields NaN that we drop later)
        pa = season['pa'].replace(0, np.nan)
        season['r_per_pa']   = season['r']   / pa
        season['rbi_per_pa'] = season['rbi'] / pa
        season['fp_total'] = (
            SCORE['r']   * season['r']
          + SCORE['tb']  * season['tb']
          + SCORE['rbi'] * season['rbi']
          + SCORE['bb']  * season['bb']
          + SCORE['hbp'] * season['hbp']
          + SCORE['sb']  * season['sb']
          + SCORE['k']   * season['k']
        )
        season['fp_per_pa_actual'] = season['fp_total'] / pa
        # Core (skill-only): TB + BB + HBP + SB - K
        season['core_fp_total'] = (
            SCORE['tb']  * season['tb']
          + SCORE['bb']  * season['bb']
          + SCORE['hbp'] * season['hbp']
          + SCORE['sb']  * season['sb']
          + SCORE['k']   * season['k']
        )
        season['core_fp_per_pa_actual'] = season['core_fp_total'] / pa

        print(f'  [{yr}] {len(season)} batters; {(season["pa"]>=200).sum()} ≥200 PA', flush=True)
        frames.append(season)

    if not frames:
        print('No frames built — aborting.', flush=True)
        return

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(['year', 'pa'], ascending=[True, False]).reset_index(drop=True)
    out.to_csv(OUT_CSV, index=False)
    print(f'\nWrote {OUT_CSV}: {len(out)} rows, {out["year"].nunique()} years', flush=True)
    print(f'  ≥200 PA total: {(out["pa"]>=200).sum()}', flush=True)
    print(f'  ≥300 PA total: {(out["pa"]>=300).sum()}', flush=True)


if __name__ == '__main__':
    build()
