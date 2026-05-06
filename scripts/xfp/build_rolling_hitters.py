"""
build_rolling_hitters.py — per-(batter, split_date) aggregations for the
Rest-of-Season hitter model.

For each historical year and a set of in-season split dates, compute:
  - features cumulated from season start through split_date
  - target FP/PA accumulated from (split_date + 1) through season end

Written to data/research/xfp_cache/rolling_hitters_{year}.csv with one
row per (batter, split_date).

The training script (xfp_rh_pipeline.py) consumes these to build a
RoS-prediction Ridge.
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

# Statcast event sets (mirror build_hitters_multiyr.py)
K_EVENTS  = {'strikeout', 'strikeout_double_play', 'strikeout_triple_play'}
BB_EVENTS = {'walk', 'intent_walk'}
H_EVENTS  = {'single', 'double', 'triple', 'home_run'}
SB_EVENTS = {'stolen_base_2b', 'stolen_base_3b', 'stolen_base_home'}
TB_MAP = {'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}
NON_PA = SB_EVENTS | {
    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
    'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
    'wild_pitch', 'passed_ball', 'balk',
}
SWING_DESC = {'swinging_strike','swinging_strike_blocked','foul','foul_tip',
              'hit_into_play','foul_bunt','missed_bunt'}
SWSTR_DESC = {'swinging_strike','swinging_strike_blocked','foul_tip','missed_bunt'}

# Split dates per year — the dates at which we slice the season into
# "to-date" vs "rest-of-season". Multiple splits per year give the model
# exposure to different sample-size regimes.
SPLIT_DAYS_OF_SEASON = [30, 60, 90, 120]  # days into season


def annotate_pitches(d: pd.DataFrame) -> pd.DataFrame:
    """Add boolean event flags + tb that the per-batter aggregator needs."""
    desc = d['description'].fillna('')
    ev = d['events'].fillna('')

    d['in_zone']  = (d['zone'] >= 1) & (d['zone'] <= 9)
    d['is_swing'] = desc.isin(SWING_DESC)
    d['is_swstr'] = desc.isin(SWSTR_DESC)
    d['is_contact'] = d['is_swing'] & ~d['is_swstr']
    d['is_called_strike'] = desc == 'called_strike'
    d['z_swing']   = d['is_swing']   & d['in_zone']
    d['z_contact'] = d['is_contact'] & d['in_zone']
    d['o_swing']   = d['is_swing']   & ~d['in_zone']

    d['is_pa_end'] = ev != ''
    d['is_k']      = ev.isin(K_EVENTS)
    d['is_bb']     = ev.isin(BB_EVENTS)
    d['is_hbp']    = ev == 'hit_by_pitch'
    d['is_h']      = ev.isin(H_EVENTS)
    d['is_hr']     = ev == 'home_run'
    d['is_sb']     = ev.isin(SB_EVENTS)
    d['is_pa']     = d['is_pa_end'] & ~ev.isin(NON_PA)
    d['is_bip']    = d['is_pa'] & ~d['is_k'] & ~d['is_bb'] & ~d['is_hbp']
    d['tb']        = ev.map(TB_MAP).fillna(0).astype(int)

    ls = pd.to_numeric(d.get('launch_speed'), errors='coerce')
    d['hard_hit'] = (ls >= 95) & d['is_bip']
    if 'launch_speed_angle' in d.columns:
        d['barrel'] = (pd.to_numeric(d['launch_speed_angle'], errors='coerce') == 6) & d['is_bip']
    else:
        la = pd.to_numeric(d.get('launch_angle'), errors='coerce')
        d['barrel'] = (ls >= 98) & la.between(26, 30) & d['is_bip']

    xwoba = pd.to_numeric(d.get('estimated_woba_using_speedangle'), errors='coerce')
    d['xwoba_con_val'] = xwoba.where(d['is_bip'])
    woba_v = pd.to_numeric(d.get('woba_value'), errors='coerce')
    woba_d = pd.to_numeric(d.get('woba_denom'), errors='coerce')
    d['woba_v_pa'] = woba_v
    bip_with = d['is_bip'] & xwoba.notna()
    d.loc[bip_with, 'woba_v_pa'] = xwoba[bip_with]
    d['woba_d_pa'] = woba_d
    return d


def aggregate_window(pitches: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to per-batter rate stats. Pitches frame is already
    annotated; expects columns from annotate_pitches()."""
    g = pitches.groupby('batter')
    agg = g.agg(
        pitches      =('batter', 'size'),
        pa           =('is_pa', 'sum'),
        bip          =('is_bip', 'sum'),
        in_zone      =('in_zone', 'sum'),
        swing        =('is_swing', 'sum'),
        contact      =('is_contact', 'sum'),
        swstr        =('is_swstr', 'sum'),
        called_strike=('is_called_strike', 'sum'),
        z_contact    =('z_contact', 'sum'),
        o_swing      =('o_swing', 'sum'),
        bb           =('is_bb', 'sum'),
        k            =('is_k', 'sum'),
        hbp          =('is_hbp', 'sum'),
        h            =('is_h', 'sum'),
        hr           =('is_hr', 'sum'),
        tb           =('tb', 'sum'),
        sb           =('is_sb', 'sum'),
        hard_hit_n   =('hard_hit', 'sum'),
        barrel_n     =('barrel', 'sum'),
        woba_v_sum   =('woba_v_pa', 'sum'),
        woba_d_sum   =('woba_d_pa', 'sum'),
    ).reset_index()

    # Derived rates
    pa = agg['pa'].replace(0, np.nan)
    swing = agg['swing'].replace(0, np.nan)
    bip = agg['bip'].replace(0, np.nan)
    in_zone = agg['in_zone'].replace(0, np.nan)
    pitches_n = agg['pitches'].replace(0, np.nan)

    agg['k_pct']         = agg['k'] / pa
    agg['bb_pct']        = agg['bb'] / pa
    agg['hr_per_pa']     = agg['hr'] / pa
    agg['sb_per_pa']     = agg['sb'] / pa
    agg['ab']            = agg['pa'] - agg['bb'] - agg['hbp']
    agg['iso']           = (agg['tb'] - agg['h']) / agg['ab'].replace(0, np.nan)
    agg['contact_pct']   = agg['contact'] / swing
    agg['whiff_pct']     = agg['swstr'] / swing
    agg['swstr_pct']     = agg['swstr'] / pitches_n
    agg['z_contact_pct'] = agg['z_contact'] / agg['z_swing'].replace(0, np.nan) if 'z_swing' in agg.columns else np.nan
    agg['chase_pct']     = agg['o_swing'] / (agg['pitches'] - agg['in_zone']).replace(0, np.nan)
    agg['in_play_pct']   = agg['bip'] / pitches_n
    agg['hard_hit_pct']  = agg['hard_hit_n'] / bip
    agg['barrel_pct']    = agg['barrel_n'] / bip
    agg['xwoba_per_pa']  = agg['woba_v_sum'] / agg['woba_d_sum'].replace(0, np.nan)
    agg['xwoba_on_contact'] = pitches.loc[pitches['is_bip']].groupby('batter')['xwoba_con_val'].mean().reindex(agg['batter']).values

    # FP target on the window
    agg['fp_total'] = (
        agg['tb'] + agg['bb'] + agg['hbp'] + agg['sb'] - agg['k']
    ).astype(float)  # core_fp; R/RBI added at outer scope from MLB API
    agg['core_fp_per_pa'] = agg['fp_total'] / pa
    return agg


