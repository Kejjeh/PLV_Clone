"""build_matchup_dashboard.py — schedule + opp + role + cap aware H2H dashboard.

Polish features:
  1. Per-game hitter opp factor uses OPPOSING SP's projection (not just team
     pit_index) → tougher SP = bigger hitter suppression.
  2. RP appearance rates by role: closer 0.55, setup 0.40, middle 0.30 of
     team games.
  3. SP 10-start-per-week cap (BrownU rule): sort projected starts by FP
     descending, keep top 10.
  4. Win probability from projected gap + combined variance.
  5. Two-start pitchers flagged with 🔥 badge.

Output: data/outputs/matchup.html + xfp-model/docs/matchup.html
"""
from __future__ import annotations
import sys
import json
import math
import unicodedata
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from html import escape as h

import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))

from plv_clone.mlb_stats import fetch_week_probables, resolve_mlbam  # noqa: E402
OUT = ROOT / 'data' / 'outputs'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
XFP_DOCS = ROOT / 'xfp-model' / 'docs'

USER_AGENT = 'Mozilla/5.0 (matchup-dashboard)'
SEASON_END = date(2026, 9, 28)

# SP start cap per BrownU rules
MAX_SP_STARTS_PER_WEEK = 10

# League-average per-event FP (for opp factor centering)
LEAGUE_AVG_SP_FP_PER_START = 11.5
LEAGUE_AVG_HITTER_PER_GAME = 2.8

# Per-event variance estimates (for win probability calculation)
SIGMA_PER_HITTER_GAME = 3.5  # std dev of hitter daily FP
SIGMA_PER_SP_START = 5.5      # std dev of SP per-start FP
SIGMA_PER_RP_GAME = 2.5       # std dev of RP per-game FP

# Reliever appearance rates by role
RP_APP_RATE = {
    'closer': 0.55, 'setup': 0.40, 'long_low': 0.30,
    'middle': 0.30, 'long': 0.30,
}
DEFAULT_RP_APP_RATE = 0.35

ESPN_TO_MLB_TEAM = {
    'BAL': 110, 'BOS': 111, 'NYY': 147, 'TB': 139, 'TOR': 141,
    'CHW': 145, 'CWS': 145, 'CLE': 114, 'DET': 116, 'KC': 118, 'KCR': 118, 'MIN': 142,
    'HOU': 117, 'LAA': 108, 'OAK': 133, 'ATH': 133, 'SEA': 136, 'TEX': 140,
    'ATL': 144, 'MIA': 146, 'NYM': 121, 'PHI': 143, 'WSH': 120, 'WSN': 120,
    'CHC': 112, 'CIN': 113, 'MIL': 158, 'PIT': 134, 'STL': 138,
    'ARI': 109, 'COL': 115, 'LAD': 119, 'SD': 135, 'SDP': 135, 'SF': 137, 'SFG': 137,
}


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def _fetch_json(url):
    req = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_matchup():
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    period = league.currentMatchupPeriod
    for bs in league.box_scores(matchup_period=period):
        if bs.home_team and 'Ligers' in bs.home_team.team_name:
            return {'mine': bs.home_team, 'opp': bs.away_team,
                    'my_score': bs.home_score, 'opp_score': bs.away_score,
                    'my_lineup': bs.home_lineup, 'opp_lineup': bs.away_lineup,
                    'period': period, 'league_obj': league}
        if bs.away_team and 'Ligers' in bs.away_team.team_name:
            return {'mine': bs.away_team, 'opp': bs.home_team,
                    'my_score': bs.away_score, 'opp_score': bs.home_score,
                    'my_lineup': bs.away_lineup, 'opp_lineup': bs.home_lineup,
                    'period': period, 'league_obj': league}
    raise RuntimeError('No Ligers matchup found')


def load_projections():
    rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv').drop_duplicates('player_name')
    rh3['nk'] = rh3['player_name'].map(_norm)
    # MA1: per-player sigma. MA2 hitter: rh3.recency_form_gap (xpwOBA delta vs prior).
    rh3_map = {r['nk']: {'per_game': r.get('xfp_rh3_per_game') or 0,
                          'per_pa': r.get('xfp_rh3_per_pa') or 0,
                          'prior_fp_per_pa': r.get('prior_fp_per_pa'),
                          'recency_form_gap': r.get('recency_form_gap'),
                          'sigma': r.get('xfp_rh3_sigma')}
                for _, r in rh3.iterrows()}

    rp3_path = OUT / 'xfp_rp3_projections_il_fixed.csv'
    if not rp3_path.exists():
        rp3_path = OUT / 'xfp_rp3_projections.csv'
    rp3 = pd.read_csv(rp3_path).drop_duplicates('player_name')
    rp3['nk'] = rp3['player_name'].map(_norm)
    rp3_map = {r['nk']: {'per_start': r.get('xfp_rp3_per_start') or 0,
                          'per_start_sched': r.get('xfp_rp3_per_start_sched') or 0,
                          'sigma': r.get('xfp_rp3_sigma')}
                for _, r in rp3.iterrows()}
    # mlbam → rp3 lookup (for opposing-SP factor)
    sp_id = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv',
                          usecols=['pitcher', 'player_name']).drop_duplicates('player_name')
    sp_id['nk'] = sp_id['player_name'].map(_norm)
    rp3_by_mlbam = {}
    for _, r in sp_id.iterrows():
        rp_info = rp3_map.get(r['nk'])
        if rp_info and rp_info['per_start']:
            rp3_by_mlbam[int(r['pitcher'])] = rp_info

    rprs2 = pd.read_csv(OUT / 'xfp_rprs2_projections.csv').drop_duplicates('name_api')
    rprs2['nk'] = rprs2['name_api'].map(_norm)
    # MA1: derive sigma from quantiles. σ ≈ (p75 - p25) / 1.35 (standard normal IQR identity)
    rprs2_map = {}
    for _, r in rprs2.iterrows():
        p25 = r.get('xfp_p25'); p75 = r.get('xfp_p75')
        sigma = (p75 - p25) / 1.35 if (pd.notna(p25) and pd.notna(p75)) else None
        rprs2_map[r['nk']] = {'xfp_ros': r.get('xfp_ros') or 0,
                              'xfp_full_year': r.get('xfp_full_year') or 0,
                              'role': r.get('role_lag1') or 'middle',
                              'sigma': sigma}

    team_strength = pd.read_csv(CACHE / 'team_strength_2026.csv')
    team_strength['team'] = team_strength['team'].str.upper()
    ts_map = team_strength.set_index('team')[['bat_index', 'pit_index']].to_dict('index')

    return rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map


# ─────────────────────────────────────────────────────────────────────────────
# MA2-MA6 adjuster data loaders + helpers
# ─────────────────────────────────────────────────────────────────────────────
def _safe_csv(path, **kw):
    try: return pd.read_csv(path, **kw)
    except Exception: return None


def load_recent_form_maps():
    """MA2 — Rolling 21d / season ratios for hitters + SPs.

    Returns (hitter_form_map, sp_form_map): mlbam_id → factor in [0.85, 1.15]
    (Rolling data is keyed on MLBAM, not name.)
    """
    hitter_form, sp_form = {}, {}

    # Hitters: keyed on `batter` MLBAM ID. Use core_fp_per_pa as the rate.
    rh = _safe_csv(CACHE / 'rolling_hitters_2018_2026.csv')
    if rh is not None and 'batter' in rh.columns:
        if 'year' in rh.columns:
            rh = rh[rh['year'] == rh['year'].max()]
        if 'split_day' in rh.columns:
            rh = rh.sort_values('split_day').drop_duplicates('batter', keep='last')
        for _, r in rh.iterrows():
            l21 = r.get('core_fp_per_pa_last21')
            tot = r.get('core_fp_per_pa_to')
            pa_last21 = r.get('pa_last21', 0) or 0
            if pd.notna(l21) and pd.notna(tot) and tot > 0 and pa_last21 >= 30:
                factor = max(0.85, min(1.15, l21 / tot))
                hitter_form[int(r['batter'])] = factor

    # SPs: keyed on `pitcher` MLBAM ID
    rp = _safe_csv(CACHE / 'rolling_pitchers_2018_2026.csv')
    if rp is not None and 'pitcher' in rp.columns:
        if 'year' in rp.columns:
            rp = rp[rp['year'] == rp['year'].max()]
        if 'split_day' in rp.columns:
            rp = rp.sort_values('split_day').drop_duplicates('pitcher', keep='last')
        for _, r in rp.iterrows():
            l21 = r.get('fp_per_start_last21')
            tot = r.get('fp_per_start_to')
            gs_last21 = r.get('gs_last21', 0) or 0
            if pd.notna(l21) and pd.notna(tot) and tot > 0 and gs_last21 >= 2:
                factor = max(0.85, min(1.15, l21 / tot))
                sp_form[int(r['pitcher'])] = factor

    return hitter_form, sp_form


def load_lineup_map():
    """MA3+MA7 — per-batter modal lineup spot + PA/game with RECENCY WEIGHTING.

    Last 7 games weighted ×2 vs games 8-21d ago (#7). This catches recent
    demotions/promotions faster than flat L21d modal.
    """
    parq = CACHE / 'hitter_lineup_appearances_2026.parquet'
    try:
        df = pd.read_parquet(parq)
    except Exception:
        return {}
    today = date.today()
    cutoff_21 = today - timedelta(days=21)
    cutoff_7 = today - timedelta(days=7)
    df['game_date'] = pd.to_datetime(df['game_date']).dt.date
    df = df[df['game_date'] >= cutoff_21]
    out = {}
    for batter, sub in df.groupby('batter'):
        starts = sub[sub['started_game'] == True]
        if len(starts) < 3:
            continue
        # Recency weighting: last-7d games count 2x
        starts = starts.copy()
        starts['_w'] = starts['game_date'].apply(lambda d: 2.0 if d >= cutoff_7 else 1.0)
        # Weighted modal lineup spot
        spots = starts.dropna(subset=['lineup_spot'])
        if len(spots):
            spot_counts = spots.groupby('lineup_spot')['_w'].sum().sort_values(ascending=False)
            modal_spot = int(spot_counts.index[0])
        else:
            modal_spot = None
        # Weighted mean PA/g
        pa_per_g = float((starts['pa_in_game'] * starts['_w']).sum() / starts['_w'].sum())
        out[int(batter)] = {'modal_spot': modal_spot, 'pa_per_g': pa_per_g}
    return out


def lineup_spot_factor(modal_spot, pa_per_g):
    """MA3 — lineup-spot + PA-volume multiplier.

    rh3 builds `xfp_rh3_per_game` from `per_pa * PA_PER_GAME_LEAGUE` where the
    constant is 3.5. Per-player PA / 3.5 corrects rh3's flat assumption.
    Clamp widened to [0.70, 1.40] after audit (24/428 hitters at 1.30 ceiling,
    p99 factor was 1.37 — clamp was truncating legit elite-leadoff hitters).
    """
    LEAGUE_PA = 3.5
    pa_factor = (pa_per_g or LEAGUE_PA) / LEAGUE_PA
    spot_bonus = 0.0
    if modal_spot in (1, 2): spot_bonus = 0.03
    elif modal_spot == 3: spot_bonus = 0.02
    elif modal_spot == 4: spot_bonus = 0.03
    elif modal_spot == 5: spot_bonus = 0.01
    elif modal_spot in (7, 8, 9): spot_bonus = -0.02
    return max(0.70, min(1.40, pa_factor * (1 + spot_bonus)))


def load_park_factors():
    """MA4 DROPPED (#5). Trivial impact (±0.1 FP) and park_factors.csv is
    minimal. Stub returns empty so _PARK stays empty if anyone references it."""
    return {}


def load_pitcher_splits():
    """MA5 — pitcher mlbam → {p_throws, xwoba_vs_L, xwoba_vs_R}."""
    df = _safe_csv(CACHE / 'pitcher_splits.csv')
    if df is None or 'pitcher' not in df.columns: return {}
    if 'year' in df.columns:
        df = df[df['year'] == df['year'].max()]
    return df.set_index('pitcher')[['p_throws', 'xwoba_vs_L', 'xwoba_vs_R']].to_dict('index')


def load_bat_side_map():
    """MA5 helper — batter mlbam → 'L' | 'R' | 'S' (modal stance).

    ESPN player objects don't expose handedness. Derive from Statcast 2026
    `stand` column (modal per batter). Switch hitters get 'S' (could refine
    later by checking opposing pitcher hand, but most platoon math uses
    'L'/'R' so we'd treat S→opposite-of-pitcher).
    """
    parq = CACHE / 'statcast_2026.parquet'
    if not parq.exists(): return {}
    try:
        import duckdb
        con = duckdb.connect()
        df = con.execute(f"""
            SELECT batter, stand, COUNT(*) n
            FROM read_parquet('{parq}')
            WHERE batter IS NOT NULL AND stand IS NOT NULL
            GROUP BY batter, stand
        """).df()
        # Modal stand per batter
        df = df.sort_values('n', ascending=False).drop_duplicates('batter', keep='first')
        return df.set_index('batter')['stand'].to_dict()
    except Exception:
        return {}


def load_il_returns(mu):
    """MA6 #10 — cache IL'd player → return_date map upstream.

    `player.returnDate` is unreliable (often None even when ESPN has it).
    Call `get_injury_details()` for all IL'd lineup players once at startup,
    cache return_date by player_id.
    """
    try:
        from plv_clone.league_state import LeagueState as _LS_inj
        get_injury_details = _LS_inj().injury_details
    except Exception:
        return {}
    il_ids = []
    for p in (mu.get('my_lineup') or []) + (mu.get('opp_lineup') or []):
        inj = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
        if inj in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'INJURY_RESERVE', 'OUT'):
            pid = getattr(p, 'playerId', None)
            if pid: il_ids.append(int(pid))
    if not il_ids: return {}
    try:
        details = get_injury_details(il_ids)
    except Exception as e:
        print(f'  ⚠ get_injury_details failed: {e}')
        return {}
    out = {}
    for _, r in details.iterrows():
        rd = r.get('return_date')
        if pd.notna(rd):
            try: out[int(r['player_id'])] = date.fromisoformat(str(rd)[:10])
            except Exception: pass
    return out


