"""trade_simulator.py — counterfactual fp impact of a hypothetical trade.

Given a give/get pair and a trade date, compute actual fp earned by each
player from the trade date to the end of that season (or current date),
using real historical statcast data + league scoring formulas.

Hitter FP = TB + R + RBI + BB + HBP + SB − K (K = −1 in BrownU)
SP  FP    = K + IP*3.3 − H − 2*ER − BB − HBP
RP  FP    = K + IP*3.3 + SV*5 + HLD*3 − BB − 2*ER − H − HBP

The R and RBI come from PA-event flow (post_bat_score − bat_score). SB
isn't tracked per PA in statcast — use the year-aggregate sb_per_pa rate
from hitters_multiyr × actual PA in window as an approximation.

Usage:
    python scripts/xfp/trade_simulator.py --give "Jordan Walker" --get "Riley Greene" --date 2024-06-01
    python scripts/xfp/trade_simulator.py --give "Sal Perez" --get "Ivan Herrera" --date 2024-04-01
"""
from __future__ import annotations
import argparse
import unicodedata
import re
from datetime import date as date_cls
from pathlib import Path
import pandas as pd
import numpy as np

from plv_clone.paths import ROOT
from plv_clone.fantasy.scoring import pitcher_fp
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'


PA_EVENTS = {
    'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play', 'field_out', 'force_out',
    'grounded_into_double_play', 'sac_fly', 'sac_bunt', 'fielders_choice',
    'fielders_choice_out', 'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


# Name join key — OWNER: plv_clone.utils.name_match.join_key (order-independent,
# so "Fried, Max" == "Max Fried"). NEVER re-derive locally: 127 local copies
# drifted apart and mis-keyed Ryan O'Hearn's curly apostrophe (2026-07-28).
from plv_clone.utils.name_match import join_key as _norm_sorted  # noqa: E402


def lookup_player_id(name: str) -> tuple[int, str, str] | None:
    """Returns (mlb_id, role, full_name). role: hitter/sp/rp/unknown."""
    nk = _norm_sorted(name)
    # Try hitters_multiyr first
    h = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv',
                     usecols=['batter', 'player_name', 'pa'])
    h['nk'] = h['player_name'].fillna('').map(_norm_sorted)
    m = h[h['nk'] == nk]
    if not m.empty:
        # Pick row with most PA (most likely real player not minors blip)
        row = m.sort_values('pa', ascending=False).iloc[0]
        return int(row['batter']), 'hitter', row['player_name']

    # Try SPs
    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv', usecols=['pitcher', 'player_name', 'gs'])
    sp['nk'] = sp['player_name'].fillna('').map(_norm_sorted)
    m = sp[sp['nk'] == nk]
    if not m.empty:
        row = m.sort_values('gs', ascending=False).iloc[0]
        return int(row['pitcher']), 'sp', row['player_name']

    # Try RPs
    rp = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv', usecols=['pitcher', 'name', 'g'])
    rp['nk'] = rp['name'].fillna('').map(_norm_sorted)
    m = rp[rp['nk'] == nk]
    if not m.empty:
        row = m.sort_values('g', ascending=False).iloc[0]
        return int(row['pitcher']), 'rp', row['name']

    return None


