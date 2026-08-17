"""live_monitor.py — real-time Ligers performance monitor.

Pulls today's MLB games from MLB Stats API and computes live BrownU
fantasy points for each Liger AND their week-matchup opponent.

Usage:
  python scripts/xfp/live_monitor.py
  python scripts/xfp/live_monitor.py --date 2026-05-12
  python scripts/xfp/live_monitor.py --watch 60          # refresh CLI every 60s
  python scripts/xfp/live_monitor.py --dashboard --watch 60   # writes live HTML

When --dashboard is set, regenerates data/outputs/live_dashboard.html
on each cycle. The HTML has a meta-refresh so the browser auto-reloads.

Detects highlights: HRs, SBs, multi-K starts, saves, holds, QS, blowups.
"""
from __future__ import annotations
import argparse
import json
import sys
import os
import time
import unicodedata
import re
from datetime import date as date_cls, datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from html import escape as h

import json
import pandas as pd

from plv_clone.paths import ROOT  # noqa: E402  (single source for repo paths)
from plv_clone.fantasy.scoring import pitcher_fp, hitter_fp  # noqa: E402
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

# Roster entries that could not be mapped to an MLBAM id this run, as
# (name, proTeam, reason). They score 0 and would otherwise vanish from the
# live totals without trace — the dashboard reprints them beside the
# scoreboard so an incomplete total is never mistaken for a complete one.
UNRESOLVED: list[tuple[str, str, str]] = []

# Lazy import shim — the lib modules touch parquet/CSV caches at first call,
# which we only want to pay once per process. Wrapped in try so the live
# monitor still runs on a stripped environment where these caches are missing.
try:
    from xfp.lib.boom_stack import compute_boom_stack, compute_high_k_pitcher
    from xfp.lib.catcher_framing import compute_catcher_framing
    from xfp.lib.il_return_flag import compute_il_return_flag
    from xfp.lib.hitter_boom_stack import (
        compute_hitter_boom_stack, resolve_opp_sp_id_for_today,
    )
    _TAGS_AVAILABLE = True
except Exception as _tag_imp_err:
    print(f'  WARN: pregame-tag libs unavailable ({_tag_imp_err}); '
          f'live dashboard will render without boom_stack overlays.')
    _TAGS_AVAILABLE = False


def _load_rp3_proj():
    """Load xfp_rp3 projections for rank/recform/next_opp lookup, keyed by pitcher MLBAM."""
    from plv_clone.projections import PROJECTIONS
    df = PROJECTIONS.rp3()
    if df.empty:
        return {}
    out = {}
    for _, r in df.iterrows():
        try:
            pid = int(r['pitcher'])
        except (TypeError, ValueError, KeyError):
            continue
        out[pid] = {
            'rank': int(r['rank']) if pd.notna(r.get('rank')) else None,
            'recform': float(r['recency_form_gap']) if pd.notna(r.get('recency_form_gap')) else None,
            'next_opp': r.get('next_opp_team') if isinstance(r.get('next_opp_team'), str) else None,
            'sigma': float(r.get('xfp_rp3_sigma')) if pd.notna(r.get('xfp_rp3_sigma')) else None,
            'p25': float(r.get('xfp_rp3_p25')) if pd.notna(r.get('xfp_rp3_p25')) else None,
            'p75': float(r.get('xfp_rp3_p75')) if pd.notna(r.get('xfp_rp3_p75')) else None,
        }
    return out


