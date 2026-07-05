"""build_weekly_fp_substrate.py — per-player per-week fp totals for 2024-2026.

Builds the data that powers the dashboard's interactive trade simulator.
For each player with a statcast appearance in 2024-2026, computes weekly
totals so the UI can show a week-by-week counterfactual.

Scope: players currently in ESPN league rosters + top free agents in our
RH3/RP3 projections (so any trade-target backtest has data).

Output: data/outputs/weekly_fp_substrate.json
  Structure:
    {
      'weeks': ['2024-03-25', '2024-04-01', ..., '2026-09-29'],
      'players': [
        {
          'pid': 605141, 'name': 'Mookie Betts', 'role': 'hitter',
          'team': 'LAD',
          'weekly_fp': {2024: [12.4, 8.1, ...], 2025: [...], 2026: [...]}
        }, ...
      ]
    }
"""
from __future__ import annotations
import json
import unicodedata
import re
from pathlib import Path
import pandas as pd
import numpy as np

from plv_clone.projections import PROJECTIONS
from plv_clone.paths import ROOT, CACHE, OUTPUTS as OUT

YEARS = [2024, 2025, 2026]
PA_EVENTS = {
    'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play', 'field_out', 'force_out',
    'grounded_into_double_play', 'sac_fly', 'sac_bunt', 'fielders_choice',
    'fielders_choice_out', 'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


# _norm routed to the name_match owner (item 10, 2026-07-04). Self-consistent
# (ESPN/rh3/rp3 name keys all built with this helper). join_key adds sorted-token
# order-independence — strictly correct (zero false-merge), and fixes cross-format
# matching (rp3 player_name is "Last, First" vs ESPN/rh3 "First Last").
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402


def get_scope_player_ids() -> tuple[set[int], set[int], dict]:
    """Return (batter_ids, pitcher_ids, id_to_name_map) of players to include."""
    name_map = {}

    # All players in ESPN league rosters (228 players)
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from plv_clone.league_state import LeagueState
        ls = LeagueState()
        teams = ls.all_teams()
        espn_names = set(_norm(n) for n in teams['player_name'].dropna())
    except Exception as e:
        print(f'  ESPN unavailable: {e}')
        espn_names = set()

    # rh3 / rp3 give us batter/pitcher IDs + names
    bat_ids, pit_ids = set(), set()
    rh = PROJECTIONS.rh3()
    rh['nk'] = rh['player_name'].map(_norm)
    # Include rostered + top-100 FAs
    for _, r in rh.head(150).iterrows():
        bat_ids.add(int(r['batter']))
        name_map[int(r['batter'])] = r['player_name']
    for _, r in rh.iterrows():
        if r['nk'] in espn_names:
            bat_ids.add(int(r['batter']))
            name_map[int(r['batter'])] = r['player_name']

    rp = PROJECTIONS.rp3()
    rp['nk'] = rp['player_name'].map(_norm)
    for _, r in rp.head(150).iterrows():
        pit_ids.add(int(r['pitcher']))
        name_map[int(r['pitcher'])] = r['player_name']
    for _, r in rp.iterrows():
        if r['nk'] in espn_names:
            pit_ids.add(int(r['pitcher']))
            name_map[int(r['pitcher'])] = r['player_name']

    return bat_ids, pit_ids, name_map


def week_starts(year: int) -> list[pd.Timestamp]:
    """ISO Mondays from Mar 18 through Sep 29 of year (covers MLB regular season)."""
    start = pd.Timestamp(year=year, month=3, day=18)
    end = pd.Timestamp(year=year, month=9, day=29)
    return list(pd.date_range(start, end, freq='W-MON'))


def hitter_weekly(df: pd.DataFrame, batter_ids: set, weeks: list[pd.Timestamp],
                  hitter_year_rates: dict) -> dict:
    """{pid: [fp_week_0, fp_week_1, ...]}"""
    df = df[df['batter'].isin(batter_ids) & df['events'].isin(PA_EVENTS)].copy()
    if df.empty:
        return {}
    df['tb'] = df['events'].map({'single':1,'double':2,'triple':3,'home_run':4}).fillna(0).astype(int)
    df['bb'] = df['events'].isin({'walk','intent_walk'}).astype(int)
    df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
    df['k'] = df['events'].isin({'strikeout','strikeout_double_play'}).astype(int)
    df['hr'] = (df['events'] == 'home_run').astype(int)
    df['rbi_proxy'] = (df['post_bat_score'] - df['bat_score']).fillna(0).clip(lower=0)

    # week_idx = how many weeks since first Monday
    first = weeks[0]
    df['week_idx'] = ((df['game_date'] - first).dt.days // 7).clip(lower=0, upper=len(weeks)-1)

    agg = df.groupby(['batter', 'week_idx']).agg(
        pa=('events', 'count'),
        tb=('tb', 'sum'), bb=('bb', 'sum'), hbp=('hbp', 'sum'), k=('k', 'sum'),
        hr=('hr', 'sum'), rbi=('rbi_proxy', 'sum')).reset_index()

    out = {}
    for _, r in agg.iterrows():
        pid = int(r['batter'])
        wi = int(r['week_idx'])
        # FP = TB + R(HR proxy) + RBI + BB + HBP + SB - K
        sb_rate = hitter_year_rates.get(pid, 0.0)
        sb = sb_rate * r['pa']
        fp = r['tb'] + r['hr'] + r['rbi'] + r['bb'] + r['hbp'] + sb - r['k']
        out.setdefault(pid, [0.0] * len(weeks))[wi] = round(float(fp), 1)
    return out


def pitcher_weekly(df: pd.DataFrame, pitcher_ids: set, weeks: list[pd.Timestamp]) -> dict:
    df = df[df['pitcher'].isin(pitcher_ids)].copy()
    if df.empty:
        return {}
    pa = df[df['events'].isin(PA_EVENTS)].copy()
    pa['k'] = pa['events'].isin({'strikeout','strikeout_double_play'}).astype(int)
    pa['bb'] = pa['events'].isin({'walk','intent_walk'}).astype(int)
    pa['hbp'] = (pa['events'] == 'hit_by_pitch').astype(int)
    pa['h'] = pa['events'].isin({'single','double','triple','home_run'}).astype(int)
    pa['runs'] = (pa['post_bat_score'] - pa['bat_score']).fillna(0).clip(lower=0)
    pa['outs'] = (~pa['events'].isin({'single','double','triple','home_run','walk','intent_walk',
                                       'hit_by_pitch','field_error','catcher_interf'})).astype(int)

    first = weeks[0]
    pa['week_idx'] = ((pa['game_date'] - first).dt.days // 7).clip(lower=0, upper=len(weeks)-1)

    agg = pa.groupby(['pitcher', 'week_idx']).agg(
        k=('k', 'sum'), bb=('bb', 'sum'), hbp=('hbp', 'sum'),
        h=('h', 'sum'), runs=('runs', 'sum'), outs=('outs', 'sum')).reset_index()
    agg['ip'] = agg['outs'] / 3.0
    agg['fp'] = (agg['k'] + agg['ip'] * 3.3 - agg['h'] - 2 * agg['runs']
                 - agg['bb'] - agg['hbp'])

    out = {}
    for _, r in agg.iterrows():
        pid = int(r['pitcher'])
        wi = int(r['week_idx'])
        out.setdefault(pid, [0.0] * len(weeks))[wi] = round(float(r['fp']), 1)
    return out


def main():
    bat_ids, pit_ids, name_map = get_scope_player_ids()
    print(f'Scope: {len(bat_ids)} hitters, {len(pit_ids)} pitchers ({len(name_map)} named)')

    # Year-aggregate sb_per_pa for hitter SB proxy
    h_multiyr = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv',
                             usecols=['batter', 'year', 'sb_per_pa'])

    out_players = {}
    all_weeks = {}
    for year in YEARS:
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        weeks = week_starts(year)
        all_weeks[year] = [w.strftime('%Y-%m-%d') for w in weeks]
        print(f'\n[{year}] {len(weeks)} weeks, loading...')

        df = pd.read_parquet(path, columns=[
            'game_date', 'batter', 'pitcher', 'events',
            'bat_score', 'post_bat_score'])
        df['game_date'] = pd.to_datetime(df['game_date'])

        # SB rate lookup
        sb_yr = h_multiyr[h_multiyr['year'] == year].set_index('batter')['sb_per_pa'].to_dict()

        hw = hitter_weekly(df, bat_ids, weeks, sb_yr)
        pw = pitcher_weekly(df, pit_ids, weeks)
        print(f'  hitters with data: {len(hw)}, pitchers with data: {len(pw)}')

        for pid, fp_list in hw.items():
            rec = out_players.setdefault(pid, {
                'pid': pid, 'name': name_map.get(pid, str(pid)),
                'role': 'hitter', 'weekly_fp': {}})
            rec['weekly_fp'][str(year)] = fp_list
        for pid, fp_list in pw.items():
            rec = out_players.setdefault(pid, {
                'pid': pid, 'name': name_map.get(pid, str(pid)),
                'role': 'pitcher', 'weekly_fp': {}})
            rec['weekly_fp'][str(year)] = fp_list

    out = {
        'weeks': all_weeks,
        'players': sorted(out_players.values(),
                           key=lambda x: str(x['name']) if x['name'] is not None else ''),
    }
    fname = OUT / 'weekly_fp_substrate.json'
    with open(fname, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f'\nwrote {fname} ({len(out["players"])} players, {fname.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
