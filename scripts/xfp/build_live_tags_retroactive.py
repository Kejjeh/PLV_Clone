"""build_live_tags_retroactive.py — Reconstruct HIGH-K-ARM + shadow-scout
percentile features per (pitcher, year) from statcast cache, 2018-2025.

Outputs:
  data/research/historical_panel/sp_live_tags_retroactive.parquet

Columns per (mlbam_id, year):
  n_pitches, n_bf
  k_pct, bb_pct, whiff_pct, csw_pct, fb_velo
  high_k_z_year                  (Step 1 — HIGH-K-ARM)
  shadow_velo_pct, shadow_k_pct, shadow_bb_pct, shadow_whiff_pct, shadow_csw_pct
                                  (Step 2 — shadow-scout, percentile-rank within year, pitch>=200 floor)
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'research' / 'historical_panel' / 'sp_live_tags_retroactive.parquet'

YEARS = list(range(2018, 2026))  # 2018-2025
FB_TYPES = {'FF', 'SI', 'FC', 'FA'}
SWING_DESCS = {'foul', 'hit_into_play', 'swinging_strike', 'foul_tip',
               'swinging_strike_blocked', 'foul_bunt', 'missed_bunt', 'bunt_foul_tip'}
WHIFF_DESCS = {'swinging_strike', 'swinging_strike_blocked', 'missed_bunt'}
CSW_DESCS = {'called_strike', 'swinging_strike', 'swinging_strike_blocked'}
PA_END_EVENTS = {'strikeout', 'walk', 'hit_by_pitch', 'intent_walk',
                 'single', 'double', 'triple', 'home_run', 'field_out',
                 'force_out', 'grounded_into_double_play', 'sac_fly', 'sac_bunt',
                 'field_error', 'double_play', 'fielders_choice',
                 'fielders_choice_out', 'strikeout_double_play', 'sac_fly_double_play',
                 'triple_play', 'catcher_interf'}

def agg_year(year: int) -> pd.DataFrame:
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        print(f'  skip {year} (no cache)')
        return pd.DataFrame()
    cols = ['pitcher', 'events', 'description', 'release_speed', 'pitch_type', 'game_date']
    df = pd.read_parquet(path, columns=cols)
    df['is_swing'] = df['description'].isin(SWING_DESCS)
    df['is_whiff'] = df['description'].isin(WHIFF_DESCS)
    df['is_csw'] = df['description'].isin(CSW_DESCS)
    df['is_pa_end'] = df['events'].isin(PA_END_EVENTS)
    df['is_k'] = df['events'].isin({'strikeout', 'strikeout_double_play'})
    df['is_bb'] = df['events'].isin({'walk'})
    df['is_fb'] = df['pitch_type'].isin(FB_TYPES)

    g = df.groupby('pitcher').agg(
        n_pitches=('description', 'size'),
        n_swing=('is_swing', 'sum'),
        n_whiff=('is_whiff', 'sum'),
        n_csw=('is_csw', 'sum'),
        n_bf=('is_pa_end', 'sum'),
        n_k=('is_k', 'sum'),
        n_bb=('is_bb', 'sum'),
        fb_velo=('release_speed', lambda s: s[df.loc[s.index, 'is_fb']].mean()),
    ).reset_index().rename(columns={'pitcher': 'mlbam_id'})
    g['year'] = year
    g['k_pct'] = g['n_k'] / g['n_bf'].replace(0, np.nan)
    g['bb_pct'] = g['n_bb'] / g['n_bf'].replace(0, np.nan)
    g['whiff_pct'] = g['n_whiff'] / g['n_swing'].replace(0, np.nan)
    g['csw_pct'] = g['n_csw'] / g['n_pitches'].replace(0, np.nan)
    return g


def add_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """Per-year percentile rank among pitchers w/ n_pitches >= 200."""
    out = []
    for yr, sub in df.groupby('year'):
        sub = sub.copy()
        elig = sub['n_pitches'] >= 200
        pop = sub[elig]
        # HIGH-K z-score (year cohort, n_bf >= 100 to be safe)
        k_pop = pop[pop['n_bf'] >= 100]['k_pct']
        mu, sd = k_pop.mean(), k_pop.std(ddof=0)
        sub['high_k_z_year'] = (sub['k_pct'] - mu) / sd if sd and sd > 0 else np.nan
        # Shadow percentiles among 200-pitch pop
        for col, sign in [('fb_velo', +1), ('k_pct', +1), ('bb_pct', -1),
                          ('whiff_pct', +1), ('csw_pct', +1)]:
            ref = pop[col].dropna()
            ranks = ref.rank(pct=True)
            mapping = dict(zip(ref.index, ranks))
            pct = sub.index.map(lambda i: mapping.get(i, np.nan))
            pct = pd.Series(pct, index=sub.index, dtype='float64')
            if sign < 0:
                pct = 1 - pct
            outcol = {'fb_velo': 'shadow_velo_pct', 'k_pct': 'shadow_k_pct',
                      'bb_pct': 'shadow_bb_pct', 'whiff_pct': 'shadow_whiff_pct',
                      'csw_pct': 'shadow_csw_pct'}[col]
            sub[outcol] = pct
        out.append(sub)
    return pd.concat(out, ignore_index=True)


def main():
    all_years = []
    for y in YEARS:
        print(f'  {y} ...')
        a = agg_year(y)
        if not a.empty:
            all_years.append(a)
    df = pd.concat(all_years, ignore_index=True)
    df = add_percentiles(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT)
    print(f'Wrote {OUT}  rows={len(df):,}')
    print(df[['year', 'n_pitches', 'k_pct', 'high_k_z_year', 'shadow_velo_pct']].describe())


if __name__ == '__main__':
    main()