def compute_pregame_tags(roster: list[dict]) -> dict[int, dict]:
    """Return {mlbam_id: {tag_string_html, tag_string_cli, ...}} for each roster entry.

    Surfaces SP boom_stack + HIGH-K + catcher framing + IL_RETURN + σ band for SPs,
    and hitter boom_stack for hitters. Deliberately skips:
      - skill_spike_anti_predictive (validated as anti-predictive — surfacing it
        would invert decisions),
      - marcel_data_divergence (internal model-QA),
      - raw catcher_quintile (folded into 🧊/⚠ binary badge).
    """
    out: dict[int, dict] = {}
    if not _TAGS_AVAILABLE:
        return out
    rp3 = _load_rp3_proj()
    for p in roster:
        pid = p['mlbam']
        role = p['role']
        cli_parts: list[str] = []
        html_parts: list[str] = []
        try:
            if role == 'SP':
                meta = rp3.get(pid, {})
                bs = None
                try:
                    bs = compute_boom_stack(
                        pitcher_id=pid,
                        recency_form_gap=meta.get('recform'),
                        next_opp_team=meta.get('next_opp'),
                        rp3_rank=meta.get('rank') or 999,
                    )
                except Exception:
                    bs = None
                if bs and bs.get('boom_stack') is not None:
                    stack = bs['boom_stack']
                    tier = bs.get('tier', '?')
                    br = bs.get('boom_rate_expected')
                    bur = bs.get('bust_rate_expected')
                    cli_parts.append(f'stack {stack}/4 [{tier}]')
                    rate_bit = ''
                    if br is not None and bur is not None:
                        rate_bit = f' <span class="tag-rate">b{br*100:.0f}/u{bur*100:.0f}%</span>'
                    html_parts.append(f'<span class="tag tag-stack" title="boom_stack {stack}/4 — tier {tier}">📊 {stack}/4 {tier}</span>{rate_bit}')
                try:
                    hk = compute_high_k_pitcher(pid)
                    if hk.get('is_high_k'):
                        cli_parts.append('HIGH-K')
                        html_parts.append('<span class="tag tag-hk" title="HIGH-K ARM (validated +K cohort)">⚡ HIGH-K</span>')
                except Exception:
                    pass
                try:
                    cf = compute_catcher_framing(p.get('team'))
                    if cf.get('is_elite_framer'):
                        cli_parts.append('ELITE-FRAME')
                        html_parts.append('<span class="tag tag-frame-good" title="elite framer behind plate">🧊 ELITE</span>')
                    elif cf.get('is_framing_tax'):
                        cli_parts.append('FRAME-TAX')
                        html_parts.append('<span class="tag tag-frame-bad" title="poor framer behind plate — borderline calls go against">⚠ TAX</span>')
                except Exception:
                    pass
                try:
                    il = compute_il_return_flag(pid)
                    if il.get('is_first_back_long_il'):
                        days = il.get('days_since_last_start') or 0
                        cli_parts.append(f'IL-RTN {days}d')
                        html_parts.append(f'<span class="tag tag-il" title="first start back from {days}d layoff (+2.93 pp bust)">🏥 {days}d</span>')
                except Exception:
                    pass
                if meta.get('p25') is not None and meta.get('p75') is not None:
                    cli_parts.append(f'σ {meta["p25"]:.0f}-{meta["p75"]:.0f}')
                    html_parts.append(f'<span class="tag tag-sigma" title="rp3 p25–p75 expected FP/start">σ {meta["p25"]:.0f}-{meta["p75"]:.0f}</span>')
            elif role == 'H':
                team = p.get('team')
                opp_sp_id = None
                try:
                    opp_sp_id = resolve_opp_sp_id_for_today(team)
                except Exception:
                    opp_sp_id = None
                try:
                    hbs = compute_hitter_boom_stack(
                        batter_id=pid, opp_sp_id=opp_sp_id, team=team,
                    )
                    if hbs and hbs.get('boom_stack') is not None:
                        stack = hbs['boom_stack']
                        br = hbs.get('boom_rate_expected')
                        bur = hbs.get('bust_rate_expected')
                        cli_parts.append(f'hboom {stack}/4')
                        rate_bit = ''
                        if br is not None and bur is not None:
                            rate_bit = f' <span class="tag-rate">b{br*100:.0f}/u{bur*100:.0f}%</span>'
                        html_parts.append(f'<span class="tag tag-stack" title="hitter boom_stack {stack}/4">📊 {stack}/4</span>{rate_bit}')
                        comps = hbs.get('components') or {}
                        # Surface lineup_amp only when it actually fires — that's
                        # the highest-leverage hitter component (top of order vs soft SP).
                        if comps.get('lineup_amp'):
                            cli_parts.append('TOP-LINEUP')
                            html_parts.append('<span class="tag tag-lineup" title="top-of-order vs soft SP">🔝 LINEUP</span>')
                except Exception:
                    pass
        except Exception:
            pass
        if cli_parts or html_parts:
            out[pid] = {
                'cli': ' · '.join(cli_parts),
                'html': ' '.join(html_parts),
            }
    return out

USER_AGENT = 'Mozilla/5.0 (live-monitor)'

# ESPN pro_team code -> MLB StatsAPI schedule abbreviation. Lookup direction at
# the liger_team_to_games consumer is ESPN -> MLB, so ESPN codes are the KEYS.
# (audit 2026-07-04: previous map was inverted and missing ARI — Diamondbacks,
# Athletics and White Sox players silently vanished from live totals.)
TEAM_ALIASES = {'ARI': 'AZ', 'OAK': 'ATH', 'CHW': 'CWS', 'WSN': 'WSH',
                'KCR': 'KC', 'TBR': 'TB', 'SFG': 'SF', 'SDP': 'SD'}


def _resolve_opponent(team: str, g: dict) -> str:
    """The other team in game `g` for a player on `team` (issue #20).

    Compare the ALIASED team code against the game's away side, not
    `team` against its own alias — the old inline check
    `team in (g['away_team'], TEAM_ALIASES.get(team))` compared team to
    its own alias (e.g. 'ARI' == TEAM_ALIASES['ARI'] == 'AZ'), which is
    never true by construction, so an aliased team playing away always
    fell through to `else` and showed its own team as the opponent.
    """
    away_key = TEAM_ALIASES.get(team, team)
    return g['home_team'] if away_key == g['away_team'] else g['away_team']


# _norm was join_key's exact algorithm (NFD-Mn + sorted alpha tokens); routed to
# the name_match owner (item 10, 2026-07-04). Proven byte-identical, so this is a
# pure move even though live_monitor produces live_dashboard.html.
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402
from plv_clone.league_config import MY_TEAM_NAME


def _fetch_json(url):
    req = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_today_schedule(d: str):
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={d}&hydrate=team,linescore'
    data = _fetch_json(url)
    games = []
    for d_block in data.get('dates', []):
        for g in d_block.get('games', []):
            games.append({
                'game_pk': g['gamePk'],
                'away_team': g['teams']['away']['team']['abbreviation'].upper(),
                'home_team': g['teams']['home']['team']['abbreviation'].upper(),
                'status': g['status']['abstractGameState'],
                'detailed': g['status'].get('detailedState', ''),
                'inning': g.get('linescore', {}).get('currentInning'),
                'inning_state': g.get('linescore', {}).get('inningState', ''),
            })
    return games


