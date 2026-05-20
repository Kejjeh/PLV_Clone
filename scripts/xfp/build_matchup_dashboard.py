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
    from app import espn_connector as ec
    league = ec._get_league()
    period = league.currentMatchupPeriod
    for bs in league.box_scores(matchup_period=period):
        if bs.home_team and 'Ligers' in bs.home_team.team_name:
            return {'mine': bs.home_team, 'opp': bs.away_team,
                    'my_score': bs.home_score, 'opp_score': bs.away_score,
                    'my_lineup': bs.home_lineup, 'opp_lineup': bs.away_lineup,
                    'period': period}
        if bs.away_team and 'Ligers' in bs.away_team.team_name:
            return {'mine': bs.away_team, 'opp': bs.home_team,
                    'my_score': bs.away_score, 'opp_score': bs.home_score,
                    'my_lineup': bs.away_lineup, 'opp_lineup': bs.home_lineup,
                    'period': period}
    raise RuntimeError('No Ligers matchup found')


def load_projections():
    rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv').drop_duplicates('player_name')
    rh3['nk'] = rh3['player_name'].map(_norm)
    # MA1: include per-player sigma
    rh3_map = {r['nk']: {'per_game': r.get('xfp_rh3_per_game') or 0,
                          'per_pa': r.get('xfp_rh3_per_pa') or 0,
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
    """MA3 — per-batter modal lineup spot + PA/game from L21d appearances."""
    parq = CACHE / 'hitter_lineup_appearances_2026.parquet'
    try:
        df = pd.read_parquet(parq)
    except Exception:
        return {}
    today = date.today()
    cutoff = today - timedelta(days=21)
    df['game_date'] = pd.to_datetime(df['game_date']).dt.date
    df = df[df['game_date'] >= cutoff]
    out = {}
    for batter, sub in df.groupby('batter'):
        starts = sub[sub['started_game'] == True]
        if len(starts) < 3:
            continue
        modal_spot = int(starts['lineup_spot'].mode().iloc[0]) if len(starts['lineup_spot'].dropna()) else None
        pa_per_g = float(starts['pa_in_game'].mean()) if len(starts) else 4.0
        out[int(batter)] = {'modal_spot': modal_spot, 'pa_per_g': pa_per_g}
    return out


def lineup_spot_factor(modal_spot, pa_per_g):
    """Spot-only multiplier (PA is already in rh3 per_game baseline).

    Returns small RBI/R bonus per lineup spot. PA component intentionally
    omitted to avoid double-counting the baseline projection.
    """
    spot_bonus = 0.0
    if modal_spot in (1, 2): spot_bonus = 0.03   # leadoff/2-hole runs boost
    elif modal_spot == 3: spot_bonus = 0.02
    elif modal_spot == 4: spot_bonus = 0.03      # cleanup RBI boost
    elif modal_spot == 5: spot_bonus = 0.01
    elif modal_spot in (7, 8, 9): spot_bonus = -0.02
    return max(0.92, min(1.08, 1 + spot_bonus))


def load_park_factors():
    """MA4 — team_abbr → park_factor (1.0 = neutral)."""
    df = _safe_csv(CACHE / 'park_factors.csv')
    if df is None or 'team_abbr' not in df.columns: return {}
    df['team_abbr'] = df['team_abbr'].str.upper()
    return df.set_index('team_abbr')['park_factor'].to_dict()


def load_pitcher_splits():
    """MA5 — pitcher mlbam → {p_throws, xwoba_vs_L, xwoba_vs_R}."""
    df = _safe_csv(CACHE / 'pitcher_splits.csv')
    if df is None or 'pitcher' not in df.columns: return {}
    if 'year' in df.columns:
        df = df[df['year'] == df['year'].max()]
    return df.set_index('pitcher')[['p_throws', 'xwoba_vs_L', 'xwoba_vs_R']].to_dict('index')


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
_ADJUSTERS_ON = False    # CLI flag: --with-adjusters or env ADJUSTERS_ON=1
_HITTER_FORM = {}
_SP_FORM = {}
_LINEUP = {}
_PARK = {}
_PSPLIT = {}
_CALIB = 1.0
LEAGUE_AVG_XWOBA = 0.310  # for MA5 platoon normalization


def get_team_schedule(team_id, start_date, end_date):
    url = (f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId={team_id}'
           f'&startDate={start_date}&endDate={end_date}'
           f'&hydrate=probablePitcher,team')
    try:
        data = _fetch_json(url)
    except Exception:
        return []
    games = []
    for d_block in data.get('dates', []):
        for g in d_block.get('games', []):
            home = g['teams']['home']
            away = g['teams']['away']
            is_home = home['team']['id'] == team_id
            opp = away['team'] if is_home else home['team']
            home_p = home.get('probablePitcher', {}) or {}
            away_p = away.get('probablePitcher', {}) or {}
            games.append({
                'date': g['gameDate'][:10],
                'is_home': is_home,
                'opp_team': opp.get('abbreviation', '?').upper(),
                'my_probable_id': home_p.get('id') if is_home else away_p.get('id'),
                'my_probable_name': home_p.get('fullName') if is_home else away_p.get('fullName'),
                'opp_probable_id': away_p.get('id') if is_home else home_p.get('id'),
                'opp_probable_name': away_p.get('fullName') if is_home else home_p.get('fullName'),
            })
    return games


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
    Hits MLB Stats API people-search endpoint. Caches results in-process."""
    if name in cache: return cache[name]
    try:
        # URL-encode the name (handle spaces, accents)
        from urllib.parse import quote
        url = f'https://statsapi.mlb.com/api/v1/people/search?names={quote(name)}'
        data = _fetch_json(url)
        ppl = data.get('people', [])
        # Prefer pitchers; for hitters, accept first match
        for p in ppl[:5]:
            pos = p.get('primaryPosition', {}).get('abbreviation', '')
            if pos == 'P':
                cache[name] = p['id']
                return p['id']
        if ppl:
            cache[name] = ppl[0]['id']
            return ppl[0]['id']
    except Exception:
        pass
    cache[name] = None
    return None


def _predict_rotation_starts(mlbam, team_abbr, team_id, schedules_by_team,
                              confirmed_dates, today, week_end):
    """Predict non-confirmed SP starts from rotation gap.

    MLB Stats API only publishes probables 2-5 days ahead. For late-week
    starts that aren't yet confirmed, infer from the pitcher's gameLog
    rotation pattern (typical 5-day gap, clamped to 4-7).

    Returns list of game dicts compatible with confirmed_starts format,
    with `confirmed=False` flag.
    """
    if not mlbam: return []
    try:
        url = (f'https://statsapi.mlb.com/api/v1/people/{mlbam}/stats?'
               f'stats=gameLog&group=pitching&season={today.year}')
        data = _fetch_json(url)
    except Exception:
        return []
    stats_list = data.get('stats', []) or []
    splits = stats_list[0].get('splits', []) if stats_list else []
    starts = [s for s in splits if int(s.get('stat', {}).get('gamesStarted', '0')) > 0]
    if not starts: return []
    starts.sort(key=lambda s: s['date'], reverse=True)
    latest_actual = datetime.fromisoformat(starts[0]['date']).date()
    # Rotation gap from last two starts, clamped to [4, 7]
    if len(starts) >= 2:
        prev = datetime.fromisoformat(starts[1]['date']).date()
        gap = max(4, min(7, (latest_actual - prev).days))
    else:
        gap = 5

    # Anchor: max of (latest actual start, latest confirmed in window).
    # This prevents re-emitting a date that's already a confirmed start.
    confirmed_dt = [datetime.fromisoformat(d).date() for d in confirmed_dates]
    anchor = max([latest_actual] + confirmed_dt)

    # Predict next starts, find one matching team's schedule in window
    games = schedules_by_team.get(team_id, [])
    team_dates_in_window = {g['date']: g for g in games
                              if today.isoformat() <= g['date'] <= week_end.isoformat()}
    predicted = []
    nd = anchor
    for _ in range(3):  # up to 3 future rotation slots in window
        nd = nd + timedelta(days=gap)
        if nd > week_end: break
        nd_s = nd.isoformat()
        # Dedup near-matches (±1 day) with confirmed
        if any(abs((nd - cd).days) <= 1 for cd in confirmed_dt):
            continue
        # Find a team game on or within ±1 day of predicted date
        match_game = None
        for offset in (0, 1, -1):
            d_try = (nd + timedelta(days=offset)).isoformat()
            if d_try in team_dates_in_window and today.isoformat() <= d_try <= week_end.isoformat():
                match_game = team_dates_in_window[d_try]
                break
        if match_game:
            predicted.append({
                'date': match_game['date'],
                'opp_team': match_game['opp_team'],
                'is_home': match_game['is_home'],
                'my_probable_id': mlbam,
                'my_probable_name': '(predicted)',
                'opp_probable_id': match_game.get('opp_probable_id'),
                'opp_probable_name': match_game.get('opp_probable_name'),
                'confirmed': False,
            })
    return predicted


def project_player(player, schedules_by_team, rh3_map, rp3_map, rp3_by_mlbam,
                     rprs2_map, ts_map, today, week_end):
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

    # MA6 — IL-window pro-rate: for non-SP IL'd players returning mid-window.
    # GATED on _ADJUSTERS_ON. When OFF, IL'd hitters/RPs keep existing behavior
    # (zero projection until they return).
    il_factor = 1.0
    inj = (getattr(player, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    if _ADJUSTERS_ON and inj in ('TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'INJURY_RESERVE', 'OUT'):
        rd_str = getattr(player, 'returnDate', None) or None
        if rd_str:
            try:
                rd = date.fromisoformat(str(rd_str)[:10])
                if rd <= week_end:
                    days_avail = max(0, (week_end - max(rd, today)).days + 1)
                    days_total = max(1, (week_end - today).days + 1)
                    il_factor = days_avail / days_total
                else:
                    return out  # returns after window — zero
            except Exception:
                pass

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

        # Confirmed probables for this pitcher in window. Guard against
        # None==None false-positive (TBD probables) by requiring non-None.
        confirmed_starts = [g for g in rem
                              if g.get('my_probable_id') is not None
                              and g.get('my_probable_id') == mlbam]
        # Rotation-gap prediction for late-week games where MLB hasn't posted probables
        confirmed_dates = {g['date'] for g in confirmed_starts}
        predicted_starts = _predict_rotation_starts(mlbam, team, mlb_id,
                                                     schedules_by_team,
                                                     confirmed_dates, today, week_end)
        starts = confirmed_starts + predicted_starts

        rp_info = rp3_map.get(nk, {})
        per_start_base = rp_info.get('per_start') or 0
        if not per_start_base or not starts: return out
        if len(starts) >= 2:
            out['badges'].append('🔥 2-START')

        # MA2: recent-form factor (rolling 21d/season) — keyed on MLBAM
        recent_factor = _SP_FORM.get(mlbam, 1.0)

        total = 0.0
        for s in starts:
            opp_idx = ts_map.get(s['opp_team'], {}).get('bat_index') or 1.0
            opp_factor = max(0.80, min(1.20, 1.0 / opp_idx))
            # MA4: park factor inverse for SP (hitter-friendly park = harder for SP)
            park_f_raw = _PARK.get(s['opp_team'] if not s.get('is_home') else team, 1.0)
            park_factor = max(0.85, min(1.15, 1.0 / park_f_raw))
            # MA7: residual calibration scalar (final pass)
            fp = per_start_base * opp_factor * recent_factor * park_factor * _CALIB
            total += fp
            out['breakdown'].append({'date': s['date'], 'opp': s['opp_team'],
                                       'opp_idx': opp_idx, 'factor': opp_factor,
                                       'recent_factor': recent_factor,
                                       'park_factor': park_factor,
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
        # MA2: recent-form factor — keyed on MLBAM
        recent_factor = _HITTER_FORM.get(batter_mlbam, 1.0) if batter_mlbam else 1.0
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

            # MA4: park factor for game's host park
            host = team if g.get('is_home') else g['opp_team']
            park_factor = max(0.85, min(1.15, _PARK.get(host, 1.0)))

            # MA5: platoon factor (pitcher splits)
            # bat_side from player.stats.batsHandedness when available; default unknown
            bat_side = getattr(player, 'batting_hand', None) or getattr(player, 'batsHand', None)
            platoon_factor = 1.0
            if opp_sp_id and opp_sp_id in _PSPLIT and bat_side in ('L', 'R'):
                ps = _PSPLIT[opp_sp_id]
                opp_xwoba = ps.get(f'xwoba_vs_{bat_side}')
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

    # Cap status
    n_starts = sum(1 for proj in my_proj.values()
                    for b in proj.get('breakdown', []) if b.get('type') == 'start')
    if n_starts < 7:
        items.append({'urgency': 'med', 'icon': '📉',
                       'text': f'Only {n_starts} probable starts this week — add a streamer to hit the 10-start cap'})

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
    # Color: green if >70, yellow 50-70, red <50
    if pct >= 70: color = '#3fb950'
    elif pct >= 55: color = '#5fa650'
    elif pct >= 45: color = '#d29922'
    elif pct >= 30: color = '#db6d28'
    else: color = '#f85149'

    return f'''<div class="gauge-wrap">
  <div class="gauge" style="background: conic-gradient({color} 0% {pct}%, #21262d {pct}% 100%);">
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
        from app import espn_connector as ec
        league = ec._get_league()
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
        from app import espn_connector as ec
        league = ec._get_league()
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
        from app import espn_connector as ec
        league = ec._get_league()
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


def render_2start_gems():
    """League-wide 2-start SP gems available on waivers."""
    try:
        from app import espn_connector as ec
        league = ec._get_league()
        rostered = set()
        for t in league.teams:
            for p in t.roster:
                rostered.add(_norm(p.name))
        rp3_path = OUT / 'xfp_rp3_projections_il_fixed.csv'
        if not rp3_path.exists():
            rp3_path = OUT / 'xfp_rp3_projections.csv'
        rp3 = pd.read_csv(rp3_path).drop_duplicates('player_name')
        rp3['nk'] = rp3['player_name'].map(_norm)

        # NOTE: For full 2-start detection we'd need to fetch every team's
        # probable pitchers this week. For dashboard speed, surface top-20 FA SPs
        # by per_start_sched as candidate streamer/2-start targets.
        fas = league.free_agents(size=300)
        gems = []
        for fa in fas:
            if getattr(fa, 'position', '') != 'SP': continue
            nk = _norm(fa.name)
            if nk in rostered: continue
            info = rp3[rp3['nk'] == nk]
            if info.empty: continue
            per_start = info.iloc[0].get('xfp_rp3_per_start_sched') or info.iloc[0].get('xfp_rp3_per_start') or 0
            if per_start < 9: continue
            gems.append({'name': fa.name, 'team': getattr(fa, 'proTeam', '?'),
                          'per_start': per_start,
                          'pct_owned': float(getattr(fa, 'percent_owned', 0) or 0)})
        gems.sort(key=lambda g: -g['per_start'])
        if not gems:
            return '<h2>💎 Streamer / 2-Start Targets</h2><p class="muted">No standouts in FA pool.</p>'
        out = ['<h2>💎 Top Streamer Targets <small class="muted">(FAs by per-start FP projection)</small></h2>',
               '<table><thead><tr><th>Pitcher</th><th>Team</th><th>%Own</th><th>per_GS</th></tr></thead><tbody>']
        for g in gems[:10]:
            out.append(f'<tr><td>{h(g["name"])}</td><td>{h(g["team"])}</td>'
                       f'<td>{g["pct_owned"]:.0f}%</td>'
                       f'<td><b>{g["per_start"]:.2f}</b></td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)
    except Exception as e:
        return f'<h2>💎 Streamer Targets</h2><p class="muted">error: {h(str(e))}</p>'


def render_cap_status(my_proj):
    """Show SP-start cap utilization for the week."""
    n_starts = 0
    for proj in my_proj.values():
        for b in proj.get('breakdown', []):
            if b.get('type') == 'start':
                n_starts += 1
    msg = ''
    if n_starts >= 10:
        msg = (f'<p class="notes"><b>⚠ SP cap at maximum:</b> {n_starts} probable starts this week. '
               f'Excess starts past 10 are zeroed in scoring.</p>')
    elif n_starts < 8:
        msg = (f'<p class="notes"><b>📉 Under SP cap:</b> only {n_starts} probable starts. '
               f'Add a streamer to claim more of the 10-start/week cap.</p>')
    else:
        msg = f'<p class="notes">✓ SP cap usage: <b>{n_starts}/10</b> probable starts.</p>'
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


def log_prediction(mu, my_total, opp_total, win_prob, today):
    """Append current prediction to predictions_history.csv for accuracy tracking."""
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
    }
    if history_path.exists():
        df = pd.read_csv(history_path)
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    else:
        df = pd.DataFrame([record])
    df.to_csv(history_path, index=False)
    print(f'  logged prediction → predictions_history.csv ({len(df)} total entries)')


def win_probability(my_proj_total, opp_proj_total, my_sigma2, opp_sigma2):
    """P(my_team > opp) given normal-approx remaining FP distributions."""
    gap = my_proj_total - opp_proj_total
    sigma = math.sqrt(my_sigma2 + opp_sigma2)
    if sigma == 0: return 1.0 if gap > 0 else 0.0
    z = gap / sigma
    # standard normal CDF approximation
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


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
                    opp_sp = ''
                    txt = (f'{b["date"][5:]} vs {b["opp"]} '
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
    _parser.add_argument('-h', '--help', action='store_true')
    _args, _ = _parser.parse_known_args()
    if _args.help:
        _parser.print_help(); return
    global _ADJUSTERS_ON
    _ADJUSTERS_ON = _args.with_adjusters or os.environ.get('ADJUSTERS_ON') == '1'

    print('Loading matchup + projections...')
    mu = get_matchup()
    rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map = load_projections()
    # MA2-MA7: load adjuster data into module-level caches (only if enabled).
    global _HITTER_FORM, _SP_FORM, _LINEUP, _PARK, _PSPLIT, _CALIB
    if _ADJUSTERS_ON:
        _HITTER_FORM, _SP_FORM = load_recent_form_maps()
        _LINEUP = load_lineup_map()
        _PARK = load_park_factors()
        _PSPLIT = load_pitcher_splits()
        _CALIB = load_calibration_scalar()
        print(f'  ⚙ ADJUSTERS ON  caches: hitter_form={len(_HITTER_FORM)} sp_form={len(_SP_FORM)} '
              f'lineup={len(_LINEUP)} park={len(_PARK)} pitcher_splits={len(_PSPLIT)} calib={_CALIB:.3f}')
    else:
        _HITTER_FORM, _SP_FORM, _LINEUP, _PARK, _PSPLIT, _CALIB = {}, {}, {}, {}, {}, 1.0
        print(f'  ⚙ ADJUSTERS OFF (baseline xfp model only — pending backtest validation)')
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    days_remaining_in_week = (week_end - today).days

    print(f'  matchup period: {mu["period"]}')
    print(f'  week: {week_start} → {week_end} (today: {today})')
    print(f'  Ligers WTD: {mu["my_score"]:.1f}  |  Opp WTD: {mu["opp_score"]:.1f}')

    # Fetch schedules
    all_teams = set()
    for p in mu['my_lineup'] + mu['opp_lineup']:
        t = (p.proTeam or '').upper()
        if t: all_teams.add(t)
    print(f'  fetching schedules for {len(all_teams)} teams...')
    schedules_by_team = {}
    for t in all_teams:
        mlb_id = ESPN_TO_MLB_TEAM.get(t)
        if mlb_id is None: continue
        schedules_by_team[mlb_id] = get_team_schedule(
            mlb_id, today.isoformat(), week_end.isoformat())

    # Project each player
    print('  projecting (schedule + opp-SP + role + cap aware)...')
    my_proj = {p.name: project_player(p, schedules_by_team, rh3_map, rp3_map,
                                         rp3_by_mlbam, rprs2_map, ts_map,
                                         today, week_end)
               for p in mu['my_lineup']}
    opp_proj = {p.name: project_player(p, schedules_by_team, rh3_map, rp3_map,
                                          rp3_by_mlbam, rprs2_map, ts_map,
                                          today, week_end)
                for p in mu['opp_lineup']}

    # Apply SP cap (10 starts/week)
    my_capped = apply_sp_cap(my_proj)
    opp_capped = apply_sp_cap(opp_proj)
    if my_capped > 0: print(f'  Ligers SP cap removed {my_capped:.1f} FP')
    if opp_capped > 0: print(f'  Opp SP cap removed {opp_capped:.1f} FP')

    # Team totals + variance
    my_rest = sum(p['fp'] for p in my_proj.values())
    opp_rest = sum(p['fp'] for p in opp_proj.values())
    my_total = mu['my_score'] + my_rest
    opp_total = mu['opp_score'] + opp_rest
    my_sigma2 = sum(p['sigma2'] for p in my_proj.values())
    opp_sigma2 = sum(p['sigma2'] for p in opp_proj.values())
    win_prob = win_probability(my_total, opp_total, my_sigma2, opp_sigma2)

    print(f'\n  Ligers: WTD {mu["my_score"]:.1f} + rest {my_rest:.1f} = {my_total:.1f} '
          f'(σ²={my_sigma2:.0f})')
    print(f'  Opp:    WTD {mu["opp_score"]:.1f} + rest {opp_rest:.1f} = {opp_total:.1f} '
          f'(σ²={opp_sigma2:.0f})')
    print(f'  Win probability: {win_prob*100:.1f}%')

    my_block, _, _ = render_team_table(mu['mine'].team_name, mu['my_lineup'],
                                          mu['my_score'], my_proj, my_capped)
    opp_block, _, _ = render_team_table(mu['opp'].team_name, mu['opp_lineup'],
                                           mu['opp_score'], opp_proj, opp_capped)

    # ---- LINEUP OPTIMIZER ----
    opt_block = render_lineup_optimizer(mu['my_lineup'], my_proj, schedules_by_team,
                                          ESPN_TO_MLB_TEAM)

    # ---- LOG PREDICTION HISTORY ----
    log_prediction(mu, my_total, opp_total, win_prob, today)

    # ---- ACCURACY HISTORY VIEW ----
    accuracy_block = render_accuracy_history()

    # ---- ADDITIONAL ENHANCEMENT SECTIONS ----
    print('  building enhancement sections...')
    power_block = render_power_rankings()
    drop_pickup_block = render_drop_pickup_suggestions(mu['my_lineup'], rh3_map)
    streamer_block = render_2start_gems()
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
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, system-ui, sans-serif; background: #0d1117;
       color: #c9d1d9; max-width: 1280px; margin: 0 auto; padding: 0 1em 4em 1em;
       line-height: 1.5; }}
header {{ border-bottom: 2px solid #30363d; padding: .8em 0; margin-bottom: 1em;
         display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap;
         position: sticky; top: 0; background: #0d1117; z-index: 100; }}
h1 {{ color: #58a6ff; margin: 0; }}
h2 {{ color: #79c0ff; margin-top: 1.5em; }}
h2 .totals {{ float: right; font-size: 0.65em; font-weight: 400; color: #8b949e; }}
h2 .totals b {{ color: #c9d1d9; }}
h2 .totals .wtd {{ color: #3fb950; }}
h2 .totals .proj {{ color: #d2a8ff; }}
h2 .totals .total {{ color: #f0883e; font-size: 1.2em; }}
nav a {{ color: #58a6ff; text-decoration: none; margin-left: 1em; font-size: .85em; }}
nav a:hover {{ text-decoration: underline; }}
.scoreboard {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
              padding: 1.5em; margin: 1em 0; }}
.score-grid {{ display: grid; grid-template-columns: 1fr 0.3fr 1fr; gap: 1em;
              text-align: center; align-items: center; }}
.score-team .name {{ color: #8b949e; font-size: .85em; margin-bottom: .3em; }}
.score-team .wtd {{ font-size: 2.5em; font-weight: bold; color: #3fb950; }}
.score-team.opp .wtd {{ color: #f85149; }}
.score-team .proj {{ font-size: .85em; color: #8b949e; margin-top: .3em; }}
.score-team .total-final {{ font-size: 1.4em; color: #f0883e; font-weight: bold; }}
.vs {{ font-size: 1.5em; color: #6e7681; }}
.win-bar {{ margin-top: 1.5em; padding-top: 1em; border-top: 1px solid #30363d; }}
.win-bar-label {{ text-align: center; margin-bottom: .5em; font-size: 1.1em; }}
.win-bar-label .pct {{ font-weight: bold; font-size: 1.5em; }}
.win-bar-label .pos {{ color: #3fb950; }}
.win-bar-label .lean-pos {{ color: #5fb950; }}
.win-bar-label .toss {{ color: #d29922; }}
.win-bar-label .lean-neg {{ color: #db6d28; }}
.win-bar-label .neg {{ color: #f85149; }}
.win-bar-track {{ height: 14px; background: #21262d; border-radius: 7px; overflow: hidden; }}
.win-bar-fill {{ height: 100%; background: linear-gradient(90deg, #3fb950, #d29922 50%, #f85149); }}
.gap-row {{ text-align: center; margin-top: 1em; font-size: 1em; color: #8b949e; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1em; font-size: .9em; }}
th {{ background: #161b22; padding: .5em; text-align: left;
      border-bottom: 2px solid #30363d; font-weight: 600; color: #8b949e;
      text-transform: uppercase; font-size: .75em; }}
td {{ padding: .35em .5em; border-bottom: 1px solid #21262d; }}
tr.breakdown td {{ color: #6e7681; font-size: .8em; padding-left: 2em;
                    border-bottom: 1px dashed #21262d; }}
tr:hover td {{ background: #161b22; }}
.pos {{ color: #3fb950; }} .neg {{ color: #f85149; }} .zero {{ color: #6e7681; }}
.muted {{ color: #8b949e; }}
.badge {{ background: #d2a8ff; color: #0d1117; padding: 1px 5px; border-radius: 3px;
          font-size: .75em; font-weight: bold; }}
.capped {{ background: #f85149; color: white; padding: 1px 5px; border-radius: 3px;
           font-size: .7em; }}
.meta {{ color: #6e7681; font-size: .85em; margin-top: 2em; text-align: center;
         border-top: 1px solid #21262d; padding-top: 1em; }}
.notes {{ background: #161b22; padding: .8em 1em; border-left: 3px solid #58a6ff;
          margin: 1em 0; font-size: .85em; }}

/* ── Action items ── */
.action-items {{ background: #161b22; border: 1px solid #30363d;
                  border-radius: 8px; padding: 1em 1.5em; margin: 1em 0; }}
.action-items h3 {{ margin: 0 0 .5em 0; color: #d2a8ff; font-size: 1.1em; }}
.action-items ul {{ margin: 0; padding: 0; list-style: none; }}
.action-items li {{ padding: .4em .8em; margin: .3em 0; border-radius: 5px;
                     border-left: 3px solid #6e7681; }}
.urgency-high {{ background: #4d1c1c; border-left-color: #f85149; }}
.urgency-med  {{ background: #3d2b1f; border-left-color: #d29922; }}
.urgency-low  {{ background: #1a2e1c; border-left-color: #3fb950; }}

/* ── Gauge ── */
.gauge-wrap {{ display: flex; justify-content: center; margin: .5em 0; }}
.gauge {{ width: 160px; height: 160px; border-radius: 50%; display: flex;
          align-items: center; justify-content: center; }}
.gauge-inner {{ width: 132px; height: 132px; background: #0d1117;
                 border-radius: 50%; display: flex; flex-direction: column;
                 align-items: center; justify-content: center; }}
.gauge-pct {{ font-size: 2.2em; font-weight: bold; color: #c9d1d9; }}
.gauge-label {{ font-size: .85em; color: #8b949e; }}

/* ── Collapsibles ── */
details {{ margin-top: 1em; }}
details > summary {{ cursor: pointer; color: #79c0ff; font-size: 1.2em;
                      font-weight: 600; padding: .5em 0;
                      border-bottom: 1px solid #21262d; user-select: none; }}
details > summary:hover {{ color: #a5d6ff; }}
details[open] > summary {{ border-bottom: 1px solid #30363d; }}
details > summary::marker {{ color: #6e7681; }}

/* ── Heatmap cells ── */
.heat-0 {{ background: #1a2e1c; }}     /* dim green */
.heat-1 {{ background: #2e4f2c; }}
.heat-2 {{ background: #3fb950; color: #0d1117; font-weight: bold; }}
.heat-3 {{ background: #66d979; color: #0d1117; font-weight: bold; }}
.heat-neg {{ background: #4d1c1c; color: #ffa198; }}

/* ── Section anchors ── */
section {{ scroll-margin-top: 80px; }}

/* ── Sortable hint ── */
th.sortable {{ cursor: pointer; user-select: none; }}
th.sortable:hover {{ background: #21262d; color: #c9d1d9; }}
th.sortable::after {{ content: ' ⇅'; opacity: 0.3; font-size: .8em; }}

/* ── TOC nav strip ── */
.toc {{ display: flex; gap: .5em; flex-wrap: wrap; padding: .5em 0; margin: 1em 0;
        border-top: 1px solid #21262d; border-bottom: 1px solid #21262d;
        font-size: .85em; overflow-x: auto; }}
.toc a {{ color: #58a6ff; text-decoration: none; padding: .3em .6em;
          border-radius: 4px; white-space: nowrap; }}
.toc a:hover {{ background: #161b22; }}

/* ── Tablet (≤ 900px) ── */
@media (max-width: 900px) {{
  body {{ padding: 0 .6em 4em .6em; }}
  h1 {{ font-size: 1.5em; }}
  h2 {{ font-size: 1.2em; margin-top: 1.2em; }}
  h2 .totals {{ display: block; float: none; margin-top: .3em; font-size: .85em; }}
  .scoreboard {{ padding: 1em; }}
  .score-team .wtd {{ font-size: 2em; }}
  .score-team .total-final {{ font-size: 1.2em; }}
  /* Wrap tables in horizontal-scroll on tablet */
  .scroll-x {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
}}

/* ── Phone (≤ 600px) — card-style player rows ── */
@media (max-width: 600px) {{
  .scoreboard {{ padding: .75em; margin: .5em 0; }}
  .score-grid {{ grid-template-columns: 1fr; gap: .5em; }}
  .vs {{ display: none; }}
  .score-team .wtd {{ font-size: 2.4em; line-height: 1; margin: .1em 0; }}
  .score-team .total-final {{ font-size: 1.3em; }}
  .score-team.opp {{ border-top: 1px solid #30363d; padding-top: .5em; }}
  .gauge {{ width: 130px; height: 130px; }}
  .gauge-inner {{ width: 108px; height: 108px; }}
  .gauge-pct {{ font-size: 1.8em; }}

  /* TOC: smaller pills */
  .toc {{ gap: .3em; font-size: .8em; padding: .4em 0; }}
  .toc a {{ padding: .35em .55em; }}

  /* Action items: bigger touch targets */
  .action-items {{ padding: .8em 1em; }}
  .action-items li {{ padding: .6em .8em; font-size: .95em; }}

  /* Collapsibles: larger tap target */
  details > summary {{ padding: .8em 0; font-size: 1.1em; min-height: 44px; }}

  /* Player table → mobile card layout */
  .player-table {{ font-size: .95em; }}
  .player-table thead {{ display: none; }}
  .player-table, .player-table tbody, .player-table tr, .player-table td {{
    display: block; width: 100%; }}
  .player-table tr {{
    background: #161b22; border: 1px solid #21262d; border-radius: 6px;
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
    color: #6e7681; font-size: .8em; text-transform: uppercase;
    letter-spacing: .03em; font-weight: 500;
  }}
  /* Player name: hide label, full-width, larger */
  .player-table td[data-label="Player"] {{
    grid-template-columns: 1fr; padding-bottom: .35em;
    margin-bottom: .35em; border-bottom: 1px solid #21262d;
    font-size: 1.05em; font-weight: 600; color: #e6edf3;
  }}
  .player-table td[data-label="Player"]::before {{ display: none; }}
  /* Total: bigger, end of card */
  .player-table td[data-label="Total"] b {{ font-size: 1.15em; color: #f0883e; }}
  /* Hide blank trailing column */
  .player-table td:nth-last-child(1):empty {{ display: none; }}
  /* Breakdown rows: full-width within their player-row card */
  .player-table tr.breakdown {{
    background: transparent; border: none; padding: 0 0 0 1em;
    margin: -.4em 0 .4em 0; font-size: .85em; color: #8b949e;
  }}
  .player-table tr.breakdown td {{
    display: block; grid-template-columns: none; padding: .15em 0;
    border-bottom: none;
  }}
  .player-table tr.breakdown td::before {{ display: none; }}

  /* Other tables: horizontal-scroll wrapper to prevent viewport overflow */
  table:not(.player-table) {{
    display: block; overflow-x: auto; -webkit-overflow-scrolling: touch;
    font-size: .85em; max-width: 100%;
  }}
  table:not(.player-table) thead, table:not(.player-table) tbody,
  table:not(.player-table) tr {{ display: table; width: 100%; }}
  table:not(.player-table) tr {{ table-layout: auto; }}

  /* Win bar: keep readable */
  .win-bar-label .pct {{ font-size: 1.4em; }}
  .win-bar-track {{ height: 18px; }}

  /* Headers a bit smaller */
  h1 {{ font-size: 1.3em; }}
  h2 {{ font-size: 1.1em; }}

  /* Sticky header more compact */
  header {{ padding: .6em 0; }}
  header h1 {{ flex: 1 1 100%; }}
  nav {{ font-size: .85em; }}
  nav a {{ margin-left: .6em; }}
}}

/* Improve color contrast for legibility */
.zero {{ color: #7d8590; }}  /* bumped from #6e7681 */
tr:nth-child(even) td {{ background: rgba(255,255,255,.015); }}
</style>
</head><body>
<header>
  <h1>🏟️ Ligers Weekly Matchup</h1>
  <nav>
    <a href="index.html">← xFP Model</a>
    <a href="live_dashboard.html">🔴 Live Today</a>
  </nav>
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
expandBtn.style.cssText = 'margin: 1em .5em; padding: .4em 1em; background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 5px; cursor: pointer;';
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
