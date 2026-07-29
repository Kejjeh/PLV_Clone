"""build_park_factors.py — per-park run-environment factors from statcast.

For each ballpark (= home_team), compare offensive output IN that park to the
overall offensive output of the same teams when playing AWAY. This isolates
park effect from team-quality bias (a Coors team's offensive numbers at home
include their own players' bats, but if those same players play away half the
time, the difference IS the park).

Output: data/research/xfp_cache/park_factors.csv
  team_abbr, park_factor, n_pa_home, n_pa_away

Where park_factor = home_xwOBA / away_xwOBA, league-mean-normalized.
1.00 = neutral; >1.00 = hitter-friendly; <1.00 = pitcher-friendly.

Uses 2022-2025 (4 seasons, ~600k PAs) to stabilize.
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'park_factors.csv'
YEARS = [2022, 2023, 2024, 2025]


def main():
    print('=== build_park_factors ===')
    rows = []
    NON_PA = {'stolen_base_2b','stolen_base_3b','stolen_base_home',
              'caught_stealing_2b','caught_stealing_3b','caught_stealing_home',
              'pickoff_1b','pickoff_2b','pickoff_3b',
              'wild_pitch','passed_ball','balk'}
    frames = []
    for yr in YEARS:
        path = CACHE / f'statcast_{yr}.parquet'
        if not path.exists():
            continue
        sc = pd.read_parquet(path, columns=['game_pk','events','home_team','away_team',
                                             'inning_topbot','woba_value','woba_denom',
                                             'estimated_woba_using_speedangle'])
        ev = sc['events'].fillna('')
        sc['is_pa'] = (ev != '') & ~ev.isin(NON_PA)
        woba_v = pd.to_numeric(sc['woba_value'], errors='coerce')
        woba_d = pd.to_numeric(sc['woba_denom'], errors='coerce')
        xwoba = pd.to_numeric(sc['estimated_woba_using_speedangle'], errors='coerce')
        sc['woba_v_eff'] = woba_v
        bip_with = sc['is_pa'] & ~ev.isin({'strikeout','walk','hit_by_pitch'}) & xwoba.notna()
        sc.loc[bip_with, 'woba_v_eff'] = xwoba[bip_with]
        sc['woba_d_eff'] = woba_d
        # Each PA's batting team:
        sc['bat_team'] = np.where(sc['inning_topbot'] == 'Top', sc['away_team'], sc['home_team'])
        # The PARK is identified by home_team
        sc['park'] = sc['home_team']
        sc['is_home_team_batting'] = (sc['bat_team'] == sc['home_team'])
        frames.append(sc[sc['is_pa']][['park','bat_team','is_home_team_batting',
                                        'woba_v_eff','woba_d_eff']])
        print(f'  [{yr}] {len(sc[sc["is_pa"]]):,} PAs')
    if not frames:
        print('No data — abort'); return
    big = pd.concat(frames, ignore_index=True)

    # For each (park, bat_team) compute xwOBA. Then for each TEAM aggregate:
    #   home_xwoba  = avg xwoba when batting AT their home park
    #   away_xwoba  = avg xwoba when batting AT other parks
    # Then park_factor for park P = (xwOBA at P) / (xwOBA at all other parks),
    # averaged across all teams that visit park P.

    # Per (park, bat_team): xwOBA + n_pa
    by_pt = big.groupby(['park','bat_team']).agg(
        wv=('woba_v_eff','sum'),
        wd=('woba_d_eff','sum'),
        n=('woba_v_eff','size'),
    ).reset_index()
    by_pt['xwoba'] = by_pt['wv'] / by_pt['wd'].replace(0, np.nan)

    # For each team, what's their xwOBA at NON-home parks?
    by_team_away = big[big['park'] != big['bat_team']].groupby('bat_team').agg(
        wv=('woba_v_eff','sum'), wd=('woba_d_eff','sum'), n=('woba_v_eff','size'),
    ).reset_index().rename(columns={'wv':'wv_away','wd':'wd_away','n':'n_away'})
    by_team_away['team_away_xwoba'] = by_team_away['wv_away'] / by_team_away['wd_away'].replace(0, np.nan)

    by_pt = by_pt.merge(by_team_away[['bat_team','team_away_xwoba']], on='bat_team', how='left')
    by_pt['rel_factor'] = by_pt['xwoba'] / by_pt['team_away_xwoba']

    # Per park, avg rel_factor across teams visiting (weighted by PAs)
    park_agg = by_pt.dropna(subset=['rel_factor']).groupby('park').agg(
        park_factor=('rel_factor', lambda s: float(np.average(s, weights=by_pt.loc[s.index, 'n']))),
        n_pa=('n','sum'),
    ).reset_index().rename(columns={'park':'team_abbr'})

    # Normalize so league-mean = 1.00
    league_mean = float(park_agg['park_factor'].mean())
    park_agg['park_factor'] = park_agg['park_factor'] / league_mean
    park_agg['park_factor'] = park_agg['park_factor'].round(4)
    park_agg = park_agg.sort_values('park_factor', ascending=False).reset_index(drop=True)

    park_agg.to_csv(OUT, index=False)
    print(f'\nWrote {OUT}: {len(park_agg)} parks')
    print('\nMost hitter-friendly:')
    print(park_agg.head(7).to_string(index=False))
    print('\nMost pitcher-friendly:')
    print(park_agg.tail(7).to_string(index=False))


if __name__ == '__main__':
    main()