def load_calibration_scalar():
    """MA7 — read MA0's calibration JSON. Returns 1.0 if not available.

    NOTE: only consume the scalar once MA0 was re-fit using POST-adjuster
    projections. The first MA0 fit (against pre-adjuster Period 7) is
    stale once MA1-MA6 are live — applying it would double-correct.
    The calibration JSON includes a `safe_to_consume` flag set by the
    re-fit step; if absent or false, return 1.0.
    """
    path = ROOT / 'data' / 'models' / 'matchup_calibration.json'
    try:
        import json
        d = json.loads(path.read_text())
        if not d.get('safe_to_consume', False):
            return 1.0
        return float(d['scalar_correction'])
    except Exception:
        return 1.0


# Module-level lazy caches (populated on first call from main())
_ADJUSTERS_ON = False        # master CLI flag
_MA2_HITTER_ON = False       # #6 — independent toggle for hitter MA2 (rh3.recency_form_gap)
_MA2_SP_ON = False           # #6 — independent toggle for SP MA2 (rolling 21d)
_HITTER_FORM = {}            # SP form keyed by mlbam (MA2 SP); hitters now use rh3 recency_form_gap directly
_SP_FORM = {}
_LINEUP = {}
_PARK = {}                   # MA4 DROPPED; kept as empty stub for backward compat
_PSPLIT = {}
_BAT_SIDE = {}
_IL_RETURNS = {}             # #10 — player_id → return_date from get_injury_details upstream cache
_CALIB = 1.0
LEAGUE_AVG_XWOBA = 0.310     # MA5 platoon normalization


def fetch_espn_week_schedule(league, week_start, week_end):
    """Pull team game schedules from ESPN's proGamesByScoringPeriod.

    Replaces the old MLB Stats API team-schedule call with ESPN's own
    authoritative game calendar.  This makes the dashboard's team-game-day
    counts match exactly what ESPN shows in their UI (since it's the same
    source), and eliminates the separate MLB Stats API schedule fetch.

    Probable-pitcher fields (my_probable_id / opp_probable_id) are left None
    here; they are filled in later by build_sp_starts_by_pitcher via
    fetch_week_probables (MLB Stats API).

    Returns: {mlb_team_id: [game_dict, …]} — same shape as the old
    fetch_schedules_by_team so all downstream code is unchanged.
    """
    try:
        raw = league.espn_request.get_pro_schedule()
    except Exception:
        return {}

    # ESPN internal team_id → uppercase abbreviation  (e.g. 11 → 'ATH')
    espn_id_to_abbr: dict[int, str] = {}
    for team in raw.get('settings', {}).get('proTeams', []):
        if team['id'] != 0:
            espn_id_to_abbr[team['id']] = team.get('abbrev', '').upper()

    # abbrev → MLB Stats API team_id (for keying the returned dict)
    abbr_to_mlb = ESPN_TO_MLB_TEAM  # defined at module level

    by_mlb: dict[int, list] = {}
    for team in raw.get('settings', {}).get('proTeams', []):
        espn_id = team['id']
        if espn_id == 0:
            continue
        abbr = espn_id_to_abbr.get(espn_id, '')
        mlb_id = abbr_to_mlb.get(abbr)
        if mlb_id is None:
            continue

        games = []
        for _sp, game_list in team.get('proGamesByScoringPeriod', {}).items():
            for g in game_list:
                cal = date.fromtimestamp(g['date'] / 1000)
                if not (week_start <= cal <= week_end):
                    continue
                home_id = g['homeProTeamId']
                away_id = g['awayProTeamId']
                is_home = (espn_id == home_id)
                opp_espn_id = away_id if is_home else home_id
                opp_abbr = espn_id_to_abbr.get(opp_espn_id, '?')
                games.append({
                    'date': cal.isoformat(),
                    'is_home': is_home,
                    'opp_team': opp_abbr,
                    # Probable pitcher fields filled in later by fetch_week_probables
                    'my_probable_id': None,
                    'my_probable_name': None,
                    'opp_probable_id': None,
                    'opp_probable_name': None,
                })
        if games:
            # Sort chronologically; deduplicate (ESPN may list doubleheaders twice)
            seen = set()
            uniq = []
            for g in sorted(games, key=lambda x: x['date']):
                key = (g['date'], g['opp_team'])
                if key not in seen:
                    seen.add(key)
                    uniq.append(g)
            by_mlb[mlb_id] = uniq

    return by_mlb


def fetch_schedules_by_team(team_ids, start_date, end_date):
    """Fallback MLB Stats API schedule fetch (used only when ESPN schedule unavailable).

    The primary path is fetch_espn_week_schedule().  This function is kept as a
    fallback and for the SP probable-pitcher overlay inside build_sp_starts_by_pitcher.

    Returns a dict keyed by MLB team_id; missing teams default to empty list
    on lookup downstream.
    """
    url = (f'https://statsapi.mlb.com/api/v1/schedule?sportId=1'
           f'&startDate={start_date}&endDate={end_date}'
           f'&hydrate=probablePitcher,team')
    try:
        data = _fetch_json(url)
    except Exception:
        return {tid: [] for tid in team_ids}
    by_team = {tid: [] for tid in team_ids}
    for d_block in data.get('dates', []):
        for g in d_block.get('games', []):
            home = g['teams']['home']
            away = g['teams']['away']
            home_id = home['team']['id']
            away_id = away['team']['id']
            home_p = home.get('probablePitcher', {}) or {}
            away_p = away.get('probablePitcher', {}) or {}
            date_s = g['gameDate'][:10]
            home_abbr = home['team'].get('abbreviation', '?').upper()
            away_abbr = away['team'].get('abbreviation', '?').upper()
            if home_id in by_team:
                by_team[home_id].append({
                    'date': date_s,
                    'is_home': True,
                    'opp_team': away_abbr,
                    'my_probable_id': home_p.get('id'),
                    'my_probable_name': home_p.get('fullName'),
                    'opp_probable_id': away_p.get('id'),
                    'opp_probable_name': away_p.get('fullName'),
                })
            if away_id in by_team:
                by_team[away_id].append({
                    'date': date_s,
                    'is_home': False,
                    'opp_team': home_abbr,
                    'my_probable_id': away_p.get('id'),
                    'my_probable_name': away_p.get('fullName'),
                    'opp_probable_id': home_p.get('id'),
                    'opp_probable_name': home_p.get('fullName'),
                })
    return by_team


def player_mlbam_lookup(name, cache={}):
    if not cache:
        for csv, col in [(CACHE / 'hitters_multiyr_2015_2026.csv', 'batter'),
                          (CACHE / 'sp_multiyr_2015_2025.csv', 'pitcher'),
                          (CACHE / 'relievers_multiyr_2018_2026.csv', 'pitcher')]:
            try:
                cols = pd.read_csv(csv, nrows=1).columns.tolist()
                ncol = 'player_name' if 'player_name' in cols else 'name'
                df = pd.read_csv(csv, usecols=[col, ncol])
                df['_nk'] = df[ncol].map(_norm)
                for _, r in df.drop_duplicates('_nk').iterrows():
                    cache.setdefault(r['_nk'], int(r[col]))
            except Exception:
                pass
    return cache.get(_norm(name))


def _resolve_mlbam_via_api(name, cache={}):
    """Fallback MLBAM resolution when player not in cached multi-year CSVs.

    Thin wrapper around `plv_clone.mlb_stats.resolve_mlbam` that retains the
    in-process per-name cache so repeated lookups don't re-hit the API.
    """
    if name in cache:
        return cache[name]
    try:
        result = resolve_mlbam([name])
    except Exception:
        result = {}
    pid = result.get(name)
    cache[name] = pid
    return pid


def build_sp_starts_by_pitcher(pitcher_ids, schedules_by_team, today, week_end):
    """Adapter — call `fetch_week_probables` once and reshape the result into
    `{mlbam: [game_dict]}` matching the original SP-start payload shape.

    Each game_dict carries the same keys the dashboard's downstream rendering
    consumes: `date`, `opp_team`, `is_home`, `my_probable_id`,
    `my_probable_name`, `opp_probable_id`, `opp_probable_name`, `confirmed`.

    The schedule data already in `schedules_by_team` is the source of truth
    for per-day team-game info (is_home, opp_probable_*). We look up each
    (pid, date) returned by `fetch_week_probables` against the pitcher's
    team-day schedule to recover those fields. `confirmed` is True when the
    pitcher matched as the listed probable; False when the start came from
    rotation-gap prediction.
    """
    pid_set = {int(p) for p in pitcher_ids if p}
    if not pid_set:
        return {}
    week_start = today  # fetch_week_probables semantic: window starts here
    try:
        wp = fetch_week_probables(
            week_start=week_start, week_end=week_end,
            pitcher_ids=pid_set,
        )
    except Exception:
        return {pid: [] for pid in pid_set}

    # Index team schedules by date for quick per-pitcher lookup. The pitcher's
    # team_id is recoverable from any confirmed game in the schedule (or — for
    # pitchers with no confirmed in-window — from the start dates themselves,
    # which fetch_week_probables resolved via the /people endpoint fallback).
    team_by_date_lookup = {}  # team_id -> {date_str: game_dict}
    for tid, games in schedules_by_team.items():
        team_by_date_lookup[tid] = {g['date']: g for g in games}

    # Pre-compute: pitcher_id -> team_id.
    # Primary: scan schedules (ESPN-sourced) for teams with the pitcher's opp on the right day.
    # Fallback: use the mlbam → MLB team mapping from the schedule.
    pid_to_team = {}
    # Try matching via opp_team abbreviation on dates where we know the start
    for (pid, start_date), opp_abbr in wp.starts.items():
        date_s = start_date.isoformat()
        for tid, games in schedules_by_team.items():
            for g in games:
                if g['date'] == date_s and g['opp_team'].upper() == opp_abbr.upper():
                    pid_to_team.setdefault(pid, tid)
                    break
            if pid in pid_to_team:
                break

    starts_by_pid = {pid: [] for pid in pid_set}
    for (pid, start_date), opp_abbr in wp.starts.items():
        date_s = start_date.isoformat()
        # Confirmed iff this (pid, date) key was in MLB's confirmed-probable list.
        # This is authoritative regardless of schedule source (ESPN vs MLB Stats API).
        confirmed = (pid, start_date) in wp.confirmed_keys

        # Find which team this pitcher plays for so we can fetch is_home, etc.
        tid = pid_to_team.get(pid)
        game_meta = None
        if tid is not None:
            game_meta = team_by_date_lookup.get(tid, {}).get(date_s)
            # ±1 day tolerance for matching the team game (mirrors mlb_stats'
            # prediction tolerance).
            if game_meta is None:
                for offset in (1, -1):
                    alt = (start_date + timedelta(days=offset)).isoformat()
                    cand = team_by_date_lookup.get(tid, {}).get(alt)
                    if cand and cand.get('opp_team', '').upper() == opp_abbr.upper():
                        game_meta = cand
                        date_s = alt  # use the matched team-game date
                        break
        if game_meta:
            starts_by_pid[pid].append({
                'date': date_s,
                'opp_team': game_meta['opp_team'],
                'is_home': game_meta['is_home'],
                'my_probable_id': pid,
                'my_probable_name': ('(probable)' if confirmed else '(predicted)'),
                'opp_probable_id': game_meta.get('opp_probable_id'),
                'opp_probable_name': game_meta.get('opp_probable_name'),
                'confirmed': confirmed,
            })
        else:
            # No matching team-day record (pitcher's team wasn't fetched, or
            # the date drifted). Emit a stub so downstream SP cap math still
            # sees the start; opp_probable lookups fall back to defaults.
            starts_by_pid[pid].append({
                'date': date_s,
                'opp_team': opp_abbr.upper(),
                'is_home': True,
                'my_probable_id': pid,
                'my_probable_name': '(predicted)',
                'opp_probable_id': None,
                'opp_probable_name': None,
                'confirmed': False,
            })
    # Sort each pitcher's starts chronologically (matches old confirmed+predicted order).
    for pid in starts_by_pid:
        starts_by_pid[pid].sort(key=lambda s: s['date'])
    return starts_by_pid


