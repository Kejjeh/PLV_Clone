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

import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

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
    from app import espn_connector as ec
    league = ec._get_league()
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


def render_team_lines(team_roster, games):
    """Walk roster, find each player's live boxscore stats, return rows."""
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
        rows.append({
            'name': lig['name'], 'role': lig['role'], 'team': team,
            'opp': opp, 'fp': fp, 'line': line, 'status': inn,
            'game_status': g['status'], 'highlights': highlights,
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
            print(f'  {r["name"]:<22s} {r["role"]:<3s} {r["fp"]:>+7.2f}  vs {r["opp"]:<4s} '
                  f'{r["status"]:<15s}{hl}')
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
                   '<th>Line</th><th>Highlights</th></tr></thead><tbody>')
        for r in rows:
            cls = 'pos' if r['fp'] > 0 else ('neg' if r['fp'] < 0 else 'zero')
            hl = ' '.join(r['highlights'])
            out.append(f'<tr><td>{h(r["name"])}</td><td>{h(r["role"])}</td>'
                       f'<td class="{cls}">{r["fp"]:+.2f}</td>'
                       f'<td>{h(r["status"])}</td><td class="line">{h(r["line"])}</td>'
                       f'<td class="hl">{h(hl)}</td></tr>')
        out.append('</tbody></table>')
        return '\n'.join(out)

    my_total = sum(r['fp'] for r in my_rows)
    opp_total = sum(r['fp'] for r in opp_rows)
    gap = my_total - opp_total

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html = f'''<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh_secs}">
<title>Ligers Live — {h(d)}</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; background: #0d1117; color: #c9d1d9; max-width: 1200px; margin: 0 auto; padding: 1em; }}
h1 {{ color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: .3em; }}
h2 {{ color: #79c0ff; }}
.total {{ float: right; font-size: 0.9em; color: #d2a8ff; }}
.scoreboard {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1em; margin: 1em 0; font-size: 1.2em; text-align: center; }}
.scoreboard .me {{ color: #3fb950; font-weight: bold; }}
.scoreboard .opp {{ color: #f85149; font-weight: bold; }}
.scoreboard .gap {{ font-size: 1.5em; margin-top: .5em; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
th {{ background: #161b22; padding: .5em; text-align: left; border-bottom: 2px solid #30363d; }}
td {{ padding: .4em .5em; border-bottom: 1px solid #21262d; font-size: .95em; }}
tr:hover {{ background: #161b22; }}
.pos {{ color: #3fb950; font-weight: bold; }}
.neg {{ color: #f85149; font-weight: bold; }}
.zero {{ color: #8b949e; }}
.line {{ color: #8b949e; font-family: monospace; font-size: .9em; }}
.hl {{ color: #d2a8ff; font-weight: bold; }}
.empty {{ color: #6e7681; font-style: italic; }}
.meta {{ color: #6e7681; font-size: .85em; margin-top: 1em; }}
</style></head><body>
<h1>🏟️  Ligers Live — {h(d)}</h1>
<div class="scoreboard">
  <span class="me">{h(my_name)}: {my_total:+.2f}</span>  vs
  <span class="opp">{h(opp_name or "Opponent")}: {opp_total:+.2f}</span>
  <div class="gap">{'🟢 UP' if gap >= 0 else '🔴 DOWN'} by {abs(gap):.2f} FP today</div>
</div>
{block_html(f"{my_name} — Today's Lines", my_rows)}
{block_html(f"{opp_name or 'Opponent'} — Today's Lines", opp_rows)}
<p class="meta">Last refresh: {h(now)} · auto-refresh every {refresh_secs}s · MLB Stats API live feed</p>
</body></html>
'''
    target = OUT / 'live_dashboard.html'
    target.write_text(html, encoding='utf-8')


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

    while True:
        try:
            games = get_today_schedule(args.date)
            my_rows = render_team_lines(my_roster, games)
            opp_rows = render_team_lines(opp_roster, games) if opp_roster else []
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
