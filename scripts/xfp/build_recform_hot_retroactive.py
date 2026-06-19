"""build_recform_hot_retroactive.py — Phase 3 Agent 5 Part A.

Compute per-(pitcher, year, split_day) trailing-5-start fp_proxy_per_bf
z-score within the same-year-same-split SP population. Output:

  data/research/historical_panel/recform_hot_retroactive.parquet

Leak-free: at split_day D, only games with day-of-season < D are used.

ER not directly in statcast — we approximate ER from events: every run-scoring
event (home_run, plus runs encoded via post_bat_score deltas) counts. We use
post_bat_score / post_fld_score deltas to get runs scored on each pitch, then
subtract unearned (we have no clean UER tag → treat all runs as ER, a known
~5% over-count vs true ER). This is acceptable for a z-score (the bias is
constant per pitcher-year).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'research' / 'historical_panel' / 'recform_hot_retroactive.parquet'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]  # excl. 2020 COVID
SPLIT_DAYS = [60, 90, 120]
TRAILING_N = 5
MIN_STARTS_AT_CUTOFF = 3
SP_START_BF_MIN = 15  # filter relief appearances


def per_start_fp_proxy(year: int) -> pd.DataFrame:
    """Return per (pitcher, game_pk, game_date) start-level fp_proxy."""
    cols = ['game_date', 'pitcher', 'game_pk', 'events', 'description',
            'post_bat_score', 'bat_score', 'inning']
    sc = pd.read_parquet(CACHE / f'statcast_{year}.parquet', columns=cols)
    sc = sc[sc['game_date'].notna() & sc['pitcher'].notna() & sc['game_pk'].notna()].copy()
    sc['game_date'] = pd.to_datetime(sc['game_date'], errors='coerce')
    sc = sc[sc['game_date'].notna()]

    # Runs scored on this pitch (post - pre, attributable to pitcher of record)
    sc['runs_on_play'] = (sc['post_bat_score'].fillna(0) - sc['bat_score'].fillna(0)).clip(lower=0)

    # Outs from events: field_out, strikeout, force_out, grounded_into_double_play (2),
    # sac_fly, sac_bunt, double_play (2), triple_play (3), caught_stealing_*, pickoff_*
    OUT_EVENTS_1 = {'field_out', 'strikeout', 'force_out', 'sac_fly', 'sac_bunt',
                    'fielders_choice_out', 'fielders_choice', 'strikeout_double_play',
                    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
                    'pickoff_1b', 'pickoff_2b', 'pickoff_3b', 'pickoff_caught_stealing_2b',
                    'pickoff_caught_stealing_3b', 'pickoff_caught_stealing_home',
                    'other_out', 'sac_fly_double_play'}
    OUT_EVENTS_2 = {'grounded_into_double_play', 'double_play'}
    OUT_EVENTS_3 = {'triple_play'}

    sc['outs_on_play'] = 0
    sc.loc[sc['events'].isin(OUT_EVENTS_1), 'outs_on_play'] = 1
    sc.loc[sc['events'].isin(OUT_EVENTS_2), 'outs_on_play'] = 2
    sc.loc[sc['events'].isin(OUT_EVENTS_3), 'outs_on_play'] = 3

    # PA-ending events flag
    PA_END = {'field_out', 'strikeout', 'home_run', 'single', 'double', 'triple',
              'walk', 'hit_by_pitch', 'force_out', 'grounded_into_double_play',
              'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
              'strikeout_double_play', 'double_play', 'triple_play',
              'sac_fly_double_play', 'field_error', 'catcher_interf', 'other_out'}
    sc['is_pa'] = sc['events'].isin(PA_END).astype(int)
    sc['is_k'] = sc['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    sc['is_bb'] = (sc['events'] == 'walk').astype(int)
    sc['is_hbp'] = (sc['events'] == 'hit_by_pitch').astype(int)
    sc['is_hit'] = sc['events'].isin({'single', 'double', 'triple', 'home_run'}).astype(int)

    g = sc.groupby(['pitcher', 'game_pk', 'game_date'], observed=True).agg(
        BF=('is_pa', 'sum'),
        K=('is_k', 'sum'),
        BB=('is_bb', 'sum'),
        HBP=('is_hbp', 'sum'),
        H=('is_hit', 'sum'),
        R=('runs_on_play', 'sum'),
        outs=('outs_on_play', 'sum'),
    ).reset_index()

    g['IP'] = g['outs'] / 3.0
    # Deliberate Statcast-source PROXY, not the canonical BrownU FP formula:
    # pitch data has runs_on_play (R), not ER (and no SV/HLD), so −2*R stands in
    # for −2*ER. Must match lib/recform_hot.py exactly — the validated good-start
    # threshold (≥ −0.0476) was calibrated on this proxy. Do NOT route to
    # fantasy.scoring.pitcher_fp or "correct" R→ER.
    g['fp_proxy'] = g['K'] + 3.3 * g['IP'] - g['H'] - 2 * g['R'] - g['BB'] - g['HBP']
    g['fp_proxy_per_bf'] = np.where(g['BF'] > 0, g['fp_proxy'] / g['BF'], np.nan)
    g['year'] = year
    g['day_of_season'] = (g['game_date'] - pd.Timestamp(f'{year}-03-15')).dt.days
    return g


def build_recform_panel() -> pd.DataFrame:
    out_rows = []
    for year in YEARS:
        print(f'  loading {year}...')
        starts = per_start_fp_proxy(year)
        starts = starts[starts['BF'] >= SP_START_BF_MIN].copy()
        starts = starts.sort_values(['pitcher', 'game_date'])

        for sd in SPLIT_DAYS:
            before = starts[starts['day_of_season'] < sd]
            # Trailing N per pitcher
            grouped = before.groupby('pitcher', observed=True)
            recform = grouped.tail(TRAILING_N).groupby('pitcher', observed=True).agg(
                trail_bf=('BF', 'sum'),
                trail_fp=('fp_proxy', 'sum'),
                trail_starts=('BF', 'count'),
            ).reset_index()
            recform = recform[recform['trail_starts'] >= MIN_STARTS_AT_CUTOFF].copy()
            recform['recform_fp_per_bf'] = recform['trail_fp'] / recform['trail_bf']
            mu = recform['recform_fp_per_bf'].mean()
            sd_pop = recform['recform_fp_per_bf'].std(ddof=0)
            recform['recform_hot_z'] = (recform['recform_fp_per_bf'] - mu) / (sd_pop if sd_pop > 0 else 1)
            recform['year'] = year
            recform['split_day'] = sd
            out_rows.append(recform[['pitcher', 'year', 'split_day',
                                     'recform_fp_per_bf', 'recform_hot_z',
                                     'trail_starts']])
    panel = pd.concat(out_rows, ignore_index=True)
    return panel


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    panel = build_recform_panel()
    panel.to_parquet(OUT, index=False)
    print(f'\nWrote {OUT}  rows={len(panel):,}')
    print(panel.groupby(['year', 'split_day']).agg(
        n=('pitcher', 'count'),
        z_mean=('recform_hot_z', 'mean'),
        z_std=('recform_hot_z', 'std'),
    ).round(3).to_string())


if __name__ == '__main__':
    main()
