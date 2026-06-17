"""seasonality_monthly.py — month-by-month career production profile.

Extends seasonality_profile.py from 2 buckets (H1/H2) to 6 monthly buckets
(April–September). For each player, computes their career fp rate per
calendar month, identifies hot/cold months relative to their annual mean,
and emits a remaining-season-weighted lift factor that updates as the
season progresses.

Method:
  1. Statcast PA-ending events 2018-2025 (excl 2020), 2026 partial.
  2. For each (player, year, month) compute fp_per_PA (hitters) or
     fp_per_start (SPs).
  3. Per player, require ≥3 seasons of ≥40 PA / ≥3 GS in each month to
     count that month toward the career rate.
  4. Career month rate = sample-weighted avg across qualifying seasons.
  5. Annual rate = (sum of fp / sum of PA) across all months/years.
  6. month_lift = (month_rate - annual_rate) / annual_rate
  7. RoS-weighted lift = sum over remaining months of (month_lift × month_weight)
     where weight = portion of remaining season in that month.

Outputs:
  data/outputs/seasonality_monthly_hitters.csv
  data/outputs/seasonality_monthly_sps.csv

Usage:
  python scripts/xfp/seasonality_monthly.py
"""
from __future__ import annotations
from datetime import date as _date
from pathlib import Path
import pandas as pd
import numpy as np

from plv_clone.paths import ROOT
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run',
    'walk', 'intent_walk',
    'hit_by_pitch', 'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
    'double_play', 'triple_play', 'field_error', 'catcher_interf',
}
OUT_EVENTS = {
    'strikeout', 'strikeout_double_play', 'field_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'force_out', 'double_play', 'triple_play',
    'fielders_choice_out', 'other_out',
    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
}
TWO_OUT_EVENTS = {'grounded_into_double_play', 'double_play'}

MONTHS = [4, 5, 6, 7, 8, 9]
MONTH_NAMES = {4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep'}


def _month(d: str) -> int:
    s = str(d)
    if len(s) < 10:
        return 0
    try:
        return int(s[5:7])
    except ValueError:
        return 0


# ─── Hitters ─────────────────────────────────────────────────────────────────

def hitter_monthly(years=range(2018, 2026)) -> pd.DataFrame:
    frames = []
    for year in years:
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['game_date', 'batter', 'events'])
        df = df[df['events'].isin(PA_EVENTS)].copy()
        if df.empty:
            continue
        df['year'] = year
        df['month'] = df['game_date'].astype(str).apply(_month)
        df = df[df['month'].isin(MONTHS)]
        df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
        df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
        df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['core_fp'] = df['tb'] + df['bb'] + df['hbp'] - df['k']
        df['pa'] = 1
        agg = df.groupby(['batter', 'year', 'month'], as_index=False).agg(
            pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
        frames.append(agg)
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full = full[full['pa'] >= 40]  # min 40 PA per (player, year, month) to count
    full['rate'] = full['core_fp'] / full['pa']

    rows = []
    for batter, sub in full.groupby('batter'):
        # Annual rate: weighted across all months/years
        total_pa = sub['pa'].sum(); total_fp = sub['core_fp'].sum()
        if total_pa < 800:
            continue  # need enough total sample
        annual_rate = total_fp / total_pa
        record = {'batter': int(batter), 'annual_rate': round(annual_rate, 4),
                  'total_pa': int(total_pa), 'seasons_used': sub['year'].nunique()}
        for m in MONTHS:
            sub_m = sub[sub['month'] == m]
            seasons_in_month = sub_m['year'].nunique()
            month_pa = sub_m['pa'].sum()
            if seasons_in_month < 3 or month_pa < 120:
                # Insufficient sample for this month
                record[f'{MONTH_NAMES[m]}_rate'] = None
                record[f'{MONTH_NAMES[m]}_pa'] = int(month_pa)
                record[f'{MONTH_NAMES[m]}_lift'] = None
                continue
            month_rate = sub_m['core_fp'].sum() / month_pa
            lift = (month_rate - annual_rate) / max(annual_rate, 0.01) * 100
            record[f'{MONTH_NAMES[m]}_rate'] = round(month_rate, 4)
            record[f'{MONTH_NAMES[m]}_pa'] = int(month_pa)
            record[f'{MONTH_NAMES[m]}_lift'] = round(lift, 1)
        rows.append(record)
    return pd.DataFrame(rows)


# ─── SPs ─────────────────────────────────────────────────────────────────────

def _identify_starter_per_year(year: int) -> pd.DataFrame:
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=['game_pk', 'inning', 'inning_topbot', 'pitcher', 'at_bat_number'])
    df = df[df['inning'] == 1].sort_values(['game_pk', 'inning_topbot', 'at_bat_number'])
    s = df.groupby(['game_pk', 'inning_topbot'])['pitcher'].first().reset_index()
    s.columns = ['game_pk', 'inning_topbot', 'starter_id']
    return s