def get_boxscore(game_pk: int):
    url = f'https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore'
    return _fetch_json(url)


def _ip_to_float(ip_str):
    s = str(ip_str)
    if '.' in s:
        w, f = s.split('.')
        return int(w) + int(f) / 3
    return float(s)


def compute_hitter_fp(stats: dict) -> float:
    if not stats: return 0.0
    h = stats.get('hits', 0)
    doubles = stats.get('doubles', 0)
    triples = stats.get('triples', 0)
    hr = stats.get('homeRuns', 0)
    singles = h - doubles - triples - hr
    tb = singles + 2*doubles + 3*triples + 4*hr
    return hitter_fp(
        r=stats.get('runs', 0), tb=tb, rbi=stats.get('rbi', 0),
        bb=stats.get('baseOnBalls', 0), hbp=stats.get('hitByPitch', 0),
        sb=stats.get('stolenBases', 0), k=stats.get('strikeOuts', 0),
    )


def compute_sp_fp(stats: dict) -> float:
    if not stats: return 0.0
    ip = _ip_to_float(stats.get('inningsPitched', '0.0'))
    return pitcher_fp(
        k=stats.get('strikeOuts', 0), ip=ip, h=stats.get('hits', 0),
        er=stats.get('earnedRuns', 0), bb=stats.get('baseOnBalls', 0),
        hbp=stats.get('hitBatsmen', 0),
    )


def compute_rp_fp(stats: dict) -> float:
    if not stats: return 0.0
    ip = _ip_to_float(stats.get('inningsPitched', '0.0'))
    # BrownU RP scoring has NO win/loss term (see LeagueScoring + CLAUDE.md).
    # The old inline formula added +2*W −2*L, over-counting by 2*(W−L)/appearance.
    return pitcher_fp(
        k=stats.get('strikeOuts', 0), ip=ip, h=stats.get('hits', 0),
        er=stats.get('earnedRuns', 0), bb=stats.get('baseOnBalls', 0),
        hbp=stats.get('hitBatsmen', 0),
        sv=stats.get('saves', 0), hld=stats.get('holds', 0),
    )


def detect_highlights(name: str, role: str, stats_b: dict, stats_p: dict) -> list[str]:
    """Return list of highlight emoji+text for this player's day."""
    h = []
    if role == 'H' and stats_b:
        hr = stats_b.get('homeRuns', 0)
        if hr >= 2: h.append(f'💎 {hr}-HR GAME')
        elif hr == 1: h.append('🏆 HR')
        if stats_b.get('hits', 0) >= 4: h.append('🔥 4+ hits')
        if stats_b.get('stolenBases', 0) >= 1:
            h.append(f'💨 {stats_b["stolenBases"]} SB')
        if stats_b.get('rbi', 0) >= 4: h.append(f'🍱 {stats_b["rbi"]} RBI')
    if role in ('SP', 'RP') and stats_p:
        k = stats_p.get('strikeOuts', 0)
        ip = _ip_to_float(stats_p.get('inningsPitched', '0.0'))
        er = stats_p.get('earnedRuns', 0)
        if role == 'SP':
            if ip >= 6 and er <= 3: h.append('✅ QS')
            if k >= 10: h.append(f'⚡ {k}-K GAME')
            elif k >= 8: h.append(f'⚡ {k} K')
            if er >= 5: h.append('🚨 blowup')
        if role == 'RP':
            sv = stats_p.get('saves', 0)
            hld = stats_p.get('holds', 0)
            if sv: h.append(f'💰 SAVE')
            if hld: h.append(f'🤝 HOLD')
    return h


