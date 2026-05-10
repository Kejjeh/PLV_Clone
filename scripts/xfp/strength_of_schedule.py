"""strength_of_schedule.py — per-batter & per-SP SoS using prior-career opponent quality.

For each (batter, year): mean of opposing-pitcher PRIOR-career fp/start across
all PAs faced. Prior-career = career fp/start using only data from years STRICTLY
BEFORE year T (no leakage).

For each (pitcher, year): mean of opposing-batter PRIOR-career fp/PA.

Outputs:
  data/outputs/hitter_sos.csv     (batter, year, sos_opp_sp_fp_per_start, n_pa)
  data/outputs/pitcher_sos.csv    (pitcher, year, sos_opp_bat_fp_per_pa, n_bf)

Both are joinable to the rolling substrate by (batter/pitcher, year).
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}


def build_pitcher_career_priors():
    """For each (pitcher, year), pitcher's CUMULATIVE prior-year career fp/start
    (computed from sp_multiyr 2015 to year-1 only)."""
    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    sp = sp[sp['gs'] >= 3]  # min sample
    sp = sp.sort_values(['pitcher', 'year'])
    rows = []
    for pid, sub in sp.groupby('pitcher'):
        cum_gs = 0; cum_fp_total = 0
        for _, r in sub.iterrows():
            yr = int(r['year'])
            if cum_gs >= 5:
                rows.append({'pitcher': pid, 'year': yr,
                             'prior_career_fp_per_start': cum_fp_total / cum_gs,
                             'prior_career_gs': cum_gs})
            else:
                rows.append({'pitcher': pid, 'year': yr,
                             'prior_career_fp_per_start': np.nan,
                             'prior_career_gs': cum_gs})
            cum_gs += int(r['gs'])
            cum_fp_total += float(r['fp_per_start_actual']) * int(r['gs'])
    return pd.DataFrame(rows)


def build_batter_career_priors():
    """Same logic for batters using hitters_multiyr + fp_per_pa_actual."""
    h = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
    h = h[h['pa'] >= 100]
    h = h.sort_values(['batter', 'year'])
    rows = []
    for bid, sub in h.groupby('batter'):
        cum_pa = 0; cum_fp_total = 0
        for _, r in sub.iterrows():
            yr = int(r['year'])
            if cum_pa >= 200:
                rows.append({'batter': bid, 'year': yr,
                             'prior_career_fp_per_pa': cum_fp_total / cum_pa,
                             'prior_career_pa': cum_pa})
            else:
                rows.append({'batter': bid, 'year': yr,
                             'prior_career_fp_per_pa': np.nan,
                             'prior_career_pa': cum_pa})
            cum_pa += int(r['pa'])
            cum_fp_total += float(r['fp_per_pa_actual']) * int(r['pa'])
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print('[1] Building per-pitcher prior-career fp/start...')
    pit_prior = build_pitcher_career_priors()
    pit_prior.to_csv(CACHE / 'pitcher_prior_career.csv', index=False)
    print(f'   {len(pit_prior)} pitcher-year priors')

    print('[2] Building per-batter prior-career fp/PA...')
    bat_prior = build_batter_career_priors()
    bat_prior.to_csv(CACHE / 'batter_prior_career.csv', index=False)
    print(f'   {len(bat_prior)} batter-year priors')

    print('[3] Building hitter SoS from statcast...')
    hit_rows = []; pit_rows = []
    for year in range(2018, 2027):
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['batter', 'pitcher', 'events'])
        df = df[df['events'].isin(PA_EVENTS)].copy()
        df['year'] = year

        # Hitter SoS: per (batter, year), mean of opposing pitcher's prior-career fp/start
        pp_yr = pit_prior[pit_prior['year'] == year][['pitcher', 'prior_career_fp_per_start']]
        df1 = df.merge(pp_yr, on='pitcher', how='left')
        df1 = df1.dropna(subset=['prior_career_fp_per_start'])
        agg = df1.groupby(['batter', 'year'], as_index=False).agg(
            sos_opp_sp_fp_per_start=('prior_career_fp_per_start', 'mean'),
            n_pa_with_sos=('events', 'count'))
        hit_rows.append(agg)

        # Pitcher SoS: per (pitcher, year), mean of opposing batter's prior-career fp/PA
        bp_yr = bat_prior[bat_prior['year'] == year][['batter', 'prior_career_fp_per_pa']]
        df2 = df.merge(bp_yr, on='batter', how='left')
        df2 = df2.dropna(subset=['prior_career_fp_per_pa'])
        agg2 = df2.groupby(['pitcher', 'year'], as_index=False).agg(
            sos_opp_bat_fp_per_pa=('prior_career_fp_per_pa', 'mean'),
            n_bf_with_sos=('events', 'count'))
        pit_rows.append(agg2)

    hit_sos = pd.concat(hit_rows, ignore_index=True) if hit_rows else pd.DataFrame()
    pit_sos = pd.concat(pit_rows, ignore_index=True) if pit_rows else pd.DataFrame()
    fname1 = OUT / 'hitter_sos.csv'
    fname2 = OUT / 'pitcher_sos.csv'
    hit_sos.to_csv(fname1, index=False)
    pit_sos.to_csv(fname2, index=False)
    print(f'   wrote {fname1} ({len(hit_sos)} rows)')
    print(f'   wrote {fname2} ({len(pit_sos)} rows)')

    print('\n  Hitter SoS distribution per year:')
    print(hit_sos.groupby('year')['sos_opp_sp_fp_per_start'].agg(['count', 'mean', 'std']).round(3))


if __name__ == '__main__':
    main()