def project_player(player, schedules_by_team, sp_starts_by_pitcher, rh3_map,
                     rp3_map, rp3_by_mlbam, rprs2_map, ts_map, today, week_end):
    """Schedule + opp + role aware projection. Returns dict with fp, units,
       per-game/start breakdown, sigma_total, and any badges."""
    name, pos = player.name, (player.position or '?')
    nk = _norm(name)
    team = (player.proTeam or '').upper()
    mlb_id = ESPN_TO_MLB_TEAM.get(team)
    out = {'fp': 0.0, 'units': 0, 'breakdown': [], 'sigma2': 0.0, 'badges': []}
    if mlb_id is None: return out
    games = schedules_by_team.get(mlb_id, [])
    today_s = today.isoformat()
    week_end_s = week_end.isoformat()
    # Include TODAY in remaining-week projection (fix: was `today_s <` strict).
    # WTD score from ESPN reflects only what's been scored at build time, so
    # today's confirmed starts must contribute to the rest-of-week projection.
    rem = [g for g in games if today_s <= g['date'] <= week_end_s]

    # MA6 — IL-window pro-rate. #10: prefer upstream-cached _IL_RETURNS map
    # (built from get_injury_details()) since `player.returnDate` is usually None.
    il_factor = 1.0
    inj = (getattr(player, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    if _ADJUSTERS_ON and inj in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'INJURY_RESERVE', 'OUT'):
        pid_for_il = getattr(player, 'playerId', None)
        rd = _IL_RETURNS.get(pid_for_il) if pid_for_il else None
        if rd is None:
            # fallback to player.returnDate if upstream cache missed
            rd_str = getattr(player, 'returnDate', None) or None
            if rd_str:
                try: rd = date.fromisoformat(str(rd_str)[:10])
                except Exception: rd = None
        if rd is not None:
            if rd <= week_end:
                days_avail = max(0, (week_end - max(rd, today)).days + 1)
                days_total = max(1, (week_end - today).days + 1)
                il_factor = days_avail / days_total
            else:
                return out  # returns after window — zero

    if pos == 'SP':
        # Skip IL'd pitchers entirely — no projection regardless of MLB stale probables
        if inj in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'INJURY_RESERVE',
                   'OUT', 'DAY_TO_DAY'):
            return out

        mlbam = player_mlbam_lookup(name)
        if not mlbam:  # unresolvable MLBAM — try MLB Stats API search
            mlbam = _resolve_mlbam_via_api(name)
        if not mlbam:
            return out  # Can't match without an ID

        # SP starts (confirmed + rotation-gap predictions) come pre-computed
        # via fetch_week_probables → build_sp_starts_by_pitcher in main().
        # Filter to in-window starts.
        all_starts = sp_starts_by_pitcher.get(int(mlbam), [])
        starts = [s for s in all_starts
                  if today_s <= s['date'] <= week_end_s]

        rp_info = rp3_map.get(nk, {})
        per_start_base = rp_info.get('per_start') or 0
        if not per_start_base or not starts: return out
        if len(starts) >= 2:
            out['badges'].append('🔥 2-START')

        # MA2 (SP): recent-form factor — gated on _MA2_SP_ON
        recent_factor = _SP_FORM.get(mlbam, 1.0) if _MA2_SP_ON else 1.0

        total = 0.0
        for s in starts:
            opp_idx = ts_map.get(s['opp_team'], {}).get('bat_index') or 1.0
            opp_factor = max(0.80, min(1.20, 1.0 / opp_idx))
            # MA7: residual calibration scalar (final pass). MA4 dropped per #5.
            fp = per_start_base * opp_factor * recent_factor * _CALIB
            total += fp
            out['breakdown'].append({'date': s['date'], 'opp': s['opp_team'],
                                       'opp_idx': opp_idx, 'factor': opp_factor,
                                       'recent_factor': recent_factor,
                                       'fp': fp, 'type': 'start',
                                       'confirmed': s.get('confirmed', True)})
        out['fp'] = total
        out['units'] = len(starts)
        # MA1: per-player sigma (gated)
        sp_sigma = (rp_info.get('sigma') or SIGMA_PER_SP_START) if _ADJUSTERS_ON else SIGMA_PER_SP_START
        out['sigma2'] = len(starts) * sp_sigma ** 2
        return out

    elif pos in ('RP', 'P'):
        rp_info = rprs2_map.get(nk, {})
        role = rp_info.get('role') or 'middle'
        app_rate = RP_APP_RATE.get(role, DEFAULT_RP_APP_RATE)
        xfp_ros = rp_info.get('xfp_ros') or 0
        if not xfp_ros or not rem: return out
        # rest_of_season RoS / team games remaining (rough)
        days_remaining_season = max((SEASON_END - today).days, 1)
        per_team_game = xfp_ros / days_remaining_season
        # apply role-based appearance rate adjustment
        expected_appearances = len(rem) * app_rate
        per_app = (per_team_game / DEFAULT_RP_APP_RATE) if DEFAULT_RP_APP_RATE else per_team_game
        # MA6 IL pro-rate + MA7 calibration
        proj = per_app * expected_appearances * il_factor * _CALIB
        out['fp'] = proj
        out['units'] = round(expected_appearances, 1)
        out['breakdown'].append({'role': role, 'app_rate': app_rate,
                                   'n_team_games': len(rem),
                                   'expected_apps': expected_appearances,
                                   'il_factor': il_factor,
                                   'fp': proj})
        # MA1 RP sigma: rprs2 p25/p75 are SEASON totals, not per-app — derived σ
        # blows up by ~5-15x. Keep static FP/game sigma until rprs2 emits per-app σ.
        out['sigma2'] = expected_appearances * SIGMA_PER_RP_GAME ** 2
        return out

    else:  # hitter
        rh = rh3_map.get(nk, {})
        per_game_base = rh.get('per_game') or 0
        if not per_game_base or not rem: return out

        # MA3: lineup-spot adjuster (uses mlbam → lineup map)
        batter_mlbam = player_mlbam_lookup(name)
        # MA2 hitter: use rh3.recency_form_gap directly (#8 — no double-count;
        # rh3 includes the column as display-only, not in features).
        # Gap is xwoba_per_pa_last21_sh - prior_fp_per_pa. Convert to factor.
        if _MA2_HITTER_ON:
            base_pa = rh.get('prior_fp_per_pa') or rh.get('per_pa') or 0
            gap = rh.get('recency_form_gap')
            if gap and base_pa and base_pa > 0:
                recent_factor = max(0.85, min(1.15, 1.0 + gap / base_pa))
            else:
                recent_factor = 1.0
        else:
            recent_factor = 1.0
        lineup_info = _LINEUP.get(batter_mlbam, {}) if batter_mlbam else {}
        lineup_factor = lineup_spot_factor(lineup_info.get('modal_spot'),
                                            lineup_info.get('pa_per_g')) if lineup_info else 1.0

        total = 0.0
        for g in rem:
            # Use opposing SP's projection if known; fall back to team pit_index
            opp_sp_id = g.get('opp_probable_id')
            opp_factor = 1.0
            opp_proj = None
            if opp_sp_id and opp_sp_id in rp3_by_mlbam:
                opp_proj = rp3_by_mlbam[opp_sp_id]['per_start']
                opp_factor = LEAGUE_AVG_SP_FP_PER_START / opp_proj if opp_proj else 1.0
                opp_factor = max(0.70, min(1.30, opp_factor))
            else:
                opp_pit = ts_map.get(g['opp_team'], {}).get('pit_index') or 1.0
                opp_factor = max(0.85, min(1.15, opp_pit))

            # MA4 DROPPED (#5) — park factor was ±0.1 FP/team, not worth complexity.
            park_factor = 1.0

            # MA5: platoon factor — opposing SP's xwOBA vs batter's stance.
            # Bat-side comes from Statcast `stand` map; switch hitters batting
            # OPPOSITE the pitcher's hand (e.g., S vs RHP → bat L).
            platoon_factor = 1.0
            if opp_sp_id and opp_sp_id in _PSPLIT and batter_mlbam in _BAT_SIDE:
                stance = _BAT_SIDE.get(batter_mlbam, 'R')
                ps = _PSPLIT[opp_sp_id]
                if stance == 'S':
                    # Switch hitters bat opposite the pitcher's throwing arm
                    p_throws = ps.get('p_throws', 'R')
                    stance = 'L' if p_throws == 'R' else 'R'
                if stance in ('L', 'R'):
                    opp_xwoba = ps.get(f'xwoba_vs_{stance}')
                    if opp_xwoba and opp_xwoba > 0:
                        platoon_factor = max(0.85, min(1.15, opp_xwoba / LEAGUE_AVG_XWOBA))

            # MA7: residual calibration as final scalar
            fp = (per_game_base * opp_factor * recent_factor * lineup_factor
                  * park_factor * platoon_factor * il_factor * _CALIB)
            total += fp
            out['breakdown'].append({
                'date': g['date'], 'opp': g['opp_team'],
                'opp_sp': g.get('opp_probable_name', '?'),
                'opp_sp_proj': opp_proj, 'factor': opp_factor,
                'recent_factor': recent_factor,
                'lineup_factor': lineup_factor,
                'park_factor': park_factor,
                'platoon_factor': platoon_factor,
                'il_factor': il_factor,
                'fp': fp, 'type': 'game',
            })
        out['fp'] = total
        out['units'] = len(rem)
        # MA1: hitter sigma — rh3's xfp_rh3_sigma is xwOBA-scale, not FP/g.
        # Keep static FP/g sigma until we have proper game-level σ.
        out['sigma2'] = len(rem) * SIGMA_PER_HITTER_GAME ** 2
        return out


def apply_sp_cap(team_projections, cap=MAX_SP_STARTS_PER_WEEK):
    """Cap SP starts at `cap` per team. Sort SP starts by FP desc; zero excess."""
    sp_starts = []
    for name, proj in team_projections.items():
        for i, b in enumerate(proj.get('breakdown', [])):
            if b.get('type') == 'start':
                sp_starts.append({'name': name, 'idx': i, 'fp': b['fp']})
    if len(sp_starts) <= cap:
        return 0
    sp_starts.sort(key=lambda x: -x['fp'])
    capped = sp_starts[cap:]
    capped_fp = 0.0
    for c in capped:
        proj = team_projections[c['name']]
        b = proj['breakdown'][c['idx']]
        b['fp_capped'] = True
        b['fp_original'] = b['fp']
        proj['fp'] -= b['fp']
        capped_fp += b['fp']
        b['fp'] = 0
    return capped_fp


def synthesize_action_items(my_proj, my_lineup, schedules_by_team, win_prob):
    """Build a TOP-OF-PAGE list of urgent actionables."""
    items = []

    # Injuries
    for p in my_lineup:
        inj = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE')
        slot = getattr(p, 'lineupSlot', '')
        if inj not in ('ACTIVE', 'NORMAL', '') and slot not in ('IL', 'INJURY_RESERVE', 'BE'):
            items.append({'urgency': 'high', 'icon': '🏥',
                           'text': f'{p.name} ({inj}) is in active slot {slot} — consider IL/bench'})

    # Cap status — count confirmed and predicted separately
    n_confirmed = sum(1 for proj in my_proj.values()
                      for b in proj.get('breakdown', [])
                      if b.get('type') == 'start' and b.get('confirmed', True))
    n_predicted = sum(1 for proj in my_proj.values()
                      for b in proj.get('breakdown', [])
                      if b.get('type') == 'start' and not b.get('confirmed', True))
    n_starts = n_confirmed + n_predicted
    pred_s = f' (+{n_predicted} predicted)' if n_predicted else ''
    if n_starts < 7:
        items.append({'urgency': 'med', 'icon': '📉',
                       'text': f'Only {n_confirmed} confirmed starts{pred_s} this week — add a streamer to hit the 10-start cap'})

    # Win prob extremes
    if win_prob < 0.40:
        items.append({'urgency': 'high', 'icon': '🚨',
                       'text': f'Trailing scenario — win probability {win_prob*100:.0f}%. Aggressive streaming + lineup tweaks needed.'})
    elif win_prob > 0.85:
        items.append({'urgency': 'low', 'icon': '🟢',
                       'text': f'Strong position — win prob {win_prob*100:.0f}%. Hold steady.'})

    if not items:
        items.append({'urgency': 'low', 'icon': '✅',
                       'text': 'No urgent action items — lineup, cap, and roster look set.'})

    out = ['<div class="action-items"><h3>⚡ Action Items</h3><ul>']
    for it in items[:6]:
        out.append(f'<li class="urgency-{it["urgency"]}">{h(it["icon"])} {h(it["text"])}</li>')
    out.append('</ul></div>')
    return '\n'.join(out)


def render_win_prob_gauge(win_prob):
    """CSS conic-gradient gauge with prominent display."""
    pct = win_prob * 100
    # Color: green if >70, yellow 50-70, red <50 — editorial palette tokens
    if pct >= 70: color = '#7fb069'      # var(--pos)
    elif pct >= 55: color = '#7fb069'
    elif pct >= 45: color = '#d4a945'    # var(--warn)
    elif pct >= 30: color = '#c1666b'    # var(--neg) toned
    else: color = '#c1666b'

    return f'''<div class="gauge-wrap">
  <div class="gauge" style="background: conic-gradient({color} 0% {pct}%, #34302a {pct}% 100%);">
    <div class="gauge-inner">
      <div class="gauge-pct">{pct:.0f}%</div>
      <div class="gauge-label">win probability</div>
    </div>
  </div>
</div>'''


def render_ci_bands(my_total, my_sigma2, opp_total, opp_sigma2):
    """Show P25/P75 CI bands around projected total."""
    import math
    my_sd = math.sqrt(my_sigma2)
    opp_sd = math.sqrt(opp_sigma2)
    # 50% CI = ±0.674 sigma
    return (f'<p class="notes">📐 <b>50% confidence intervals</b>: '
            f'Ligers [<b>{my_total - 0.674*my_sd:.1f}</b> – <b>{my_total + 0.674*my_sd:.1f}</b>] '
            f'vs Opp [<b>{opp_total - 0.674*opp_sd:.1f}</b> – <b>{opp_total + 0.674*opp_sd:.1f}</b>]. '
            f'80% CI: ±{1.282*my_sd:.0f} / ±{1.282*opp_sd:.0f} FP respectively.</p>')