def sp_monthly(years=range(2018, 2026)) -> pd.DataFrame:
    frames = []
    for year in years:
        if year == 2020:
            continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(
            path,
            columns=['game_pk', 'game_date', 'pitcher', 'inning', 'inning_topbot',
                     'events', 'bat_score', 'post_bat_score', 'at_bat_number'])
        starters = _identify_starter_per_year(year)
        if starters.empty:
            continue
        df = df.merge(starters, on=['game_pk', 'inning_topbot'], how='left')
        df = df[df['pitcher'] == df['starter_id']].copy()
        if df.empty:
            continue
        ev = df['events'].fillna('')
        df['k'] = ev.isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['bb'] = ev.isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (ev == 'hit_by_pitch').astype(int)
        df['h'] = ev.isin({'single', 'double', 'triple', 'home_run'}).astype(int)
        df['outs'] = ev.isin(OUT_EVENTS).astype(int)
        df.loc[ev.isin(TWO_OUT_EVENTS), 'outs'] = 2
        df['is_pa_end'] = (ev != '') & ev.isin(PA_EVENTS)
        runs = (pd.to_numeric(df['post_bat_score'], errors='coerce')
                - pd.to_numeric(df['bat_score'], errors='coerce')).clip(lower=0)
        df['er'] = runs.where(df['is_pa_end'], 0)
        df['year'] = year
        df['month'] = df['game_date'].astype(str).apply(_month)
        df = df[df['month'].isin(MONTHS)]
        per_start = df.groupby(['game_pk', 'pitcher', 'year', 'month'], as_index=False).agg(
            k=('k', 'sum'), bb=('bb', 'sum'), hbp=('hbp', 'sum'),
            h=('h', 'sum'), outs=('outs', 'sum'), er=('er', 'sum'))
        per_start['ip'] = per_start['outs'] / 3
        per_start['fp'] = (per_start['k'] + per_start['ip'] * 3.3
                           - per_start['h'] - 2 * per_start['er']
                           - per_start['bb'] - per_start['hbp'])
        frames.append(per_start)
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    season = full.groupby(['pitcher', 'year', 'month'], as_index=False).agg(
        gs=('game_pk', 'count'), fp_total=('fp', 'sum'))
    season = season[season['gs'] >= 3]  # ≥3 GS per (player, year, month)
    season['fp_per_start'] = season['fp_total'] / season['gs']

    rows = []
    for pid, sub in season.groupby('pitcher'):
        total_gs = sub['gs'].sum(); total_fp = sub['fp_total'].sum()
        if total_gs < 50:
            continue
        annual = total_fp / total_gs
        record = {'pitcher': int(pid), 'annual_rate': round(annual, 3),
                  'total_gs': int(total_gs), 'seasons_used': sub['year'].nunique()}
        for m in MONTHS:
            sub_m = sub[sub['month'] == m]
            seasons_in_month = sub_m['year'].nunique()
            month_gs = sub_m['gs'].sum()
            if seasons_in_month < 3 or month_gs < 8:
                record[f'{MONTH_NAMES[m]}_rate'] = None
                record[f'{MONTH_NAMES[m]}_gs'] = int(month_gs)
                record[f'{MONTH_NAMES[m]}_lift'] = None
                continue
            month_rate = sub_m['fp_total'].sum() / month_gs
            lift = (month_rate - annual) / max(annual, 0.01) * 100
            record[f'{MONTH_NAMES[m]}_rate'] = round(month_rate, 3)
            record[f'{MONTH_NAMES[m]}_gs'] = int(month_gs)
            record[f'{MONTH_NAMES[m]}_lift'] = round(lift, 1)
        rows.append(record)
    return pd.DataFrame(rows)


# ─── RoS-weighted lift ───────────────────────────────────────────────────────

def remaining_month_weights(today: _date | None = None) -> dict:
    """Fraction of remaining season in each month."""
    if today is None:
        today = _date.today()
    weights = {}
    for m in MONTHS:
        if m < today.month:
            weights[MONTH_NAMES[m]] = 0
        elif m == today.month:
            # partial month from today to end of month (rough)
            from calendar import monthrange
            last_day = monthrange(today.year, m)[1]
            weights[MONTH_NAMES[m]] = (last_day - today.day + 1) / 30
        else:
            weights[MONTH_NAMES[m]] = 1.0
    total = sum(weights.values())
    if total > 0:
        for k in weights:
            weights[k] = round(weights[k] / total, 3)
    return weights


def add_ros_weighted_lift(df: pd.DataFrame, today: _date | None = None) -> pd.DataFrame:
    """Add ros_lift_pct column = weighted average of available month lifts
    over the remaining season."""
    weights = remaining_month_weights(today)
    out = df.copy()
    out['remaining_weights'] = str(weights)

    def compute(row):
        num = den = 0
        for m_name, w in weights.items():
            if w <= 0:
                continue
            lift = row.get(f'{m_name}_lift')
            if lift is None or pd.isna(lift):
                continue
            num += lift * w
            den += w
        return round(num / den, 1) if den > 0 else None

    out['ros_weighted_lift_pct'] = out.apply(compute, axis=1)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print('[seasonality-monthly] hitters...')
    h = hitter_monthly()
    if not h.empty:
        rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
        h = h.merge(rh[['batter', 'player_name', 'team', 'rank',
                        'xfp_rh3_per_game', 'expected_total_fp_remaining']],
                    on='batter', how='left')
        h = add_ros_weighted_lift(h)
        h = h.sort_values('ros_weighted_lift_pct', ascending=False)
        out = OUT / 'seasonality_monthly_hitters.csv'
        h.to_csv(out, index=False)
        print(f'  wrote {out} ({len(h)} hitters)')

    print('[seasonality-monthly] SPs...')
    s = sp_monthly()
    if not s.empty:
        rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
        s = s.merge(rp[['pitcher', 'player_name', 'rank',
                        'xfp_rp3_per_start_sched', 'gs_to']],
                    on='pitcher', how='left')
        s = add_ros_weighted_lift(s)
        s = s.sort_values('ros_weighted_lift_pct', ascending=False)
        out = OUT / 'seasonality_monthly_sps.csv'
        s.to_csv(out, index=False)
        print(f'  wrote {out} ({len(s)} SPs)')


if __name__ == '__main__':
    main()
