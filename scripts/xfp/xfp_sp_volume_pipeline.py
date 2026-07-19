"""
xfp_sp_volume — SP FORWARD-VOLUME (start count) companion model.

Projects RoS starts per remaining TEAM game (rate form, so season length and
cutoff timing cancel) for every SP, per (pitcher, year, split_day).

WHY: forward-error recon (2026-07-09) showed realized forward STARTS dominate
SP forward-total fantasy points (Spearman 0.79-0.83 vs 0.35-0.40 for the rate
projection); 8% of non-IL SPs made 0 starts in the next 20 days and 60% of
IL-flagged SPs on 6/04 never started within 34 days. This model converts the
(good) rp3 per-start rate projections into better RoS TOTAL rankings:

    RoS total FP  ~=  xfp_rp3_per_start  x  proj_ros_gs_per_teamgame  x  team_games_remaining

It is a COMPANION model: it does NOT touch rh3/rp3/rprs2 and is not in any
FEATS list. The 10-start weekly cap is a DECISION layer, not part of this
model. Pre-registration:
data/research/validation_runs/sp_volume_model_2026-07-09.md

Substrate truncation (pre-acknowledged): the rolling builder emits a split
row only when the pitcher has >= 1 subsequent start, so ros_gs >= 1 on 100%
of rows — the model ranks volume CONDITIONAL on at least one more start.
"Projects low" means few starts, never zero starts.

Idiom mirrors scripts/xfp/xfp_volume_pipeline.py (the hitter volume model,
PASS 2026-07-09): Ridge + StandardScaler, LOO cross-year over TRAIN_YEARS,
then final fit on all train years and a 2026 projection from each pitcher's
latest recent in-progress split (rp3's recency-window idiom).

Baseline = naive persistence: RoS GS/team-game := to-date GS/team-game.
Gates (locked in the prereg BEFORE results):
  1. pooled LOO ΔSpearman (model - naive) >= +0.03
  2. per-year Δ > 0 in >= 5/7 LOO years
  3. 2024 AND 2025 LOO folds both Δ > 0

Output: data/outputs/xfp_sp_volume_projections.csv
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

from lib.volume_model import (
    build_team_games, attach_team_games,
    make_pipe, cross_year_eval as _cross_year_eval,
    tercile_calibration as _tercile_calibration,
    check_gates as _check_gates,
)

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
ROLLING_CSV = CACHE / 'rolling_pitchers_2018_2026.csv'
MULTIYR_CSV = CACHE / 'sp_multiyr_2015_2025.csv'   # actually carries 2015-2026
IL_CSV = CACHE / 'il_split_features_2018_2026.csv'
TEAM_MAP_CSV = CACHE / 'pitcher_primary_team_2018_2026.csv'
PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_sp_volume_projections.csv'

TARGET = 'ros_gs_per_teamgame'
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
HOLDOUT_YEARS = [2024, 2025]
GS_TO_MIN = 2              # rp3's EVAL_GS_MIN — the SP modeling-universe filter
TEAMGAMES_TO_MIN = 15
TEAMGAMES_REMAIN_MIN = 15
MIN_CELL_N = 30            # min rows per (year, split_day) cell for Spearman
GATE_POOLED_DSPEAR = 0.03
GATE_YEARS_POSITIVE = 5
SEASON_GAMES = 162
PRED_CLIP = (0.0, 0.30)    # strict every-4th-day workhorse tops out ~0.25
PROJ_SPLIT_RECENCY_DAYS = 14  # rp3 idiom: latest snapshot per pitcher, capped

SP_VOLUME_FEATS = [
    'gs_per_teamgame_to',       # persistence anchor
    'gs_last21',
    'fp_per_start_to',          # rotation-spot retention quality
    'prior1_gs_per_g',
    'prior2_gs_per_g',
    'has_prior1',
    'career_stage',
    'il_stints_to',
    'days_on_il_to',
    'is_on_il_at_split',
    'days_since_il_return_imp',
    'split_day',
]


# team games / eval toolkit: shared lib.volume_model
# (hoisted 2026-07-19 — bodies unchanged, per-year disk-cached scans)

# ------------------------------------------------------------------ features
def prepare(rolling: pd.DataFrame) -> pd.DataFrame:
    multiyr = pd.read_csv(MULTIYR_CSV, usecols=['pitcher', 'year', 'gs', 'player_name'])

    pt = pd.read_csv(TEAM_MAP_CSV).rename(columns={'pitcher_team': 'team'})
    pt = pt.drop_duplicates(['pitcher', 'year'])

    print('Building team-games schedule from statcast parquets...', flush=True)
    team_games = build_team_games()
    rolling = attach_team_games(rolling, team_games, pt, id_col='pitcher')

    # target + anchor
    rolling['gs_per_teamgame_to'] = rolling['gs_to'] / rolling['team_games_to']
    rolling[TARGET] = rolling['ros_gs'] / rolling['team_games_remaining']

    # priors from official prior-year GS totals
    gs_year = multiyr.groupby(['pitcher', 'year'])['gs'].max()
    for off, col in ((1, 'prior1_gs_per_g'), (2, 'prior2_gs_per_g')):
        prior_year = rolling['year'] - off
        # 2021 looks back to 2019 (skip the 60-game 2020 season)
        prior_year = prior_year.where(prior_year != 2020, 2019)
        keys = list(zip(rolling['pitcher'], prior_year))
        vals = gs_year.reindex(keys).values
        rolling[col] = vals / SEASON_GAMES
    rolling['has_prior1'] = rolling['prior1_gs_per_g'].notna().astype(int)
    rolling['prior1_gs_per_g'] = rolling['prior1_gs_per_g'].fillna(0.0)
    rolling['prior2_gs_per_g'] = rolling['prior2_gs_per_g'].fillna(0.0)

    # career stage (rh3/rp3 idiom)
    first_year = multiyr.groupby('pitcher')['year'].min().to_dict()
    rolling['career_stage'] = (rolling['year'] -
                               rolling['pitcher'].map(first_year).fillna(rolling['year'])
                               ).clip(0, 20)

    # recent-volume fill
    rolling['gs_last21'] = rolling['gs_last21'].fillna(0.0)

    # IL state — the IL file only has MONTHLY split anchors (30/60/90/120 +
    # end-of-season) while the rolling substrate is weekly, so an exact join
    # matches <1% of rows (verified 2026-07-09; rp3's exact join has the same
    # property). Use the hitter volume pipeline's asof-backward idiom instead:
    # each weekly row picks up the most recent PAST IL anchor (leakage-safe).
    il = pd.read_csv(IL_CSV).sort_values('split_day')
    roll_sorted = rolling.sort_values('split_day')
    rolling = pd.merge_asof(roll_sorted, il,
                            on='split_day', by=['pitcher', 'year'],
                            direction='backward').sort_index()
    for c in ('il_stints_to', 'days_on_il_to', 'is_on_il_at_split'):
        rolling[c] = rolling[c].fillna(0.0)
    _dsr_max = rolling['days_since_il_return'].max(skipna=True)
    max_dsr = float(_dsr_max) if pd.notna(_dsr_max) else 200.0
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)

    return rolling


def eligible(df: pd.DataFrame, need_target: bool = True) -> pd.DataFrame:
    m = ((df['gs_to'] >= GS_TO_MIN)
         & (df['team_games_to'] >= TEAMGAMES_TO_MIN)
         & (df['team_games_remaining'] >= TEAMGAMES_REMAIN_MIN)
         & (df['year'] != 2020))
    out = df[m].dropna(subset=SP_VOLUME_FEATS)
    if need_target:
        out = out.dropna(subset=[TARGET])
    return out


# ---------------------------------------------------------------------- eval
def cross_year_eval(df: pd.DataFrame):
    """LOO over TRAIN_YEARS (shared engine, SP parametrization)."""
    return _cross_year_eval(
        df, feats=SP_VOLUME_FEATS, target=TARGET, naive_col='gs_per_teamgame_to',
        id_col='pitcher', train_years=TRAIN_YEARS, pred_clip=PRED_CLIP,
        eligible_fn=eligible, min_cell_n=MIN_CELL_N)


def tercile_calibration(detail: pd.DataFrame) -> pd.DataFrame:
    return _tercile_calibration(detail, TARGET, 'gs_per_teamgame_to', decimals=4)


# --------------------------------------------------------------------- gates
def check_gates(per_year: dict, pooled: dict) -> tuple[bool, list[str]]:
    return _check_gates(per_year, pooled, pooled_gate=GATE_POOLED_DSPEAR,
                        years_positive=GATE_YEARS_POSITIVE,
                        holdout_years=HOLDOUT_YEARS)


# ---------------------------------------------------------------------- main
def main():
    print('=== xfp_sp_volume — SP forward-volume (start count) model ===')
    usecols = ['pitcher', 'year', 'split_day', 'cutoff_date', 'gs_to',
               'gs_last21', 'fp_per_start_to', 'ros_gs']
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
    pipe.fit(train[SP_VOLUME_FEATS].values, train[TARGET].values)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final fit (n_train={len(train)}, '
          f'alpha={pipe.named_steps["r"].alpha_:.1f}) — coefficients ---')
    for f, c in sorted(zip(SP_VOLUME_FEATS, coefs), key=lambda x: -abs(x[1])):
        print(f'    {f:<28s} {c:+.4f}')

    # projection year = latest season in the substrate (audit R2: the old
    # hardcoded ==2026 would silently no-op on 2027-01-01)
    proj_year = int(rolling['year'].max())
    df_26 = rolling[rolling['year'] == proj_year].copy()
    if df_26.empty:
        print(f'No {proj_year} rows — skipping projection output.')
        return verdict
    latest_split = int(df_26['split_day'].max())
    # rp3 idiom: each pitcher's MOST-RECENT snapshot within the recency window
    # (a pitcher's latest-split row only exists once a subsequent start is
    # logged, so latest-split-only silently drops recent starters).
    df_26 = df_26[(df_26['split_day'] >= latest_split - PROJ_SPLIT_RECENCY_DAYS)
                  & (df_26['gs_to'] >= GS_TO_MIN)
                  & (df_26['team_games_to'] >= TEAMGAMES_TO_MIN)]
    df_26 = (df_26.sort_values('split_day')
             .groupby('pitcher', as_index=False, sort=False)
             .tail(1))
    df_26 = df_26.dropna(subset=SP_VOLUME_FEATS).drop_duplicates('pitcher')
    df_26['proj_ros_gs_per_teamgame'] = np.clip(
        pipe.predict(df_26[SP_VOLUME_FEATS].values), *PRED_CLIP)
    df_26['naive_pace'] = df_26['gs_per_teamgame_to']
    # Implied RoS start count: statcast-derived team_games_remaining is only
    # "games already played after cutoff" for the in-progress season, so use
    # the 162-game schedule instead.
    df_26['team_games_remaining_implied'] = (SEASON_GAMES - df_26['team_games_to']).clip(lower=0)
    df_26['proj_ros_starts'] = (df_26['proj_ros_gs_per_teamgame']
                                * df_26['team_games_remaining_implied']).round(1)
    df_26['volume_percentile'] = (df_26['proj_ros_gs_per_teamgame']
                                  .rank(pct=True) * 100).round(1)

    names = (pd.read_csv(MULTIYR_CSV, usecols=['pitcher', 'year', 'player_name'])
             .sort_values('year', ascending=False)
             .drop_duplicates('pitcher')[['pitcher', 'player_name']])
    df_26 = df_26.merge(names, on='pitcher', how='left')

    out = df_26.rename(columns={'pitcher': 'mlbam_id'})
    out_cols = ['mlbam_id', 'player_name', 'team',
                'proj_ros_gs_per_teamgame', 'naive_pace', 'proj_ros_starts',
                'team_games_remaining_implied', 'volume_percentile',
                'gs_to', 'team_games_to', 'gs_per_teamgame_to', 'gs_last21',
                'fp_per_start_to', 'prior1_gs_per_g', 'career_stage',
                'is_on_il_at_split', 'days_since_il_return_imp',
                'il_stints_to', 'split_day']
    out_cols = [c for c in out_cols if c in out.columns]
    out = out.sort_values('proj_ros_gs_per_teamgame', ascending=False)
    out[out_cols].round(4).to_csv(PROJ_CSV, index=False)
    print(f'\nWrote {PROJ_CSV}: {len(out)} pitchers (latest split={latest_split}, '
          f'as of {date.today()})')

    show = ['player_name', 'team', 'proj_ros_gs_per_teamgame', 'naive_pace',
            'proj_ros_starts', 'gs_to', 'gs_last21', 'is_on_il_at_split']
    print('\nTop 12 by projected RoS GS/team-game:')
    print(out[show].head(12).to_string(index=False))

    print('\nSanity — IL-stint arms now active again (il_stints_to >= 1, '
          'gs_last21 >= 3): model should sit ABOVE season-long naive pace '
          '(the naive pace is dragged down by the missed weeks):')
    il_ret = out[(out['il_stints_to'] >= 1) & (out['gs_last21'] >= 3)].copy()
    il_ret['model_minus_naive'] = (il_ret['proj_ros_gs_per_teamgame']
                                   - il_ret['naive_pace']).round(4)
    il_ret = il_ret.sort_values('model_minus_naive', ascending=False)
    print(il_ret[show + ['model_minus_naive']].head(8).to_string(index=False))
    frac_above = float((il_ret['model_minus_naive'] > 0).mean()) if len(il_ret) else np.nan
    print(f'  share of active IL-stint arms projected above naive pace: {frac_above:.1%}')

    print('\nSanity — recent callups (gs_to <= 6, no prior-year GS): '
          'should project BELOW full-season workhorses:')
    callups = out[(out['gs_to'] <= 6) & (out['prior1_gs_per_g'] == 0)]
    print(callups[show].head(8).to_string(index=False))
    return verdict


if __name__ == '__main__':
    main()