def render_days_of_fire(my_proj):
    """7-day FP forecast per top Liger hitter."""
    rows = []
    for name, proj in my_proj.items():
        if not proj.get('breakdown'): continue
        # Hitters only
        if not any(b.get('type') == 'game' for b in proj['breakdown']): continue
        rows.append({
            'name': name,
            'games': [(b['date'], b['fp']) for b in proj['breakdown'] if b.get('type') == 'game'],
            'total': proj['fp'],
        })
    if not rows:
        return ''
    rows.sort(key=lambda r: -r['total'])
    out = ['<h2>🔥 Days of Fire <small class="muted">(per-day projected FP, top Ligers)</small></h2>',
           '<table style="font-size:.85em"><thead><tr><th>Player</th>']
    # collect unique dates
    all_dates = sorted({d for r in rows for d, _ in r['games']})
    for d in all_dates:
        out.append(f'<th>{d[5:]}</th>')
    out.append('<th>Total</th></tr></thead><tbody>')
    for r in rows[:8]:
        out.append(f'<tr><td>{h(r["name"])}</td>')
        date_to_fp = dict(r['games'])
        for d in all_dates:
            fp = date_to_fp.get(d)
            if fp is None:
                out.append('<td class="muted">—</td>')
            else:
                # Heatmap color tied to FP magnitude
                if fp < 0:
                    cls = 'heat-neg'
                elif fp < 1.5:
                    cls = 'heat-0'
                elif fp < 2.5:
                    cls = 'heat-1'
                elif fp < 3.5:
                    cls = 'heat-2'
                else:
                    cls = 'heat-3'
                out.append(f'<td class="{cls}">{fp:.1f}</td>')
        out.append(f'<td><b>{r["total"]:.1f}</b></td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


def render_playoff_simulation():
    """Monte Carlo: estimate Ligers' regular-season win count given current
       per-week win probability + remaining weeks."""
    history_path = OUT / 'predictions_history.csv'
    if not history_path.exists():
        return ''
    df = pd.read_csv(history_path)
    if df.empty: return ''
    # Use most-recent win_probability as proxy for "typical" weekly win prob
    latest_wp = df.iloc[-1]['win_probability']
    # BrownU has 20 matchup periods; assume current period and remaining periods
    current_period = int(df.iloc[-1]['period'])
    remaining_periods = max(20 - current_period, 0)
    if remaining_periods == 0:
        return '<h2>🎲 Playoff Probability</h2><p class="muted">Regular season complete.</p>'

    # Monte Carlo: 10000 sims of remaining_periods Bernoulli(latest_wp)
    import random
    random.seed(42)
    n_sims = 10000
    wins = []
    for _ in range(n_sims):
        w = sum(1 for _ in range(remaining_periods) if random.random() < latest_wp)
        wins.append(w)
    wins.sort()
    p25 = wins[n_sims // 4]
    p50 = wins[n_sims // 2]
    p75 = wins[n_sims * 3 // 4]
    # Assume playoff threshold ≈ top 4 → ~12 wins in 20-period season
    # (rough; depends on league specifics)
    playoff_threshold = 12
    pct_make = sum(1 for w in wins if w >= playoff_threshold - 4) / n_sims  # assuming 4 prior wins
    return (f'<h2>🎲 Playoff Simulation '
            f'<small class="muted">(Monte Carlo, 10k sims · uses latest weekly win prob)</small></h2>'
            f'<p class="notes">'
            f'Latest weekly win prob: <b>{latest_wp*100:.1f}%</b> · '
            f'{remaining_periods} periods remain<br>'
            f'Projected additional wins: <b>P25 {p25}</b> · '
            f'<b>median {p50}</b> · <b>P75 {p75}</b><br>'
            f'Rough playoff probability (top 4): <b class="pos">{pct_make*100:.1f}%</b> '
            f'(assumes ~{playoff_threshold - 4} more wins needed)'
            f'</p>')


def render_position_competition(rh3_map):
    """For each position, top hot/cold movers among FAs + Ligers."""
    try:
        from plv_clone.league_state import LeagueState
        league = LeagueState()._get_league()
        rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv').drop_duplicates('player_name')
        rh3['nk'] = rh3['player_name'].map(_norm)
        # for each position, top 5 by RoS league-wide
        rostered_by_team = {}
        for t in league.teams:
            for p in t.roster:
                rostered_by_team[_norm(p.name)] = t.team_name

        if 'primary_position' not in rh3.columns:
            return ''
        out = ['<h2>📍 Position-Specific Competition <small class="muted">(top 3 RoS by primary position)</small></h2>',
               '<table><thead><tr><th>Pos</th><th>Top 3 (RoS · owner)</th></tr></thead><tbody>']
        for pos in ['C', '1B', '2B', '3B', 'SS', 'OF']:
            sub = rh3[rh3['primary_position'] == pos].nlargest(5, 'expected_total_fp_remaining')
            entries = []
            for _, r in sub.iterrows():
                owner = rostered_by_team.get(r['nk'], '🆓')
                marker = '⭐' if 'Ligers' in str(owner) else ('🆓' if owner == '🆓' else '')
                entries.append(f'{h(r["player_name"])} <b>{r["expected_total_fp_remaining"]:.0f}</b> · {marker}{h(owner) if owner != "🆓" else "FA"}')
            out.append(f'<tr><td><b>{pos}</b></td><td>{" · ".join(entries[:3])}</td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return f'<h2>📍 Position Competition</h2><p class="muted">error: {h(str(e))}</p>'


def render_injury_alerts(my_lineup):
    """Flag any Liger with current injury status."""
    injured = []
    for p in my_lineup:
        inj = getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE'
        if inj not in ('ACTIVE', 'NORMAL', ''):
            slot = getattr(p, 'lineupSlot', '?')
            injured.append({'name': p.name, 'pos': p.position, 'injury': inj, 'slot': slot})
    if not injured:
        return '<h2>🏥 Injury Status</h2><p class="muted">No injury concerns on your active roster.</p>'
    out = ['<h2>🏥 Injury Status <small class="muted">(current per ESPN)</small></h2>',
           '<table><thead><tr><th>Player</th><th>Pos</th><th>Status</th><th>Slot</th></tr></thead><tbody>']
    for i in injured:
        out.append(f'<tr><td>{h(i["name"])}</td><td>{h(i["pos"])}</td>'
                   f'<td class="neg">{h(i["injury"])}</td><td>{h(str(i["slot"]))}</td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


def render_power_rankings():
    """League-wide team rankings by total RoS projection."""
    try:
        from plv_clone.league_state import LeagueState
        league = LeagueState()._get_league()
        rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv').drop_duplicates('player_name')
        rh3['nk'] = rh3['player_name'].map(_norm)
        rh3_ros = dict(zip(rh3['nk'], rh3['expected_total_fp_remaining'].fillna(0)))
        rp3_path = OUT / 'xfp_rp3_projections_il_fixed.csv'
        if not rp3_path.exists():
            rp3_path = OUT / 'xfp_rp3_projections.csv'
        rp3 = pd.read_csv(rp3_path).drop_duplicates('player_name')
        rp3['nk'] = rp3['player_name'].map(_norm)
        SP_REM = 24
        rp3_ros = dict(zip(rp3['nk'],
                            (rp3.get('ros_fixed', rp3.get('xfp_rp3_per_start_sched',
                                       rp3.get('xfp_rp3_per_start', 0)) * SP_REM)).fillna(0)))
        rprs2 = pd.read_csv(OUT / 'xfp_rprs2_projections.csv').drop_duplicates('name_api')
        rprs2['nk'] = rprs2['name_api'].map(_norm)
        rprs2_ros = dict(zip(rprs2['nk'], rprs2['xfp_ros'].fillna(0)))
        rows = []
        for t in league.teams:
            total = 0
            for p in t.roster:
                nk = _norm(p.name)
                slots = set(getattr(p, 'eligibleSlots', []) or [])
                if slots & {'C','1B','2B','3B','SS','OF','DH','UTIL'}:
                    total += rh3_ros.get(nk, 0)
                else:
                    total += rp3_ros.get(nk, 0) + rprs2_ros.get(nk, 0) * 0.5
            rows.append({'name': t.team_name, 'ros': total})
        rows.sort(key=lambda r: -r['ros'])
        out = ['<h2>🏆 League Power Rankings <small class="muted">(by total RoS projection)</small></h2>',
               '<table><thead><tr><th>#</th><th>Team</th><th>Total RoS</th><th>Δ vs Avg</th></tr></thead><tbody>']
        avg = sum(r['ros'] for r in rows) / len(rows)
        for i, r in enumerate(rows, 1):
            delta = r['ros'] - avg
            cls = 'pos' if delta > 0 else 'neg'
            star = ' ⭐' if 'Ligers' in r['name'] else ''
            out.append(f'<tr><td>{i}</td><td>{h(r["name"])}{star}</td>'
                       f'<td>{r["ros"]:.0f}</td>'
                       f'<td class="{cls}">{delta:+.0f}</td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return f'<h2>🏆 League Power Rankings</h2><p class="muted">error: {h(str(e))}</p>'


def render_drop_pickup_suggestions(my_lineup, rh3_map):
    """Find your lowest-RoS Ligers + matching FA upgrades."""
    try:
        from plv_clone.league_state import LeagueState
        league = LeagueState()._get_league()
        rostered = set()
        for t in league.teams:
            for p in t.roster:
                rostered.add(_norm(p.name))
        fas = league.free_agents(size=300)
        rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv').drop_duplicates('player_name')
        rh3['nk'] = rh3['player_name'].map(_norm)
        rh3_lkup = rh3.set_index('nk').to_dict('index')

        my_hit = []
        for p in my_lineup:
            slots = set(getattr(p, 'eligibleSlots', []) or [])
            if not (slots & {'C','1B','2B','3B','SS','OF','DH','UTIL'}): continue
            nk = _norm(p.name)
            info = rh3_lkup.get(nk, {})
            ros = info.get('expected_total_fp_remaining') or 0
            my_hit.append({'name': p.name, 'ros': ros, 'slots': slots})
        my_hit.sort(key=lambda x: x['ros'])  # ascending — worst first

        fa_hit = []
        for fa in fas:
            nk = _norm(fa.name)
            if nk in rostered: continue
            slots = set(getattr(fa, 'eligibleSlots', []) or [])
            if not (slots & {'C','1B','2B','3B','SS','OF','DH','UTIL'}): continue
            info = rh3_lkup.get(nk, {})
            ros = info.get('expected_total_fp_remaining') or 0
            if ros < 100: continue
            fa_hit.append({'name': fa.name, 'ros': ros, 'slots': slots,
                            'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0)})
        fa_hit.sort(key=lambda x: -x['ros'])

        suggestions = []
        used_fa = set()
        for drop in my_hit[:5]:  # bottom 5 Ligers
            for fa in fa_hit:
                if fa['name'] in used_fa: continue
                # Slot compatibility: FA can play at least one of drop's slots
                if not (drop['slots'] & fa['slots']): continue
                gain = fa['ros'] - drop['ros']
                if gain < 20: continue
                suggestions.append({'drop': drop, 'add': fa, 'gain': gain})
                used_fa.add(fa['name'])
                break
        if not suggestions:
            return ('<h2>🔄 Drop / Pickup Suggestions</h2>'
                    '<p class="muted">No clear upgrades — your roster is well-set.</p>')
        out = ['<h2>🔄 Drop / Pickup Suggestions <small class="muted">(positions match, gain ≥ 20 RoS)</small></h2>',
               '<table><thead><tr><th>Drop</th><th>RoS</th><th>→ Add</th><th>%Own</th><th>RoS</th><th>Gain</th></tr></thead><tbody>']
        for s in suggestions:
            out.append(f'<tr><td class="neg">{h(s["drop"]["name"])}</td>'
                       f'<td>{s["drop"]["ros"]:.0f}</td>'
                       f'<td class="pos">{h(s["add"]["name"])}</td>'
                       f'<td>{s["add"]["pct_owned"]:.0f}%</td>'
                       f'<td>{s["add"]["ros"]:.0f}</td>'
                       f'<td><b class="pos">+{s["gain"]:.0f}</b></td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return f'<h2>🔄 Drop / Pickup Suggestions</h2><p class="muted">error: {h(str(e))}</p>'


def render_2start_gems(schedules_by_team=None, today=None, week_end=None):
    """Streamer targets ranked by next-start expected FP.

    Ranking:  baseline_per_start  ×  park_adj  ×  opp_adj
      - baseline:  rp3 per-start projection (validated model)
      - park_adj:  1 − 0.5 × (pf_wOBA − 1)  for the venue of the next start
      - opp_adj:   1 − 0.7 × (bat_index_recent − 1)  for the opposing offense
    Multiplier clipped to [0.6, 1.4]. Coefficients are heuristic (matched to
    SP-FP elasticity vs opp xwOBA ≈ −0.7 from the formula structure) — direction
    is validated, magnitude is conservative. Pitcher L/R splits intentionally
    excluded: YoY stability of pitcher split xwOBA = 0.05–0.09 (test B1, this
    session) — would add noise, not signal. Team-level offensive index and park
    factors ARE stable across years.
    """
    try:
        from plv_clone.league_state import LeagueState
        league = LeagueState()._get_league()
        rostered = set()
        for t in league.teams:
            for p in t.roster:
                rostered.add(_norm(p.name))
        rp3_path = OUT / 'xfp_rp3_projections_il_fixed.csv'
        if not rp3_path.exists():
            rp3_path = OUT / 'xfp_rp3_projections.csv'
        rp3 = pd.read_csv(rp3_path).drop_duplicates('player_name')
        rp3['nk'] = rp3['player_name'].map(_norm)

        # Validated multipliers
        pf_path = CACHE / 'park_factors_2018_2026.csv'
        ts_path = CACHE / 'team_strength_2026.csv'
        pf_map = {}
        if pf_path.exists():
            pf_df = pd.read_csv(pf_path)
            pf_cur = pf_df[pf_df['year'] == pf_df['year'].max()]
            pf_map = dict(zip(pf_cur['team_abbr'].str.upper(), pf_cur['pf_wOBA']))
        ts_map_local = {}
        if ts_path.exists():
            ts_df = pd.read_csv(ts_path)
            ts_map_local = {row['team'].upper():
                            (row['bat_index_recent'] if pd.notna(row.get('bat_index_recent'))
                             else row.get('bat_index', 1.0))
                            for _, row in ts_df.iterrows()}

        # Collect candidate FAs with baseline projection
        candidates = []
        fas = league.free_agents(size=2000)  # full pool — avoid silent truncation
        for fa in fas:
            if getattr(fa, 'position', '') != 'SP':
                continue
            nk = _norm(fa.name)
            if nk in rostered:
                continue
            info = rp3[rp3['nk'] == nk]
            if info.empty:
                continue
            per_start = (info.iloc[0].get('xfp_rp3_per_start_sched')
                         or info.iloc[0].get('xfp_rp3_per_start') or 0)
            if per_start < 9:
                continue
            candidates.append({
                'name': fa.name,
                'team': (getattr(fa, 'proTeam', '?') or '?').upper(),
                'per_start': float(per_start),
                'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0),
            })

        if not candidates:
            return '<h2>💎 Streamer Targets</h2><p class="muted">No FA SPs above baseline.</p>'

        # Resolve next start for each candidate
        next_start_by_name = {}
        if schedules_by_team and today and week_end:
            mlbam_by_name = {}
            for c in candidates:
                pid = _resolve_mlbam_via_api(c['name'])
                if pid:
                    mlbam_by_name[c['name']] = int(pid)
            if mlbam_by_name:
                starts = build_sp_starts_by_pitcher(
                    set(mlbam_by_name.values()), schedules_by_team, today, week_end)
                for nm, pid in mlbam_by_name.items():
                    games = starts.get(pid, [])
                    if games:
                        next_start_by_name[nm] = games[0]  # already sorted by date

        # Rank by adjusted expected FP
        for c in candidates:
            ns = next_start_by_name.get(c['name'])
            if ns:
                opp = (ns.get('opp_team') or '').upper()
                is_home = bool(ns.get('is_home'))
                venue = c['team'] if is_home else opp
                pf_wOBA = pf_map.get(venue, 1.0)
                opp_idx = ts_map_local.get(opp, 1.0)
                mult = (1 - 0.5 * (pf_wOBA - 1)) * (1 - 0.7 * (opp_idx - 1))
                mult = max(0.6, min(1.4, mult))
                c['opp'] = opp
                c['is_home'] = is_home
                c['pf_wOBA'] = pf_wOBA
                c['opp_idx'] = opp_idx
                c['adj_mult'] = mult
                c['exp_fp'] = c['per_start'] * mult
                c['date'] = ns.get('date', '')
                c['confirmed'] = ns.get('confirmed', False)
            else:
                c['opp'] = '—'
                c['is_home'] = None
                c['pf_wOBA'] = 1.0
                c['opp_idx'] = 1.0
                c['adj_mult'] = 1.0
                c['exp_fp'] = c['per_start']
                c['date'] = ''
                c['confirmed'] = False

        candidates.sort(key=lambda x: -x['exp_fp'])

        out = [
            '<h2>💎 Top Streamer Targets <small class="muted">'
            '(next-start expected FP — baseline × park × opponent)</small></h2>',
            '<p class="notes">'
            'Ranking = rp3 baseline × park factor × opponent batting index. '
            'Pitcher L/R splits excluded (failed YoY stability validation, B1). '
            'Coefficients heuristic; direction validated.'
            '</p>',
            '<table><thead><tr>'
            '<th>Pitcher</th><th>Team</th><th>%Own</th>'
            '<th>Next vs</th><th>Date</th>'
            '<th>Park</th><th>Opp idx</th>'
            '<th>Baseline</th><th>Exp FP</th>'
            '</tr></thead><tbody>',
        ]
        for g in candidates[:12]:
            opp_disp = g['opp']
            if g['opp'] != '—':
                arrow = 'vs' if g.get('is_home') else '@'
                opp_disp = f"{arrow} {g['opp']}"
                if not g['confirmed']:
                    opp_disp += ' <small class="muted">(pred)</small>'
            adj_pct = (g['adj_mult'] - 1) * 100
            adj_class = 'pos' if adj_pct >= 1 else ('neg' if adj_pct <= -1 else 'muted')
            out.append(
                f'<tr><td>{h(g["name"])}</td>'
                f'<td>{h(g["team"])}</td>'
                f'<td>{g["pct_owned"]:.0f}%</td>'
                f'<td>{opp_disp}</td>'
                f'<td>{h(g["date"])}</td>'
                f'<td>{g["pf_wOBA"]:.3f}</td>'
                f'<td>{g["opp_idx"]:.3f}</td>'
                f'<td>{g["per_start"]:.2f}</td>'
                f'<td><b>{g["exp_fp"]:.2f}</b> '
                f'<small class="{adj_class}">({adj_pct:+.0f}%)</small></td>'
                f'</tr>'
            )
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return f'<h2>💎 Streamer Targets</h2><p class="muted">error: {h(str(e))}</p>'


def render_cap_status(my_proj):
    """Show SP-start cap utilization for the week, split confirmed vs predicted."""
    n_confirmed = 0
    n_predicted = 0
    for proj in my_proj.values():
        for b in proj.get('breakdown', []):
            if b.get('type') == 'start':
                if b.get('confirmed', True):
                    n_confirmed += 1
                else:
                    n_predicted += 1
    n_starts = n_confirmed + n_predicted
    pred_note = (f' <span class="muted">(+{n_predicted} rotation-gap predicted)</span>'
                 if n_predicted else '')
    if n_starts >= 10:
        msg = (f'<p class="notes"><b>⚠ SP cap at maximum:</b> {n_confirmed} confirmed'
               f'{pred_note} · {n_starts}/10 starts this week. '
               f'Excess starts past 10 are zeroed in scoring.</p>')
    elif n_starts < 8:
        msg = (f'<p class="notes"><b>📉 Under SP cap:</b> {n_confirmed} confirmed'
               f'{pred_note} · only {n_starts}/10 starts. '
               f'Add a streamer to claim more of the 10-start/week cap.</p>')
    else:
        msg = (f'<p class="notes">✓ SP cap: <b>{n_confirmed} confirmed</b>'
               f'{pred_note} · <b>{n_starts}/10</b> total projected starts.</p>')
    return msg


def render_closer_tracker():
    """Show save-leaders by team with role status."""
    try:
        save_csv = OUT / 'save_handcuffs.csv'
        if not save_csv.exists():
            return '<h2>🔒 Closer Tracker</h2><p class="muted">save_handcuffs.csv not found</p>'
        df = pd.read_csv(save_csv)
        # take top SV-leader per team
        if 'team' in df.columns and 'role' in df.columns:
            closers = df.groupby('team').first().reset_index() if 'role_rank' not in df.columns else df[df['role_rank'] == 1]
        else:
            closers = df.head(15)
        out = ['<h2>🔒 Closer-of-Record Tracker</h2>',
               '<p class="notes">From save_handcuffs analysis. Cross-reference with closer_persistence (~83%).</p>',
               '<table><thead><tr><th>Team</th><th>Closer</th><th>SV (current)</th></tr></thead><tbody>']
        cols = closers.columns.tolist()
        for _, r in closers.head(15).iterrows():
            name_col = 'name' if 'name' in cols else ('player_name' if 'player_name' in cols else cols[0])
            sv_col = 'sv' if 'sv' in cols else ('sv_2026' if 'sv_2026' in cols else 'saves')
            team_col = 'team' if 'team' in cols else 'proTeam'
            try:
                out.append(f'<tr><td>{h(str(r.get(team_col, "?")))}</td>'
                           f'<td>{h(str(r.get(name_col, "?")))}</td>'
                           f'<td>{r.get(sv_col, "—")}</td></tr>')
            except Exception:
                continue
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return f'<h2>🔒 Closer Tracker</h2><p class="muted">error: {h(str(e))}</p>'


def render_snapshot_diff():
    """Show what changed since last generation."""
    history_path = OUT / 'predictions_history.csv'
    if not history_path.exists():
        return ''
    df = pd.read_csv(history_path)
    if len(df) < 2:
        return ''
    df = df.tail(2)
    prev = df.iloc[0]
    curr = df.iloc[1]
    delta_my = curr['my_projected_total'] - prev['my_projected_total']
    delta_opp = curr['opp_projected_total'] - prev['opp_projected_total']
    delta_wp = (curr['win_probability'] - prev['win_probability']) * 100
    if abs(delta_my) < 0.5 and abs(delta_opp) < 0.5 and abs(delta_wp) < 0.5:
        return ('<p class="notes">📊 No meaningful change from previous snapshot.</p>')
    return (f'<p class="notes">📊 Since last snapshot: '
            f'Ligers projected <b class="{("pos" if delta_my >= 0 else "neg")}">{delta_my:+.1f}</b>, '
            f'Opp projected <b class="{("pos" if delta_opp <= 0 else "neg")}">{delta_opp:+.1f}</b>, '
            f'win prob <b class="{("pos" if delta_wp >= 0 else "neg")}">{delta_wp:+.1f} pp</b>.</p>')


def render_lineup_optimizer(lineup, projections, schedules_by_team, espn_to_mlb):
    """Find sub-optimal lineup placements: bench players projecting higher
       than active players at slots where they overlap.
       Returns HTML block + list of suggested swaps."""
    # Hitter slot eligibility mapping
    HITTER_SLOTS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF',
                     'DH', 'UTIL', 'MI', 'CI'}
    active_slots = {'C', '1B', '2B', '3B', 'SS', 'OF', 'MI', 'CI', 'UTIL'}

    # Build per-player view
    players = []
    for p in lineup:
        proj = projections.get(p.name, {})
        per_game = proj['fp'] / max(proj.get('units', 1), 1) if proj.get('units') else 0
        slot = p.lineupSlot
        if not slot: continue
        elig = set(p.eligibleSlots or [])
        is_hitter = bool(elig & HITTER_SLOTS)
        if not is_hitter: continue  # SP/RP optimization is more complex
        players.append({
            'name': p.name, 'slot': slot, 'elig': elig,
            'per_game': per_game, 'units': proj.get('units', 0),
            'is_active': slot in active_slots, 'is_bench': slot == 'BE',
            'is_il': slot in ('IL', 'INJURY_RESERVE'),
        })

    # Suggested swaps: for each bench (or low-active) player, find an active
    # player at any slot they could fill where bench > active by per-game.
    swaps = []
    bench = [p for p in players if p['is_bench'] and p['per_game'] > 0]
    active = [p for p in players if p['is_active']]
    for b in bench:
        # Could this bench player play at any of these active slots?
        for a in active:
            # Bench player must be eligible for active player's slot
            if a['slot'] not in b['elig']: continue
            # Also active player must have alternative (UTIL or other slot)
            # otherwise we'd just shift the lower projection elsewhere
            if b['per_game'] > a['per_game']:
                gain_per_game = b['per_game'] - a['per_game']
                weekly_gain = gain_per_game * max(b.get('units', 1), 1)
                swaps.append({
                    'bench_name': b['name'], 'bench_proj': b['per_game'],
                    'active_name': a['name'], 'active_proj': a['per_game'],
                    'slot': a['slot'], 'gain_per_game': gain_per_game,
                    'weekly_gain': weekly_gain,
                })
    # Sort by biggest gain. Filter duplicates (a bench player vs many actives).
    swaps.sort(key=lambda s: -s['weekly_gain'])
    seen_bench = set()
    seen_active = set()
    unique_swaps = []
    for s in swaps:
        if s['bench_name'] in seen_bench: continue
        if s['active_name'] in seen_active: continue
        seen_bench.add(s['bench_name']); seen_active.add(s['active_name'])
        unique_swaps.append(s)

    if not unique_swaps:
        return ('<h2>🎯 Lineup Optimizer</h2>'
                '<p class="muted">No obvious upgrades — current lineup looks well-set.</p>')

    out = ['<h2>🎯 Lineup Optimizer <small class="muted">— suggested swaps for next game day</small></h2>']
    out.append('<table><thead><tr>'
                '<th>Start (active → bench)</th><th>Current Proj</th>'
                '<th>Bench Better (bench → active)</th><th>Bench Proj</th>'
                '<th>Slot</th><th>Gain/wk</th></tr></thead><tbody>')
    for s in unique_swaps[:10]:
        out.append(
            f'<tr><td class="neg">{h(s["active_name"])} →BE</td>'
            f'<td>{s["active_proj"]:.2f}/g</td>'
            f'<td class="pos">{h(s["bench_name"])} →{h(s["slot"])}</td>'
            f'<td>{s["bench_proj"]:.2f}/g</td>'
            f'<td>{h(s["slot"])}</td>'
            f'<td><b class="pos">+{s["weekly_gain"]:.2f}</b></td></tr>')
    total_gain = sum(s['weekly_gain'] for s in unique_swaps)
    out.append(f'</tbody></table>'
                f'<p class="notes">Total weekly FP left on the bench: '
                f'<b class="pos">+{total_gain:.1f}</b> if all swaps executed. '
                f'Note: only obvious projection-based swaps shown; ESPN may auto-fill '
                f'optimal lineup if you set your lineup to "auto". Manual override only.</p>')
    return '\n'.join(out)


def render_accuracy_history():
    """Show prediction-vs-actual accuracy for past weeks. Returns HTML block."""
    history_path = OUT / 'predictions_history.csv'
    if not history_path.exists():
        return '<h2>📈 Prediction Accuracy</h2><p class="muted">No history yet — first snapshot saved today.</p>'
    df = pd.read_csv(history_path)
    if len(df) < 2:
        return (f'<h2>📈 Prediction Accuracy</h2>'
                f'<p class="muted">Tracking started — '
                f'{len(df)} snapshot{"s" if len(df) != 1 else ""} logged. '
                f'Accuracy chart populates as matchup periods complete.</p>')
    # Keep only one entry per (period, date)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    out = ['<h2>📈 Prediction Accuracy History</h2>',
           '<table><thead><tr><th>Period</th><th>Date</th><th>My WTD</th>'
           '<th>My Projected</th><th>Opp WTD</th><th>Opp Projected</th>'
           '<th>Win Prob</th></tr></thead><tbody>']
    for _, r in df.tail(20).iterrows():
        out.append(
            f'<tr><td>{int(r["period"])}</td><td>{r["date"].strftime("%m/%d")}</td>'
            f'<td>{r["my_wtd"]:.1f}</td><td><b>{r["my_projected_total"]:.1f}</b></td>'
            f'<td>{r["opp_wtd"]:.1f}</td><td><b>{r["opp_projected_total"]:.1f}</b></td>'
            f'<td>{r["win_probability"]*100:.1f}%</td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


def log_prediction(mu, my_total, opp_total, win_prob, today, model_version='baseline'):
    """Append current prediction to predictions_history.csv.

    `model_version` distinguishes which projection iteration produced this
    snapshot — 'baseline' (adjusters OFF, production) or 'MA_v1' (full
    adjuster chain). Shadow-logging writes both per build so we accumulate
    paired observations for backtest without flipping live.
    """
    history_path = OUT / 'predictions_history.csv'
    record = {
        'timestamp': datetime.now().isoformat(),
        'date': today.isoformat(),
        'period': mu['period'],
        'my_team': mu['mine'].team_name,
        'opp_team': mu['opp'].team_name,
        'my_wtd': round(mu['my_score'], 2),
        'my_projected_total': round(my_total, 2),
        'opp_wtd': round(mu['opp_score'], 2),
        'opp_projected_total': round(opp_total, 2),
        'win_probability': round(win_prob, 4),
        'model_version': model_version,
        # actuals backfilled post-period by fetch_closed_matchup_actuals.py
        'actual_my_final': pd.NA,
        'actual_opp_final': pd.NA,
    }
    if history_path.exists():
        df = pd.read_csv(history_path)
        # Ensure new schema columns exist (graceful migration for old rows)
        for c in ('model_version', 'actual_my_final', 'actual_opp_final'):
            if c not in df.columns: df[c] = pd.NA
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    else:
        df = pd.DataFrame([record])
    df.to_csv(history_path, index=False)
    print(f'  logged prediction ({model_version}) → predictions_history.csv ({len(df)} total entries)')


def win_probability(my_proj_total, opp_proj_total, my_sigma2, opp_sigma2):
    """P(my_team > opp) given normal-approx remaining FP distributions."""
    gap = my_proj_total - opp_proj_total
    sigma = math.sqrt(my_sigma2 + opp_sigma2)
    if sigma == 0: return 1.0 if gap > 0 else 0.0
    z = gap / sigma
    # standard normal CDF approximation
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def win_probability_bootstrap(my_proj, opp_proj, my_wtd, opp_wtd, n_trials=5000):
    """#11 — Monte Carlo win prob with right-skewed (lognormal) marginals per player.

    Each player's `fp` (mean) + `sigma2` (variance) are matched to a lognormal
    distribution; team total per trial = WTD + sum of player draws. Win prob is
    the fraction of trials where my_total > opp_total.

    Lognormal captures HR upside (right tail) which the normal-approx misses.
    For mean ≤ 0 (rare — bad SP projection) falls back to normal draws.
    """
    import numpy as np
    rng = np.random.default_rng(seed=42)

    def _player_draws(p):
        mu = p['fp']
        var = p['sigma2']
        if mu <= 0 or var <= 0:
            return rng.normal(mu, max(math.sqrt(max(var, 0)), 1e-6), n_trials)
        sig2 = math.log(1 + var / (mu * mu))
        lmu = math.log(mu) - sig2 / 2
        return rng.lognormal(lmu, math.sqrt(sig2), n_trials)

    my_trials = np.full(n_trials, my_wtd, dtype=float)
    for p in my_proj.values():
        my_trials = my_trials + _player_draws(p)
    opp_trials = np.full(n_trials, opp_wtd, dtype=float)
    for p in opp_proj.values():
        opp_trials = opp_trials + _player_draws(p)
    return float((my_trials > opp_trials).mean())


def render_team_table(label, lineup, wtd_score, projections, capped_fp=0):
    rows = []
    for p in lineup:
        proj = projections.get(p.name, {'fp': 0, 'units': 0, 'breakdown': [], 'badges': []})
        rows.append({
            'name': p.name, 'pos': p.position or '?',
            'wtd': p.points or 0,
            'rest': proj['fp'],
            'units': proj['units'],
            'total': (p.points or 0) + proj['fp'],
            'breakdown': proj['breakdown'],
            'badges': proj['badges'],
        })
    rows.sort(key=lambda r: -r['total'])
    total_rest = sum(r['rest'] for r in rows)
    total_proj = wtd_score + total_rest

    out = [f'<h2>{h(label)} '
           f'<span class="totals">WTD <b class="wtd">{wtd_score:.1f}</b> · '
           f'rest <b class="proj">{total_rest:.1f}</b>'
           f'{f" <small>(−{capped_fp:.1f} capped)</small>" if capped_fp > 0 else ""} · '
           f'total <b class="total">{total_proj:.1f}</b></span></h2>']
    out.append('<table class="player-table"><thead><tr>'
                '<th>Player</th><th>Pos</th><th>WTD</th>'
                '<th>Units</th><th>Rest</th><th>Total</th><th></th></tr></thead><tbody>')
    for r in rows:
        wtd_cls = 'pos' if r['wtd'] > 0 else ('neg' if r['wtd'] < 0 else 'zero')
        if r['pos'] == 'SP':
            unit_label = f'{int(r["units"])} start{"s" if r["units"] != 1 else ""}'
        elif r['pos'] in ('RP', 'P'):
            unit_label = f'~{r["units"]:.1f} app'
        else:
            unit_label = f'{int(r["units"])} games'
        if r['units'] == 0:
            unit_label = '—'
        badges = ' '.join(f'<span class="badge">{h(b)}</span>' for b in r['badges'])
        out.append(f'<tr><td data-label="Player">{h(r["name"])}{(" " + badges) if badges else ""}</td>'
                   f'<td data-label="Pos">{h(r["pos"])}</td>'
                   f'<td data-label="WTD" class="{wtd_cls}">{r["wtd"]:+.1f}</td>'
                   f'<td data-label="Units" class="muted">{unit_label}</td>'
                   f'<td data-label="Rest">{r["rest"]:+.1f}</td>'
                   f'<td data-label="Total"><b>{r["total"]:+.1f}</b></td><td></td></tr>')
        if r['breakdown']:
            for b in r['breakdown']:
                if b.get('type') == 'start':
                    cap_marker = ' <span class="capped">⚠ CAPPED</span>' if b.get('fp_capped') else ''
                    # Confirmed probable (✓) vs rotation-gap prediction (~)
                    conf_marker = ('✓' if b.get('confirmed', True) else
                                   '<span class="muted" title="rotation-gap prediction — not yet confirmed probable">~</span>')
                    txt = (f'{conf_marker} {b["date"][5:]} vs {b["opp"]} '
                           f'(opp bat {b["opp_idx"]:.2f}, ×{b["factor"]:.2f}, '
                           f'<b>{b.get("fp_original", b["fp"]):.1f} FP</b>){cap_marker}')
                    out.append(f'<tr class="breakdown"><td colspan="7">→ {txt}</td></tr>')
                elif b.get('type') == 'game':
                    opp_sp_s = ''
                    if b.get('opp_sp') and b.get('opp_sp') != '?':
                        opp_proj_s = f', {b["opp_sp_proj"]:.1f} FP/start' if b.get('opp_sp_proj') else ''
                        opp_sp_s = f' (vs {b["opp_sp"]}{opp_proj_s})'
                    txt = f'{b["date"][5:]} vs {b["opp"]}{opp_sp_s} · ×{b["factor"]:.2f} = {b["fp"]:.1f}'
                    out.append(f'<tr class="breakdown"><td colspan="7">→ {txt}</td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out), total_rest, total_proj


def main():
    # MA0-MA7 adjuster gating: default OFF for production builds.
    # Set ADJUSTERS_ON=1 environment variable OR pass --with-adjusters to enable.
    import os, argparse
    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument('--with-adjusters', action='store_true',
                          help='Enable MA0-MA7 accuracy adjuster chain (default OFF — pending validation)')
    _parser.add_argument('--bootstrap', action='store_true',
                          help='Use Monte Carlo (lognormal) win-prob instead of normal-approx CDF')
    _parser.add_argument('-h', '--help', action='store_true')
    _args, _ = _parser.parse_known_args()
    if _args.help:
        _parser.print_help(); return
    global _ADJUSTERS_ON, _MA2_HITTER_ON, _MA2_SP_ON
    _ADJUSTERS_ON = _args.with_adjusters or os.environ.get('ADJUSTERS_ON') == '1'
    _USE_BOOTSTRAP = _args.bootstrap or os.environ.get('WIN_PROB_BOOTSTRAP') == '1'
    # MA2 sub-toggles default to master flag (#6 — can be split independently
    # later via env vars if MAE shows one direction net-helps but the other doesn't)
    _MA2_HITTER_ON = _ADJUSTERS_ON and os.environ.get('MA2_HITTER_OFF') != '1'
    _MA2_SP_ON = _ADJUSTERS_ON and os.environ.get('MA2_SP_OFF') != '1'

    print('Loading matchup + projections...')
    mu = get_matchup()
    rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map = load_projections()
    # MA2-MA7: load adjuster data into module-level caches (only if enabled).
    global _HITTER_FORM, _SP_FORM, _LINEUP, _PARK, _PSPLIT, _BAT_SIDE, _IL_RETURNS, _CALIB
    if _ADJUSTERS_ON:
        _HITTER_FORM, _SP_FORM = load_recent_form_maps()  # SP form only used now
        _LINEUP = load_lineup_map()
        _PARK = load_park_factors()                       # stub returns {}
        _PSPLIT = load_pitcher_splits()
        _BAT_SIDE = load_bat_side_map()
        _IL_RETURNS = load_il_returns(mu)                 # #10
        _CALIB = load_calibration_scalar()
        print(f'  ⚙ ADJUSTERS ON  MA2_hitter={_MA2_HITTER_ON} MA2_sp={_MA2_SP_ON}  '
              f'caches: sp_form={len(_SP_FORM)} lineup={len(_LINEUP)} '
              f'pitcher_splits={len(_PSPLIT)} bat_side={len(_BAT_SIDE)} '
              f'il_returns={len(_IL_RETURNS)} calib={_CALIB:.3f}')
    else:
        _HITTER_FORM, _SP_FORM, _LINEUP, _PARK, _PSPLIT, _BAT_SIDE, _IL_RETURNS, _CALIB = (
            {}, {}, {}, {}, {}, {}, {}, 1.0)
        print(f'  ⚙ ADJUSTERS OFF (baseline xfp model only — pending backtest validation)')
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    days_remaining_in_week = (week_end - today).days

    print(f'  matchup period: {mu["period"]}')
    print(f'  week: {week_start} → {week_end} (today: {today})')
    print(f'  Ligers WTD: {mu["my_score"]:.1f}  |  Opp WTD: {mu["opp_score"]:.1f}')

    # Fetch schedules — primary source is ESPN's proGamesByScoringPeriod
    # (same data ESPN uses in their UI → our team-game-day counts match theirs).
    # Falls back to MLB Stats API if ESPN schedule returns empty.
    print(f'  fetching schedules from ESPN proGamesByScoringPeriod...')
    schedules_by_team = fetch_espn_week_schedule(mu['league_obj'], week_start, week_end)
    if not schedules_by_team:
        # Fallback: MLB Stats API team schedule
        all_teams = set()
        for p in mu['my_lineup'] + mu['opp_lineup']:
            t = (p.proTeam or '').upper()
            if t: all_teams.add(t)
        team_ids = {ESPN_TO_MLB_TEAM[t] for t in all_teams if t in ESPN_TO_MLB_TEAM}
        print(f'  ⚠ ESPN schedule empty — falling back to MLB Stats API ({len(team_ids)} teams)')
        schedules_by_team = fetch_schedules_by_team(
            team_ids, today.isoformat(), week_end.isoformat())
    else:
        n_teams = len(schedules_by_team)
        n_games = sum(len(v) for v in schedules_by_team.values())
        print(f'  ESPN schedule: {n_teams} teams, {n_games} game-slots this week')

    # Resolve mlbam for all rostered SPs; precompute their full SP-start lists
    # (confirmed probables + rotation-gap predictions) via
    # plv_clone.mlb_stats.fetch_week_probables.
    sp_pitcher_ids = set()
    for p in mu['my_lineup'] + mu['opp_lineup']:
        if (p.position or '') != 'SP':
            continue
        inj_p = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
        if inj_p in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL',
                     'INJURY_RESERVE', 'OUT', 'DAY_TO_DAY'):
            continue
        pid_sp = player_mlbam_lookup(p.name) or _resolve_mlbam_via_api(p.name)
        if pid_sp:
            sp_pitcher_ids.add(int(pid_sp))
    print(f'  resolving rotation for {len(sp_pitcher_ids)} healthy SPs...')
    sp_starts_by_pitcher = build_sp_starts_by_pitcher(
        sp_pitcher_ids, schedules_by_team, today, week_end)

    # Project each player
    print('  projecting (schedule + opp-SP + role + cap aware)...')
    my_proj = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                         rh3_map, rp3_map, rp3_by_mlbam,
                                         rprs2_map, ts_map, today, week_end)
               for p in mu['my_lineup']}
    opp_proj = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                          rh3_map, rp3_map, rp3_by_mlbam,
                                          rprs2_map, ts_map, today, week_end)
                for p in mu['opp_lineup']}

    # Apply SP cap (10 starts/week)
    my_capped = apply_sp_cap(my_proj)
    opp_capped = apply_sp_cap(opp_proj)
    if my_capped > 0: print(f'  Ligers SP cap removed {my_capped:.1f} FP')
    if opp_capped > 0: print(f'  Opp SP cap removed {opp_capped:.1f} FP')

    # Summarise confirmed vs rotation-gap predicted starts
    my_conf = sum(1 for p in my_proj.values()
                  for b in p.get('breakdown', [])
                  if b.get('type') == 'start' and b.get('confirmed', True))
    my_pred = sum(1 for p in my_proj.values()
                  for b in p.get('breakdown', [])
                  if b.get('type') == 'start' and not b.get('confirmed', True))
    my_total_starts = my_conf + my_pred
    pred_note = f' + {my_pred} rotation-gap predicted' if my_pred else ''
    print(f'  SP starts: {my_conf} confirmed{pred_note} = {my_total_starts}/10 cap')

    # Team totals + variance
    my_rest = sum(p['fp'] for p in my_proj.values())
    opp_rest = sum(p['fp'] for p in opp_proj.values())
    my_total = mu['my_score'] + my_rest
    opp_total = mu['opp_score'] + opp_rest
    my_sigma2 = sum(p['sigma2'] for p in my_proj.values())
    opp_sigma2 = sum(p['sigma2'] for p in opp_proj.values())
    if _USE_BOOTSTRAP:
        win_prob = win_probability_bootstrap(my_proj, opp_proj,
                                              mu['my_score'], mu['opp_score'])
        wp_method = 'bootstrap'
    else:
        win_prob = win_probability(my_total, opp_total, my_sigma2, opp_sigma2)
        wp_method = 'normal'

    print(f'\n  Ligers: WTD {mu["my_score"]:.1f} + rest {my_rest:.1f} = {my_total:.1f} '
          f'(σ²={my_sigma2:.0f})')
    print(f'  Opp:    WTD {mu["opp_score"]:.1f} + rest {opp_rest:.1f} = {opp_total:.1f} '
          f'(σ²={opp_sigma2:.0f})')
    print(f'  Win probability ({wp_method}): {win_prob*100:.1f}%')

    my_block, _, _ = render_team_table(mu['mine'].team_name, mu['my_lineup'],
                                          mu['my_score'], my_proj, my_capped)
    opp_block, _, _ = render_team_table(mu['opp'].team_name, mu['opp_lineup'],
                                           mu['opp_score'], opp_proj, opp_capped)

    # ---- LINEUP OPTIMIZER ----
    opt_block = render_lineup_optimizer(mu['my_lineup'], my_proj, schedules_by_team,
                                          ESPN_TO_MLB_TEAM)

    # ---- LOG PREDICTION HISTORY ----
    live_version = 'MA_v1' if _ADJUSTERS_ON else 'baseline'
    log_prediction(mu, my_total, opp_total, win_prob, today, model_version=live_version)

    # ---- SHADOW LOG: also write the OTHER version so we accumulate paired data
    # without flipping live behavior. Off-build → shadow-logs MA_v1; on-build → shadow-logs baseline.
    try:
        shadow_on = not _ADJUSTERS_ON
        shadow_version = 'MA_v1' if shadow_on else 'baseline'
        # Toggle module state for the shadow projection
        prior_state = (_ADJUSTERS_ON, _HITTER_FORM, _SP_FORM, _LINEUP, _PARK, _PSPLIT, _BAT_SIDE, _CALIB)
        globals()['_ADJUSTERS_ON'] = shadow_on
        if shadow_on:
            globals()['_HITTER_FORM'], globals()['_SP_FORM'] = load_recent_form_maps()
            globals()['_LINEUP'] = load_lineup_map()
            globals()['_PARK'] = load_park_factors()
            globals()['_PSPLIT'] = load_pitcher_splits()
            globals()['_BAT_SIDE'] = load_bat_side_map()
            globals()['_CALIB'] = load_calibration_scalar()
        else:
            (globals()['_HITTER_FORM'], globals()['_SP_FORM'], globals()['_LINEUP'],
             globals()['_PARK'], globals()['_PSPLIT'], globals()['_BAT_SIDE'],
             globals()['_CALIB']) = {}, {}, {}, {}, {}, {}, 1.0
        # Reproject under shadow state
        my_proj_s = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                              rh3_map, rp3_map, rp3_by_mlbam,
                                              rprs2_map, ts_map, today, week_end)
                     for p in mu['my_lineup']}
        opp_proj_s = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                                rh3_map, rp3_map, rp3_by_mlbam,
                                                rprs2_map, ts_map, today, week_end)
                      for p in mu['opp_lineup']}
        apply_sp_cap(my_proj_s); apply_sp_cap(opp_proj_s)
        my_total_s = mu['my_score'] + sum(p['fp'] for p in my_proj_s.values())
        opp_total_s = mu['opp_score'] + sum(p['fp'] for p in opp_proj_s.values())
        my_sig2_s = sum(p['sigma2'] for p in my_proj_s.values())
        opp_sig2_s = sum(p['sigma2'] for p in opp_proj_s.values())
        if _USE_BOOTSTRAP:
            wp_s = win_probability_bootstrap(my_proj_s, opp_proj_s,
                                              mu['my_score'], mu['opp_score'])
        else:
            wp_s = win_probability(my_total_s, opp_total_s, my_sig2_s, opp_sig2_s)
        log_prediction(mu, my_total_s, opp_total_s, wp_s, today, model_version=shadow_version)
        # Restore prior state for any downstream code (no live impact, but be tidy)
        (globals()['_ADJUSTERS_ON'], globals()['_HITTER_FORM'], globals()['_SP_FORM'],
         globals()['_LINEUP'], globals()['_PARK'], globals()['_PSPLIT'],
         globals()['_BAT_SIDE'], globals()['_CALIB']) = prior_state
    except Exception as e:
        print(f'  ⚠ shadow-log skipped: {e}')

    # ---- ACCURACY HISTORY VIEW ----
    accuracy_block = render_accuracy_history()

    # ---- ADDITIONAL ENHANCEMENT SECTIONS ----
    print('  building enhancement sections...')
    power_block = render_power_rankings()
    drop_pickup_block = render_drop_pickup_suggestions(mu['my_lineup'], rh3_map)
    streamer_block = render_2start_gems(schedules_by_team, today, week_end)
    cap_block = render_cap_status(my_proj)
    closer_block = render_closer_tracker()
    diff_block = render_snapshot_diff()
    ci_block = render_ci_bands(my_total, my_sigma2, opp_total, opp_sigma2)
    action_items_block = synthesize_action_items(my_proj, mu['my_lineup'],
                                                    schedules_by_team, win_prob)
    gauge_html = render_win_prob_gauge(win_prob)
    fire_block = render_days_of_fire(my_proj)
    playoff_block = render_playoff_simulation()
    pos_comp_block = render_position_competition(rh3_map)
    injury_block = render_injury_alerts(mu['my_lineup'])

    current_gap = mu['my_score'] - mu['opp_score']
    proj_gap = my_total - opp_total
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Win-prob bar color
    if win_prob >= 0.7: win_class = 'pos'
    elif win_prob >= 0.55: win_class = 'lean-pos'
    elif win_prob >= 0.45: win_class = 'toss'
    elif win_prob >= 0.30: win_class = 'lean-neg'
    else: win_class = 'neg'

    html = f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ligers Weekly Matchup</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Source+Serif+4:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #1a1815;
  --panel: #211e1a;
  --stripe: #1d1b17;
  --border: #34302a;
  --text: #f5f1ea;
  --dim: #a89e8a;
  --faint: #3a352e;
  --accent: #d97757;
  --pos: #7fb069;
  --neg: #c1666b;
  --warn: #d4a945;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{ font-family: 'Source Serif 4', 'Iowan Old Style', Georgia, serif;
       background: var(--bg); color: var(--text);
       font-size: 16px; line-height: 1.6; }}
