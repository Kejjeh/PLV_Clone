"""
build_rolling_pitchers.py — per-(pitcher, split_date) aggregations for the
Rest-of-Season pitcher model.

Mirrors build_rolling_hitters.py for the pitching side:
  - features cumulated from season start through split_date (V11/V12 inputs)
  - target FP/start accumulated from (split_date + 1) through season end

Output: data/research/xfp_cache/rolling_pitchers_2018_2026.csv
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
from lib.rolling_splits import select_inprogress_splits  # shared, unit-tested

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

# Mirror build_sp_multiyr.py classifier sets
SWING_DESC = {'swinging_strike','swinging_strike_blocked','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt'}
SWSTR_DESC = {'swinging_strike','swinging_strike_blocked','foul_tip','missed_bunt'}

SPLIT_DAYS_OF_SEASON = [30, 60, 90, 120]
# Weekly cadence for the Player-Profiles trajectory dashboard. Day 30 anchor,
# step 7 days through day 200. Applied only for years in WEEKLY_YEARS so we
# don't 7× the runtime on the full 2018-2023 history.
WEEKLY_SPLIT_DAYS = list(range(30, 201, 7))
WEEKLY_YEARS = {2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026}


def annotate_pitches(d: pd.DataFrame) -> pd.DataFrame:
    desc = d['description'].fillna('')
    ev = d['events'].fillna('')

    d['in_zone']  = (d['zone'] >= 1) & (d['zone'] <= 9)
    d['is_swing'] = desc.isin(SWING_DESC)
    d['is_swstr'] = desc.isin(SWSTR_DESC)
    d['is_contact'] = d['is_swing'] & ~d['is_swstr']
    d['is_called_strike'] = desc == 'called_strike'
    d['z_swing']   = d['is_swing']   & d['in_zone']
    d['o_swing']   = d['is_swing']   & ~d['in_zone']

    d['is_pa_end'] = ev != ''
    d['is_k']      = ev == 'strikeout'
    d['is_bb']     = ev == 'walk'
    d['is_hbp']    = ev == 'hit_by_pitch'
    d['is_h']      = ev.isin({'single','double','triple','home_run'})
    d['is_hr']     = ev == 'home_run'
    d['is_bip']    = d['is_pa_end'] & ~d['is_k'] & ~d['is_bb'] & ~d['is_hbp']

    woba_v = pd.to_numeric(d.get('woba_value'), errors='coerce')
    woba_d = pd.to_numeric(d.get('woba_denom'), errors='coerce')
    xwoba = pd.to_numeric(d.get('estimated_woba_using_speedangle'), errors='coerce')
    d['woba_v_pa'] = woba_v
    bip_with = d['is_bip'] & xwoba.notna()
    d.loc[bip_with, 'woba_v_pa'] = xwoba[bip_with]
    d['woba_d_pa'] = woba_d

    # Quality-of-contact flags (Statcast definitions). All gated to BIP.
    ls = pd.to_numeric(d.get('launch_speed'), errors='coerce')
    lsa = pd.to_numeric(d.get('launch_speed_angle'), errors='coerce')
    bb_type = d.get('bb_type', pd.Series('', index=d.index)).fillna('')
    d['is_barrel']    = d['is_bip'] & (lsa == 6)
    d['is_hard_hit']  = d['is_bip'] & (ls >= 95.0)
    d['is_gb']        = d['is_bip'] & (bb_type == 'ground_ball')
    # xwOBA on contact: sum/count only over BIP rows that have a valid xwoba estimate
    d['xwoba_bip_sum']   = xwoba.where(bip_with, 0.0)
    d['xwoba_bip_count'] = bip_with.astype(int)
    return d


def aggregate_window(pitches: pd.DataFrame) -> pd.DataFrame:
    """Per-pitcher window aggregation for V11/V12 features."""
    g = pitches.groupby('pitcher')
    agg = g.agg(
        pitches      =('pitcher', 'size'),
        tbf          =('is_pa_end', 'sum'),
        bip          =('is_bip', 'sum'),
        in_zone      =('in_zone', 'sum'),
        swing        =('is_swing', 'sum'),
        contact      =('is_contact', 'sum'),
        swstr        =('is_swstr', 'sum'),
        called_strike=('is_called_strike', 'sum'),
        z_swing      =('z_swing', 'sum'),
        o_swing      =('o_swing', 'sum'),
        avg_velo     =('release_speed', 'mean'),
        avg_pfxz     =('pfx_z', 'mean'),
        k            =('is_k', 'sum'),
        bb           =('is_bb', 'sum'),
        hbp          =('is_hbp', 'sum'),
        h            =('is_h', 'sum'),
        hr           =('is_hr', 'sum'),
        woba_v_sum   =('woba_v_pa', 'sum'),
        woba_d_sum   =('woba_d_pa', 'sum'),
        barrel_n     =('is_barrel', 'sum'),
        hard_hit_n   =('is_hard_hit', 'sum'),
        gb_n         =('is_gb', 'sum'),
        xwoba_bip_sum_  =('xwoba_bip_sum', 'sum'),
        xwoba_bip_count_=('xwoba_bip_count', 'sum'),
    ).reset_index()

    pn = agg['pitches'].replace(0, np.nan)
    sw = agg['swing'].replace(0, np.nan)
    iz = agg['in_zone'].replace(0, np.nan)
    tbf = agg['tbf'].replace(0, np.nan)
    out_zone = agg['pitches'] - agg['in_zone']
    agg['swstr_pct']    = agg['swstr'] / pn
    agg['c_plus_swstr'] = (agg['called_strike'] + agg['swstr']) / pn
    agg['zone_pct']     = agg['in_zone'] / pn
    agg['z_swing_pct']  = agg['z_swing'] / iz
    agg['o_swing_pct']  = agg['o_swing'] / out_zone.replace(0, np.nan)
    agg['k_pct']        = agg['k'] / tbf
    agg['bb_pct']       = agg['bb'] / tbf
    agg['xwoba_per_pa'] = agg['woba_v_sum'] / agg['woba_d_sum'].replace(0, np.nan)
    agg['xwoba_x_swstr'] = agg['xwoba_per_pa'] * agg['swstr_pct']

    # Quality-of-contact rates (over BIP)
    bip = agg['bip'].replace(0, np.nan)
    agg['barrel_pct']       = agg['barrel_n']   / bip
    agg['hard_hit_pct']     = agg['hard_hit_n'] / bip
    agg['gb_pct']           = agg['gb_n']       / bip
    agg['xwoba_on_contact'] = (agg['xwoba_bip_sum_']
                                / agg['xwoba_bip_count_'].replace(0, np.nan))
    agg = agg.drop(columns=['xwoba_bip_sum_', 'xwoba_bip_count_'])
    return agg


def aggregate_starts(pitches_full: pd.DataFrame) -> pd.DataFrame:
    """Per-(pitcher, game) start aggregation; mean FP/start per pitcher."""
    p = pitches_full.copy()
    p['inning'] = pd.to_numeric(p['inning'], errors='coerce')
    starts = (p[p['inning'] == 1].groupby(['game_pk', 'inning_topbot'])['pitcher']
                .first().reset_index().rename(columns={'pitcher': 'starter_id'}))
    p = p.merge(starts, on=['game_pk', 'inning_topbot'], how='left')
    p = p[p['pitcher'] == p['starter_id']].copy()

    ev = p['events'].fillna('')
    p['is_k']   = ev == 'strikeout'
    p['is_bb']  = ev == 'walk'
    p['is_hbp'] = ev == 'hit_by_pitch'
    p['is_h']   = ev.isin({'single','double','triple','home_run'})
    p['is_pa_end'] = ev != ''
    out_events = {'strikeout','field_out','grounded_into_double_play','sac_fly',
                   'sac_bunt','force_out','double_play','triple_play','fielders_choice_out',
                   'caught_stealing_2b','caught_stealing_3b','caught_stealing_home','other_out'}
    p['outs_made'] = ev.isin(out_events).astype(int)
    p.loc[ev.isin(['grounded_into_double_play','double_play']), 'outs_made'] = 2
    p.loc[ev == 'triple_play', 'outs_made'] = 3
    runs = (pd.to_numeric(p['post_bat_score'], errors='coerce')
            - pd.to_numeric(p['bat_score'], errors='coerce')).clip(lower=0)
    p['runs_on_play'] = runs.where(p['is_pa_end'], 0)

    g = p.groupby(['game_pk', 'pitcher'])
    per_start = g.agg(
        k=('is_k', 'sum'), bb=('is_bb', 'sum'), hbp=('is_hbp', 'sum'),
        h=('is_h', 'sum'), outs=('outs_made', 'sum'),
        er=('runs_on_play', 'sum'),
    ).reset_index()
    per_start['ip'] = per_start['outs'] / 3.0
    per_start['fp'] = (per_start['k']
                      + per_start['ip'] * 3.3
                      - per_start['h']
                      - 2 * per_start['er']
                      - per_start['bb']
                      - per_start['hbp'])

    by_pitcher = per_start.groupby('pitcher').agg(
        gs=('game_pk', 'count'),
        fp_per_start=('fp', 'mean'),
    ).reset_index()
    return by_pitcher


def build_year(year: int, season_start: pd.Timestamp) -> pd.DataFrame:
    from datetime import date as _date
    sc_path = CACHE / f'statcast_{year}.parquet'
    if not sc_path.exists():
        return pd.DataFrame()
    print(f'  [{year}] loading statcast...', flush=True)
    pitches = pd.read_parquet(sc_path)
    pitches['game_date'] = pd.to_datetime(pitches['game_date'])
    pitches_anno = annotate_pitches(pitches)
    today = pd.Timestamp(_date.today())
    is_in_progress = year >= today.year
    max_data_date = pitches['game_date'].max()
    base_splits = WEEKLY_SPLIT_DAYS if year in WEEKLY_YEARS else SPLIT_DAYS_OF_SEASON
    if is_in_progress:
        # Shared, unit-tested split selection: emits a current snapshot whenever data
        # lands past the last weekly cutoff, so SPs whose last start WAS the cutoff
        # date aren't dropped by the training-row inner-join (the Vlad/Judge bug).
        splits_to_use, elapsed_days = select_inprogress_splits(
            base_splits, season_start, max_data_date, today)
        print(f'  [{year}] season_start={season_start.date()} max_data={max_data_date.date()} '
              f'elapsed={elapsed_days}d -> {len(splits_to_use)} splits '
              f'({"weekly" if year in WEEKLY_YEARS else "monthly"})', flush=True)
    else:
        splits_to_use = base_splits

    rows = []
    for split_day in splits_to_use:
        cutoff = season_start + pd.Timedelta(days=split_day)
        actual_cutoff = min(cutoff, max_data_date) if is_in_progress else cutoff
        before_anno = pitches_anno[pitches_anno['game_date'] <= actual_cutoff]
        before_full = pitches[pitches['game_date'] <= actual_cutoff]
        after_full  = pitches[pitches['game_date'] >  actual_cutoff]
        if before_anno.empty:
            continue
        in_progress_row = is_in_progress and after_full.empty

        feat = aggregate_window(before_anno).add_suffix('_to')
        feat['pitcher'] = feat['pitcher_to']
        feat = feat.drop(columns=['pitcher_to'])

        # Last-21-day pitch-level rates — captures recent form
        recent_start = actual_cutoff - pd.Timedelta(days=21)
        recent_anno = pitches_anno[(pitches_anno['game_date'] > recent_start)
                                   & (pitches_anno['game_date'] <= actual_cutoff)]
        if not recent_anno.empty:
            feat21 = aggregate_window(recent_anno).add_suffix('_last21')
            feat21['pitcher'] = feat21['pitcher_last21']
            feat21 = feat21.drop(columns=['pitcher_last21'])
            feat = feat.merge(feat21, on='pitcher', how='left')
            recent_full = pitches[(pitches['game_date'] > recent_start)
                                  & (pitches['game_date'] <= actual_cutoff)]
            recent_starts = aggregate_starts(recent_full).rename(
                columns={'gs': 'gs_last21', 'fp_per_start': 'fp_per_start_last21'})
            feat = feat.merge(recent_starts, on='pitcher', how='left')

        before_starts = aggregate_starts(before_full).rename(
            columns={'gs': 'gs_to', 'fp_per_start': 'fp_per_start_to'})
        feat = feat.merge(before_starts, on='pitcher', how='inner')
        feat = feat[feat['gs_to'] >= 2]

        if in_progress_row:
            merged = feat.copy()
            merged['ros_gs'] = np.nan
            merged['ros_fp_per_start'] = np.nan
        else:
            target = aggregate_starts(after_full).rename(
                columns={'gs': 'ros_gs', 'fp_per_start': 'ros_fp_per_start'})
            merged = feat.merge(target, on='pitcher', how='inner')
        merged['year'] = year
        merged['split_day'] = split_day
        merged['cutoff_date'] = actual_cutoff.date()
        rows.append(merged)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# Bump when build_year logic changes (invalidates the per-year immutable cache).
BUILDER_VERSION = 1


def main():
    season_starts = {
        2018: '2018-03-29', 2019: '2019-03-20',
        2021: '2021-04-01', 2022: '2022-04-07',
        2023: '2023-03-30', 2024: '2024-03-28',
        2025: '2025-03-27', 2026: '2026-03-26',
    }
    print('=== build_rolling_pitchers ===', flush=True)
    from lib.disk_cache import year_cached_frame
    frames = []
    for yr, start in season_starts.items():
        out = year_cached_frame(
            'rolling_pitchers', yr,
            lambda yr=yr, start=start: build_year(yr, pd.Timestamp(start)),
            dep_paths=[str(CACHE / f'statcast_{yr}.parquet')],
            version=BUILDER_VERSION)
        if not out.empty:
            print(f'  [{yr}] {len(out)} (pitcher, split) rows', flush=True)
            frames.append(out)
    if not frames:
        print('No data — aborting')
        return
    df = pd.concat(frames, ignore_index=True)
    out_path = CACHE / 'rolling_pitchers_2018_2026.csv'
    df.to_csv(out_path, index=False)
    print(f'\nWrote {out_path}: {len(df)} rows')
    print('  by split_day:')
    print(df.groupby('split_day').size().to_string())
    print('  by year:')
    print(df.groupby('year').size().to_string())


if __name__ == '__main__':
    main()