def build_team_id_map(team):
    """Map roster names → MLBAM IDs and roles, collision-safe.

    Resolution path (per player):
      1. Hitters → `resolve_batter_id(name, team=proTeam, position=primary_slot)`
      2. Pitchers → `resolve_pitcher_id(name, team=proTeam, role=role_guess)`

    The naive `_norm(name) → id` map is retained ONLY as a fast prefilter
    for non-colliding names; any name in KNOWN_COLLISIONS /
    KNOWN_PITCHER_COLLISIONS is force-routed through the resolver so the
    Max Muncy LAD-vs-ATH and Logan Allen CLE-vs-SD cases can't sneak
    through. Players that don't resolve are logged + skipped, not crashed.
    See `memory/feedback_player_name_collisions.md`.
    """
    from plv_clone.utils.name_match import (
        resolve_batter_id, resolve_pitcher_id,
        KNOWN_COLLISIONS, KNOWN_PITCHER_COLLISIONS,
    )

    hitters = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv',
                            usecols=['batter', 'player_name'])
    sps = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv',
                       usecols=['pitcher', 'player_name'])
    rps = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv',
                       usecols=['pitcher', 'name'])
    # Fast-path lookup tables built from the same caches the resolvers consult.
    # Only used for non-colliding names; colliding names ALWAYS go through
    # the resolver so team/position disambiguation actually runs.
    hitters_nk = hitters.assign(nk=hitters['player_name'].map(_norm))
    sps_nk = sps.assign(nk=sps['player_name'].map(_norm))
    rps_nk = rps.assign(nk=rps['name'].map(_norm))
    # Drop names that map to >1 mlbam id from the fast-path entirely — those
    # are collisions that MUST disambiguate via team/position.
    h_lookup = (hitters_nk.groupby('nk')['batter'].nunique()
                .pipe(lambda s: hitters_nk[hitters_nk['nk'].isin(s[s == 1].index)])
                .set_index('nk')['batter'].to_dict())
    sp_lookup = (sps_nk.groupby('nk')['pitcher'].nunique()
                 .pipe(lambda s: sps_nk[sps_nk['nk'].isin(s[s == 1].index)])
                 .set_index('nk')['pitcher'].to_dict())
    rp_lookup = (rps_nk.groupby('nk')['pitcher'].nunique()
                 .pipe(lambda s: rps_nk[rps_nk['nk'].isin(s[s == 1].index)])
                 .set_index('nk')['pitcher'].to_dict())

    # Names known to collide — must always force resolver path.
    collide_batter = set(KNOWN_COLLISIONS.keys())
    collide_pitcher = set(KNOWN_PITCHER_COLLISIONS.keys())

    roster = []
    for p in team.roster:
        name = p.name
        nk = _norm(name)
        proTeam = (getattr(p, 'proTeam', '?') or '').upper()
        slots = list(getattr(p, 'eligibleSlots', []) or [])
        hit_slots = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH', 'UTIL'}
        is_hitter = bool(set(slots) & hit_slots)
        # Primary position hint for hitter disambiguation: first matching slot.
        position_hint = next((s for s in slots if s in hit_slots and s != 'UTIL'), None)
        pid = None
        role = None
        try:
            if is_hitter:
                role = 'H'
                if name in collide_batter:
                    pid = resolve_batter_id(name, team=proTeam, position=position_hint)
                else:
                    pid = h_lookup.get(nk)
                    if pid is None:
                        pid = resolve_batter_id(name, team=proTeam, position=position_hint)
            else:
                # Pitcher. Role guess: if eligible only for RP-ish slots prefer RP cache.
                role_hint = 'RP' if ('RP' in slots and 'SP' not in slots) else (
                    'SP' if 'SP' in slots else None)
                if name in collide_pitcher:
                    pid = resolve_pitcher_id(name, team=proTeam, role=role_hint)
                else:
                    pid = sp_lookup.get(nk) or rp_lookup.get(nk)
                    if pid is None:
                        pid = resolve_pitcher_id(name, team=proTeam, role=role_hint)
                # Role via the OWNER (gotcha #8, audit 2026-07-04): converted
                # relievers were scored with the SP formula (SV/HLD dropped)
                # because cache membership decided the role. detect_pitcher_role
                # checks eligible_slots + real gamesStarted.
                if pid is not None:
                    try:
                        from lib.pitcher_role import detect_pitcher_role
                        role = detect_pitcher_role(
                            {'player_name': name, 'eligible_slots': slots,
                             'pro_team': proTeam, 'position': role_hint or ''},
                            mlbam_id=int(pid))
                    except Exception:
                        # fallback: legacy cache-membership heuristic
                        if pid in sp_lookup.values() or nk in sp_lookup:
                            role = 'SP'
                        elif pid in rp_lookup.values() or nk in rp_lookup:
                            role = 'RP'
                        else:
                            role = role_hint or 'SP'
        except Exception as e:
            print(f'  WARN: resolver error for {name} ({proTeam}): {e}; skipping')
            UNRESOLVED.append((name, proTeam, f'resolver error: {e}'))
            continue
        if pid is None:
            print(f'  WARN: could not resolve {name} ({proTeam}, slots={slots}); skipping')
            UNRESOLVED.append((name, proTeam, 'no mlbam match'))
            continue
        roster.append({
            'name': name, 'mlbam': int(pid), 'role': role,
            'team': proTeam,
            'injury': getattr(p, 'injuryStatus', 'ACTIVE'),
        })
    return roster


def get_my_team_and_opponent():
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    my_team = next(t for t in league.teams if t.team_name == MY_TEAM_NAME)
    # current matchup period → find opponent
    period = league.currentMatchupPeriod
    opponent = None
    try:
        for bs in league.box_scores(matchup_period=period):
            if bs.home_team and bs.home_team.team_name == MY_TEAM_NAME:
                opponent = bs.away_team
                break
            if bs.away_team and bs.away_team.team_name == MY_TEAM_NAME:
                opponent = bs.home_team
                break
    except Exception as e:
        print(f'  opponent lookup error: {e}')
    return my_team, opponent, period