.wrap {{ max-width: 1480px; margin: 0 auto; padding: 0 1.2em 4em 1.2em; }}
.mono {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; }}

header {{ border-bottom: 1px solid var(--border); padding: .9em 0;
         margin-bottom: 1em; position: sticky; top: 0;
         background: var(--bg); z-index: 100; }}
.header-row {{ display: flex; justify-content: space-between; align-items: baseline;
              flex-wrap: wrap; gap: 1.2em; }}
h1 {{ color: var(--accent); margin: 0; font-size: 2em; font-weight: 700;
     letter-spacing: .01em; line-height: 1.15;
     font-family: 'Source Serif 4', Georgia, serif; }}
h2 {{ color: var(--text); margin-top: 2em; font-size: 1.5em; font-weight: 600;
     border-bottom: 1px solid var(--border); padding-bottom: .35em;
     letter-spacing: .01em; line-height: 1.2;
     font-family: 'Source Serif 4', Georgia, serif; }}
h2 .totals {{ float: right; font-size: 0.6em; font-weight: 400; color: var(--dim);
             font-family: 'IBM Plex Mono', monospace; }}
h2 .totals b {{ color: var(--text); }}
h2 .totals .wtd {{ color: var(--pos); }}
h2 .totals .proj {{ color: var(--accent); }}
h2 .totals .total {{ color: var(--accent); font-size: 1.2em; }}

