"""
build_team_strength.py — per-team batting + pitching strength index for the
current season, used by RH3/RP3 schedule-strength adjustment.

For each MLB team:
  bat_xwoba_for       = team batting xwOBA/PA (offense)
  pit_xwoba_against   = team pitching xwOBA/PA allowed (pitching)
  bat_fp_per_pa       = team batting FP/PA (with R+RBI proxy, simple core form)
  bat_index           = bat_xwoba_for / league_mean    (>1 = good lineup)
  pit_index           = pit_xwoba_against / league_mean  (>1 = bad pitching)

Output: data/research/xfp_cache/team_strength_2026.csv
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'team_strength_2026.csv'

NON_PA = {
    'stolen_base_2b', 'stolen_base_3b', 'stolen_base_home',
    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
    'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
    'wild_pitch', 'passed_ball', 'balk',
}


def main(year: int = 2026):
    sc = pd.read_parquet(CACHE / f'statcast_{year}.parquet')
    sc['game_date'] = pd.to_datetime(sc['game_date'])
    sc['bat_team'] = np.where(sc['inning_topbot'] == 'Top', sc['away_team'], sc['home_team'])
    sc['pit_team'] = np.where(sc['inning_topbot'] == 'Top', sc['home_team'], sc['away_team'])

    ev = sc['events'].fillna('')
    sc['is_pa'] = (ev != '') & ~ev.isin(NON_PA)
    sc['woba_v'] = pd.to_numeric(sc.get('woba_value'), errors='coerce')
    sc['woba_d'] = pd.to_numeric(sc.get('woba_denom'), errors='coerce')
    xwoba = pd.to_numeric(sc.get('estimated_woba_using_speedangle'), errors='coerce')
    sc['woba_v_eff'] = sc['woba_v']
    bip_with = sc['is_pa'] & ~ev.isin({'strikeout','walk','hit_by_pitch'}) & xwoba.notna()
    sc.loc[bip_with, 'woba_v_eff'] = xwoba[bip_with]

    # Recent (last 21 days) window for short-term form
    cutoff = sc['game_date'].max()
    recent = sc[sc['game_date'] > cutoff - pd.Timedelta(days=21)]

    def agg(df: pd.DataFrame, group_col: str, label: str) -> pd.DataFrame:
        g = df[df['is_pa']].groupby(group_col).agg(
            pa=('is_pa', 'sum'),
            woba_v=('woba_v_eff', 'sum'),
            woba_d=('woba_d', 'sum'),
        ).reset_index()
        g['xwoba'] = g['woba_v'] / g['woba_d'].replace(0, np.nan)
        g = g.rename(columns={'pa': f'pa_{label}', 'xwoba': f'xwoba_{label}'})
        g = g[[group_col, f'pa_{label}', f'xwoba_{label}']]
        return g

    bat_to = agg(sc, 'bat_team', 'bat_to')
    bat_recent = agg(recent, 'bat_team', 'bat_recent')
    pit_to = agg(sc, 'pit_team', 'pit_to')
    pit_recent = agg(recent, 'pit_team', 'pit_recent')

    bat_to = bat_to.rename(columns={'bat_team': 'team'})
    bat_recent = bat_recent.rename(columns={'bat_team': 'team'})
    pit_to = pit_to.rename(columns={'pit_team': 'team'})
    pit_recent = pit_recent.rename(columns={'pit_team': 'team'})

    df = bat_to.merge(bat_recent, on='team', how='outer') \
               .merge(pit_to, on='team', how='outer') \
               .merge(pit_recent, on='team', how='outer')

    league_bat = float(np.nansum(df['xwoba_bat_to'] * df['pa_bat_to']) / df['pa_bat_to'].sum())
    league_pit = float(np.nansum(df['xwoba_pit_to'] * df['pa_pit_to']) / df['pa_pit_to'].sum())
    df['bat_index']        = df['xwoba_bat_to'] / league_bat
    df['bat_index_recent'] = df['xwoba_bat_recent'] / league_bat
    df['pit_index']        = df['xwoba_pit_to'] / league_pit
    df['pit_index_recent'] = df['xwoba_pit_recent'] / league_pit

    for c in ['xwoba_bat_to', 'xwoba_bat_recent', 'xwoba_pit_to', 'xwoba_pit_recent',
              'bat_index', 'bat_index_recent', 'pit_index', 'pit_index_recent']:
        if c in df.columns:
            df[c] = df[c].astype(float).round(4)

    df = df.sort_values('bat_index', ascending=False).reset_index(drop=True)
    df.to_csv(OUT, index=False)
    print(f'Wrote {OUT}: {len(df)} teams')
    print(f'  league bat xwOBA = {league_bat:.4f}, pit xwOBA = {league_pit:.4f}')
    print(f'  Strongest lineups (bat_index):')
    print(df[['team', 'pa_bat_to', 'xwoba_bat_to', 'bat_index', 'bat_index_recent']].head(5).to_string(index=False))
    print(f'  Best pitching staffs (lowest pit_index):')
    print(df.sort_values('pit_index')[['team', 'pa_pit_to', 'xwoba_pit_to', 'pit_index', 'pit_index_recent']].head(5).to_string(index=False))


if __name__ == '__main__':
    main()
