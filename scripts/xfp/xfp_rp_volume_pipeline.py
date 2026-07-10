"""
xfp_rp_volume — RP FORWARD-VOLUME (appearance count) companion model.

Projects RoS relief appearances per remaining TEAM game (rate form, so
season length and cutoff timing cancel) for every RP, per
(pitcher, year, split_day).

WHY: rprs2 projects a RoS TOTAL (fp_year_total minus actuals) but reliever
workload varies hugely with role/health/team context; realized forward
volume dominated forward-total FP for both hitters and SPs (2026-07-09
recon) and nothing in the stack projects RP appearances — the snapshot
logger's proj_volume column is NaN for RPs. This model completes the
volume layer (hitter +0.074 / SP +0.100 Spearman vs naive, both PASS
2026-07-09):

    RoS total FP  ~=  rprs2_rate_skill  x  proj_ros_g_per_teamgame  x  team_games_remaining

It is a COMPANION model: it does NOT touch rh3/rp3/rprs2 and is not in any
FEATS list. Pre-registration:
data/research/validation_runs/rp_volume_model_2026-07-10.md

Target derivation (pre-registered): the reliever rolling substrate carries
NO RoS column, so ros_g is derived from the statcast parquets with the
substrate builder's own relief-appearance idiom (pitcher != half-inning
starter, distinct game_pk) — verified to reproduce substrate g_to exactly.
Unlike the SP substrate there is NO truncation: the zero-forward-appearance
class exists (~22% of rows) and attrition IS learnable.

Idiom mirrors scripts/xfp/xfp_sp_volume_pipeline.py: Ridge + StandardScaler,
LOO cross-year over TRAIN_YEARS, then final fit on all train years and a
2026 projection from each pitcher's latest recent in-progress split.

Baseline = naive persistence: RoS G/team-game := to-date G/team-game.
Gates (locked in the prereg BEFORE results):
  1. pooled LOO ΔSpearman (model - naive) >= +0.03
  2. per-year Δ > 0 in >= 5/6 LOO years
  3. 2024 AND 2025 LOO folds both Δ > 0
MARGINAL band [+0.01, +0.03): report exact numbers, do NOT wire the logger.

Output: data/outputs/xfp_rp_volume_projections.csv
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
ROLLING_CSV = CACHE / 'rolling_relievers_2018_2026.csv'
MULTIYR_CSV = CACHE / 'relievers_multiyr_2018_2026.csv'
IL_CSV = CACHE / 'il_split_features_2018_2026.csv'
PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_rp_volume_projections.csv'

TARGET = 'ros_g_per_teamgame'
TRAIN_YEARS = [2019, 2021, 2022, 2023, 2024, 2025]   # rprs2 convention
HOLDOUT_YEARS = [2024, 2025]
G_TO_MIN = 5               # rprs2's EVAL_G_MIN / substrate MIN_G_TO
TEAMGAMES_TO_MIN = 15
TEAMGAMES_REMAIN_MIN = 15
MIN_CELL_N = 30            # min rows per (year, split_day) cell for Spearman
GATE_POOLED_DSPEAR = 0.03
MARGINAL_DSPEAR = 0.01
GATE_YEARS_POSITIVE = 5
SEASON_GAMES = 162
PRED_CLIP = (0.0, 0.55)    # max-workload RP ~80 appearances / 162 ~ 0.49
PROJ_SPLIT_RECENCY_DAYS = 14  # SP-volume idiom: latest snapshot per pitcher
LAST21_DAYS = 21

RP_VOLUME_FEATS = [
    'g_per_teamgame_to',        # persistence anchor
    'g_last21',
    'ip_per_g_to',
    'gf_pct_to',
    'sv_per_g_to',
    'hld_per_g_to',
    'fp_skill_per_g_to',
    'prior1_g_per_g',
    'prior2_g_per_g',
    'has_prior1',
    'sv_per_g_lag1',
    'hld_per_g_lag1',
    'career_stage',
    'il_stints_to',
    'days_on_il_to',
    'is_on_il_at_split',
    'days_since_il_return_imp',
    'split_day',
]


# --------------------------------------------- statcast pass (single load/yr)
def build_schedule_and_relief_apps() -> tuple[pd.DataFrame, dict]:
    """One statcast pass per year returning both:
    - team_games: long frame (year, team, game_date), one row per team-game
    - relief_apps: {(year, pitcher) -> sorted np.datetime64 array of relief
      appearance dates}, using the substrate builder's own idiom
      (build_rolling_relievers.relief_pitches_only): a pitcher-game is a
      relief appearance iff pitcher != first pitcher of his
      (game_pk, inning_topbot) half.
    """
    tg_frames = []
    relief_apps: dict[tuple[int, int], np.ndarray] = {}
    for yr in list(range(2018, 2027)):
        if yr == 2020:
            continue
        p_path = CACHE / f'statcast_{yr}.parquet'
        if not p_path.exists():
            continue
        p = pd.read_parquet(p_path, columns=['game_pk', 'game_date', 'pitcher',
                                             'inning', 'inning_topbot',
                                             'home_team', 'away_team'])
        p['game_date'] = pd.to_datetime(p['game_date'])

        # team games
        d = p.drop_duplicates('game_pk')
        home = d[['game_pk', 'game_date', 'home_team']].rename(columns={'home_team': 'team'})
        away = d[['game_pk', 'game_date', 'away_team']].rename(columns={'away_team': 'team'})
        tg = pd.concat([home, away], ignore_index=True)
        tg['year'] = yr
        tg_frames.append(tg[['year', 'team', 'game_date']])

        # relief appearances (builder idiom — frame order preserved, no sort)
        p['inning'] = pd.to_numeric(p['inning'], errors='coerce')
        starts = (p[p['inning'] == 1]
                  .groupby(['game_pk', 'inning_topbot'])['pitcher']
                  .first().reset_index().rename(columns={'pitcher': 'starter_id'}))
        pg = p[['game_pk', 'game_date', 'pitcher', 'inning_topbot']].drop_duplicates(
            ['game_pk', 'pitcher', 'inning_topbot'])
        pg = pg.merge(starts, on=['game_pk', 'inning_topbot'], how='left')
        relief = (pg[pg['pitcher'] != pg['starter_id']]
                  .drop_duplicates(['game_pk', 'pitcher']))
        for pid, g in relief.groupby('pitcher'):
            relief_apps[(yr, int(pid))] = np.sort(g['game_date'].values)
    return pd.concat(tg_frames, ignore_index=True), relief_apps


def attach_team_games(rolling: pd.DataFrame, team_games: pd.DataFrame) -> pd.DataFrame:
    """Attach team_games_to / team_games_remaining per row via the substrate's
    own team_abbr column; league-mean fallback when the team is unmapped."""
    out = rolling.rename(columns={'team_abbr': 'team'}).copy()
    out['cutoff_date'] = pd.to_datetime(out['cutoff_date'])

    dates_by = {k: np.sort(g['game_date'].values)
                for k, g in team_games.groupby(['year', 'team'])}
    total_by = {k: len(v) for k, v in dates_by.items()}

    to_arr = np.full(len(out), np.nan)
    rem_arr = np.full(len(out), np.nan)
    for (yr, team, cut), ix in out.groupby(['year', 'team', 'cutoff_date'],
                                           dropna=False).groups.items():
        key = (yr, team)
        if key in dates_by:
            n_to = int(np.searchsorted(dates_by[key], np.datetime64(cut), side='right'))
            n_total = total_by[key]
        else:
            keys = [k for k in dates_by if k[0] == yr]
            if not keys:
                continue
            n_to = int(np.mean([np.searchsorted(dates_by[k], np.datetime64(cut), side='right')
                                for k in keys]))
            n_total = int(np.mean([total_by[k] for k in keys]))
        to_arr[out.index.get_indexer(ix)] = n_to
        rem_arr[out.index.get_indexer(ix)] = n_total - n_to
    out['team_games_to'] = to_arr
    out['team_games_remaining'] = rem_arr
    return out


def attach_forward_apps(rolling: pd.DataFrame, relief_apps: dict) -> pd.DataFrame:
    """Derive ros_g (relief appearances after cutoff) and g_last21 from the
    per-(year, pitcher) sorted appearance-date arrays. Leakage note: ros_g is
    the TARGET (future); g_last21 uses only dates <= cutoff (as-of safe)."""
    ros = np.full(len(rolling), np.nan)
    last21 = np.zeros(len(rolling))
    cuts = rolling['cutoff_date'].values
    yrs = rolling['year'].values
    pids = rolling['pitcher'].values
    for i in range(len(rolling)):
        a = relief_apps.get((int(yrs[i]), int(pids[i])))
        if a is None:
            ros[i] = 0.0
            continue
        cut = np.datetime64(cuts[i])
        n_to = int(np.searchsorted(a, cut, side='right'))
        n_from = int(np.searchsorted(a, cut - np.timedelta64(LAST21_DAYS, 'D'),
                                     side='right'))
        ros[i] = len(a) - n_to
        last21[i] = n_to - n_from
    rolling['ros_g'] = ros
    rolling['g_last21'] = last21
    return rolling


# ------------------------------------------------------------------ features
def prepare(rolling: pd.DataFrame) -> pd.DataFrame:
    multiyr = pd.read_csv(MULTIYR_CSV, usecols=['pitcher', 'year', 'g', 'name'])

    print('Building team-games schedule + relief appearance dates from '
          'statcast parquets...', flush=True)
    team_games, relief_apps = build_schedule_and_relief_apps()
    rolling = attach_team_games(rolling, team_games)
    rolling = attach_forward_apps(rolling, relief_apps)

    # target + anchor
    rolling['g_per_teamgame_to'] = rolling['g_to'] / rolling['team_games_to']
    rolling[TARGET] = rolling['ros_g'] / rolling['team_games_remaining']

    # workload shape / role / skill rates (as-of)
    g_nz = rolling['g_to'].replace(0, np.nan)
    rolling['ip_per_g_to'] = rolling['ip_to'] / g_nz
    rolling['fp_skill_per_g_to'] = rolling['fp_skill_to'] / g_nz
    for c in ('gf_pct_to', 'sv_per_g_to', 'hld_per_g_to',
              'sv_per_g_lag1', 'hld_per_g_lag1'):
        rolling[c] = rolling[c].fillna(0.0)

    # priors from official prior-year G totals (multiyr, NOT the substrate's
    # 0-filled g_lag1 — we need real NaN to build has_prior1)
    g_year = multiyr.groupby(['pitcher', 'year'])['g'].max()
    for off, col in ((1, 'prior1_g_per_g'), (2, 'prior2_g_per_g')):
        prior_year = rolling['year'] - off
        # 2021 looks back to 2019 (skip the 60-game 2020 season)
        prior_year = prior_year.where(prior_year != 2020, 2019)
        keys = list(zip(rolling['pitcher'], prior_year))
        vals = g_year.reindex(keys).values
        rolling[col] = vals / SEASON_GAMES
    rolling['has_prior1'] = rolling['prior1_g_per_g'].notna().astype(int)
    rolling['prior1_g_per_g'] = rolling['prior1_g_per_g'].fillna(0.0)
    rolling['prior2_g_per_g'] = rolling['prior2_g_per_g'].fillna(0.0)

    # career stage (rprs2 idiom)
    first_year = multiyr.groupby('pitcher')['year'].min().to_dict()
    rolling['career_stage'] = (rolling['year'] -
                               rolling['pitcher'].map(first_year).fillna(rolling['year'])
                               ).clip(0, 20)

    # IL state — the IL cache was rebuilt 2026-07-09 onto the PITCHER rolling
    # substrate's split grid; exact join on the reliever grid matches only
    # ~31% of rows (verified pre-registration), so use the hitter/SP volume
    # pipelines' asof-backward idiom: each row picks up the most recent PAST
    # IL anchor (leakage-safe).
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
    m = ((df['g_to'] >= G_TO_MIN)
         & (df['team_games_to'] >= TEAMGAMES_TO_MIN)
         & (df['team_games_remaining'] >= TEAMGAMES_REMAIN_MIN)
         & (df['year'] != 2020))
    out = df[m].dropna(subset=RP_VOLUME_FEATS)
    if need_target:
        out = out.dropna(subset=[TARGET])
    return out


# ---------------------------------------------------------------------- eval
def _make_pipe():
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])


def _cell_spearman(sub: pd.DataFrame, pred_col: str) -> list[tuple[int, float]]:
    """[(n, spearman)] per (split_day) cell with n >= MIN_CELL_N."""
    from scipy.stats import spearmanr
    out = []
    for _, g in sub.groupby('split_day'):
        if len(g) < MIN_CELL_N:
            continue
        rho = spearmanr(g[pred_col], g[TARGET]).statistic
        out.append((len(g), float(rho)))
    return out


def _wavg(cells: list[tuple[int, float]]) -> float:
    if not cells:
        return np.nan
    n = np.array([c[0] for c in cells], dtype=float)
    v = np.array([c[1] for c in cells], dtype=float)
    return float(np.sum(n * v) / np.sum(n))


def cross_year_eval(df: pd.DataFrame):
    """LOO over TRAIN_YEARS. Returns per-year dict + pooled dict + detail."""
    df = eligible(df)
    per_year = {}
    all_cells_model, all_cells_naive = [], []
    detail_frames = []
    mae_m_num = mae_n_num = mae_den = 0.0
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]
        test = df[df['year'] == held].copy()
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = _make_pipe()
        pipe.fit(train[RP_VOLUME_FEATS].values, train[TARGET].values)
        test['pred'] = np.clip(pipe.predict(test[RP_VOLUME_FEATS].values), *PRED_CLIP)
        cells_m = _cell_spearman(test, 'pred')
        cells_n = _cell_spearman(test, 'g_per_teamgame_to')
        sp_m, sp_n = _wavg(cells_m), _wavg(cells_n)
        mae_m = float(np.mean(np.abs(test['pred'] - test[TARGET])))
        mae_n = float(np.mean(np.abs(test['g_per_teamgame_to'] - test[TARGET])))
        per_year[held] = {'spear_model': round(sp_m, 4), 'spear_naive': round(sp_n, 4),
                          'delta': round(sp_m - sp_n, 4),
                          'mae_model': round(mae_m, 4), 'mae_naive': round(mae_n, 4),
                          'n': len(test)}
        all_cells_model += cells_m
        all_cells_naive += cells_n
        mae_m_num += mae_m * len(test)
        mae_n_num += mae_n * len(test)
        mae_den += len(test)
        detail_frames.append(test[['pitcher', 'year', 'split_day', 'pred',
                                   'g_per_teamgame_to', TARGET]])
    pooled = {
        'spear_model': round(_wavg(all_cells_model), 4),
        'spear_naive': round(_wavg(all_cells_naive), 4),
        'delta': round(_wavg(all_cells_model) - _wavg(all_cells_naive), 4),
        'mae_model': round(mae_m_num / mae_den, 4),
        'mae_naive': round(mae_n_num / mae_den, 4),
        'n': int(mae_den),
    }
    detail = pd.concat(detail_frames, ignore_index=True)
    return per_year, pooled, detail


def tercile_calibration(detail: pd.DataFrame) -> pd.DataFrame:
    d = detail.copy()
    d['tercile'] = pd.qcut(d['pred'], 3, labels=['low', 'mid', 'high'])
    return (d.groupby('tercile')
            .agg(n=('pred', 'size'),
                 mean_pred=('pred', 'mean'),
                 mean_actual=(TARGET, 'mean'),
                 mean_naive=('g_per_teamgame_to', 'mean'))
            .round(4))


# --------------------------------------------------------------------- gates
def check_gates(per_year: dict, pooled: dict) -> tuple[str, list[str]]:
    lines = []
    g1 = pooled['delta'] >= GATE_POOLED_DSPEAR
    lines.append(f"Gate 1 pooled ΔSpearman {pooled['delta']:+.4f} >= +{GATE_POOLED_DSPEAR}: "
                 f"{'PASS' if g1 else 'FAIL'}")
    pos_years = sum(1 for v in per_year.values() if v['delta'] > 0)
    g2 = pos_years >= GATE_YEARS_POSITIVE
    lines.append(f"Gate 2 per-year Δ>0 in {pos_years}/{len(per_year)} years "
                 f"(need >= {GATE_YEARS_POSITIVE}): {'PASS' if g2 else 'FAIL'}")
    g3 = all(per_year.get(y, {'delta': -1})['delta'] > 0 for y in HOLDOUT_YEARS)
    lines.append(f"Gate 3 holdout {HOLDOUT_YEARS} both Δ>0: {'PASS' if g3 else 'FAIL'}")
    if g1 and g2 and g3:
        return 'PASS', lines
    if MARGINAL_DSPEAR <= pooled['delta'] < GATE_POOLED_DSPEAR:
        return 'MARGINAL', lines
    return 'REJECTED', lines


# ---------------------------------------------------------------------- main
def main():
    print('=== xfp_rp_volume — RP forward-volume (appearance count) model ===')
    usecols = ['pitcher', 'year', 'split_day', 'cutoff_date', 'g_to', 'gs_to',
               'ip_to', 'gf_pct_to', 'sv_per_g_to', 'hld_per_g_to',
               'fp_skill_to', 'sv_per_g_lag1', 'hld_per_g_lag1', 'team_abbr']
    rolling = pd.read_csv(ROLLING_CSV, usecols=usecols)
    print(f'rolling: {len(rolling)} rows')

    rolling = prepare(rolling)
    zero_share = float((rolling.loc[rolling['year'] != 2026, 'ros_g'] == 0).mean())
    print(f'ros_g == 0 share (past years, pre-filter): {zero_share:.3f} '
          f'(no truncation — attrition class present)')

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
    verdict, lines = check_gates(per_year, pooled)
    for ln in lines:
        print('  ' + ln)
    print(f'  VERDICT: {verdict}')

    # ------------------------------------------------ final fit + 2026 output
    train = eligible(rolling[rolling['year'].isin(TRAIN_YEARS)])
    pipe = _make_pipe()
    pipe.fit(train[RP_VOLUME_FEATS].values, train[TARGET].values)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final fit (n_train={len(train)}, '
          f'alpha={pipe.named_steps["r"].alpha_:.1f}) — coefficients ---')
    for f, c in sorted(zip(RP_VOLUME_FEATS, coefs), key=lambda x: -abs(x[1])):
        print(f'    {f:<28s} {c:+.4f}')

    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        print('No 2026 rows — skipping projection output.')
        return verdict
    latest_split = int(df_26['split_day'].max())
    # SP-volume idiom: each pitcher's MOST-RECENT snapshot within the recency
    # window (an RP idle for a couple of weeks still projects from his last
    # qualifying snapshot).
    df_26 = df_26[(df_26['split_day'] >= latest_split - PROJ_SPLIT_RECENCY_DAYS)
                  & (df_26['g_to'] >= G_TO_MIN)
                  & (df_26['team_games_to'] >= TEAMGAMES_TO_MIN)]
    df_26 = (df_26.sort_values('split_day')
             .groupby('pitcher', as_index=False, sort=False)
             .tail(1))
    df_26 = df_26.dropna(subset=RP_VOLUME_FEATS).drop_duplicates('pitcher')
    df_26['proj_ros_g_per_teamgame'] = np.clip(
        pipe.predict(df_26[RP_VOLUME_FEATS].values), *PRED_CLIP)
    df_26['naive_pace'] = df_26['g_per_teamgame_to']
    # Implied RoS appearance count: statcast-derived team_games_remaining is
    # only "games already played after cutoff" for the in-progress season, so
    # use the 162-game schedule instead.
    df_26['team_games_remaining_implied'] = (SEASON_GAMES - df_26['team_games_to']).clip(lower=0)
    df_26['proj_ros_g'] = (df_26['proj_ros_g_per_teamgame']
                           * df_26['team_games_remaining_implied']).round(1)
    df_26['volume_percentile'] = (df_26['proj_ros_g_per_teamgame']
                                  .rank(pct=True) * 100).round(1)

    names = (pd.read_csv(MULTIYR_CSV, usecols=['pitcher', 'year', 'name'])
             .sort_values('year', ascending=False)
             .drop_duplicates('pitcher')
             .rename(columns={'name': 'player_name'})[['pitcher', 'player_name']])
    df_26 = df_26.merge(names, on='pitcher', how='left')
    # mlbam-keyed name fallback for arms missing from the multiyr file
    # (2026 in-progress arms below its threshold) — rprs2's API names.
    rprs2_csv = ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv'
    if rprs2_csv.exists() and df_26['player_name'].isna().any():
        api_names = (pd.read_csv(rprs2_csv, usecols=['pitcher', 'name_api'])
                     .drop_duplicates('pitcher'))
        df_26 = df_26.merge(api_names, on='pitcher', how='left')
        df_26['player_name'] = df_26['player_name'].fillna(df_26['name_api'])
        df_26 = df_26.drop(columns=['name_api'])

    out = df_26.rename(columns={'pitcher': 'mlbam_id'})
    out_cols = ['mlbam_id', 'player_name', 'team',
                'proj_ros_g_per_teamgame', 'naive_pace', 'proj_ros_g',
                'team_games_remaining_implied', 'volume_percentile',
                'g_to', 'team_games_to', 'g_per_teamgame_to', 'g_last21',
                'ip_per_g_to', 'gf_pct_to', 'sv_per_g_to', 'hld_per_g_to',
                'fp_skill_per_g_to', 'prior1_g_per_g', 'career_stage',
                'is_on_il_at_split', 'days_since_il_return_imp',
                'il_stints_to', 'split_day']
    out_cols = [c for c in out_cols if c in out.columns]
    out = out.sort_values('proj_ros_g_per_teamgame', ascending=False)
    out[out_cols].round(4).to_csv(PROJ_CSV, index=False)
    print(f'\nWrote {PROJ_CSV}: {len(out)} relievers (latest split={latest_split}, '
          f'as of {date.today()})')

    show = ['player_name', 'team', 'proj_ros_g_per_teamgame', 'naive_pace',
            'proj_ros_g', 'g_to', 'g_last21', 'sv_per_g_to', 'gf_pct_to']
    print('\nTop 15 by projected RoS G/team-game:')
    print(out[show].head(15).to_string(index=False))

    print('\nSanity — established closers (sv_per_g_to >= 0.35, g_to >= 20):')
    closers = out[(out['sv_per_g_to'] >= 0.35) & (out['g_to'] >= 20)]
    print(closers[show].head(10).to_string(index=False))

    print('\nSanity — recently active but thin season (g_last21 >= 5, '
          'g_to <= 20): model should sit ABOVE season-long naive pace:')
    recalled = out[(out['g_last21'] >= 5) & (out['g_to'] <= 20)].copy()
    recalled['model_minus_naive'] = (recalled['proj_ros_g_per_teamgame']
                                     - recalled['naive_pace']).round(4)
    recalled = recalled.sort_values('model_minus_naive', ascending=False)
    print(recalled[show + ['model_minus_naive']].head(8).to_string(index=False))
    frac_above = float((recalled['model_minus_naive'] > 0).mean()) if len(recalled) else np.nan
    print(f'  share of recently-active thin-season arms projected above naive: {frac_above:.1%}')

    print('\nSanity — thin-history arms (g_to <= 12, no prior-year G): '
          'should project BELOW established high-leverage arms:')
    callups = out[(out['g_to'] <= 12) & (out['prior1_g_per_g'] == 0)]
    print(callups[show].head(8).to_string(index=False))
    return verdict


if __name__ == '__main__':
    main()
