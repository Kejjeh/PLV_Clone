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

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

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
    f = OUT / 'xfp_rp3_projections.csv'
    if not f.exists():
        return {}
    df = pd.read_csv(f)
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

TEAM_ALIASES = {'CWS': 'CHW', 'ATH': 'OAK', 'WSN': 'WSH', 'KCR': 'KC',
                 'TBR': 'TB', 'SFG': 'SF', 'SDP': 'SD'}


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


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
    return (stats.get('runs', 0) + tb + stats.get('rbi', 0)
              + stats.get('baseOnBalls', 0) + stats.get('hitByPitch', 0)
              + stats.get('stolenBases', 0) - stats.get('strikeOuts', 0))


def compute_sp_fp(stats: dict) -> float:
    if not stats: return 0.0
    ip = _ip_to_float(stats.get('inningsPitched', '0.0'))
    return (stats.get('strikeOuts', 0) + ip*3.3
              - stats.get('hits', 0) - 2*stats.get('earnedRuns', 0)
              - stats.get('baseOnBalls', 0) - stats.get('hitBatsmen', 0))


def compute_rp_fp(stats: dict) -> float:
    if not stats: return 0.0
    ip = _ip_to_float(stats.get('inningsPitched', '0.0'))
    return (stats.get('strikeOuts', 0) + ip*3.3
              + stats.get('saves', 0)*5 + stats.get('holds', 0)*3
              + stats.get('wins', 0)*2 - stats.get('losses', 0)*2
              - stats.get('baseOnBalls', 0) - stats.get('hitBatsmen', 0)
              - 2*stats.get('earnedRuns', 0) - stats.get('hits', 0))


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
    """Map roster names → MLBAM IDs and roles."""
    hitters = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv',
                            usecols=['batter', 'player_name'])
    sps = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv',
                       usecols=['pitcher', 'player_name'])
    rps = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv',
                       usecols=['pitcher', 'name'])
    rps = rps.rename(columns={'name': 'player_name'})
    hitters['nk'] = hitters['player_name'].map(_norm)
    sps['nk'] = sps['player_name'].map(_norm)
    rps['nk'] = rps['player_name'].map(_norm)
    h_lookup = dict(zip(hitters['nk'], hitters['batter']))
    sp_lookup = dict(zip(sps['nk'], sps['pitcher']))
    rp_lookup = dict(zip(rps['nk'], rps['pitcher']))

    roster = []
    for p in team.roster:
        nk = _norm(p.name)
        slots = list(getattr(p, 'eligibleSlots', []) or [])
        is_hitter = bool(set(slots) & {'C','1B','2B','3B','SS','OF','LF','CF','RF','DH','UTIL'})
        if is_hitter:
            pid = h_lookup.get(nk); role = 'H'
        else:
            pid = sp_lookup.get(nk) or rp_lookup.get(nk)
            role = 'SP' if nk in sp_lookup else 'RP'
        if pid is None: continue
        roster.append({
            'name': p.name, 'mlbam': int(pid), 'role': role,
            'team': (getattr(p, 'proTeam', '?') or '').upper(),
            'injury': getattr(p, 'injuryStatus', 'ACTIVE'),
        })
    return roster


def get_my_team_and_opponent():
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    my_team = next(t for t in league.teams if t.team_name == 'New York Ligers')
    # current matchup period → find opponent
    period = league.currentMatchupPeriod
    opponent = None
    try:
        for bs in league.box_scores(matchup_period=period):
            if bs.home_team and bs.home_team.team_name == 'New York Ligers':
                opponent = bs.away_team
                break
            if bs.away_team and bs.away_team.team_name == 'New York Ligers':
                opponent = bs.home_team
                break
    except Exception as e:
        print(f'  opponent lookup error: {e}')
    return my_team, opponent, period


def render_team_lines(team_roster, games, pregame_tags=None):
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
            box = get_boxscore(g['game_pk'])
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
        opp = g['home_team'] if team in (g['away_team'], TEAM_ALIASES.get(team)) \
                                  and team != g['home_team'] else g['away_team']
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
<table>
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
<table>
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
        out.append('<table>')
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

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
</style></head><body>
<div class="wrap">
<header>
  <div class="header-row">
    <div>
      <h1>Ligers Live <span class="date-tag">{h(d)}</span></h1>
      <nav class="topnav">
        <a class="current">Live</a>
        <a href="matchup.html">Matchup</a>
        <a href="player_profiles.html">Profiles</a>
        <a href="index.html">XFP</a>
      </nav>
    </div>
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
            my_rows = render_team_lines(my_roster, games, pregame_tags)
            opp_rows = render_team_lines(opp_roster, games, pregame_tags) if opp_roster else []
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
