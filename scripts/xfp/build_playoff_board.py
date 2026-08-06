# -*- coding: utf-8 -*-
"""Playoff-window FP board: what the roster is worth over the bracket only.

Regular-season FP buys seeding; once seeding is settled, the only thing that
matters is FP inside the playoff matchup periods. That changes the inputs:

  * TEAM GAMES IN WINDOW, not "rest of season". Clubs differ by 2-3 games over
    five weeks, which is ~6% of a player's entire output.
  * An IL'd player is worth only the share of the window he is back for.
  * A player whose VOLUME is IL-suppressed must not be scored on it. Every
    volume input -- model projection, season-to-date, trailing-30d -- is
    depressed by a stint, so a returning regular reads as a part-timer. His
    most recent healthy season's rate is substituted, then shrunk like anyone
    else's.

VOLUME HANDLING -- the bug this script exists to not repeat
----------------------------------------------------------
The first version of this board took
`max(proj_ros_pa_per_teamgame, pa_per_teamgame_to, measured_30d)`. That is
wrong. `xfp_volume_projections.csv` already applies the validated forward
retention shrink (0.873, against an empirical 0.865 -- see
`lib/late_season_volume`), so taking a max against raw pace discards the
calibration whenever raw pace is higher, which is most of the time. On the
2026-08-05 roster it inflated the hitter total by 140 FP (+13.6%) and moved
Michael Harris II from 3rd to 6th among hitters.

The projection is used AS IS. Season-to-date is a fallback for players with
no projection row, and is shrunk on the way in.
"""
from __future__ import annotations

import argparse
import datetime
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from plv_clone.utils.name_match import safe_name_key            # noqa: E402
from scripts.xfp.lib import late_season_volume as lsv           # noqa: E402
from scripts.xfp.lib.team_override import (                     # noqa: E402
    ESPN_TEAM_ALIASES, load_map, verify_identity)

