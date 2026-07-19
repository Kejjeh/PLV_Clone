"""volume_model.py — shared toolkit for the three forward-volume pipelines.

Hoisted 2026-07-19 (audit backlog #2, D1/W4): xfp_volume_pipeline (hitter),
xfp_sp_volume_pipeline (SP) and xfp_rp_volume_pipeline (RP) carried ~250 lines
of byte-identical helpers, and each rebuilt the identical (year, team) ->
game-dates schedule from ~8 large statcast parquets on every nightly run
(the hitter pipeline scanned them TWICE via the catcher-flag pass).

This module is a pure extraction — every function body matches the pipelines'
former local copies exactly (parametrized only where the pipelines differed by
a column name), so model outputs are unchanged. The one behavioral addition is
the PER-YEAR disk cache on the two statcast scans: a year's derived frame is
rebuilt only when that year's parquet is newer than the cache, so the seven
immutable historical seasons stop being re-read nightly (~2.5 GB/night of
parquet IO across the three pipelines). Cache files live FLAT in xfp_cache as
*.parquet so the existing gitignore rule covers them.

NOT hoisted (intentionally): each pipeline's FEATS list, eligibility filter,
prepare() feature engineering, and the RP pipeline's combined
schedule+relief-apps scan / string-verdict gates — those differ by design.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parents[3] / 'data' / 'research' / 'xfp_cache'


def _default_years():
    """2018..current year (2020 excluded by the scanners). Dynamic so the
    scans pick up a new season's parquet without a code change (audit R3 —
    the old hardcoded range(2018, 2027) would silently omit 2027)."""
    return range(2018, date.today().year + 1)


# ------------------------------------------------------------- statcast scans
def _cached_year_frame(yr: int, cache_name: str, build_fn) -> pd.DataFrame | None:
    """Per-year mtime-guarded disk cache for a statcast-derived frame.

    Rebuilds only when statcast_{yr}.parquet is newer than the cached frame
    (2026 changes nightly; 2018-2025 are immutable => read once, ever).
    Returns None when the source parquet doesn't exist.
    """
    src = CACHE / f'statcast_{yr}.parquet'
    if not src.exists():
        return None
    dst = CACHE / f'{cache_name}_{yr}.parquet'
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        try:
            return pd.read_parquet(dst)
        except Exception:
            pass  # corrupt cache -> rebuild
    frame = build_fn(src)
    try:
        frame.to_parquet(dst, index=False)
    except Exception:
        pass  # cache write is best-effort; the frame is still returned
    return frame


def _team_games_year(src: Path) -> pd.DataFrame:
    d = pd.read_parquet(src, columns=['game_pk', 'game_date', 'home_team', 'away_team'])
    d = d.drop_duplicates('game_pk')
    d['game_date'] = pd.to_datetime(d['game_date'])
    home = d[['game_pk', 'game_date', 'home_team']].rename(columns={'home_team': 'team'})
    away = d[['game_pk', 'game_date', 'away_team']].rename(columns={'away_team': 'team'})
    return pd.concat([home, away], ignore_index=True)[['game_date', 'team']]


def build_team_games(years=None) -> pd.DataFrame:
    """Per (year, team): one row per team-game (distinct game_pk), long form.

    Output identical to the pipelines' former local build_team_games();
    per-year disk-cached (see _cached_year_frame).
    """
    frames = []
    for yr in list(years if years is not None else _default_years()):
        if yr == 2020:
            continue
        tg = _cached_year_frame(yr, 'team_games_cache', _team_games_year)
        if tg is None:
            continue
        tg = tg.copy()
        tg['game_date'] = pd.to_datetime(tg['game_date'])
        tg['year'] = yr
        frames.append(tg[['year', 'team', 'game_date']])
    return pd.concat(frames, ignore_index=True)


def _catcher_counts_year(src: Path) -> pd.DataFrame:
    vc = pd.read_parquet(src, columns=['fielder_2'])['fielder_2'].value_counts()
    return pd.DataFrame({'mlbam': vc.index.astype('int64'), 'pitches': vc.values})


def build_catcher_flags(min_pitches: int = 100,
                        years=None) -> dict[tuple[int, int], int]:
    """(year, mlbam_id) -> 1 if the player caught >= min_pitches.

    Output identical to the hitter pipeline's former local version;
    per-year disk-cached.
    """
    flags: dict[tuple[int, int], int] = {}
    for yr in list(years if years is not None else _default_years()):
        if yr == 2020:
            continue
        cc = _cached_year_frame(yr, 'catcher_pitch_counts_cache', _catcher_counts_year)
        if cc is None:
            continue
        for pid in cc.loc[cc['pitches'] >= min_pitches, 'mlbam']:
            flags[(yr, int(pid))] = 1
    return flags


def attach_team_games(rolling: pd.DataFrame, team_games: pd.DataFrame,
                      team_map: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """Attach team_games_to / team_games_remaining per row via the player's
    (id_col, year) -> team map; league-mean fallback when the team is unmapped.
    Body identical to the former hitter/SP local copies (id column only)."""
    out = rolling.merge(team_map, on=[id_col, 'year'], how='left')
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


# ----------------------------------------------------------------------- eval
def make_pipe():
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])


def cell_spearman(sub: pd.DataFrame, pred_col: str, target: str,
                  min_cell_n: int = 30) -> list[tuple[int, float]]:
    """[(n, spearman)] per split_day cell with n >= min_cell_n."""
    from scipy.stats import spearmanr
    out = []
    for _, g in sub.groupby('split_day'):
        if len(g) < min_cell_n:
            continue
        rho = spearmanr(g[pred_col], g[target]).statistic
        out.append((len(g), float(rho)))
    return out


def wavg(cells: list[tuple[int, float]]) -> float:
    if not cells:
        return np.nan
    n = np.array([c[0] for c in cells], dtype=float)
    v = np.array([c[1] for c in cells], dtype=float)
    return float(np.sum(n * v) / np.sum(n))


def cross_year_eval(df: pd.DataFrame, *, feats: list[str], target: str,
                    naive_col: str, id_col: str, train_years: list[int],
                    pred_clip: tuple[float, float], eligible_fn,
                    min_cell_n: int = 30):
    """LOO over train_years. Returns per-year dict + pooled dict + detail.
    Body identical to the former hitter/SP local copies, parametrized on the
    columns that differed (feats / target / naive anchor / id column)."""
    df = eligible_fn(df)
    per_year = {}
    all_cells_model, all_cells_naive = [], []
    detail_frames = []
    mae_m_num = mae_n_num = mae_den = 0.0
    for held in train_years:
        train = df[df['year'] != held]
        test = df[df['year'] == held].copy()
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = make_pipe()
        pipe.fit(train[feats].values, train[target].values)
        test['pred'] = np.clip(pipe.predict(test[feats].values), *pred_clip)
        cells_m = cell_spearman(test, 'pred', target, min_cell_n)
        cells_n = cell_spearman(test, naive_col, target, min_cell_n)
        sp_m, sp_n = wavg(cells_m), wavg(cells_n)
        mae_m = float(np.mean(np.abs(test['pred'] - test[target])))
        mae_n = float(np.mean(np.abs(test[naive_col] - test[target])))
        per_year[held] = {'spear_model': round(sp_m, 4), 'spear_naive': round(sp_n, 4),
                          'delta': round(sp_m - sp_n, 4),
                          'mae_model': round(mae_m, 4), 'mae_naive': round(mae_n, 4),
                          'n': len(test)}
        all_cells_model += cells_m
        all_cells_naive += cells_n
        mae_m_num += mae_m * len(test)
        mae_n_num += mae_n * len(test)
        mae_den += len(test)
        detail_frames.append(test[[id_col, 'year', 'split_day', 'pred',
                                   naive_col, target]])
    pooled = {
        'spear_model': round(wavg(all_cells_model), 4),
        'spear_naive': round(wavg(all_cells_naive), 4),
        'delta': round(wavg(all_cells_model) - wavg(all_cells_naive), 4),
        'mae_model': round(mae_m_num / mae_den, 4),
        'mae_naive': round(mae_n_num / mae_den, 4),
        'n': int(mae_den),
    }
    detail = pd.concat(detail_frames, ignore_index=True)
    return per_year, pooled, detail


def tercile_calibration(detail: pd.DataFrame, target: str, naive_col: str,
                        decimals: int = 3) -> pd.DataFrame:
    d = detail.copy()
    d['tercile'] = pd.qcut(d['pred'], 3, labels=['low', 'mid', 'high'])
    return (d.groupby('tercile')
            .agg(n=('pred', 'size'),
                 mean_pred=('pred', 'mean'),
                 mean_actual=(target, 'mean'),
                 mean_naive=(naive_col, 'mean'))
            .round(decimals))


def check_gates(per_year: dict, pooled: dict, *, pooled_gate: float,
                years_positive: int, holdout_years: list[int]) -> tuple[bool, list[str]]:
    lines = []
    g1 = pooled['delta'] >= pooled_gate
    lines.append(f"Gate 1 pooled ΔSpearman {pooled['delta']:+.4f} >= +{pooled_gate}: "
                 f"{'PASS' if g1 else 'FAIL'}")
    pos_years = sum(1 for v in per_year.values() if v['delta'] > 0)
    g2 = pos_years >= years_positive
    lines.append(f"Gate 2 per-year Δ>0 in {pos_years}/{len(per_year)} years "
                 f"(need >= {years_positive}): {'PASS' if g2 else 'FAIL'}")
    g3 = all(per_year.get(y, {'delta': -1})['delta'] > 0 for y in holdout_years)
    lines.append(f"Gate 3 holdout {holdout_years} both Δ>0: {'PASS' if g3 else 'FAIL'}")
    return (g1 and g2 and g3), lines
