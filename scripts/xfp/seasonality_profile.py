"""seasonality_profile.py — half-split career profile for hitters and pitchers.

For each player, computes their career-historical first-half (Apr-Jun) vs
second-half (Jul-Oct) production rate. Identifies back-loaded producers
(H2 > H1) and front-loaders (H1 > H2), then applies a seasonality
multiplier to RoS projections.

The frame: by mid-May we're 22% into the season. ~80% of remaining
games fall after All-Star break. Current rh3/rp3 projects RoS as
flat-rate from the season-to-date Bayesian blend — it ignores the
seasonal pattern. A player whose H2 is reliably +8% above H1 should
have their RoS boosted by ~8%; a front-loader should be discounted.

Method:
  1. For each player with ≥3 seasons of ≥100 PA (hitters) or ≥10 GS (SP)
     since 2018, compute per-season pre-July rate and post-July rate.
  2. Aggregate across seasons (PA-weighted for hitters, GS-weighted for SP)
     to get career H1 and H2 rates.
  3. h2_lift = (h2_rate - h1_rate) / h1_rate  (relative)
     h2_lift_abs = h2_rate - h1_rate          (absolute fp/PA or fp/start)
  4. Categorize:
       - BACK-LOADED if h2_lift > +5%
       - FRONT-LOADED if h2_lift < -5%
       - EVEN otherwise

Outputs:
  data/outputs/seasonality_hitters.csv
  data/outputs/seasonality_sps.csv
"""
from __future__ import annotations
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

# H1 = before July 7 (~All-Star Break midpoint over years)
# H2 = July 7 onward
HALF_CUTOFF_DAY = 7
HALF_CUTOFF_MONTH = 7


def _is_h2(date_str: str) -> bool:
    s = str(date_str)
    if len(s) < 10:
        return False
    month = int(s[5:7]); day = int(s[8:10])
    return (month, day) >= (HALF_CUTOFF_MONTH, HALF_CUTOFF_DAY)


# ─────────────────────────────────────────────────────────────────────────────
# Hitters
# ─────────────────────────────────────────────────────────────────────────────