def hitter_fp_in_window(batter_id: int, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Compute hitter fp from statcast PA events in [start, end]."""
    year = start.year
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return {}
    df = pd.read_parquet(path, columns=[
        'game_date', 'batter', 'events', 'bat_score', 'post_bat_score',
        'fld_score', 'post_fld_score', 'on_1b', 'on_2b', 'on_3b'])
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[(df['batter'] == batter_id) & (df['game_date'] >= start) & (df['game_date'] <= end)
            & df['events'].isin(PA_EVENTS)]
    if df.empty:
        return {'fp': 0.0, 'pa': 0, 'tb': 0, 'bb': 0, 'k': 0, 'r': 0, 'rbi': 0, 'sb_proxy': 0}

    df = df.copy()
    df['tb'] = df['events'].map({'single':1,'double':2,'triple':3,'home_run':4}).fillna(0).astype(int)
    df['bb'] = df['events'].isin({'walk','intent_walk'}).astype(int)
    df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
    df['k'] = df['events'].isin({'strikeout','strikeout_double_play'}).astype(int)
    df['hr'] = (df['events'] == 'home_run').astype(int)
    df['rbi_proxy'] = (df['post_bat_score'] - df['bat_score']).fillna(0).clip(lower=0)
    # R proxy: batter scores if HR OR (post_bat_score - bat_score) > 0 AND on_3b had batter run home — too noisy
    # Use HR as a floor for R contribution; underestimates but consistent
    df['r_proxy'] = df['hr']  # conservative R estimate (HR scoring run)

    tb = int(df['tb'].sum())
    bb = int(df['bb'].sum())
    hbp = int(df['hbp'].sum())
    k = int(df['k'].sum())
    pa = len(df)
    rbi = float(df['rbi_proxy'].sum())
    r = int(df['r_proxy'].sum())

    # SB proxy: use year-aggregate sb_per_pa × PA in window
    h = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv',
                     usecols=['batter', 'year', 'sb_per_pa'])
    sb_rate = h[(h['batter'] == batter_id) & (h['year'] == year)]['sb_per_pa']
    sb = float(sb_rate.iloc[0]) * pa if not sb_rate.empty else 0.0

    # FP = TB + R + RBI + BB + HBP + SB - K
    fp = tb + r + rbi + bb + hbp + sb - k
    return {'fp': round(fp, 1), 'pa': pa, 'tb': tb, 'bb': bb, 'k': k,
            'r': r, 'rbi': round(rbi, 1), 'sb_proxy': round(sb, 1),
            'days': (end - start).days + 1}


def pitcher_fp_in_window(pitcher_id: int, start: pd.Timestamp, end: pd.Timestamp,
                          role: str = 'sp') -> dict:
    """Compute pitcher fp from statcast in [start, end]. Approximate IP from outs."""
    year = start.year
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return {}
    df = pd.read_parquet(path, columns=[
        'game_date', 'game_pk', 'pitcher', 'events', 'bat_score', 'post_bat_score',
        'inning'])
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[(df['pitcher'] == pitcher_id) & (df['game_date'] >= start) & (df['game_date'] <= end)]
    if df.empty:
        return {'fp': 0.0, 'g': 0, 'gs': 0, 'k': 0, 'bb': 0, 'h': 0, 'er': 0, 'ip': 0.0}

    pa = df[df['events'].isin(PA_EVENTS)].copy()
    pa['k'] = pa['events'].isin({'strikeout','strikeout_double_play'}).astype(int)
    pa['bb'] = pa['events'].isin({'walk','intent_walk'}).astype(int)
    pa['hbp'] = (pa['events'] == 'hit_by_pitch').astype(int)
    pa['h'] = pa['events'].isin({'single','double','triple','home_run'}).astype(int)
    pa['runs_allowed'] = (pa['post_bat_score'] - pa['bat_score']).fillna(0).clip(lower=0)
    pa['outs'] = (~pa['events'].isin({'single','double','triple','home_run','walk','intent_walk',
                                        'hit_by_pitch','field_error','catcher_interf'})).astype(int)

    games = pa['game_pk'].nunique()
    gs = pa[pa['inning'] == 1]['game_pk'].nunique() if 'inning' in pa.columns else 0
    k = int(pa['k'].sum()); bb = int(pa['bb'].sum()); hbp = int(pa['hbp'].sum())
    h = int(pa['h'].sum()); er = float(pa['runs_allowed'].sum())
    outs = int(pa['outs'].sum())
    ip = outs / 3.0

    fp = pitcher_fp(k=k, ip=ip, h=h, er=er, bb=bb, hbp=hbp)
    return {'fp': round(fp, 1), 'g': games, 'gs': gs, 'k': k, 'bb': bb,
            'h': h, 'er': round(er, 1), 'ip': round(ip, 1),
            'days': (end - start).days + 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--give', required=True, help='Player you would have traded AWAY')
    ap.add_argument('--get',  required=True, help='Player you would have RECEIVED')
    ap.add_argument('--date', required=True, help='Hypothetical trade date YYYY-MM-DD')
    ap.add_argument('--end', default=None, help='End date YYYY-MM-DD (default: season end or today)')
    args = ap.parse_args()

    give_info = lookup_player_id(args.give)
    get_info = lookup_player_id(args.get)
    if give_info is None:
        print(f'Could not find player: {args.give}'); return
    if get_info is None:
        print(f'Could not find player: {args.get}'); return

    start = pd.Timestamp(args.date)
    year = start.year
    if args.end:
        end = pd.Timestamp(args.end)
    else:
        if year == date_cls.today().year:
            end = pd.Timestamp(date_cls.today())
        else:
            end = pd.Timestamp(f'{year}-09-30')

    print(f'\nHypothetical trade on {args.date}')
    print(f'  GIVE: {give_info[2]} (id={give_info[0]}, role={give_info[1]})')
    print(f'  GET:  {get_info[2]} (id={get_info[0]}, role={get_info[1]})')
    print(f'  Window: {start.date()} -> {end.date()} ({(end - start).days + 1} days)')

    def compute(info):
        bid, role, _ = info
        if role == 'hitter':
            return hitter_fp_in_window(bid, start, end), 'hitter'
        elif role in ('sp', 'rp'):
            return pitcher_fp_in_window(bid, start, end, role), role
        return {}, 'unknown'

    give_res, give_role = compute(give_info)
    get_res, get_role = compute(get_info)

    print(f'\n{"=" * 60}')
    print(f'GIVE: {give_info[2]} ({give_role})')
    for k, v in give_res.items(): print(f'  {k:<10s} {v}')
    print(f'\nGET:  {get_info[2]} ({get_role})')
    for k, v in get_res.items(): print(f'  {k:<10s} {v}')

    net = get_res.get('fp', 0) - give_res.get('fp', 0)
    print(f'\n{"=" * 60}')
    sign = '+' if net >= 0 else '−'
    verdict = 'WIN' if net >= 0 else 'LOSS'
    print(f'NET fp delta (got − gave): {sign}{abs(net):.1f}  [{verdict} for the proposed trade]')
    print(f'{"=" * 60}\n')


if __name__ == '__main__':
    main()
