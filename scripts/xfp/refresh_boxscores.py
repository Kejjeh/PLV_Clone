"""
refresh_boxscores.py — pull MLB Stats API boxscores and compute BrownU FP.

Bridges the 1-2 day Statcast lag. The MLB Stats API boxscore endpoint is
real-time (available minutes after game end); Statcast pitch-level data
typically lags 1-2 days.

Counting stats → BrownU FP:
  SP FP = K + IP*3.3 − H − 2*ER − BB − HBP
  RP FP = K + IP*3.3 − H − 2*ER − BB − HBP + 5*SV + 2*HLD
  H FP  = R + TB + RBI + BB + HBP + SB − K

Outputs (cumulative, deduped by game_pk + mlbam_id):
  data/research/xfp_cache/boxscore_pitchers.parquet
  data/research/xfp_cache/boxscore_hitters.parquet

Usage:
  python scripts/xfp/refresh_boxscores.py                     # yesterday
  python scripts/xfp/refresh_boxscores.py --date 2026-06-15
  python scripts/xfp/refresh_boxscores.py --start 2026-06-10 --end 2026-06-15
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from plv_clone.fantasy.scoring import pitcher_fp, hitter_fp

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_P = CACHE / 'boxscore_pitchers.parquet'
OUT_H = CACHE / 'boxscore_hitters.parquet'

MLB_API = 'https://statsapi.mlb.com/api/v1'
SESSION = requests.Session()
SESSION.headers['User-Agent'] = 'plv_clone/boxscore-bridge'


def _get(path: str, params: dict | None = None, retries: int = 3) -> dict:
    url = f'{MLB_API}{path}'
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 ** attempt)
    return {}


def _ip_to_float(ip_str: str) -> float:
    """'6.2' → 6.667 (MLB 'outs' notation: .1 = 1/3 IP)."""
    try:
        whole, frac = str(ip_str).split('.')
        return int(whole) + int(frac) / 3
    except Exception:
        try:
            return float(ip_str)
        except Exception:
            return 0.0


def game_pks_for_date(game_date: date) -> list[int]:
    data = _get('/schedule', {'sportId': 1, 'date': game_date.isoformat()})
    pks = []
    for d in data.get('dates', []):
        for g in d.get('games', []):
            status = g.get('status', {}).get('abstractGameState', '')
            # Regular season only ('R'). The live gameLog (season=YYYY) returns
            # regular-season games, so spring training ('S')/exhibition ('E') would
            # pollute boom/bust actuals and break parity with the live fallback tier.
            if status == 'Final' and g.get('gameType') == 'R':
                pks.append(g['gamePk'])
    return pks


def boxscore_rows(game_pk: int, game_date: date) -> tuple[list[dict], list[dict]]:
    """Return (pitcher_rows, hitter_rows) for one game."""
    bs = _get(f'/game/{game_pk}/boxscore')
    pitchers, hitters = [], []

    for side in ('home', 'away'):
        team = bs.get('teams', {}).get(side, {})
        team_id = team.get('team', {}).get('id')
        team_name = team.get('team', {}).get('name', '')
        players = team.get('players', {})

        for pid in team.get('pitchers', []):
            p = players.get(f'ID{pid}', {})
            ps = p.get('stats', {}).get('pitching', {})
            if not ps:
                continue
            ip_f = _ip_to_float(ps.get('inningsPitched', '0'))
            # Keep 0-out appearances that still faced batters: a reliever who
            # records no outs but allows hits/runs (a -12 FP blowup) is a real,
            # scoreable game — and dropping it would silently censor the worst
            # bust outings from the boom/bust lens. Only skip true no-ops.
            if ip_f == 0 and int(ps.get('battersFaced', 0)) == 0:
                continue
            h = int(ps.get('hits', 0))
            er = int(ps.get('earnedRuns', 0))
            bb = int(ps.get('baseOnBalls', 0))
            so = int(ps.get('strikeOuts', 0))
            hbp = int(ps.get('hitBatsmen', 0))
            sv = int(ps.get('saves', 0))
            hld = int(ps.get('holds', 0))
            gs = int(ps.get('gamesStarted', 0))  # 0/1 — lets boom/bust filter starts vs relief exactly like the live gameLog path
            base = pitcher_fp(k=so, ip=ip_f, h=h, er=er, bb=bb, hbp=hbp)
            pitchers.append({
                'game_pk':    game_pk,
                'game_date':  game_date.isoformat(),
                'mlbam_id':   pid,
                'player_name': p.get('person', {}).get('fullName', ''),
                'team_id':    team_id,
                'team_name':  team_name,
                'gs':         gs,
                'ip':         round(ip_f, 4),
                'h_allowed':  h,
                'er':         er,
                'bb_allowed': bb,
                'so':         so,
                'hbp_allowed': hbp,
                'sv':         sv,
                'hld':        hld,
                'fp_sp':      round(base, 2),
                'fp_rp':      round(pitcher_fp(k=so, ip=ip_f, h=h, er=er, bb=bb, hbp=hbp, sv=sv, hld=hld), 2),
            })

        for bid in team.get('batters', []):
            p = players.get(f'ID{bid}', {})
            hs = p.get('stats', {}).get('batting', {})
            if not hs or not hs.get('plateAppearances'):
                continue
            r   = int(hs.get('runs', 0))
            tb  = int(hs.get('totalBases', 0))
            rbi = int(hs.get('rbi', 0))
            bb  = int(hs.get('baseOnBalls', 0))
            hbp = int(hs.get('hitByPitch', 0))
            sb  = int(hs.get('stolenBases', 0))
            k   = int(hs.get('strikeOuts', 0))
            hitters.append({
                'game_pk':    game_pk,
                'game_date':  game_date.isoformat(),
                'mlbam_id':   bid,
                'player_name': p.get('person', {}).get('fullName', ''),
                'team_id':    team_id,
                'team_name':  team_name,
                'r':   r, 'tb': tb, 'rbi': rbi,
                'bb':  bb, 'hbp': hbp, 'sb': sb, 'k': k,
                'fp_h': round(hitter_fp(r=r, tb=tb, rbi=rbi, bb=bb, hbp=hbp, sb=sb, k=k), 2),
            })

    return pitchers, hitters


def load_existing(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame()


def atomic_write(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix('.tmp.parquet')
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def date_range(start: date, end: date) -> list[date]:
    out = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='single date YYYY-MM-DD (default: yesterday)')
    ap.add_argument('--start', help='range start YYYY-MM-DD')
    ap.add_argument('--end', help='range end YYYY-MM-DD')
    args = ap.parse_args()

    yesterday = date.today() - timedelta(days=1)
    if args.start and args.end:
        dates = date_range(
            datetime.strptime(args.start, '%Y-%m-%d').date(),
            datetime.strptime(args.end, '%Y-%m-%d').date(),
        )
    elif args.date:
        dates = [datetime.strptime(args.date, '%Y-%m-%d').date()]
    else:
        dates = [yesterday]

    existing_p = load_existing(OUT_P)
    existing_h = load_existing(OUT_H)
    seen_pks_p = set(existing_p['game_pk'].tolist()) if len(existing_p) else set()
    seen_pks_h = set(existing_h['game_pk'].tolist()) if len(existing_h) else set()

    new_p_rows, new_h_rows = [], []
    total_games = 0

    for d in dates:
        pks = game_pks_for_date(d)
        fresh = [pk for pk in pks if pk not in seen_pks_p or pk not in seen_pks_h]
        if not fresh:
            print(f'  {d}: {len(pks)} games, all cached - skip')
            continue
        print(f'  {d}: {len(pks)} games, {len(fresh)} need refresh')
        for pk in fresh:
            try:
                p_rows, h_rows = boxscore_rows(pk, d)
                if pk not in seen_pks_p:
                    new_p_rows.extend(p_rows)
                    seen_pks_p.add(pk)
                if pk not in seen_pks_h:
                    new_h_rows.extend(h_rows)
                    seen_pks_h.add(pk)
                total_games += 1
            except Exception as e:
                print(f'    !! game {pk} failed: {e}', file=sys.stderr)

    if new_p_rows:
        df_new_p = pd.DataFrame(new_p_rows)
        df_p = pd.concat([existing_p, df_new_p], ignore_index=True)
        atomic_write(df_p, OUT_P)
        print(f'  pitchers -> {len(df_p)} rows ({len(new_p_rows)} new) -> {OUT_P.name}')

        # quick summary for new games
        for _, r in df_new_p[df_new_p['ip'] >= 5].sort_values('fp_sp', ascending=False).head(5).iterrows():
            print(f'    {r["game_date"]} {r["player_name"]}: {r["ip"]:.1f}IP '
                  f'{r["so"]}K {r["h_allowed"]}H {r["er"]}ER -> {r["fp_sp"]:.1f} FP(SP)')
    else:
        print('  pitchers: no new games')

    if new_h_rows:
        df_new_h = pd.DataFrame(new_h_rows)
        df_h = pd.concat([existing_h, df_new_h], ignore_index=True)
        atomic_write(df_h, OUT_H)
        print(f'  hitters  -> {len(df_h)} rows ({len(new_h_rows)} new) -> {OUT_H.name}')
    else:
        print('  hitters: no new games')

    print(f'  done - {total_games} games refreshed')


if __name__ == '__main__':
    main()