def render_team_lines(team_roster, games, pregame_tags=None, box_cache=None):
    if box_cache is None:
        box_cache = {}
    """Walk roster, find each player's live boxscore stats, return rows."""
    pregame_tags = pregame_tags or {}
    liger_team_to_games = {}
    for g in games:
        for tk in (g['away_team'], g['home_team']):
            liger_team_to_games[tk] = g

    rows = []
    for lig in team_roster:
        team = lig['team']
        g = liger_team_to_games.get(team) or liger_team_to_games.get(
            TEAM_ALIASES.get(team, team))
        if g is None: continue
        try:
            pk_key = g['game_pk']
            if pk_key not in box_cache:
                box_cache[pk_key] = get_boxscore(pk_key)
            box = box_cache[pk_key]
        except Exception:
            continue
        all_players = {**box['teams']['away']['players'],
                        **box['teams']['home']['players']}
        pk = f'ID{lig["mlbam"]}'
        if pk not in all_players: continue
        p_box = all_players[pk]
        stats = p_box.get('stats', {})
        bstat = stats.get('batting')
        pstat = stats.get('pitching')
        line = ''
        fp = 0.0
        if lig['role'] == 'H' and bstat:
            fp = compute_hitter_fp(bstat)
            line = (f'AB:{bstat.get("atBats",0)} H:{bstat.get("hits",0)} '
                    f'HR:{bstat.get("homeRuns",0)} R:{bstat.get("runs",0)} '
                    f'RBI:{bstat.get("rbi",0)} BB:{bstat.get("baseOnBalls",0)} '
                    f'K:{bstat.get("strikeOuts",0)} SB:{bstat.get("stolenBases",0)}')
        elif lig['role'] == 'SP' and pstat:
            fp = compute_sp_fp(pstat)
            line = (f'IP:{pstat.get("inningsPitched","0.0")} H:{pstat.get("hits",0)} '
                    f'ER:{pstat.get("earnedRuns",0)} BB:{pstat.get("baseOnBalls",0)} '
                    f'K:{pstat.get("strikeOuts",0)}')
        elif lig['role'] == 'RP' and pstat:
            fp = compute_rp_fp(pstat)
            line = (f'IP:{pstat.get("inningsPitched","0.0")} K:{pstat.get("strikeOuts",0)} '
                    f'ER:{pstat.get("earnedRuns",0)} SV:{pstat.get("saves",0)} '
                    f'HLD:{pstat.get("holds",0)}')
        if not line: continue
        highlights = detect_highlights(lig['name'], lig['role'], bstat, pstat)
        inn = (f'{g["inning_state"]} {g["inning"]}' if g['inning'] and g['status'] == 'Live'
               else g['detailed'])
        opp = _resolve_opponent(team, g)
        tags = pregame_tags.get(lig['mlbam'], {'cli': '', 'html': ''})
        rows.append({
            'name': lig['name'], 'role': lig['role'], 'team': team,
            'opp': opp, 'fp': fp, 'line': line, 'status': inn,
            'game_status': g['status'], 'highlights': highlights,
            'pregame_cli': tags.get('cli', ''),
            'pregame_html': tags.get('html', ''),
        })
    rows.sort(key=lambda r: -r['fp'])
    return rows


def render_console(d, games, my_rows, opp_rows, opp_name):
    print(f'\n{"="*84}')
    print(f'  LIGERS LIVE — {d}  |  refreshed {datetime.now().strftime("%H:%M:%S")}')
    print(f'{"="*84}')
    print(f'\n  {len(games)} MLB games  |  {sum(1 for g in games if g["status"] == "Live")} live  |  '
          f'{sum(1 for g in games if g["status"] == "Final")} final  |  '
          f'{sum(1 for g in games if g["status"] == "Preview")} not started')

    def render_block(label, rows):
        print(f'\n  ─── {label} ───')
        if not rows:
            print('    (no players in active games yet)')
            return 0.0
        total = 0.0
        for r in rows:
            hl = ' ' + ' '.join(r['highlights']) if r['highlights'] else ''
            tg = f'  [{r["pregame_cli"]}]' if r.get('pregame_cli') else ''
            print(f'  {r["name"]:<22s} {r["role"]:<3s} {r["fp"]:>+7.2f}  vs {r["opp"]:<4s} '
                  f'{r["status"]:<15s}{hl}{tg}')
            total += r['fp']
        print(f'  ─── TOTAL {label} FP: {total:+.2f} ───')
        return total

    my_total = render_block('LIGERS (today)', my_rows)
    opp_total = render_block(f'{opp_name or "OPPONENT"} (today)', opp_rows)

    gap = my_total - opp_total
    sign = '+' if gap >= 0 else ''
    print(f'\n  ╔════════════════════════════════════════════════════════════════════════╗')
    print(f'  ║  HEAD-TO-HEAD TODAY:  Ligers {my_total:+.2f}  vs  Opp {opp_total:+.2f}      ')
    print(f'  ║  {"LIGERS UP" if gap >= 0 else "TRAILING"} by {abs(gap):.2f} FP {sign}                                  ')
    print(f'  ╚════════════════════════════════════════════════════════════════════════╝')

    # An unresolved player contributes 0 to the totals above, so a silent skip
    # reads as "he did nothing" rather than "we could not see him". On
    # 2026-08-07 Soriano + García Jr. both failed to resolve and the only
    # notice was a WARN line ~40 rows earlier, already scrolled away — the
    # printed daily total was understated and looked authoritative. Repeat the
    # roster gaps HERE, next to the number they corrupt.
    if UNRESOLVED:
        print(f'\n  ⚠  {len(UNRESOLVED)} player(s) UNRESOLVED — NOT counted in the '
              f'totals above (this scoreboard is INCOMPLETE):')
        for nm, tm, why in UNRESOLVED:
            print(f'       · {nm} ({tm or "?"}) — {why}')
        print('     ESPN\'s own period score is authoritative; fix the mapping '
              'before trusting today\'s FP.')