IL_STATES = {'TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'OUT'}
OUT_CSV = Path('data/outputs/playoff_roster_fp.csv')
# a full rotation slot; nobody starts more often than this over a long window
MAX_GS_PER_TG = 0.21
# rprs2 xfp_ros spans this many team-games, so RP totals rescale to the window
RPRS2_WINDOW_GAMES = 49.0


def team_games(start: datetime.date, end: datetime.date) -> dict[str, int]:
    """MLB games per club inside the window, from the live schedule."""
    r = requests.get('https://statsapi.mlb.com/api/v1/schedule',
                     params={'sportId': 1, 'startDate': start.isoformat(),
                             'endDate': end.isoformat(), 'hydrate': 'team'},
                     timeout=60).json()
    tg: dict[str, int] = defaultdict(int)
    for dt in r.get('dates', []):
        for g in dt.get('games', []):
            for side in ('home', 'away'):
                ab = (g['teams'][side]['team'] or {}).get('abbreviation')
                if ab:
                    ab = str(ab).upper()
                    tg[ESPN_TEAM_ALIASES.get(ab, ab)] += 1
    return dict(tg)


def healthy_volume(mlbam: int, side: str) -> float | None:
    """Volume rate from the most recent season the player was actually healthy.

    Used only for players an IL stint has suppressed. Hitters need a real
    workload (400+ PA) and starters a real rotation year (20+ starts) before a
    season counts as healthy.
    """
    grp = 'hitting' if side == 'H' else 'pitching'
    try:
        r = requests.get(f'https://statsapi.mlb.com/api/v1/people/{mlbam}/stats',
                         params={'stats': 'yearByYear', 'group': grp},
                         timeout=30).json()
    except requests.RequestException:
        return None
    best = None
    this_year = datetime.date.today().year
    for s in (r.get('stats') or [{}])[0].get('splits', []):
        st = s['stat']
        try:
            yr = int(s['season'])
        except (KeyError, ValueError):
            continue
        if yr >= this_year:
            continue
        if side == 'H':
            pa, g = int(st.get('plateAppearances', 0) or 0), int(st.get('gamesPlayed', 0) or 0)
            if pa < 400 or g < 1:
                continue
            v = pa / g * 0.95            # games played -> team games
        else:
            gs = int(st.get('gamesStarted', 0) or 0)
            if gs < 20:
                continue
            v = min(gs / 162.0, MAX_GS_PER_TG)
        if best is None or yr > best[0]:
            best = (yr, v)
    return None if best is None else best[1]


def availability(inj: str, ret: datetime.date | None,
                 start: datetime.date, end: datetime.date) -> float:
    """Share of the window the player is available for."""
    if inj not in IL_STATES:
        return 1.0
    if ret is None:
        return 0.0
    if ret <= start:
        return 1.0
    if ret >= end:
        return 0.0
    return (end - ret).days / (end - start).days


def resolve_volume(proj, to_date, side: str, healthy=None) -> float:
    """The one place volume is decided. Never a max against raw pace.

    Order: an IL-suppressed player's healthy rate (shrunk), else the
    already-calibrated model projection, else season-to-date (shrunk).
    """
    cap = MAX_GS_PER_TG if side == 'SP' else 4.6
    if healthy is not None and pd.notna(healthy):
        return min(lsv.volume_from_to_date(healthy, side), cap)
    if proj is not None and pd.notna(proj):
        return min(float(proj), cap)          # already retention-calibrated
    if to_date is not None and pd.notna(to_date):
        return min(lsv.volume_from_to_date(to_date, side), cap)
    return 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--start', required=True, help='playoff window start, YYYY-MM-DD')
    ap.add_argument('--end', required=True, help='playoff window end, YYYY-MM-DD')
    ap.add_argument('--team', default='Ligers', help='substring of my team name')
    a = ap.parse_args()
    start = datetime.date.fromisoformat(a.start)
    end = datetime.date.fromisoformat(a.end)

    tg = team_games(start, end)
    med = sorted(tg.values())[len(tg) // 2]
    print(f'MLB games {start}..{end}: median {med}, '
          f'range {min(tg.values())}-{max(tg.values())}')

    from app.espn_connector import _get_league, get_all_teams, get_injury_details
    lg = _get_league()
    mine = get_all_teams()
    mine = mine[mine['team_name'].str.contains(a.team, na=False)].copy()
    mine['k'] = mine['player_name'].map(safe_name_key)

    ret_map: dict[int, datetime.date] = {}
    try:
        ids = [int(x) for x in mine['player_id'] if str(x).isdigit()]
        det = get_injury_details(ids).dropna(subset=['return_date'])
        ret_map = dict(zip(det['player_id'],
                           pd.to_datetime(det['return_date']).dt.date))
    except Exception as exc:                       # non-gating: no dates = no credit
        print(f'  (injury detail fetch unavailable: {exc})')

    rh = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
    rp3 = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
    rprs2 = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
    volh = pd.read_csv('data/outputs/xfp_volume_projections.csv')
    vols = pd.read_csv('data/outputs/xfp_sp_volume_projections.csv')
    for d, c in ((rh, 'player_name'), (rp3, 'player_name'), (rprs2, 'name_api'),
                 (volh, 'player_name'), (vols, 'player_name')):
        d['k'] = d[c].map(safe_name_key)

    mine['abbr'] = mine['pro_team'].map(
        lambda t: ESPN_TEAM_ALIASES.get(str(t).upper(), str(t).upper()))
    mine['games'] = mine['abbr'].map(tg).fillna(med)
    mine['espn_id'] = pd.to_numeric(mine['player_id'], errors='coerce')
    mine['inj'] = mine['injury_status'].fillna('')
    mine['avail'] = [availability(r.inj, ret_map.get(r.espn_id), start, end)
                     for r in mine.itertuples(index=False)]

    rows = []
    for bucket, sub in (('H', mine[~mine['position'].isin(['SP', 'RP', 'P'])]),
                        ('SP', mine[mine['position'] == 'SP']),
                        ('RP', mine[mine['position'] == 'RP'])):
        if bucket == 'H':
            m = sub.merge(rh[['k', 'batter', 'rank', 'xfp_rh3_per_pa']], on='k')
            m, dropped = verify_identity(m, load_map(), mlbam_col='batter',
                                         team_col='pro_team')
            if len(dropped):
                print(f'  identity guard dropped {len(dropped)} row(s): '
                      f'{", ".join(dropped["player_name"])}')
            m = m.merge(volh[['k', 'proj_ros_pa_per_teamgame',
                              'pa_per_teamgame_to']], on='k', how='left')
            m = m.drop_duplicates('k', keep='first')     # one slot, one row
            for r in m.itertuples(index=False):
                hv = (healthy_volume(int(r.batter), 'H')
                      if r.inj in IL_STATES else None)
                vol = resolve_volume(r.proj_ros_pa_per_teamgame,
                                     r.pa_per_teamgame_to, 'H', hv)
                rows.append(dict(player_name=r.player_name, bucket='H',
                                 position=r.position, team=r.abbr,
                                 rank=r.rank, rate=r.xfp_rh3_per_pa, vol=vol,
                                 games=int(r.games), avail=r.avail,
                                 il_substituted=hv is not None,
                                 po_fp=round(r.xfp_rh3_per_pa * vol
                                             * r.games * r.avail, 1)))
        elif bucket == 'SP':
            m = sub.merge(rp3[['k', 'pitcher', 'rank', 'xfp_rp3_per_start',
                               'data_quality_tag']], on='k')
            m = m.merge(vols[['k', 'proj_ros_gs_per_teamgame',
                              'gs_per_teamgame_to']], on='k', how='left')
            m = m.drop_duplicates('k', keep='first')
            for r in m.itertuples(index=False):
                hv = (healthy_volume(int(r.pitcher), 'SP')
                      if r.inj in IL_STATES else None)
                vol = resolve_volume(r.proj_ros_gs_per_teamgame,
                                     r.gs_per_teamgame_to, 'SP', hv)
                rows.append(dict(player_name=r.player_name, bucket='SP',
                                 position=r.position, team=r.abbr,
                                 rank=r.rank, rate=r.xfp_rp3_per_start, vol=vol,
                                 games=int(r.games), avail=r.avail,
                                 il_substituted=hv is not None,
                                 po_fp=round(r.xfp_rp3_per_start * vol
                                             * r.games * r.avail, 1)))
        else:
            m = sub.merge(rprs2[['k', 'rank', 'xfp_ros']], on='k')
            m = m.drop_duplicates('k', keep='first')
            for r in m.itertuples(index=False):
                rows.append(dict(player_name=r.player_name, bucket='RP',
                                 position=r.position, team=r.abbr,
                                 rank=r.rank, rate=float('nan'),
                                 vol=float('nan'), games=int(r.games),
                                 avail=r.avail, il_substituted=False,
                                 po_fp=round(r.xfp_ros * (r.games / RPRS2_WINDOW_GAMES)
                                             * r.avail, 1)))

    b = pd.DataFrame(rows).sort_values('po_fp', ascending=False)
    print(f'\n{"FP":>7}  {"":<3} {"pos":<4} {"g":>3} {"avail":>6}  player')
    for r in b.itertuples(index=False):
        mark = ' [IL vol substituted]' if r.il_substituted else ''
        print(f'{r.po_fp:>7.1f}  {r.bucket:<3} {r.position:<4} {r.games:>3} '
              f'{r.avail:>5.0%}  {r.player_name}{mark}')
    print(f'\n  TOTAL projected playoff FP: {b.po_fp.sum():.0f}')
    print(f'  NOTE: starter volume runs ~{(lsv.SP_MODEL_OPTIMISM - 1):.0%} hot '
          f'vs history (lib/late_season_volume); SP totals are an upper read.')

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    b.to_csv(OUT_CSV, index=False)
    print(f'  wrote {OUT_CSV}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
