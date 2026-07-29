"""validate_velo_trend.py — test velo_trend as a candidate rp3 feature.

Pre-registered: data/research/validation_runs/velo_trend_2026-06-02.md

velo_trend at (pitcher, year, split_day):
  mean release_speed of pitcher's PRIMARY pitch type over their LAST 3 STARTS
  strictly before cutoff_date
  MINUS
  season-to-date mean release_speed of same pitch type
  (all starts strictly before cutoff_date).

Primary pitch type = most-thrown pitch type season-to-date up to cutoff.
Pitchers with < 3 prior starts get velo_trend = 0 (neutral).
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report

from plv_clone.models.xfp.rp3 import RP3_FEATS, cross_year_eval, TARGET

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'

ALL_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
CONV_SPLIT_DAYS = [30, 44, 58]  # closest grid match to requested 30/42/56


# ---------------------------------------------------------------------------
# velo_trend feature build
# ---------------------------------------------------------------------------
def per_pitcher_per_date_velo_by_pitchtype(year: int) -> pd.DataFrame:
    """Aggregate per (pitcher, game_date, pitch_type) velo sum + count."""
    p = CACHE / f'statcast_{year}.parquet'
    df = pd.read_parquet(
        p,
        columns=['game_date', 'pitcher', 'pitch_type', 'release_speed'],
    )
    df = df.dropna(subset=['release_speed', 'pitch_type', 'game_date', 'pitcher'])
    df['game_date'] = pd.to_datetime(df['game_date']).dt.date
    df['pitcher'] = df['pitcher'].astype('int64')
    agg = (
        df.groupby(['pitcher', 'game_date', 'pitch_type'], as_index=False)
          .agg(velo_sum=('release_speed', 'sum'),
               n_pitches=('release_speed', 'size'))
    )
    return agg


def build_velo_trend_for_year(year: int, cutoffs: list[pd.Timestamp]) -> pd.DataFrame:
    """For each (pitcher, cutoff) compute velo_trend.

    velo_trend = last3_start_mean_velo(primary_pitch) − season_mean_velo(primary_pitch)
    using only pitches with game_date strictly < cutoff_date.
    Pitchers with < 3 prior starts on the primary pitch → velo_trend = 0.
    """
    print(f'  loading statcast {year}...')
    agg = per_pitcher_per_date_velo_by_pitchtype(year)
    if agg.empty:
        return pd.DataFrame()

    cutoff_dates = [pd.Timestamp(c).date() for c in cutoffs]
    rows: list[dict] = []

    # Sort once; group by pitcher.
    agg = agg.sort_values(['pitcher', 'game_date'])
    for p, sub in agg.groupby('pitcher', sort=False):
        # For each cutoff: slice strictly before, compute primary pitch + last-3 vs season.
        for cd in cutoff_dates:
            prior = sub[sub['game_date'] < cd]
            if prior.empty:
                rows.append({'pitcher': int(p), 'year': year, 'cutoff_date': str(cd),
                             'velo_trend': 0.0, 'n_prior_starts': 0,
                             'primary_pitch': None})
                continue
            primary = prior.groupby('pitch_type')['n_pitches'].sum().idxmax()
            prior_pri = prior[prior['pitch_type'] == primary]
            if prior_pri.empty:
                rows.append({'pitcher': int(p), 'year': year, 'cutoff_date': str(cd),
                             'velo_trend': 0.0, 'n_prior_starts': 0,
                             'primary_pitch': primary})
                continue
            per_date = (prior_pri.groupby('game_date', as_index=False)
                                  .agg(vs=('velo_sum', 'sum'),
                                       np_=('n_pitches', 'sum')))
            n_prior = len(per_date)
            season_mean = per_date['vs'].sum() / per_date['np_'].sum()
            if n_prior < 3:
                rows.append({'pitcher': int(p), 'year': year, 'cutoff_date': str(cd),
                             'velo_trend': 0.0, 'n_prior_starts': n_prior,
                             'primary_pitch': primary})
                continue
            last3 = per_date.tail(3)
            last3_mean = last3['vs'].sum() / last3['np_'].sum()
            rows.append({'pitcher': int(p), 'year': year, 'cutoff_date': str(cd),
                         'velo_trend': float(last3_mean - season_mean),
                         'n_prior_starts': int(n_prior),
                         'primary_pitch': primary})

    return pd.DataFrame(rows)


def build_full_velo_trend_panel(rolling: pd.DataFrame) -> pd.DataFrame:
    """Build velo_trend for ALL split_days x ALL years that appear in rolling.

    rolling already has the cutoff_date column. Per-year we collect all distinct
    cutoff_dates and build velo_trend at each of them.
    """
    rolling = rolling.copy()
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    out_frames = []
    for y in sorted(rolling['year'].unique()):
        if y == 2020:
            continue
        sub = rolling[rolling['year'] == y]
        cutoffs = sorted(sub['cutoff_date'].unique())
        print(f'YEAR {y}: {len(cutoffs)} cutoffs from {pd.Timestamp(cutoffs[0]).date()} '
              f'to {pd.Timestamp(cutoffs[-1]).date()}')
        vt = build_velo_trend_for_year(int(y), cutoffs)
        out_frames.append(vt)
    out = pd.concat(out_frames, ignore_index=True)
    out['cutoff_date'] = pd.to_datetime(out['cutoff_date'])
    return out


# ---------------------------------------------------------------------------
# Convergence check (per split_day)
# ---------------------------------------------------------------------------
def per_split_day_lift(rolling: pd.DataFrame) -> dict:
    """For each split_day in CONV_SPLIT_DAYS, restrict to that split_day and
    run leave-one-year-out on the same RP3_FEATS baseline vs +velo_trend."""
    out: dict = {}
    for sd in CONV_SPLIT_DAYS:
        sub = rolling[rolling['split_day'] == sd].copy()
        if len(sub) < 200:
            out[sd] = {'skipped': True, 'n': len(sub)}
            continue
        py_b, ov_b = cross_year_eval(sub, RP3_FEATS)
        py_f, ov_f = cross_year_eval(sub, RP3_FEATS + ['velo_trend'])
        per_year_lift = {y: round(py_f[y]['r'] - py_b[y]['r'], 4)
                         for y in py_b if y in py_f}
        out[sd] = {
            'n_total': int(len(sub)),
            'r_baseline': ov_b['r'],
            'r_full': ov_f['r'],
            'r_gain': round(ov_f['r'] - ov_b['r'], 4),
            'mae_baseline': ov_b['mae'],
            'mae_full': ov_f['mae'],
            'mae_gain': round(ov_b['mae'] - ov_f['mae'], 4),
            'per_year_lift': per_year_lift,
            'n_eval_baseline': ov_b['n'],
            'n_eval_full': ov_f['n'],
        }
    return out


# ---------------------------------------------------------------------------
# Partial r computation (rigorous "added-variable" form)
# ---------------------------------------------------------------------------
def partial_r_full_baseline(rolling: pd.DataFrame) -> dict:
    """Compute partial r of velo_trend vs full RP3_FEATS using cross-year
    leave-one-year-out predictions.

    For each held year:
      - train RidgeCV on baseline → predict y on held
      - train RidgeCV on (full = baseline + velo_trend) → predict y on held
      - residuals: y - pred_base, pred_full - pred_base
    Pool across all training years (2018-2025), compute pearson r of pooled
    residual pair.
    """
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    from scipy.stats import pearsonr

    full = RP3_FEATS + ['velo_trend']
    df = rolling.dropna(subset=full + [TARGET]).copy()
    df = df[(df['gs_to'] >= 2) & (df['ros_gs'] >= 5) & (df['year'] != 2020)]

    train_years = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
    res_y = []; res_full = []
    for held in train_years:
        train = df[df['year'] != held]
        test = df[df['year'] == held]
        if len(train) < 50 or len(test) < 10:
            continue
        pipe_b = Pipeline([('sc', StandardScaler()),
                           ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe_b.fit(train[RP3_FEATS].values, train[TARGET].values)
        pred_b = pipe_b.predict(test[RP3_FEATS].values)
        pipe_f = Pipeline([('sc', StandardScaler()),
                           ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe_f.fit(train[full].values, train[TARGET].values)
        pred_f = pipe_f.predict(test[full].values)
        y_true = test[TARGET].values
        res_y.extend((y_true - pred_b).tolist())
        res_full.extend((pred_f - pred_b).tolist())

    if len(res_y) < 10 or np.std(res_full) == 0:
        return {'partial_r': float('nan'), 'n': len(res_y)}
    return {'partial_r': float(pearsonr(res_y, res_full)[0]), 'n': len(res_y)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print('=== validate_velo_trend ===')
    print('Step 1: prepare full rp3 production substrate (rolling + shrinkage + drift + IL + prior)...')
    rolling = prep_rolling()
    # Merge ros_opp_xwoba_weighted (RP3_FEATS-required but not in shared harness).
    sched_path = CACHE / 'ros_schedule_features_2018_2026.csv'
    if sched_path.exists() and 'ros_opp_xwoba_weighted' not in rolling.columns:
        sched = pd.read_csv(sched_path)
        rolling = rolling.merge(
            sched[['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']],
            on=['pitcher', 'year', 'split_day'], how='left',
        )
        # Per-year mean impute (mirrors rp3.py main()).
        rolling['ros_opp_xwoba_weighted'] = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform(
            lambda s: s.fillna(s.mean()))
    if 'ros_opp_xwoba_weighted' not in rolling.columns:
        print('  WARN: ros_opp_xwoba_weighted unavailable - filling 0')
        rolling['ros_opp_xwoba_weighted'] = 0.0
    print(f'  rolling rows: {len(rolling)}')
    print(f'  RP3_FEATS = {len(RP3_FEATS)} feats')
    miss = [f for f in RP3_FEATS if f not in rolling.columns]
    print(f'  missing baseline feats post-prep: {miss}')

    print('Step 2: build velo_trend feature panel from statcast parquets...')
    vt = build_full_velo_trend_panel(rolling)
    print(f'  velo_trend rows: {len(vt)}')
    print(f'  velo_trend distribution: mean={vt["velo_trend"].mean():.4f}  '
          f'std={vt["velo_trend"].std():.4f}  '
          f'pct_nonzero={(vt["velo_trend"].abs() > 1e-9).mean():.1%}')

    # Merge onto rolling on (pitcher, year, cutoff_date).
    rolling = rolling.copy()
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    rolling = rolling.merge(
        vt[['pitcher', 'year', 'cutoff_date', 'velo_trend', 'n_prior_starts']],
        on=['pitcher', 'year', 'cutoff_date'],
        how='left',
    )
    rolling['velo_trend'] = rolling['velo_trend'].fillna(0.0)
    rolling['n_prior_starts'] = rolling['n_prior_starts'].fillna(0).astype(int)
    print(f'  post-merge rolling: {len(rolling)}, '
          f'velo_trend nonzero: {(rolling["velo_trend"].abs() > 1e-9).mean():.1%}')

    print('Step 3: run full Rule-9 lift test (RP3_FEATS vs + velo_trend)...')
    result = evaluate_candidate(rolling, 'velo_trend', fill_value=0.0, label='velo_trend')
    print_report(result)

    print('Step 4: convergence check across split_days 30/44/58...')
    conv = per_split_day_lift(rolling)
    for sd, c in conv.items():
        if c.get('skipped'):
            print(f'  sd={sd}: SKIPPED (n={c["n"]})')
            continue
        print(f'  sd={sd:>3}: r_base={c["r_baseline"]:.4f}  r_full={c["r_full"]:.4f}  '
              f'gain={c["r_gain"]:+.4f}  mae_gain={c["mae_gain"]:+.4f}  n={c["n_eval_full"]}')

    print('Step 5: partial r vs full baseline (added-variable form)...')
    pr = partial_r_full_baseline(rolling)
    print(f'  partial r = {pr["partial_r"]:+.4f}  (pooled n={pr["n"]})')

    # MAE on holdout 2024-2025 specifically
    print('Step 6: MAE on holdout 2024-2025 only...')
    hold = rolling[rolling['year'].isin([2024, 2025])]
    py_b, ov_b = cross_year_eval(rolling, RP3_FEATS)
    py_f, ov_f = cross_year_eval(rolling, RP3_FEATS + ['velo_trend'])
    holdout_mae_b = float(np.mean([py_b[y]['mae'] for y in [2024, 2025] if y in py_b]))
    holdout_mae_f = float(np.mean([py_f[y]['mae'] for y in [2024, 2025] if y in py_f]))
    print(f'  holdout MAE baseline: {holdout_mae_b:.4f}  full: {holdout_mae_f:.4f}  '
          f'gain: {holdout_mae_b - holdout_mae_f:+.4f} FP/start')

    # Persist
    output = {
        'rule9_lift_test': result,
        'convergence_per_split_day': conv,
        'partial_r_vs_full_baseline': pr,
        'holdout_mae': {
            'baseline': holdout_mae_b,
            'full': holdout_mae_f,
            'gain_fp_per_start': holdout_mae_b - holdout_mae_f,
        },
        'feature_distribution': {
            'mean': float(rolling['velo_trend'].mean()),
            'std': float(rolling['velo_trend'].std()),
            'pct_nonzero': float((rolling['velo_trend'].abs() > 1e-9).mean()),
            'min': float(rolling['velo_trend'].min()),
            'max': float(rolling['velo_trend'].max()),
        },
    }
    out_json = OUT_DIR / 'velo_trend_results.json'
    with open(out_json, 'w') as fh:
        json.dump(output, fh, indent=2, default=float)
    print(f'\nWrote {out_json}')


if __name__ == '__main__':
    main()