def fp_per_pa_with_rrbi(window_agg: pd.DataFrame, rrbi_rates: pd.Series) -> pd.Series:
    """Add R + RBI per PA (proportional from MLB API season totals).
    rrbi_rates is keyed on batter, value is total (r+rbi)/season-pa.
    """
    pa = window_agg['pa'].replace(0, np.nan)
    rrbi_per_pa = window_agg['batter'].map(rrbi_rates).fillna(0.0)
    return ((window_agg['fp_total'] + window_agg['pa'] * rrbi_per_pa) / pa).round(4)


def build_year(year: int, season_start: pd.Timestamp) -> pd.DataFrame:
    """For one year, build rows for each (batter, split_day) pair."""
    sc_path = CACHE / f'statcast_{year}.parquet'
    if not sc_path.exists():
        return pd.DataFrame()
    print(f'  [{year}] loading statcast...', flush=True)
    pitches = pd.read_parquet(sc_path)
    pitches['game_date'] = pd.to_datetime(pitches['game_date'])
    pitches = annotate_pitches(pitches)

    # MLB API per-batter R/RBI rates from existing counting-stats cache
    rrbi_rates: pd.Series
    counts_path = CACHE / f'hitter_counting_stats_{year}.json'
    if counts_path.exists():
        import json as _json
        cnts = pd.DataFrame(_json.loads(counts_path.read_text()))
        if 'mlb_pa' in cnts.columns:
            cnts['rrbi_per_pa'] = (cnts['mlb_r'].fillna(0) + cnts['mlb_rbi'].fillna(0)) / cnts['mlb_pa'].replace(0, np.nan)
            rrbi_rates = cnts.set_index('batter')['rrbi_per_pa']
        else:
            rrbi_rates = pd.Series(dtype=float)
    else:
        rrbi_rates = pd.Series(dtype=float)

    rows = []
    for split_day in SPLIT_DAYS_OF_SEASON:
        cutoff = season_start + pd.Timedelta(days=split_day)
        before = pitches[pitches['game_date'] <= cutoff]
        after  = pitches[pitches['game_date'] >  cutoff]
        if before.empty or after.empty:
            continue

        feat = aggregate_window(before)
        feat = feat.add_suffix('_to')
        feat['batter'] = feat['batter_to']
        feat = feat.drop(columns=['batter_to'])

        target = aggregate_window(after)[['batter', 'pa', 'fp_total']].rename(
            columns={'pa': 'pa_after', 'fp_total': 'fp_after_core'})
        target['ros_pa'] = target['pa_after']
        target['ros_core_fp_per_pa'] = target['fp_after_core'] / target['pa_after'].replace(0, np.nan)

        merged = feat.merge(target, on='batter', how='inner')
        merged['ros_full_fp_per_pa'] = (
            merged['ros_core_fp_per_pa'] + merged['batter'].map(rrbi_rates).fillna(0.0)
        ).round(4)
        merged['year'] = year
        merged['split_day'] = split_day
        merged['cutoff_date'] = cutoff.date()
        rows.append(merged)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main():
    season_starts = {
        2018: '2018-03-29', 2019: '2019-03-20',
        2021: '2021-04-01', 2022: '2022-04-07',
        2023: '2023-03-30', 2024: '2024-03-28',
        2025: '2025-03-27', 2026: '2026-03-26',
    }
    print('=== build_rolling_hitters ===', flush=True)
    frames = []
    for yr, start in season_starts.items():
        out = build_year(yr, pd.Timestamp(start))
        if not out.empty:
            print(f'  [{yr}] {len(out)} (batter, split) rows', flush=True)
            frames.append(out)
    if not frames:
        print('No data — aborting')
        return
    df = pd.concat(frames, ignore_index=True)
    out_path = CACHE / 'rolling_hitters_2018_2026.csv'
    df.to_csv(out_path, index=False)
    print(f'\nWrote {out_path}: {len(df)} rows')
    # Summary
    print('  by split_day:')
    print(df.groupby('split_day').size().to_string())
    print('  by year:')
    print(df.groupby('year').size().to_string())


if __name__ == '__main__':
    main()