nav.topnav {{ display: flex; align-items: center; gap: 0;
             font-family: 'IBM Plex Mono', monospace;
             font-size: .72em; text-transform: uppercase; letter-spacing: .15em;
             margin-top: .4em; }}
nav.topnav a {{ color: var(--dim); text-decoration: none; padding: .35em .9em;
               border: 1px solid var(--border); border-right: 0;
               cursor: pointer; }}
nav.topnav a:first-child {{ border-radius: 3px 0 0 3px; }}
nav.topnav a:last-child  {{ border-radius: 0 3px 3px 0; border-right: 1px solid var(--border); }}
nav.topnav a:hover {{ color: var(--text); background: var(--panel); }}
nav.topnav a.current {{ color: var(--accent); background: var(--panel); border-color: var(--accent); }}

.scoreboard {{ background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
              padding: 1.5em; margin: 1em 0; }}
.score-grid {{ display: grid; grid-template-columns: 1fr 0.3fr 1fr; gap: 1em;
              text-align: center; align-items: center; }}
.score-team .name {{ color: var(--dim); font-size: .85em; margin-bottom: .3em;
                    font-family: 'IBM Plex Mono', monospace;
                    text-transform: uppercase; letter-spacing: .1em; }}
.score-team .wtd {{ font-size: 2.5em; font-weight: 700; color: var(--pos);
                    font-family: 'Source Serif 4', Georgia, serif;
                    font-variant-numeric: tabular-nums; }}