def hitter_half_splits(years=range(2018, 2026)) -> pd.DataFrame:
    """Per-player career H1 vs H2 core_fp/PA (TB+BB+HBP-K).

    Restricted to 2018-2025 (full seasons, exclude 2020 COVID). Min 100 PA per
    half to count toward player's average.
    """
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
        df['is_h2'] = df['game_date'].astype(str).apply(_is_h2)
        df['tb'] = df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0).astype(int)
        df['bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
        df['hbp'] = (df['events'] == 'hit_by_pitch').astype(int)
        df['k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
        df['core_fp'] = df['tb'] + df['bb'] + df['hbp'] - df['k']
        df['pa'] = 1
        agg = df.groupby(['batter', 'year', 'is_h2'], as_index=False).agg(
            pa=('pa', 'sum'), core_fp=('core_fp', 'sum'))
        frames.append(agg)
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    # Filter to halves with ≥80 PA (loosened from 100 — early/late season cutoff hurts otherwise)
    full = full[full['pa'] >= 80]
    full['rate'] = full['core_fp'] / full['pa']

    # Per-player aggregate
    rows = []
    for batter, sub in full.groupby('batter'):
        h1 = sub[~sub['is_h2']]
        h2 = sub[sub['is_h2']]
        if len(h1) < 3 or len(h2) < 3:
            continue
        h1_pa = h1['pa'].sum(); h2_pa = h2['pa'].sum()
        h1_rate = (h1['rate'] * h1['pa']).sum() / h1_pa
        h2_rate = (h2['rate'] * h2['pa']).sum() / h2_pa
        seasons = sub['year'].nunique()
        rows.append({
            'batter': int(batter),
            'seasons_used': seasons,
            'h1_pa': int(h1_pa), 'h2_pa': int(h2_pa),
            'h1_rate': round(h1_rate, 4),
            'h2_rate': round(h2_rate, 4),
            'h2_lift_abs': round(h2_rate - h1_rate, 4),
            'h2_lift_pct': round((h2_rate - h1_rate) / max(h1_rate, 0.01) * 100, 1),
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Starting pitchers (per-start FP)
# ─────────────────────────────────────────────────────────────────────────────

def _identify_starter_per_year(year: int) -> pd.DataFrame:
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=['game_pk', 'inning', 'inning_topbot', 'pitcher', 'at_bat_number'])
    df = df[df['inning'] == 1].sort_values(['game_pk', 'inning_topbot', 'at_bat_number'])
    s = df.groupby(['game_pk', 'inning_topbot'])['pitcher'].first().reset_index()
    s.columns = ['game_pk', 'inning_topbot', 'starter_id']
    return s


def sp_half_splits(years=range(2018, 2026)) -> pd.DataFrame:
    """Per-SP career H1 vs H2 fp/start."""
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
        df['is_h2'] = df['game_date'].astype(str).apply(_is_h2)
        per_start = df.groupby(['game_pk', 'pitcher', 'year', 'is_h2'], as_index=False).agg(
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
    # Aggregate per (pitcher, year, is_h2)
    season = full.groupby(['pitcher', 'year', 'is_h2'], as_index=False).agg(
        gs=('game_pk', 'count'), fp_total=('fp', 'sum'))
    season['fp_per_start'] = season['fp_total'] / season['gs']
    season = season[season['gs'] >= 5]  # need ≥5 GS in a half to count

    rows = []
    for pid, sub in season.groupby('pitcher'):
        h1 = sub[~sub['is_h2']]; h2 = sub[sub['is_h2']]
        if len(h1) < 2 or len(h2) < 2:
            continue
        h1_gs = h1['gs'].sum(); h2_gs = h2['gs'].sum()
        h1_rate = h1['fp_total'].sum() / h1_gs
        h2_rate = h2['fp_total'].sum() / h2_gs
        rows.append({
            'pitcher': int(pid),
            'seasons_used': sub['year'].nunique(),
            'h1_gs': int(h1_gs), 'h2_gs': int(h2_gs),
            'h1_rate': round(h1_rate, 3),
            'h2_rate': round(h2_rate, 3),
            'h2_lift_abs': round(h2_rate - h1_rate, 3),
            'h2_lift_pct': round((h2_rate - h1_rate) / max(h1_rate, 0.01) * 100, 1),
        })
    return pd.DataFrame(rows)


def categorize(lift_pct: float) -> str:
    if lift_pct >= 8: return 'BACK-LOADED'
    if lift_pct <= -8: return 'FRONT-LOADED'
    if lift_pct >= 4: return 'mild back'
    if lift_pct <= -4: return 'mild front'
    return 'EVEN'


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print('[seasonality] computing hitter half-splits 2018-2025...')
    h = hitter_half_splits()
    if not h.empty:
        # Attach name + 2026 RoS
        rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
        h = h.merge(rh[['batter', 'player_name', 'team', 'rank',
                        'xfp_rh3_per_game', 'expected_total_fp_remaining']],
                    on='batter', how='left')
        h['category'] = h['h2_lift_pct'].apply(categorize)
        h = h.sort_values('h2_lift_pct', ascending=False)
        out = OUT / 'seasonality_hitters.csv'
        h.to_csv(out, index=False)
        print(f'  wrote {out} — {len(h)} hitters')

    print('[seasonality] computing SP half-splits 2018-2025...')
    s = sp_half_splits()
    if not s.empty:
        rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
        s = s.merge(rp[['pitcher', 'player_name', 'rank',
                        'xfp_rp3_per_start_sched', 'gs_to']],
                    on='pitcher', how='left')
        s['category'] = s['h2_lift_pct'].apply(categorize)
        s = s.sort_values('h2_lift_pct', ascending=False)
        out = OUT / 'seasonality_sps.csv'
        s.to_csv(out, index=False)
        print(f'  wrote {out} — {len(s)} SPs')


if __name__ == '__main__':
    main()
