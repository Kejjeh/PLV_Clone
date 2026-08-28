"""build_closer_watch — nightly ninth-inning role monitor (refresh step 4.946).

Watches the arms whose save role is live, and reports a CHANGE only when the
box score can actually support one. See lib/closer_watch for the rule that
matters: a club with no save opportunities yields NO_CHANCES, never "role
intact" — the 2026-08-03 Dodgers case, where the job changed on the manager's
word while five days of silence looked like confirmation.

Watchlist lives in data/reference/closer_watchlist.json so it can be edited
without touching code. Expected roles come from reporting; this surface tests
them against evidence rather than assuming them.

Non-gating: every failure path prints and exits 0.
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))

import datetime  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from plv_clone.utils.name_match import safe_name_key  # noqa: E402
from scripts.xfp.lib.closer_watch import (  # noqa: E402
    ROLE_LOST, HOLDS_ROLE, build_watch, save_opportunities,
)

WATCHLIST = Path('data/reference/closer_watchlist.json')
OUT = Path('data/outputs/closer_watch.csv')
STATE = Path('data/research/closer_watch_state.json')
WINDOW_DAYS = 7

DEFAULT_WATCH = {
    'edwin diaz':      dict(name='Edwin Díaz', team='Los Angeles Dodgers',
                            expect='CLOSER',
                            why='Roberts 7/27: closer on return from elbow surgery'),
    'tanner scott':    dict(name='Tanner Scott', team='Los Angeles Dodgers',
                            expect='SETUP',
                            why='moved to the 8th when Diaz returned; first in line if Diaz falters'),
    'luke weaver':     dict(name='Luke Weaver', team='Pittsburgh Pirates',
                            expect='CLOSER', why='acquired 8/3, Bednar traded to NYY'),
    'gregory soto':    dict(name='Gregory Soto', team='Pittsburgh Pirates',
                            expect='SETUP', why='13 saves before Weaver arrived'),
    'jeff hoffman':    dict(name='Jeff Hoffman', team='Minnesota Twins',
                            expect='CLOSER',
                            why='MIN traded four relievers; best save environment in MLB'),
    'jhoan duran':     dict(name='Jhoan Duran', team='Philadelphia Phillies',
                            expect='CLOSER', why='MINE — fewest save chances in MLB'),
    'emilio pagan':    dict(name='Emilio Pagán', team='Cincinnati Reds',
                            expect='CLOSER', why='MINE — best save environment I own'),
    'jacob latz':      dict(name='Jacob Latz', team='Texas Rangers',
                            expect='CLOSER', why='MINE'),
    'david bednar':    dict(name='David Bednar', team='New York Yankees',
                            expect='SETUP', why='behind Devin Williams'),
    'louis varland':   dict(name='Louis Varland', team='Toronto Blue Jays',
                            expect='CLOSER', why='highest role-aware RoS of any RP checked'),
}


def load_watchlist():
    if WATCHLIST.exists():
        try:
            return json.loads(WATCHLIST.read_text(encoding='utf-8'))
        except Exception as exc:
            print(f'  watchlist unreadable ({exc}) — using built-in default')
    WATCHLIST.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST.write_text(json.dumps(DEFAULT_WATCH, indent=1, ensure_ascii=False),
                         encoding='utf-8')
    print(f'  seeded {WATCHLIST}')
    return DEFAULT_WATCH


def main() -> int:
    wl = load_watchlist()
    end = datetime.date.today()
    start = end - datetime.timedelta(days=WINDOW_DAYS)

    try:
        r = requests.get('https://statsapi.mlb.com/api/v1/schedule',
                         params={'sportId': 1, 'startDate': start.isoformat(),
                                 'endDate': end.isoformat()}, timeout=45).json()
    except Exception as exc:
        print(f'  closer-watch: schedule fetch failed ({exc}) — '
              'NOT an all-clear, no watch computed')
        return 0
    rows = []
    for g in (x for d in r.get('dates', []) for x in d.get('games', [])):
        if g['status']['detailedState'] not in ('Final', 'Completed Early',
                                                'Game Over'):
            continue
        for side, oth in (('home', 'away'), ('away', 'home')):
            t, o = g['teams'][side], g['teams'][oth]
            if t.get('score') is None:
                continue
            rows.append(dict(team=t['team']['name'], date=g.get('officialDate'),
                             margin=t['score'] - o['score']))
    opps = save_opportunities(pd.DataFrame(rows))
    chances = (opps.groupby('team')['save_opp'].sum().to_dict()
               if len(opps) else {})

    try:
        bp = pd.read_parquet('data/research/xfp_cache/boxscore_pitchers.parquet')
    except Exception as exc:
        print(f'  closer-watch: boxscore unreadable ({exc}) — no watch computed')
        return 0
    bp['game_date'] = pd.to_datetime(bp['game_date'])
    w = bp[(bp['game_date'] >= pd.Timestamp(start)) & (bp['gs'] == 0)].copy()
    w['player_key'] = w['player_name'].apply(safe_name_key)
    saves = (w[w['sv'] > 0].groupby(['player_key', 'team_name'])['sv']
             .sum().reset_index()
             .rename(columns={'team_name': 'team', 'sv': 'n'}))
    watched_teams = {(v.get('team') or '') for v in wl.values()}
    saves = saves[saves['team'].isin(watched_teams)]
    apps = w.groupby('player_key').size().to_dict()
    # games with the club he is WATCHED on - a traded arm's old-club
    # outings must not be scored against his new club's save chances.
    gwt = {}
    for k, meta in wl.items():
        team = meta.get('team') or ''
        gwt[k] = int(((w['player_key'] == k)
                      & (w['team_name'] == team)).sum())

    board = build_watch(watchlist=wl, saves=saves, chances=chances,
                        appearances=apps, games_with_team=gwt)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(OUT, index=False)

    n_act = int(board['actionable'].sum()) if len(board) else 0
    print(f'  closer-watch: {len(board)} arms, window {start}..{end}, '
          f'{n_act} ACTIONABLE -> {OUT}')
    for _, r0 in board.iterrows():
        flag = '**' if r0['actionable'] else '  '
        print('  %s %-16s %-22s exp=%-6s %-12s (self %d / mates %d / '
              'chances %d / apps %d)'
              % (flag, r0['player'], str(r0['team'])[:22], r0['expect'],
                 r0['signal'], r0['saves_self'], r0['saves_teammates'],
                 r0['team_chances'], r0['appearances']))
        if r0['actionable']:
            print('       -> %s' % r0['note'])

    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(
            {'as_of': end.isoformat(),
             'signals': dict(zip(board['player'], board['signal']))},
            indent=1, ensure_ascii=False), encoding='utf-8')
    except Exception as exc:
        print(f'  closer-watch: state write failed ({exc}) — non-gating')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