.score-team.opp .wtd {{ color: var(--neg); }}
.score-team .proj {{ font-size: .85em; color: var(--dim); margin-top: .3em;
                    font-family: 'IBM Plex Mono', monospace; }}
.score-team .total-final {{ font-size: 1.4em; color: var(--accent); font-weight: 700;
                            font-family: 'Source Serif 4', Georgia, serif; }}
.vs {{ font-size: 1.5em; color: var(--dim);
       font-family: 'IBM Plex Mono', monospace; }}
.win-bar {{ margin-top: 1.5em; padding-top: 1em; border-top: 1px solid var(--border); }}
.win-bar-label {{ text-align: center; margin-bottom: .5em; font-size: 1.1em;
                 font-family: 'IBM Plex Mono', monospace; }}
.win-bar-label .pct {{ font-weight: 700; font-size: 1.5em;
                       font-family: 'Source Serif 4', Georgia, serif; }}
.win-bar-label .pos {{ color: var(--pos); }}
.win-bar-label .lean-pos {{ color: var(--pos); opacity: .85; }}
.win-bar-label .toss {{ color: var(--warn); }}
.win-bar-label .lean-neg {{ color: var(--neg); opacity: .85; }}
.win-bar-label .neg {{ color: var(--neg); }}
.win-bar-track {{ height: 14px; background: var(--stripe); border-radius: 7px; overflow: hidden;
                 border: 1px solid var(--faint); }}
.win-bar-fill {{ height: 100%; background: linear-gradient(90deg, var(--pos), var(--warn) 50%, var(--neg)); }}
.gap-row {{ text-align: center; margin-top: 1em; font-size: 1em; color: var(--dim);
           font-family: 'IBM Plex Mono', monospace; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.2em;
        font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .87em; }}
th {{ background: var(--panel); padding: .65em .8em; text-align: left;
      border-bottom: 1px solid var(--border); border-top: 1px solid var(--border);
      font-weight: 600; color: var(--dim);
      text-transform: uppercase; font-size: .72em; letter-spacing: .12em;
      font-family: 'IBM Plex Mono', monospace; }}
td {{ padding: .55em .8em; border-bottom: 1px solid var(--faint);
      font-variant-numeric: tabular-nums; }}
tr.breakdown td {{ color: var(--dim); font-size: .8em; padding-left: 2em;
                    border-bottom: 1px dashed var(--faint); }}
tbody tr:nth-child(even) td {{ background: var(--stripe); }}
tbody tr:hover td {{ background: var(--panel); }}
.pos {{ color: var(--pos); }} .neg {{ color: var(--neg); }} .zero {{ color: var(--dim); }}
.muted {{ color: var(--dim); }}
.badge {{ display: inline-block; padding: 1px 7px; border-radius: 2px;
          font-size: .72em; font-family: 'IBM Plex Mono', monospace;
          background: rgba(217,119,87,0.18); color: var(--accent);
          letter-spacing: .08em; font-weight: 600; }}
.capped {{ display: inline-block; padding: 1px 7px; border-radius: 2px;
          font-size: .7em; font-family: 'IBM Plex Mono', monospace;
          background: rgba(193,102,107,0.22); color: var(--neg);
          letter-spacing: .08em; font-weight: 600; }}
.meta {{ color: var(--dim); font-size: .78em; margin-top: 2em; text-align: center;
         border-top: 1px solid var(--faint); padding-top: 1em;
         font-family: 'IBM Plex Mono', monospace; letter-spacing: .08em; }}
.notes {{ background: var(--panel); padding: .8em 1em; border-left: 3px solid var(--accent);
          border-radius: 3px;
          margin: 1em 0; font-size: .9em; color: var(--text);
          font-family: 'Source Serif 4', Georgia, serif; }}

/* ── Action items ── */
.action-items {{ background: var(--panel); border: 1px solid var(--border);
                  border-radius: 5px; padding: 1em 1.5em; margin: 1em 0; }}
.action-items h3 {{ margin: 0 0 .5em 0; color: var(--accent); font-size: 1.05em;
                    font-family: 'Source Serif 4', Georgia, serif; font-weight: 600; }}
.action-items ul {{ margin: 0; padding: 0; list-style: none; }}
.action-items li {{ padding: .5em .9em; margin: .3em 0; border-radius: 3px;
                     border-left: 3px solid var(--dim);
                     background: var(--stripe);
                     font-family: 'IBM Plex Mono', monospace; font-size: .85em; }}
.urgency-high {{ background: rgba(193,102,107,0.14); border-left-color: var(--neg); }}
.urgency-med  {{ background: rgba(212,169,69,0.14); border-left-color: var(--warn); }}
.urgency-low  {{ background: rgba(127,176,105,0.14); border-left-color: var(--pos); }}

