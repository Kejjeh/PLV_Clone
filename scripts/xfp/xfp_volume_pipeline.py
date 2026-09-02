"""
xfp_volume — hitter FORWARD-VOLUME (playing time) companion model.

Projects RoS PA per remaining TEAM game (rate form, so season length and
cutoff timing cancel) for every hitter, per (batter, year, split_day).

WHY: forward-error recon on 25 logged projection snapshots (2026-07-09)
showed realized forward PA explains R^2 = 0.47-0.69 of forward TOTAL
fantasy points vs 0.14-0.20 for the projected rate — volume is 3-5x the
rate signal and nothing in the stack projects it. This model converts the
(good) rh3 per-PA rate projections into better RoS TOTAL rankings:

    RoS total FP  ~=  xfp_rh3_per_pa  x  proj_ros_pa_per_teamgame  x  team_games_remaining

It is a COMPANION model: it does NOT touch rh3/rp3/rprs2 and is not in
any FEATS list. Pre-registration:
data/research/validation_runs/hitter_volume_model_2026-07-09.md

Idiom mirrors src/plv_clone/models/xfp/rh3.py: Ridge + StandardScaler,
LOO cross-year over TRAIN_YEARS, then final fit on all train years and a
2026 projection from the latest in-progress split.

Baseline = naive persistence: RoS PA/team-game := to-date PA/team-game.
Gates (locked in the prereg BEFORE results):
  1. pooled LOO ΔSpearman (model - naive) >= +0.03
  2. per-year Δ > 0 in >= 5/7 LOO years
  3. 2024 AND 2025 LOO folds both Δ > 0

Output: data/outputs/xfp_volume_projections.csv
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

from lib.volume_model import (
    build_team_games, build_catcher_flags, attach_team_games,
    make_pipe, cross_year_eval as _cross_year_eval,
    tercile_calibration as _tercile_calibration,
    check_gates as _check_gates,
)

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
ROLLING_CSV = CACHE / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = CACHE / 'hitters_multiyr_2015_2026.csv'
IL_CSV = CACHE / 'il_split_features_2018_2026.csv'
PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_volume_projections.csv'

TARGET = 'ros_pa_per_teamgame'
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
HOLDOUT_YEARS = [2024, 2025]
PA_TO_MIN = 30
TEAMGAMES_TO_MIN = 15
TEAMGAMES_REMAIN_MIN = 15
MIN_CELL_N = 30           # min rows per (year, split_day) cell for Spearman
GATE_POOLED_DSPEAR = 0.03
GATE_YEARS_POSITIVE = 5
SEASON_GAMES = 162
CATCHER_MIN_PITCHES = 100  # pitches caught (fielder_2) to flag position=C
PRED_CLIP = (0.0, 5.2)     # a team game has ~5.2 PA max realistic top spot

VOLUME_FEATS = [
    'pa_per_teamgame_to',       # persistence anchor
    'started_pct_to',
    'lineup_spot_to',
    'lineup_spot_missing',
    'pa_per_started_game_to',
    'pa_last21',
    'prior1_pa_per_g',
    'prior2_pa_per_g',
    'has_prior1',
    'career_stage',
    'is_catcher',
    'il_stints_to',
    'days_on_il_to',
    'is_on_il_at_split',
    'split_day',
]


# team games / catcher flags / eval toolkit: shared lib.volume_model
# (hoisted 2026-07-19 — bodies unchanged, per-year disk-cached scans)

# ------------------------------------------------------------------ features
def prepare(rolling: pd.DataFrame) -> pd.DataFrame:
    multiyr = pd.read_csv(MULTIYR_CSV,
                          usecols=['batter', 'year', 'team', 'pa', 'mlb_pa',
                                   'player_name'])

    # batter -> modal team per year (row with max statcast pa)
    bt = (multiyr.sort_values('pa', ascending=False)
          .drop_duplicates(['batter', 'year'])[['batter', 'year', 'team']])

    print('Building team-games schedule from statcast parquets...', flush=True)
    team_games = build_team_games()
    rolling = attach_team_games(rolling, team_games, bt, id_col='batter')

    # target + anchor
    rolling['pa_per_teamgame_to'] = rolling['pa_to'] / rolling['team_games_to']
    rolling[TARGET] = rolling['ros_pa'] / rolling['team_games_remaining']

    # priors from official (mlb_pa) prior-year totals
    pa_year = multiyr.groupby(['batter', 'year'])['mlb_pa'].max()
    for off, col in ((1, 'prior1_pa_per_g'), (2, 'prior2_pa_per_g')):
        prior_year = rolling['year'] - off
        # 2021 looks back to 2019 (skip the 60-game 2020 season)
        prior_year = prior_year.where(prior_year != 2020, 2019)
        keys = list(zip(rolling['batter'], prior_year))
        vals = pa_year.reindex(keys).values
        rolling[col] = vals / SEASON_GAMES
    rolling['has_prior1'] = rolling['prior1_pa_per_g'].notna().astype(int)
    rolling['prior1_pa_per_g'] = rolling['prior1_pa_per_g'].fillna(0.0)
    rolling['prior2_pa_per_g'] = rolling['prior2_pa_per_g'].fillna(0.0)

    # career stage (rh3 idiom)
    first_year = multiyr.groupby('batter')['year'].min().to_dict()
    rolling['career_stage'] = (rolling['year'] -
                               rolling['batter'].map(first_year).fillna(rolling['year'])
                               ).clip(0, 20)

    # catcher flag
    print('Deriving catcher flags from fielder_2...', flush=True)
    cflags = build_catcher_flags(CATCHER_MIN_PITCHES)
    rolling['is_catcher'] = [cflags.get((y, int(b)), 0)
                             for y, b in zip(rolling['year'], rolling['batter'])]

    # lineup features
    rolling['lineup_spot_missing'] = rolling['lineup_spot_to'].isna().astype(int)
    rolling['lineup_spot_to'] = rolling['lineup_spot_to'].fillna(10.0)
    train_mask = rolling['year'].isin(TRAIN_YEARS)
    ppsg_mu = rolling.loc[train_mask, 'pa_per_started_game_to'].mean()
    rolling['pa_per_started_game_to'] = rolling['pa_per_started_game_to'].fillna(ppsg_mu)
    rolling['started_pct_to'] = rolling['started_pct_to'].fillna(0.0)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0.0)

    # IL state — file only has monthly-ish split anchors; asof-backward join
    il = pd.read_csv(IL_CSV).rename(columns={'pitcher': 'batter'})
    il = il.sort_values('split_day')
    roll_sorted = rolling.sort_values('split_day')
    merged = pd.merge_asof(roll_sorted, il,
                           on='split_day', by=['batter', 'year'],
                           direction='backward')
    rolling = merged.sort_index()
    for c in ('il_stints_to', 'days_on_il_to', 'is_on_il_at_split'):
        rolling[c] = rolling[c].fillna(0.0)

    return rolling


def eligible(df: pd.DataFrame, need_target: bool = True) -> pd.DataFrame:
    m = ((df['pa_to'] >= PA_TO_MIN)
         & (df['team_games_to'] >= TEAMGAMES_TO_MIN)
         & (df['team_games_remaining'] >= TEAMGAMES_REMAIN_MIN)
         & (df['year'] != 2020))
    out = df[m].dropna(subset=VOLUME_FEATS)
    if need_target:
        out = out.dropna(subset=[TARGET])
    return out


# ---------------------------------------------------------------------- eval
def cross_year_eval(df: pd.DataFrame):
    """LOO over TRAIN_YEARS (shared engine, hitter parametrization)."""
    return _cross_year_eval(
        df, feats=VOLUME_FEATS, target=TARGET, naive_col='pa_per_teamgame_to',
        id_col='batter', train_years=TRAIN_YEARS, pred_clip=PRED_CLIP,
        eligible_fn=eligible, min_cell_n=MIN_CELL_N)


def tercile_calibration(detail: pd.DataFrame) -> pd.DataFrame:
    return _tercile_calibration(detail, TARGET, 'pa_per_teamgame_to', decimals=3)


# --------------------------------------------------------------------- gates
def check_gates(per_year: dict, pooled: dict) -> tuple[bool, list[str]]:
    return _check_gates(per_year, pooled, pooled_gate=GATE_POOLED_DSPEAR,
                        years_positive=GATE_YEARS_POSITIVE,
                        holdout_years=HOLDOUT_YEARS)


# ---------------------------------------------------------------------- main
def main():
    print('=== xfp_volume — hitter forward-volume (playing time) model ===')
    usecols = ['batter', 'year', 'split_day', 'cutoff_date', 'pa_to',
               'pa_last21', 'ros_pa', 'lineup_spot_to', 'started_pct_to',
               'pa_per_started_game_to']
    rolling = pd.read_csv(ROLLING_CSV, usecols=usecols)
    print(f'rolling: {len(rolling)} rows')

    rolling = prepare(rolling)

    print('\n--- LOO cross-year eval (model vs naive persistence) ---')
    per_year, pooled, detail = cross_year_eval(rolling)
    print(f"  {'year':>5} {'sp_model':>9} {'sp_naive':>9} {'Δ':>8} "
          f"{'mae_m':>7} {'mae_n':>7} {'n':>6}")
    for y, v in sorted(per_year.items()):
        print(f"  {y:>5} {v['spear_model']:>9.4f} {v['spear_naive']:>9.4f} "
              f"{v['delta']:>+8.4f} {v['mae_model']:>7.4f} {v['mae_naive']:>7.4f} "
              f"{v['n']:>6}")
    print(f"  {'POOL':>5} {pooled['spear_model']:>9.4f} {pooled['spear_naive']:>9.4f} "
          f"{pooled['delta']:>+8.4f} {pooled['mae_model']:>7.4f} "
          f"{pooled['mae_naive']:>7.4f} {pooled['n']:>6}")

    print('\n--- Calibration by predicted tercile (pooled LOO) ---')
    print(tercile_calibration(detail).to_string())

    print('\n--- Pre-registered gates ---')
    passed, lines = check_gates(per_year, pooled)
    for ln in lines:
        print('  ' + ln)
    verdict = 'PASS' if passed else 'REJECTED'
    print(f'  VERDICT: {verdict}')

    # ------------------------------------------------ final fit + 2026 output
    train = eligible(rolling[rolling['year'].isin(TRAIN_YEARS)])
    pipe = make_pipe()
    pipe.fit(train[VOLUME_FEATS].values, train[TARGET].values)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final fit (n_train={len(train)}, '
          f'alpha={pipe.named_steps["r"].alpha_:.1f}) — coefficients ---')
    for f, c in sorted(zip(VOLUME_FEATS, coefs), key=lambda x: -abs(x[1])):
        print(f'    {f:<26s} {c:+.4f}')

    # projection year = latest season in the substrate (audit R2: the old
    # hardcoded ==2026 would silently no-op on 2027-01-01)
    proj_year = int(rolling['year'].max())
    df_26 = rolling[rolling['year'] == proj_year].copy()
    if df_26.empty:
        print(f'No {proj_year} rows — skipping projection output.')
        return verdict
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split)
                  & (df_26['pa_to'] >= PA_TO_MIN)
                  & (df_26['team_games_to'] >= TEAMGAMES_TO_MIN)]
    df_26 = df_26.dropna(subset=VOLUME_FEATS).drop_duplicates('batter')
    df_26['proj_ros_pa_per_teamgame'] = np.clip(
        pipe.predict(df_26[VOLUME_FEATS].values), *PRED_CLIP)
    df_26['naive_pace'] = df_26['pa_per_teamgame_to']
    df_26['volume_percentile'] = (df_26['proj_ros_pa_per_teamgame']
                                  .rank(pct=True) * 100).round(1)

    names = (pd.read_csv(MULTIYR_CSV, usecols=['batter', 'year', 'player_name', 'team'])
             .query('year == @proj_year').drop_duplicates('batter')
             [['batter', 'player_name', 'team']])
    df_26 = df_26.merge(names, on='batter', how='left', suffixes=('', '_m'))
    if 'team' not in df_26.columns and 'team_m' in df_26.columns:
        df_26['team'] = df_26['team_m']

    out = df_26.rename(columns={'batter': 'mlbam_id'})
    out_cols = ['mlbam_id', 'player_name', 'team',
                'proj_ros_pa_per_teamgame', 'naive_pace', 'volume_percentile',
                'pa_to', 'team_games_to', 'pa_per_teamgame_to',
                'started_pct_to', 'lineup_spot_to', 'pa_per_started_game_to',
                'pa_last21', 'prior1_pa_per_g', 'is_catcher',
                'is_on_il_at_split', 'career_stage', 'split_day']
    out_cols = [c for c in out_cols if c in out.columns]
    out = out.sort_values('proj_ros_pa_per_teamgame', ascending=False)
    out[out_cols].round(4).to_csv(PROJ_CSV, index=False)
    print(f'\nWrote {PROJ_CSV}: {len(out)} hitters (split_day={latest_split}, '
          f'as of {date.today()})')

    print('\nTop 12 by projected RoS PA/team-game:')
    show = ['player_name', 'team', 'proj_ros_pa_per_teamgame', 'naive_pace',
            'started_pct_to', 'lineup_spot_to', 'is_catcher']
    print(out[show].head(12).to_string(index=False))
    print('\nSanity — catchers (should sit well below everyday regulars):')
    print(out[out['is_catcher'] == 1][show].head(8).to_string(index=False))
    return verdict


if __name__ == '__main__':
    main()
