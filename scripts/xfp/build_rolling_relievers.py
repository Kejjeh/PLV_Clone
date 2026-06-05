"""build_rolling_relievers.py — per-(reliever, year, split_day) substrate.

Mirrors `build_rolling_pitchers.py` but for relief appearances. Used by the
RP RoS model.

For each year and split_day in [30, 60, 90, 120]:
  - Aggregate relief pitches through cutoff per pitcher (rate stats)
  - Count games appeared (G), IP, K, BB, H, ER, HBP through cutoff
  - Filter to RP-eligible: G_through_cutoff >= MIN_G_TO (default 5)
  - Attach prior-year role + SV + HLD + fp_per_g (lag features)

Target = full-year reliever FP TOTAL for that year (from MLB API counting stats),
which the RoS model predicts. Rest-of-season = predicted_full_year − actual_to_date
is computed downstream at projection time.

Output: data/research/xfp_cache/rolling_relievers_2018_2026.csv
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'rolling_relievers_2018_2026.csv'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]  # skip 2020
SPLIT_DAYS = [30, 60, 90, 120]
# Weekly cadence for the Player-Profiles RP trajectory view. Only applied for
# 2024-2026 to keep runtime manageable (older years stay monthly for the model).
WEEKLY_SPLIT_DAYS = list(range(30, 201, 7))
WEEKLY_YEARS = {2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026}
SEASON_STARTS = {
    2018: '2018-03-29', 2019: '2019-03-20',
    2021: '2021-04-01', 2022: '2022-04-07', 2023: '2023-03-30',
    2024: '2024-03-28', 2025: '2025-03-27', 2026: '2026-03-26',
}
MIN_G_TO = 5            # min in-season relief appearances to qualify
MAX_GS_TO = 2           # exclude SP-types (more than 2 starts so far disqualifies)

SWING_DESC = {'swinging_strike','swinging_strike_blocked','foul','foul_tip',
              'hit_into_play','foul_bunt','missed_bunt'}
SWSTR_DESC = {'swinging_strike','swinging_strike_blocked','foul_tip','missed_bunt'}


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
    d['is_bip']    = d['is_pa_end'] & ~d['is_k'] & ~d['is_bb'] & ~d['is_hbp']
    woba_v = pd.to_numeric(d.get('woba_value'), errors='coerce')
    woba_d = pd.to_numeric(d.get('woba_denom'), errors='coerce')
    xwoba = pd.to_numeric(d.get('estimated_woba_using_speedangle'), errors='coerce')
    d['woba_v_pa'] = woba_v
    bip_with = d['is_bip'] & xwoba.notna()
    d.loc[bip_with, 'woba_v_pa'] = xwoba[bip_with]
    d['woba_d_pa'] = woba_d

    # Quality-of-contact flags (Statcast definitions). Mirror build_rolling_pitchers.py.
    ls = pd.to_numeric(d.get('launch_speed'), errors='coerce')
    lsa = pd.to_numeric(d.get('launch_speed_angle'), errors='coerce')
    bb_type = d.get('bb_type', pd.Series('', index=d.index)).fillna('')
    d['is_barrel']    = d['is_bip'] & (lsa == 6)
    d['is_hard_hit']  = d['is_bip'] & (ls >= 95.0)
    d['is_gb']        = d['is_bip'] & (bb_type == 'ground_ball')
    # xwOBA on contact: aggregate only over BIP rows that carry a valid xwoba estimate
    d['xwoba_bip_sum']   = xwoba.where(bip_with, 0.0)
    d['xwoba_bip_count'] = bip_with.astype(int)
    return d


def aggregate_window(pitches: pd.DataFrame) -> pd.DataFrame:
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
    out_zone = (agg['pitches'] - agg['in_zone']).replace(0, np.nan)
    tbf = agg['tbf'].replace(0, np.nan)
    agg['swstr_pct']    = agg['swstr'] / pn
    agg['c_plus_swstr'] = (agg['called_strike'] + agg['swstr']) / pn
    agg['zone_pct']     = agg['in_zone'] / pn
    agg['z_swing_pct']  = agg['z_swing'] / iz
    agg['o_swing_pct']  = agg['o_swing'] / out_zone
    agg['contact_pct']  = agg['contact'] / sw
    agg['k_pct']        = agg['k'] / tbf
    agg['bb_pct']       = agg['bb'] / tbf
    agg['xwoba_per_pa'] = agg['woba_v_sum'] / agg['woba_d_sum'].replace(0, np.nan)

    # Quality-of-contact rates (over BIP). Null when BIP=0.
    bip = agg['bip'].replace(0, np.nan)
    agg['barrel_pct']       = agg['barrel_n']   / bip
    agg['hard_hit_pct']     = agg['hard_hit_n'] / bip
    agg['gb_pct']           = agg['gb_n']       / bip
    agg['xwoba_on_contact'] = (agg['xwoba_bip_sum_']
                                / agg['xwoba_bip_count_'].replace(0, np.nan))
    agg = agg.drop(columns=['xwoba_bip_sum_', 'xwoba_bip_count_'])
    return agg


def role_usage_aggregate(year: int, cutoff: pd.Timestamp,
                          eligible_pitchers: set | None = None) -> pd.DataFrame:
    """Aggregate per-(pitcher, year, cutoff_date) role usage:
    gf_to, sv_to, hld_to, bs_to (and rates) from role_usage_appearances_{yr}.parquet."""
    path = CACHE / f'role_usage_appearances_{year}.parquet'
    if not path.exists():
        return pd.DataFrame(columns=['pitcher','gf_to','sv_to','hld_to','bs_to'])
    apps = pd.read_parquet(path)
    apps['game_date'] = pd.to_datetime(apps['game_date'])
    apps = apps[apps['game_date'] <= cutoff]
    if eligible_pitchers is not None:
        apps = apps[apps['pitcher'].isin(eligible_pitchers)]
    by_p = apps.groupby('pitcher').agg(
        gf_to=('gf', 'sum'),
        sv_to=('sv', 'sum'),
        hld_to=('hld', 'sum'),
        bs_to=('blown_sv', 'sum'),
        ip_in_app_total=('ip_in_app', 'sum'),
    ).reset_index()
    return by_p


def per_appearance_aggregate(pitches: pd.DataFrame) -> pd.DataFrame:
    """For relief outings: count games appeared, IP, ER through cutoff.
    K/BB/H/HBP come from aggregate_window to avoid duplication."""
    p = pitches.copy()
    ev = p['events'].fillna('')
    p['is_pa_end'] = ev != ''
    out_events = {'strikeout','field_out','grounded_into_double_play','sac_fly',
                  'sac_bunt','force_out','double_play','triple_play',
                  'fielders_choice_out','caught_stealing_2b','caught_stealing_3b',
                  'caught_stealing_home','other_out'}
    p['outs_made'] = ev.isin(out_events).astype(int)
    p.loc[ev.isin(['grounded_into_double_play','double_play']), 'outs_made'] = 2
    p.loc[ev == 'triple_play', 'outs_made'] = 3
    runs = (pd.to_numeric(p['post_bat_score'], errors='coerce')
            - pd.to_numeric(p['bat_score'], errors='coerce')).clip(lower=0)
    p['runs_on_play'] = runs.where(p['is_pa_end'], 0)
    by_p = p.groupby('pitcher').agg(
        g_to=('game_pk', 'nunique'),
        outs_to=('outs_made', 'sum'),
        er_to=('runs_on_play', 'sum'),
    ).reset_index()
    by_p['ip_to'] = by_p['outs_to'] / 3.0
    return by_p


def relief_pitches_only(pitches_anno: pd.DataFrame, pitches_full: pd.DataFrame) -> pd.DataFrame:
    p = pitches_full.copy()
    p['inning'] = pd.to_numeric(p['inning'], errors='coerce')
    starts = (p[p['inning'] == 1]
              .groupby(['game_pk', 'inning_topbot'])['pitcher']
              .first().reset_index().rename(columns={'pitcher': 'starter_id'}))
    p_marked = pitches_anno.merge(starts, on=['game_pk', 'inning_topbot'], how='left')
    return p_marked[p_marked['pitcher'] != p_marked['starter_id']].copy()


def build_year(year: int) -> pd.DataFrame:
    sc_path = CACHE / f'statcast_{year}.parquet'
    if not sc_path.exists():
        return pd.DataFrame()
    print(f'[{year}] loading statcast...', flush=True)
    pitches = pd.read_parquet(sc_path)
    from datetime import date as _date
    pitches['game_date'] = pd.to_datetime(pitches['game_date'])
    pitches_anno = annotate_pitches(pitches)
    relief_anno = relief_pitches_only(pitches_anno, pitches)
    season_start = pd.Timestamp(SEASON_STARTS[year])
    # For in-progress year, use today's date as the cutoff label (so IL state
    # joins use today's data even if statcast lags by a few days). For complete
    # past years, use max statcast date.
    today = pd.Timestamp(_date.today())
    if year >= today.year:
        max_data_date = today
    else:
        max_data_date = pitches['game_date'].max()

    # Also separate relief-only from raw pitches for GS counting
    p_full = pitches.copy()
    p_full['inning'] = pd.to_numeric(p_full['inning'], errors='coerce')
    starts = (p_full[p_full['inning'] == 1]
              .groupby(['game_pk', 'inning_topbot'])['pitcher']
              .first().reset_index().rename(columns={'pitcher': 'starter_id'}))

    # Determine which split_days are usable: nominal cutoff <= max data date.
    # For an in-progress year, only completed cutoffs emit rows. Plus one
    # "current" row using actual elapsed days as split_day so the projection
    # uses today's snapshot at today's elapsed time (not at day 120's label).
    elapsed_days = int((max_data_date - season_start).days)
    base_splits = WEEKLY_SPLIT_DAYS if year in WEEKLY_YEARS else SPLIT_DAYS
    splits_to_use = [s for s in base_splits if season_start + pd.Timedelta(days=s) <= max_data_date]
    # If the current cutoff is between defined split_days, add an actual-elapsed row.
    if (not splits_to_use) or (elapsed_days > max(splits_to_use, default=0) + 5):
        splits_to_use = list(splits_to_use) + [elapsed_days]
    print(f'  [{year}] season_start={season_start.date()} max_data={max_data_date.date()} '
          f'elapsed={elapsed_days}d -> {len(splits_to_use)} splits '
          f'({"weekly" if year in WEEKLY_YEARS else "monthly"})')

    rows = []
    for split_day in splits_to_use:
        cutoff = season_start + pd.Timedelta(days=split_day)
        # Cap cutoff at max data date (so the elapsed-days variant uses real data)
        actual_cutoff = min(cutoff, max_data_date)
        relief_cut = relief_anno[relief_anno['game_date'] <= actual_cutoff]
        full_cut   = p_full[p_full['game_date'] <= actual_cutoff]
        if relief_cut.empty:
            continue

        # GS-to-date (to filter SP-types)
        gs_to_date = (starts.merge(full_cut[['game_pk','inning_topbot']]
                                   .drop_duplicates(), on=['game_pk','inning_topbot'])
                      .groupby('starter_id').size()
                      .reset_index().rename(columns={'starter_id':'pitcher', 0:'gs_to'}))
        if gs_to_date.empty:
            gs_to_date = pd.DataFrame(columns=['pitcher','gs_to'])
        else:
            gs_to_date.columns = ['pitcher','gs_to']

        rates = aggregate_window(relief_cut).add_suffix('_to')
        rates = rates.rename(columns={'pitcher_to': 'pitcher'})
        appears = per_appearance_aggregate(relief_cut)

        merged = rates.merge(appears, on='pitcher', how='inner')
        merged = merged.merge(gs_to_date, on='pitcher', how='left')
        merged['gs_to'] = merged['gs_to'].fillna(0).astype(int)
        merged = merged[(merged['g_to'] >= MIN_G_TO) & (merged['gs_to'] <= MAX_GS_TO)]

        # Role usage through cutoff (statcast-derived: GF, SV, HLD, BS)
        usage = role_usage_aggregate(year, actual_cutoff,
                                     eligible_pitchers=set(merged['pitcher']))
        merged = merged.merge(usage, on='pitcher', how='left')
        for c in ['gf_to','sv_to','hld_to','bs_to']:
            merged[c] = merged[c].fillna(0).astype(int)
        merged['gf_pct_to']     = merged['gf_to'] / merged['g_to'].replace(0, np.nan)
        merged['sv_per_g_to']   = merged['sv_to'] / merged['g_to'].replace(0, np.nan)
        merged['hld_per_g_to']  = merged['hld_to'] / merged['g_to'].replace(0, np.nan)
        merged['sv_plus_hld_to'] = merged['sv_to'] + merged['hld_to']

        # FP-to-date NOW including SV/HLD/BS bonuses derived from statcast
        # (full BrownU scoring: K + IP×3.3 + SV×5 + HLD×2 − BB − 2×ER − H − HBP)
        merged['fp_skill_to'] = (
            merged['k_to'] + merged['ip_to']*3.3 - merged['bb_to']
            - 2*merged['er_to'] - merged['h_to'] - merged['hbp_to']
        ).round(1)
        merged['fp_with_role_to'] = (
            merged['fp_skill_to'] + 5*merged['sv_to'] + 2*merged['hld_to']
        ).round(1)

        merged['year'] = year
        merged['split_day'] = split_day
        merged['cutoff_date'] = cutoff.date()
        rows.append(merged)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def attach_lag_and_target(df: pd.DataFrame, multiyr: pd.DataFrame) -> pd.DataFrame:
    """Attach prior-year role/SV/HLD/fp_per_g and full-year target."""
    # Prior-year features
    lag = multiyr[['pitcher','year','role','sv','hld','g','ip','fp','fp_per_g',
                   'k_pct','bb_pct','xwoba_per_pa']].copy()
    lag['year_target'] = lag['year'] + 1
    lag = lag.drop(columns='year').rename(columns={
        'role':'role_lag1','sv':'sv_lag1','hld':'hld_lag1','g':'g_lag1',
        'ip':'ip_lag1','fp':'fp_lag1','fp_per_g':'fp_per_g_lag1',
        'k_pct':'k_pct_lag1','bb_pct':'bb_pct_lag1','xwoba_per_pa':'xwoba_per_pa_lag1',
    })
    df = df.merge(lag, left_on=['pitcher','year'], right_on=['pitcher','year_target'],
                   how='left').drop(columns=['year_target'])
    df['role_closer_lag1'] = (df['role_lag1'] == 'closer').astype(int)
    df['role_setup_lag1']  = (df['role_lag1'] == 'setup').astype(int)
    df['role_middle_lag1'] = (df['role_lag1'] == 'middle').astype(int)

    # Year-T target: full-year FP from multiyr
    target = multiyr[['pitcher','year','fp']].rename(columns={'fp':'fp_year_total'})
    df = df.merge(target, on=['pitcher','year'], how='left')
    return df


def main():
    print('=== build_rolling_relievers ===')
    if not (CACHE / 'relievers_multiyr_2018_2026.csv').exists():
        print('relievers_multiyr substrate missing — run build_relievers_multiyr.py first')
        return
    multiyr = pd.read_csv(CACHE / 'relievers_multiyr_2018_2026.csv')
    print(f'multiyr substrate: {len(multiyr)} rows')

    frames = []
    for yr in YEARS:
        sub = build_year(yr)
        if not sub.empty:
            print(f'  [{yr}] {len(sub)} (RP, split) rows')
            frames.append(sub)
    if not frames:
        print('No rolling RP data — abort'); return

    rolling = pd.concat(frames, ignore_index=True)
    rolling = attach_lag_and_target(rolling, multiyr)

    rolling.to_csv(OUT, index=False)
    print(f'\nWrote {OUT}: {len(rolling)} rows')
    print('  by year:')
    print(rolling.groupby('year').size().to_string())
    print('  by split_day:')
    print(rolling.groupby('split_day').size().to_string())
    print('\n  Coverage of fp_year_total target (non-null):')
    print(rolling.groupby('year')['fp_year_total'].apply(
        lambda s: f'{s.notna().sum()}/{len(s)}').to_string())
    print('\n  Coverage of lag features (non-null role_lag1):')
    print(rolling.groupby('year')['role_lag1'].apply(
        lambda s: f'{s.notna().sum()}/{len(s)}').to_string())


if __name__ == '__main__':
    main()
