"""build_park_factors_by_year.py — per-year per-team park factors.

Extends build_park_factors.py (which produces a single pooled 2022-2025
factor per team) to a year-by-year cache covering 2018-2026.

Methodology (same as build_park_factors.py, per year):
  For each year:
    For each (park=home_team, bat_team):
      xwOBA at park, n PAs
    For each bat_team:
      team away xwOBA = xwOBA across all parks != home
    park rel_factor = (xwOBA at P by team T) / (team T away xwOBA)
    Aggregate per park: weighted mean of rel_factor across visiting teams
    Normalize so league mean = 1.00 per year.

Three outputs per (year, park):
  pf_wOBA — xwOBA-based hitter-friendliness  (>1.00 = hitter-friendly)
  pf_HR   — HR-rate-based                    (>1.00 = HR-friendly)
  pf_R    — run-event proxy (1B+2B+3B+HR per PA, normalized)

NOTES / v1 LIMITATIONS:
  - Each year stands alone (no Bayesian shrinkage to a multi-year prior).
    A single-season factor for an oddball park-year (e.g. weather) will
    be noisier than a 3-year rolling factor. This is acceptable for the
    purpose of testing whether park exposure has ANY predictive lift.
  - Park identity assumed = home_team abbr. Stadium changes inside a
    season (e.g. ATH 2025 Sutter Health Park) are NOT split out.
  - 2020 is included as-is despite the 60-game COVID season (~30k PAs);
    factor noise will be higher that year.
  - 2026 (in progress) included — early-season factors are noisy by
    construction.

Output: data/research/xfp_cache/park_factors_2018_2026.csv
  columns: year, team_abbr, pf_wOBA, pf_HR, pf_R, n_pa
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'park_factors_2018_2026.csv'
YEARS = list(range(2018, 2027))

NON_PA = {'stolen_base_2b', 'stolen_base_3b', 'stolen_base_home',
          'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
          'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
          'wild_pitch', 'passed_ball', 'balk'}

HIT_EVENTS = {'single', 'double', 'triple', 'home_run'}


def per_year_factors(sc: pd.DataFrame) -> pd.DataFrame:
    """Compute per-park pf_wOBA, pf_HR, pf_R for one year's statcast frame."""
    ev = sc['events'].fillna('')
    sc = sc.copy()
    sc['is_pa'] = (ev != '') & ~ev.isin(NON_PA)
    sc = sc[sc['is_pa']].copy()
    woba_v = pd.to_numeric(sc['woba_value'], errors='coerce')
    woba_d = pd.to_numeric(sc['woba_denom'], errors='coerce')
    xwoba = pd.to_numeric(sc['estimated_woba_using_speedangle'], errors='coerce')
    sc['woba_v_eff'] = woba_v
    bip_with = ~ev.loc[sc.index].isin({'strikeout', 'walk', 'hit_by_pitch'}) & xwoba.notna()
    sc.loc[bip_with, 'woba_v_eff'] = xwoba[bip_with]
    sc['woba_d_eff'] = woba_d
    sc['is_hr'] = (ev.loc[sc.index] == 'home_run').astype(int)
    sc['is_hit'] = ev.loc[sc.index].isin(HIT_EVENTS).astype(int)

    sc['bat_team'] = np.where(sc['inning_topbot'] == 'Top',
                              sc['away_team'], sc['home_team'])
    sc['park'] = sc['home_team']

    # Per (park, bat_team) aggregates
    by_pt = sc.groupby(['park', 'bat_team']).agg(
        wv=('woba_v_eff', 'sum'),
        wd=('woba_d_eff', 'sum'),
        hr=('is_hr', 'sum'),
        hit=('is_hit', 'sum'),
        n=('woba_v_eff', 'size'),
    ).reset_index()
    by_pt['xwoba'] = by_pt['wv'] / by_pt['wd'].replace(0, np.nan)
    by_pt['hr_rate'] = by_pt['hr'] / by_pt['n'].replace(0, np.nan)
    by_pt['hit_rate'] = by_pt['hit'] / by_pt['n'].replace(0, np.nan)

    # Per bat_team: away (visiting) rates as baseline
    away = sc[sc['park'] != sc['bat_team']].groupby('bat_team').agg(
        wv=('woba_v_eff', 'sum'),
        wd=('woba_d_eff', 'sum'),
        hr=('is_hr', 'sum'),
        hit=('is_hit', 'sum'),
        n=('woba_v_eff', 'size'),
    ).reset_index()
    away['team_away_xwoba'] = away['wv'] / away['wd'].replace(0, np.nan)
    away['team_away_hr_rate'] = away['hr'] / away['n'].replace(0, np.nan)
    away['team_away_hit_rate'] = away['hit'] / away['n'].replace(0, np.nan)

    by_pt = by_pt.merge(
        away[['bat_team', 'team_away_xwoba', 'team_away_hr_rate', 'team_away_hit_rate']],
        on='bat_team', how='left')
    by_pt['rel_woba'] = by_pt['xwoba'] / by_pt['team_away_xwoba']
    by_pt['rel_hr'] = by_pt['hr_rate'] / by_pt['team_away_hr_rate']
    by_pt['rel_r'] = by_pt['hit_rate'] / by_pt['team_away_hit_rate']

    def wavg(col):
        def _f(s):
            w = by_pt.loc[s.index, 'n']
            sm = w.sum()
            if sm == 0:
                return np.nan
            return float(np.average(s.fillna(s.mean() if s.notna().any() else 0),
                                    weights=w))
        return _f

    park = by_pt.dropna(subset=['rel_woba']).groupby('park').agg(
        pf_wOBA=('rel_woba', wavg('rel_woba')),
        pf_HR=('rel_hr', wavg('rel_hr')),
        pf_R=('rel_r', wavg('rel_r')),
        n_pa=('n', 'sum'),
    ).reset_index().rename(columns={'park': 'team_abbr'})

    # Normalize each factor so league mean = 1.00
    for col in ('pf_wOBA', 'pf_HR', 'pf_R'):
        mu = float(park[col].mean())
        if mu > 0:
            park[col] = park[col] / mu
        park[col] = park[col].round(4)
    return park