def _render_sp_alerts_html() -> str:
    """Read sp_alerts.json and render an HTML alerts block (editorial palette)."""
    alerts_file = OUT / 'sp_alerts.json'
    if not alerts_file.exists():
        return ''
    try:
        data = json.loads(alerts_file.read_text(encoding='utf-8'))
    except Exception:
        return ''
    alerts = data.get('alerts', [])
    if not alerts:
        return (
            '<h2>SP Upgrade Alerts</h2>'
            '<p style="color:var(--dim);font-style:italic;">No FA SP upgrades detected today.</p>'
        )
    floor = data.get('upgrade_floor_fpp', 0)
    generated = data.get('generated', '')
    rows = []
    for a in alerts:
        tier_color = 'var(--neg)' if a['tier'] == 'HIGH' else 'var(--warn)'
        sigs = ' '.join(a['signals'])
        rows.append(
            f'<tr>'
            f'<td>{h(a["name"])}</td>'
            f'<td style="color:{tier_color};font-weight:600;">{h(a["tier"])}</td>'
            f'<td>{a["gs"]}</td>'
            f'<td style="color:{"var(--pos)" if a["fpp"]>=0 else "var(--neg)"};">'
            f'{a["fpp"]:+.4f}</td>'
            f'<td style="color:{"var(--pos)" if a["fpp_gap"]>=0.030 else "var(--warn)"};">'
            f'{a["fpp_gap"]:+.3f}</td>'
            f'<td>{a["l4"]}</td>'
            f'<td>{a["whiff_pct"]:.1f}%</td>'
            f'<td>{a["xwoba_con"]:.3f}</td>'
            f'<td>#{a["rp3_rank"]}</td>'
            f'<td style="color:var(--accent);">{h(sigs)}</td>'
            f'</tr>'
        )
    rows_html = '\n'.join(rows)
    # Hitter alerts
    hitter_alerts = data.get('hitter_alerts', [])
    hit_floor = data.get('hit_upgrade_floor_xwoba', 0)
    hit_rows = []
    for a in hitter_alerts:
        tier_color = 'var(--neg)' if a['tier'] == 'HIGH' else 'var(--warn)'
        hit_rows.append(
            f'<tr>'
            f'<td>{h(a["name"])}</td>'
            f'<td style="color:{tier_color};font-weight:600;">{h(a["tier"])}</td>'
            f'<td>{a["pa"]}</td>'
            f'<td style="color:var(--pos);">{a["xwoba_szn"]:.3f}</td>'
            f'<td style="color:{"var(--pos)" if a["xwoba_gap"]>=0.040 else "var(--warn)"};">'
            f'{a["xwoba_gap"]:+.3f}</td>'
            f'<td>{a["xwoba_con"]:.3f}</td>'
            f'<td>#{a["rh3_rank"]}</td>'
            f'</tr>'
        )
    hit_rows_html = '\n'.join(hit_rows)
    hit_block = ''
    if hitter_alerts:
        hit_block = f'''
<h2>Hitter Upgrade Alerts
  <span style="float:right;font-size:0.6em;font-weight:400;color:var(--dim);font-family:'IBM Plex Mono',monospace;">floor xwOBA={hit_floor:.3f}</span>
</h2>
<table data-cols="live_hit_alerts" data-col-lock="1">
<thead><tr>
  <th>Player</th><th>Tier</th><th>PA</th><th>xwOBA</th>
  <th>vs floor</th><th>xwOBACON</th><th>rh3</th>
</tr></thead>
<tbody>{hit_rows_html}</tbody>
</table>'''

    return f'''
<h2>SP Upgrade Alerts
  <span style="float:right;font-size:0.6em;font-weight:400;color:var(--dim);font-family:'IBM Plex Mono',monospace;">
    floor={floor:+.4f} · {h(generated)}
  </span>
</h2>
<table data-cols="live_sp_alerts" data-col-lock="1">
<thead><tr>
  <th>Player</th><th>Tier</th><th>GS</th><th>fpp</th>
  <th>vs floor</th><th>L4</th><th>Whiff</th><th>xCON</th><th>rp3</th><th>Signals</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
{hit_block}'''