/* ── Gauge ── */
.gauge-wrap {{ display: flex; justify-content: center; margin: .5em 0; }}
.gauge {{ width: 160px; height: 160px; border-radius: 50%; display: flex;
          align-items: center; justify-content: center; }}
.gauge-inner {{ width: 132px; height: 132px; background: var(--bg);
                 border-radius: 50%; display: flex; flex-direction: column;
                 align-items: center; justify-content: center;
                 border: 1px solid var(--border); }}
.gauge-pct {{ font-size: 2.2em; font-weight: 700; color: var(--text);
              font-family: 'Source Serif 4', Georgia, serif; }}
.gauge-label {{ font-size: .8em; color: var(--dim);
               font-family: 'IBM Plex Mono', monospace;
               text-transform: uppercase; letter-spacing: .1em; }}

/* ── Collapsibles ── */
details {{ margin-top: 1em; }}
details > summary {{ cursor: pointer; color: var(--text); font-size: 1em;
                      font-weight: 600; padding: .55em 0;
                      border-bottom: 1px solid var(--faint); user-select: none;
                      font-family: 'IBM Plex Mono', monospace;
                      text-transform: uppercase; letter-spacing: .12em; }}
details > summary:hover {{ color: var(--accent); }}
details[open] > summary {{ border-bottom: 1px solid var(--border); color: var(--accent); }}
details > summary::marker {{ color: var(--dim); }}

/* ── Heatmap cells ── */
.heat-0 {{ background: rgba(127,176,105,0.10); }}
.heat-1 {{ background: rgba(127,176,105,0.22); }}
.heat-2 {{ background: var(--pos); color: var(--bg); font-weight: 700; }}
.heat-3 {{ background: var(--pos); color: var(--bg); font-weight: 700; filter: brightness(1.1); }}
.heat-neg {{ background: rgba(193,102,107,0.22); color: var(--neg); }}

/* ── Section anchors ── */
section {{ scroll-margin-top: 100px; }}

/* ── Sortable hint ── */
th.sortable {{ cursor: pointer; user-select: none; }}
th.sortable:hover {{ background: var(--stripe); color: var(--accent); }}
th.sortable::after {{ content: ' ⇅'; opacity: 0.3; font-size: .8em; }}

/* ── TOC nav strip ── */
.toc {{ display: flex; gap: .4em; flex-wrap: wrap; padding: .55em 0; margin: 1em 0 1.2em 0;
        border-top: 1px solid var(--faint); border-bottom: 1px solid var(--faint);
        font-family: 'IBM Plex Mono', monospace;
        font-size: .78em; overflow-x: auto; }}
.toc a {{ color: var(--dim); text-decoration: none; padding: .25em .7em;
          border-radius: 3px; white-space: nowrap;
          text-transform: uppercase; letter-spacing: .08em; }}
.toc a:hover {{ color: var(--accent); background: var(--stripe); }}

/* ── Tablet (≤ 900px) ── */
@media (max-width: 900px) {{
  .wrap {{ padding: 0 .8em 4em .8em; }}
  h1 {{ font-size: 1.5em; }}
  h2 {{ font-size: 1.2em; margin-top: 1.2em; }}
  h2 .totals {{ display: block; float: none; margin-top: .3em; font-size: .85em; }}
  .scoreboard {{ padding: 1em; }}
  .score-team .wtd {{ font-size: 2em; }}
  .score-team .total-final {{ font-size: 1.2em; }}
  .scroll-x {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
}}

/* ── Phone (≤ 600px) — card-style player rows ── */
@media (max-width: 600px) {{
  .scoreboard {{ padding: .75em; margin: .5em 0; }}
  .score-grid {{ grid-template-columns: 1fr; gap: .5em; }}
  .vs {{ display: none; }}
  .score-team .wtd {{ font-size: 2.4em; line-height: 1; margin: .1em 0; }}
  .score-team .total-final {{ font-size: 1.3em; }}
  .score-team.opp {{ border-top: 1px solid var(--border); padding-top: .5em; }}
  .gauge {{ width: 130px; height: 130px; }}
  .gauge-inner {{ width: 108px; height: 108px; }}
  .gauge-pct {{ font-size: 1.8em; }}

  .toc {{ gap: .3em; font-size: .75em; padding: .4em 0; }}
  .toc a {{ padding: .35em .55em; }}

  .action-items {{ padding: .8em 1em; }}
  .action-items li {{ padding: .6em .8em; font-size: .9em; }}

  details > summary {{ padding: .8em 0; font-size: 1em; min-height: 44px; }}

  .player-table {{ font-size: .95em; }}
  .player-table thead {{ display: none; }}
  .player-table, .player-table tbody, .player-table tr, .player-table td {{
    display: block; width: 100%; }}
  .player-table tr {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
    padding: .6em .75em; margin-bottom: .5em; position: relative;
  }}
  .player-table tr:hover td {{ background: transparent; }}
  .player-table td {{
    border: none; padding: .15em 0;
    display: grid; grid-template-columns: 70px 1fr;
    align-items: baseline;
  }}
  .player-table td::before {{
    content: attr(data-label);
    color: var(--dim); font-size: .75em; text-transform: uppercase;
    letter-spacing: .08em; font-weight: 500;
  }}
  .player-table td[data-label="Player"] {{
    grid-template-columns: 1fr; padding-bottom: .35em;
    margin-bottom: .35em; border-bottom: 1px solid var(--faint);
    font-size: 1.05em; font-weight: 600; color: var(--text);
    font-family: 'Source Serif 4', Georgia, serif;
  }}
  .player-table td[data-label="Player"]::before {{ display: none; }}
  .player-table td[data-label="Total"] b {{ font-size: 1.15em; color: var(--accent); }}
  .player-table td:nth-last-child(1):empty {{ display: none; }}
  .player-table tr.breakdown {{
    background: transparent; border: none; padding: 0 0 0 1em;
    margin: -.4em 0 .4em 0; font-size: .82em; color: var(--dim);
  }}
  .player-table tr.breakdown td {{
    display: block; grid-template-columns: none; padding: .15em 0;
    border-bottom: none;
  }}
  .player-table tr.breakdown td::before {{ display: none; }}

  table:not(.player-table) {{
    display: block; overflow-x: auto; -webkit-overflow-scrolling: touch;
    font-size: .82em; max-width: 100%;
  }}
  table:not(.player-table) thead, table:not(.player-table) tbody,
  table:not(.player-table) tr {{ display: table; width: 100%; }}
  table:not(.player-table) tr {{ table-layout: auto; }}

  .win-bar-label .pct {{ font-size: 1.4em; }}
  .win-bar-track {{ height: 18px; }}

  h1 {{ font-size: 1.3em; }}
  h2 {{ font-size: 1.1em; }}

  header {{ padding: .6em 0; }}
  .header-row {{ gap: .6em; }}
  nav.topnav {{ font-size: .65em; }}
  nav.topnav a {{ padding: .3em .65em; }}
}}
</style>
</head><body>
<div class="wrap">
<header>
  <div class="header-row">
    <div>
      <h1>Ligers Weekly Matchup</h1>
      <nav class="topnav">
        <a href="live_dashboard.html">Live</a>
        <a class="current">Matchup</a>
        <a href="player_profiles.html">Profiles</a>
        <a href="index.html">XFP</a>
      </nav>
    </div>
  </div>
</header>

<div class="scoreboard">
  <div class="score-grid">
    <div class="score-team">
      <div class="name">{h(mu["mine"].team_name)}</div>
      <div class="wtd">{mu["my_score"]:.1f}</div>
      <div class="proj">+ <b>{my_rest:.1f}</b> projected rest</div>
      <div class="total-final">→ {my_total:.1f}</div>
    </div>
    <div class="vs">vs</div>
    <div class="score-team opp">
      <div class="name">{h(mu["opp"].team_name)}</div>
      <div class="wtd">{mu["opp_score"]:.1f}</div>
      <div class="proj">+ <b>{opp_rest:.1f}</b> projected rest</div>
      <div class="total-final">→ {opp_total:.1f}</div>
    </div>
  </div>

  {gauge_html}
  <div class="gap-row">
    Current gap: <b class="{"pos" if current_gap >= 0 else "neg"}">{current_gap:+.1f}</b>
    &nbsp;·&nbsp; Projected final gap: <b class="{"pos" if proj_gap >= 0 else "neg"}">{proj_gap:+.1f}</b>
  </div>
</div>

{action_items_block}

<div class="toc">
  <a href="#optimizer">🎯 Optimizer</a>
  <a href="#fire">🔥 Days of Fire</a>
  <a href="#drops">🔄 Drops/Pickups</a>
  <a href="#streamers">💎 Streamers</a>
  <a href="#myteam">My Roster</a>
  <a href="#opp">Opponent</a>
  <a href="#closers">🔒 Closers</a>
  <a href="#power">🏆 Power Rankings</a>
  <a href="#playoff">🎲 Playoff Sim</a>
  <a href="#position">📍 By Position</a>
  <a href="#accuracy">📈 Accuracy</a>
</div>

<div class="notes">
  📅 Period <b>{mu["period"]}</b> · {h(str(week_start))} → {h(str(week_end))} ·
  Today is {h(today.strftime("%A %b %d"))} · {days_remaining_in_week} days remaining after today.<br>
  📊 SPs: probable starts × opp-bat-index factor (BrownU 10-start/week cap applied).
  Hitters: per-game × opposing-SP-projection factor.
  RPs: role-based appearance rate (closer 55%, setup 40%, middle 30%).<br>
  🎲 Win probability: normal approximation from team variance estimates
  (σ/game: hitter {SIGMA_PER_HITTER_GAME}, SP start {SIGMA_PER_SP_START}, RP {SIGMA_PER_RP_GAME}).
</div>

{diff_block}
{ci_block}
{cap_block}

{injury_block}

<section id="optimizer"><details open>
<summary>🎯 Lineup Optimizer</summary>
{opt_block}
</details></section>

<section id="fire"><details open>
<summary>🔥 Days of Fire — per-day forecast</summary>
{fire_block}
</details></section>

<section id="drops"><details open>
<summary>🔄 Drop / Pickup Suggestions</summary>
{drop_pickup_block}
</details></section>

<section id="streamers"><details open>
<summary>💎 Streamer Targets</summary>
{streamer_block}
</details></section>

<section id="myteam"><details open>
<summary>My Roster — full breakdown</summary>
{my_block}
</details></section>

<section id="opp"><details>
<summary>Opponent — full breakdown</summary>
{opp_block}
</details></section>

<section id="closers"><details>
<summary>🔒 Closer-of-Record Tracker</summary>
{closer_block}
</details></section>

<section id="position"><details>
<summary>📍 Position Competition</summary>
{pos_comp_block}
</details></section>

<section id="power"><details>
<summary>🏆 League Power Rankings</summary>
{power_block}
</details></section>

<section id="playoff"><details>
<summary>🎲 Playoff Simulation</summary>
{playoff_block}
</details></section>

<section id="accuracy"><details>
<summary>📈 Prediction Accuracy History</summary>
{accuracy_block}
</details></section>

<p class="meta">Generated {h(now_s)} ·
<code>python scripts/xfp/build_matchup_dashboard.py</code>
<meta http-equiv="refresh" content="300">
</p>
</div>

<script>
// Click-to-sort tables (mark every <th> with class="sortable" via JS)
document.querySelectorAll('table').forEach(table => {{
  const headers = table.querySelectorAll('thead th');
  headers.forEach((th, idx) => {{
    th.classList.add('sortable');
    th.addEventListener('click', () => {{
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr')).filter(r => !r.classList.contains('breakdown'));
      const dir = th.dataset.sortDir === 'asc' ? 'desc' : 'asc';
      th.dataset.sortDir = dir;
      rows.sort((a, b) => {{
        const av = a.children[idx]?.innerText.trim() || '';
        const bv = b.children[idx]?.innerText.trim() || '';
        const an = parseFloat(av.replace(/[^\\d.+-]/g, ''));
        const bn = parseFloat(bv.replace(/[^\\d.+-]/g, ''));
        if (!isNaN(an) && !isNaN(bn)) {{
          return dir === 'asc' ? an - bn : bn - an;
        }}
        return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      }});
      // Re-insert in new order (keeping breakdown rows attached)
      tbody.innerHTML = '';
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});
}});

// Expand/collapse all controls
const expandBtn = document.createElement('button');
expandBtn.textContent = 'Expand all';
expandBtn.style.cssText = 'margin: 1em .5em; padding: .4em 1em; background: #211e1a; color: #f5f1ea; border: 1px solid #34302a; border-radius: 3px; cursor: pointer; font-family: \\'IBM Plex Mono\\', monospace; font-size: .8em; text-transform: uppercase; letter-spacing: .12em;';
expandBtn.onclick = () => document.querySelectorAll('details').forEach(d => d.open = true);
const collapseBtn = document.createElement('button');
collapseBtn.textContent = 'Collapse all';
collapseBtn.style.cssText = expandBtn.style.cssText;
collapseBtn.onclick = () => document.querySelectorAll('details').forEach(d => d.open = false);
document.querySelector('.toc').appendChild(expandBtn);
document.querySelector('.toc').appendChild(collapseBtn);
</script>
</body></html>
'''

    local = OUT / 'matchup.html'
    local.write_text(html, encoding='utf-8')
    print(f'  wrote {local}')
    if XFP_DOCS.exists():
        target = XFP_DOCS / 'matchup.html'
        target.write_text(html, encoding='utf-8')
        print(f'  wrote {target}')
        live_local = OUT / 'live_dashboard.html'
        if live_local.exists():
            shutil.copy(live_local, XFP_DOCS / 'live_dashboard.html')

    print(f'\n  Win probability: {win_prob*100:.1f}%')
    print(f'  Projected: {"WIN" if proj_gap >= 0 else "LOSE"} by {abs(proj_gap):.1f}')


if __name__ == '__main__':
    main()
