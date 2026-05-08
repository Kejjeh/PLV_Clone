"""build_handedness_splits.py — pitcher L/R splits + team lineup hand mix.

Outputs:
  data/research/xfp_cache/pitcher_splits.csv
    pitcher, year, p_throws, tbf_vs_L, tbf_vs_R, xwoba_vs_L, xwoba_vs_R
    Multi-year aggregation (2022-2025) for stability.

  data/research/xfp_cache/team_handedness.csv
    team_abbr, year, pct_lhb, pct_rhb, n_pa
    Per-team batting handedness mix.
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
YEARS = [2022, 2023, 2024, 2025, 2026]

NON_PA = {'stolen_base_2b','stolen_base_3b','stolen_base_home',
          'caught_stealing_2b','caught_stealing_3b','caught_stealing_home',
          'pickoff_1b','pickoff_2b','pickoff_3b',
          'wild_pitch','passed_ball','balk'}


def annotate_pa(sc):
    ev = sc['events'].fillna('')
    sc['is_pa'] = (ev != '') & ~ev.isin(NON_PA)
    woba_v = pd.to_numeric(sc['woba_value'], errors='coerce')
    woba_d = pd.to_numeric(sc['woba_denom'], errors='coerce')
    xwoba = pd.to_numeric(sc['estimated_woba_using_speedangle'], errors='coerce')
    sc['woba_v_eff'] = woba_v
    bip_with = sc['is_pa'] & ~ev.isin({'strikeout','walk','hit_by_pitch'}) & xwoba.notna()
    sc.loc[bip_with, 'woba_v_eff'] = xwoba[bip_with]
    sc['woba_d_eff'] = woba_d
    return sc


def build_pitcher_splits():
    """Per-(pitcher, year, vs_stand) split. Aggregate to wide format with vs_L and vs_R columns."""
    frames = []
    for yr in YEARS:
        path = CACHE / f'statcast_{yr}.parquet'
        if not path.exists(): continue
        sc = pd.read_parquet(path, columns=['pitcher','stand','p_throws','events',
                                             'woba_value','woba_denom',
                                             'estimated_woba_using_speedangle'])
        sc = annotate_pa(sc)
        sc = sc[sc['is_pa']].copy()
        sc = sc[sc['stand'].isin(['L','R'])]
        agg = sc.groupby(['pitcher','p_throws','stand']).agg(
            tbf=('is_pa', 'sum'),
            wv=('woba_v_eff', 'sum'),
            wd=('woba_d_eff', 'sum'),
        ).reset_index()
        agg['xwoba'] = agg['wv'] / agg['wd'].replace(0, np.nan)
        agg['year'] = yr
        frames.append(agg)
        print(f'  pitcher splits [{yr}]: {agg["pitcher"].nunique()} pitchers')
    big = pd.concat(frames, ignore_index=True)
    # Pivot: one row per (pitcher, year), columns vs_L/vs_R
    pvt = big.pivot_table(index=['pitcher','year','p_throws'],
                          columns='stand',
                          values=['tbf','xwoba'],
                          aggfunc='first').reset_index()
    pvt.columns = [f'{a}_vs_{b}' if b else a for a, b in pvt.columns]
    pvt = pvt.rename(columns={'pitcher_vs_': 'pitcher', 'year_vs_': 'year',
                               'p_throws_vs_': 'p_throws'})
    out = CACHE / 'pitcher_splits.csv'
    pvt.to_csv(out, index=False)
    print(f'\nWrote {out}: {len(pvt)} (pitcher, year) rows')
    return pvt


def build_team_handedness():
    """Per (team, year), batting PA distribution by handedness."""
    frames = []
    for yr in YEARS:
        path = CACHE / f'statcast_{yr}.parquet'
        if not path.exists(): continue
        sc = pd.read_parquet(path, columns=['stand','events','home_team','away_team',
                                             'inning_topbot','woba_value','woba_denom',
                                             'estimated_woba_using_speedangle'])
        sc = annotate_pa(sc)
        sc = sc[sc['is_pa']].copy()
        sc = sc[sc['stand'].isin(['L','R'])]
        sc['bat_team'] = np.where(sc['inning_topbot'] == 'Top', sc['away_team'], sc['home_team'])
        agg = sc.groupby(['bat_team','stand']).agg(n_pa=('is_pa','sum')).reset_index()
        agg['year'] = yr
        frames.append(agg)
    big = pd.concat(frames, ignore_index=True)
    # Pivot to L/R columns
    pvt = big.pivot_table(index=['bat_team','year'], columns='stand',
                          values='n_pa', aggfunc='first', fill_value=0).reset_index()
    pvt.columns.name = None
    pvt = pvt.rename(columns={'L':'n_lhb_pa', 'R':'n_rhb_pa'})
    pvt['n_pa'] = pvt['n_lhb_pa'] + pvt['n_rhb_pa']
    pvt['pct_lhb'] = pvt['n_lhb_pa'] / pvt['n_pa'].replace(0, np.nan)
    pvt['pct_rhb'] = pvt['n_rhb_pa'] / pvt['n_pa'].replace(0, np.nan)
    pvt = pvt.rename(columns={'bat_team':'team_abbr'})
    out = CACHE / 'team_handedness.csv'
    pvt.to_csv(out, index=False)
    print(f'\nWrote {out}: {len(pvt)} (team, year) rows')
    return pvt


def main():
    print('=== build_handedness_splits ===\n')
    p = build_pitcher_splits()
    t = build_team_handedness()

    # Sanity check: known LHP — Sheehan should have decent splits
    print('\n--- Pitcher splits sanity check (recent 2025) ---')
    p25 = p[p['year'] == 2025]
    sample = p25[p25['tbf_vs_L'].fillna(0) + p25['tbf_vs_R'].fillna(0) >= 100]
    sample = sample.head(8)
    print(f'  LHP/RHP count: {p25.groupby("p_throws").size().to_dict()}')
    print(f'  Mean xwoba_vs_L: {p25["xwoba_vs_L"].mean():.4f}')
    print(f'  Mean xwoba_vs_R: {p25["xwoba_vs_R"].mean():.4f}')
    print(f'  Among LHP: vs_L mean = {p25[p25["p_throws"]=="L"]["xwoba_vs_L"].mean():.4f}, '
          f'vs_R mean = {p25[p25["p_throws"]=="L"]["xwoba_vs_R"].mean():.4f}')
    print(f'  Among RHP: vs_L mean = {p25[p25["p_throws"]=="R"]["xwoba_vs_L"].mean():.4f}, '
          f'vs_R mean = {p25[p25["p_throws"]=="R"]["xwoba_vs_R"].mean():.4f}')

    print('\n--- Team handedness 2025 (top LHB-heavy lineups) ---')
    t25 = t[t['year'] == 2025].sort_values('pct_lhb', ascending=False)
    print(t25.head(7)[['team_abbr','n_pa','pct_lhb','pct_rhb']].to_string(index=False))
    print('  Bottom (heaviest RHB lineups):')
    print(t25.tail(7)[['team_abbr','n_pa','pct_lhb','pct_rhb']].to_string(index=False))


if __name__ == '__main__':
    main()