def render_dashboard_html(d, my_rows, opp_rows, my_name, opp_name, refresh_secs=60):
    """Write a live HTML dashboard with auto-refresh."""
    def block_html(label, rows):
        total = sum(r['fp'] for r in rows)
        out = [f'<h2>{h(label)} <span class="total">{total:+.2f} FP</span></h2>']
        if not rows:
            out.append('<p class="empty">No players in active games yet.</p>')
            return '\n'.join(out)
        out.append('<table data-cols="live_lines" data-col-lock="1">')
        out.append('<thead><tr><th>Player</th><th>R</th><th>FP</th><th>Status</th>'
                   '<th>Line</th><th>Highlights</th><th>Pre-Game</th></tr></thead><tbody>')
        for r in rows:
            cls = 'pos' if r['fp'] > 0 else ('neg' if r['fp'] < 0 else 'zero')
            hl = ' '.join(r['highlights'])
            # pregame_html is pre-escaped lib output (badges); do NOT h()-escape.
            tags_html = r.get('pregame_html', '') or '<span class="tag-empty">—</span>'
            out.append(f'<tr><td>{h(r["name"])}</td><td>{h(r["role"])}</td>'
                       f'<td class="{cls}">{r["fp"]:+.2f}</td>'
                       f'<td>{h(r["status"])}</td><td class="line">{h(r["line"])}</td>'
                       f'<td class="hl">{h(hl)}</td>'
                       f'<td class="tags">{tags_html}</td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)

    my_total = sum(r['fp'] for r in my_rows)
    opp_total = sum(r['fp'] for r in opp_rows)
    gap = my_total - opp_total

    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M:%S') + ' ET'
    from lib.dashboard_chrome import (  # unified nav + theme owner
        topnav, topnav_css, theme_css, theme_boot_js, theme_toggle_html,
        column_toggle_js,
    )
    html = f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{refresh_secs}">
<title>Ligers Live — {h(d)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Source+Serif+4:wght@400;600;700&display=swap" rel="stylesheet">
<style>
{theme_css()}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{ font-family: 'Source Serif 4', 'Iowan Old Style', Georgia, serif;
       background: var(--bg); color: var(--text);
       font-size: 16px; line-height: 1.6; }}
.wrap {{ max-width: none; width: 100%; margin: 0; padding: 0 2em 4em 2em; }}
@media (min-width: 1600px) {{ .wrap {{ padding: 0 3em 4em 3em; }} }}
.empty, p {{ max-width: 95ch; }}

header {{ border-bottom: 1px solid var(--border); padding: .9em 0;
         position: sticky; top: 0; background: var(--bg); z-index: 100;
         margin-bottom: 1em; }}
.header-row {{ display: flex; justify-content: space-between; align-items: baseline;
              flex-wrap: wrap; gap: 1.2em; }}
h1 {{ color: var(--accent); margin: 0; font-size: 2em; font-weight: 700;
     letter-spacing: .01em; line-height: 1.15;
     font-family: 'Source Serif 4', Georgia, serif; }}
h1 .date-tag {{ color: var(--dim); font-size: .55em; font-weight: 400;
               margin-left: .8em; letter-spacing: .12em;
               font-family: 'IBM Plex Mono', monospace; text-transform: uppercase; }}
h2 {{ color: var(--text); margin-top: 2em; font-size: 1.4em; font-weight: 600;
     border-bottom: 1px solid var(--border); padding-bottom: .35em;
     letter-spacing: .01em; line-height: 1.2;
     font-family: 'Source Serif 4', Georgia, serif; }}
.total {{ float: right; font-size: .65em; font-weight: 400; color: var(--accent);
         font-family: 'IBM Plex Mono', monospace; }}

{topnav_css()}

.scoreboard {{ background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
              padding: 1.2em 1.5em; margin: 1em 0; font-size: 1.2em; text-align: center; }}
.scoreboard .me {{ color: var(--pos); font-weight: 700;
                   font-family: 'Source Serif 4', Georgia, serif;
                   font-variant-numeric: tabular-nums; }}
.scoreboard .opp {{ color: var(--neg); font-weight: 700;
                    font-family: 'Source Serif 4', Georgia, serif;
                    font-variant-numeric: tabular-nums; }}
.scoreboard .sep {{ color: var(--dim); margin: 0 .5em;
                    font-family: 'IBM Plex Mono', monospace; }}
.scoreboard .gap {{ font-size: 1.4em; margin-top: .5em; color: var(--text);
                    font-family: 'Source Serif 4', Georgia, serif;
                    font-weight: 600; }}
.scoreboard .gap.up {{ color: var(--pos); }}
.scoreboard .gap.down {{ color: var(--neg); }}

table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5em;
        font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .87em; }}
th {{ background: var(--panel); padding: .65em .8em; text-align: left;
      border-bottom: 1px solid var(--border); border-top: 1px solid var(--border);
      font-weight: 600; color: var(--dim);
      text-transform: uppercase; font-size: .72em; letter-spacing: .12em;
      font-family: 'IBM Plex Mono', monospace; }}
td {{ padding: .55em .8em; border-bottom: 1px solid var(--faint);
      font-variant-numeric: tabular-nums; }}
tbody tr:nth-child(even) td {{ background: var(--stripe); }}
tbody tr:hover td {{ background: var(--panel); }}
.pos {{ color: var(--pos); font-weight: 600; }}
.neg {{ color: var(--neg); font-weight: 600; }}
.zero {{ color: var(--dim); }}
.line {{ color: var(--dim); font-family: 'IBM Plex Mono', monospace; font-size: .88em; }}
.hl {{ color: var(--accent); font-weight: 600; }}
.empty {{ color: var(--dim); font-style: italic;
         font-family: 'Source Serif 4', Georgia, serif; }}
.meta {{ color: var(--dim); font-size: .78em; margin-top: 2em; text-align: center;
         border-top: 1px solid var(--faint); padding-top: 1em;
         font-family: 'IBM Plex Mono', monospace; letter-spacing: .08em; }}

/* Two-column layout for the my-team / opponent blocks at wide widths */
.team-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5em; align-items: start; }}
.team-grid > div {{ min-width: 0; }}
.team-grid table {{ margin-bottom: .5em; }}
@media (max-width: 1100px) {{
  .team-grid {{ grid-template-columns: 1fr; gap: 0; }}
}}