def main():
    print('=== build_park_factors_by_year ===')
    rows = []
    for yr in YEARS:
        path = CACHE / f'statcast_{yr}.parquet'
        if not path.exists():
            print(f'  [{yr}] missing parquet — skip')
            continue
        sc = pd.read_parquet(path, columns=['events', 'home_team', 'away_team',
                                            'inning_topbot', 'woba_value', 'woba_denom',
                                            'estimated_woba_using_speedangle'])
        pf = per_year_factors(sc)
        pf['year'] = yr
        rows.append(pf)
        print(f'  [{yr}] {len(pf)} parks, n_pa={int(pf["n_pa"].sum()):,}')
    if not rows:
        print('No data — abort'); return
    out = pd.concat(rows, ignore_index=True)[
        ['year', 'team_abbr', 'pf_wOBA', 'pf_HR', 'pf_R', 'n_pa']
    ].sort_values(['year', 'team_abbr']).reset_index(drop=True)
    out.to_csv(OUT, index=False)
    print(f'\nWrote {OUT}: {len(out)} rows')
    # Quick sanity check: COL pf_wOBA should be > 1
    print('\nCOL across years (sanity, expect >1.0 most years):')
    print(out[out['team_abbr'] == 'COL'][['year', 'pf_wOBA', 'pf_HR']].to_string(index=False))
    print('\nSEA / SD / OAK across years (expect <1.0 most years):')
    print(out[out['team_abbr'].isin(['SEA', 'SD', 'OAK', 'ATH'])][
        ['year', 'team_abbr', 'pf_wOBA']].to_string(index=False))


if __name__ == '__main__':
    main()