/* Pre-game badge tags (boom_stack, HIGH-K, framing, IL_RETURN, σ band, hitter lineup). */
.tags {{ font-family: 'IBM Plex Mono', monospace; font-size: .78em;
        white-space: nowrap; line-height: 1.7; }}
.tag {{ display: inline-block; padding: .05em .45em; margin-right: .25em;
       border-radius: 3px; border: 1px solid var(--faint);
       background: var(--panel); color: var(--dim); font-weight: 500;
       letter-spacing: .03em; }}
.tag-stack {{ color: var(--accent); border-color: var(--accent); }}
.tag-hk {{ color: var(--warn); border-color: var(--warn); }}
.tag-frame-good {{ color: var(--pos); border-color: var(--pos); }}
.tag-frame-bad {{ color: var(--neg); border-color: var(--neg); }}
.tag-il {{ color: var(--neg); border-color: var(--neg); }}
.tag-sigma {{ color: var(--dim); }}
.tag-lineup {{ color: var(--pos); border-color: var(--pos); }}
.tag-rate {{ color: var(--dim); font-size: .92em; margin-right: .35em; }}
.tag-empty {{ color: var(--faint); }}

@media (max-width: 700px) {{
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.1em; }}
  .scoreboard {{ font-size: 1em; padding: .9em 1em; }}
  table {{ font-size: .82em; }}
  th, td {{ padding: .45em .55em; }}
  .tags {{ font-size: .7em; }}
}}
</style>
{theme_boot_js()}
</head><body>
<div class="wrap">
<header>
  <div class="header-row">
    <div>
      <h1>Ligers Live <span class="date-tag">{h(d)}</span></h1>
      {topnav("live")}
    </div>
    {theme_toggle_html()}
  </div>
</header>
<div class="scoreboard">
  <span class="me">{h(my_name)}: {my_total:+.2f}</span><span class="sep">vs</span><span class="opp">{h(opp_name or "Opponent")}: {opp_total:+.2f}</span>
  <div class="gap {'up' if gap >= 0 else 'down'}">{'▲ UP' if gap >= 0 else '▼ DOWN'} by {abs(gap):.2f} FP today</div>
</div>
<div class="team-grid">
  <div>{block_html(f"{my_name} — Today's Lines", my_rows)}</div>
  <div>{block_html(f"{opp_name or 'Opponent'} — Today's Lines", opp_rows)}</div>
</div>
<p class="meta">Last refresh: {h(now)} · auto-refresh every {refresh_secs}s · MLB Stats API live feed</p>
{column_toggle_js("live")}
</div>
</body></html>
'''
    sp_alerts_block = _render_sp_alerts_html()

    target = OUT / 'live_dashboard.html'
    # Inject alerts inside the .wrap container (before its closing </div>) so
    # they inherit max-width + padding tokens consistently.
    target.write_text(
        html.replace('</div>\n</body></html>', sp_alerts_block + '\n</div>\n</body></html>'),
        encoding='utf-8'
    )


def main():
    # Force UTF-8 stdout so box-drawing chars / emoji badges don't crash on Windows cp1252.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass  # fallback: some environments don't support reconfigure

    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=str(date_cls.today()))
    ap.add_argument('--watch', type=int, default=0)
    ap.add_argument('--dashboard', action='store_true',
                    help='also write data/outputs/live_dashboard.html')
    args = ap.parse_args()

    print('Loading rosters via ESPN...')
    my_team, opponent, period = get_my_team_and_opponent()
    my_roster = build_team_id_map(my_team)
    opp_roster = build_team_id_map(opponent) if opponent else []
    print(f'  Ligers: {len(my_roster)} players matched | '
          f'Opponent ({opponent.team_name if opponent else "?"}): {len(opp_roster)} players matched | '
          f'matchup period: {period}')

    # Pre-compute pregame tag overlays once. These are pre-game state (boom_stack,
    # HIGH-K, catcher framing, IL_RETURN, σ band, hitter lineup_amp) and don't
    # change mid-game — recomputing each refresh would waste cache hits.
    pregame_tags = compute_pregame_tags(my_roster + opp_roster)
    if pregame_tags:
        print(f'  Pre-game tags computed for {len(pregame_tags)} players')

    while True:
        try:
            games = get_today_schedule(args.date)
            _box_cache = {}   # fresh per cycle — ~58 fetches -> <=15 unique games
            my_rows = render_team_lines(my_roster, games, pregame_tags, box_cache=_box_cache)
            opp_rows = render_team_lines(opp_roster, games, pregame_tags, box_cache=_box_cache) if opp_roster else []
            opp_name = opponent.team_name if opponent else 'Opponent'
            render_console(args.date, games, my_rows, opp_rows, opp_name)
            if args.dashboard:
                render_dashboard_html(args.date, my_rows, opp_rows,
                                        my_team.team_name, opp_name,
                                        refresh_secs=max(args.watch, 60))
                print(f'\n  → live_dashboard.html updated')
        except URLError as e:
            print(f'  NETWORK ERROR: {e}')
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'  ERROR: {e}')
        if args.watch <= 0:
            break
        print(f'\n  next refresh in {args.watch}s...')
        time.sleep(args.watch)


if __name__ == '__main__':
    main()
