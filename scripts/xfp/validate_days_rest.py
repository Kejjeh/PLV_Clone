"""validate_days_rest.py - test days_rest as a candidate rp3 feature.

Pre-registered: data/research/validation_runs/days_rest_2026-06-02.md

days_rest at (pitcher, year, cutoff_date):
  most_recent_start_date - second_most_recent_start_date,
  in calendar days, computed strictly from game_dates < cutoff_date.
  Clamped to [3, 7].
  Pitchers with < 2 prior starts -> days_rest = 5 (neutral default).

A "start" is one distinct game_date where this pitcher threw pitches.
This is robust to relievers and openers because we treat each distinct
game_date as a single start.
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

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'

CONV_SPLIT_DAYS = [30, 44, 58]
NEUTRAL_REST = 5
CLAMP_LO, CLAMP_HI = 3, 7


# ---------------------------------------------------------------------------
# days_rest feature build
# ---------------------------------------------------------------------------
def per_pitcher_per_date_starts(year: int) -> pd.DataFrame:
    """Return one row per (pitcher, game_date) for the year — these are 'starts'
    in the sense of distinct game_dates the pitcher appeared. We rely on the
    rp3 substrate already filtering rolling to SP-relevant rows, so we don't
    need to distinguish SP vs RP here.
    """
    p = CACHE / f'statcast_{year}.parquet'
    df = pd.read_parquet(p, columns=['game_date', 'pitcher'])
    df = df.dropna(subset=['game_date', 'pitcher'])
    df['game_date'] = pd.to_datetime(df['game_date']).dt.date
    df['pitcher'] = df['pitcher'].astype('int64')
    starts = (
        df.drop_duplicates(subset=['pitcher', 'game_date'])
          .sort_values(['pitcher', 'game_date'])
          .reset_index(drop=True)
    )
    return starts


def build_days_rest_for_year(year: int, cutoffs: list[pd.Timestamp]) -> pd.DataFrame:
    """For each (pitcher, cutoff) compute days_rest = (max date < cutoff)
    - (second-max date < cutoff), in calendar days, clamped to [3, 7]."""
    print(f'  loading statcast {year}...')
    starts = per_pitcher_per_date_starts(year)
    if starts.empty:
        return pd.DataFrame()
    cutoff_dates = [pd.Timestamp(c).date() for c in cutoffs]
    rows: list[dict] = []
    for p, sub in starts.groupby('pitcher', sort=False):
        dates_sorted = sub['game_date'].tolist()  # already sorted
        for cd in cutoff_dates:
            prior = [d for d in dates_sorted if d < cd]
            n_prior = len(prior)
            if n_prior < 2:
                rows.append({
                    'pitcher': int(p), 'year': year, 'cutoff_date': str(cd),
                    'days_rest': float(NEUTRAL_REST),
                    'days_rest_raw': float('nan'),
                    'n_prior_starts': n_prior,
                })
                continue
            most_recent = prior[-1]
            prev = prior[-2]
            raw = (most_recent - prev).days
            clamped = float(max(CLAMP_LO, min(CLAMP_HI, raw)))
            rows.append({
                'pitcher': int(p), 'year': year, 'cutoff_date': str(cd),
                'days_rest': clamped,
                'days_rest_raw': float(raw),
                'n_prior_starts': n_prior,
            })
    return pd.DataFrame(rows)


def build_full_days_rest_panel(rolling: pd.DataFrame) -> pd.DataFrame:
    rolling = rolling.copy()
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    out_frames = []
    for y in sorted(rolling['year'].unique()):
        if y == 2020:
            continue
        sub = rolling[rolling['year'] == y]
        cutoffs = sorted(sub['cutoff_date'].unique())
        if not cutoffs:
            continue
        print(f'YEAR {y}: {len(cutoffs)} cutoffs from {pd.Timestamp(cutoffs[0]).date()} '
              f'to {pd.Timestamp(cutoffs[-1]).date()}')
        dr = build_days_rest_for_year(int(y), cutoffs)
        if not dr.empty:
            out_frames.append(dr)
    out = pd.concat(out_frames, ignore_index=True)
    out['cutoff_date'] = pd.to_datetime(out['cutoff_date'])
    return out


# ---------------------------------------------------------------------------
# Convergence check (per split_day)
# ---------------------------------------------------------------------------
def per_split_day_lift(rolling: pd.DataFrame, feature: str) -> dict:
    out: dict = {}
    for sd in CONV_SPLIT_DAYS:
        sub = rolling[rolling['split_day'] == sd].copy()
        if len(sub) < 200:
            out[sd] = {'skipped': True, 'n': len(sub)}
            continue
        py_b, ov_b = cross_year_eval(sub, RP3_FEATS)
        py_f, ov_f = cross_year_eval(sub, RP3_FEATS + [feature])
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
# Partial r vs full baseline
# ---------------------------------------------------------------------------
def partial_r_full_baseline(rolling: pd.DataFrame, feature: str) -> dict:
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    from scipy.stats import pearsonr

    full = RP3_FEATS + [feature]
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


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('=== validate_days_rest ===')
    print('Step 1: prep full rp3 substrate...')
    rolling = prep_rolling()
    sched_path = CACHE / 'ros_schedule_features_2018_2026.csv'
    if sched_path.exists() and 'ros_opp_xwoba_weighted' not in rolling.columns:
        sched = pd.read_csv(sched_path)
        rolling = rolling.merge(
            sched[['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']],
            on=['pitcher', 'year', 'split_day'], how='left',
        )
        rolling['ros_opp_xwoba_weighted'] = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform(
            lambda s: s.fillna(s.mean()))
    if 'ros_opp_xwoba_weighted' not in rolling.columns:
        rolling['ros_opp_xwoba_weighted'] = 0.0
    print(f'  rolling rows: {len(rolling)}')

    print('Step 2: build days_rest panel from statcast...')
    dr = build_full_days_rest_panel(rolling)
    print(f'  days_rest rows: {len(dr)}')
    print(f'  days_rest distribution (clamped):')
    print(f'    mean: {dr["days_rest"].mean():.3f}, std: {dr["days_rest"].std():.3f}')
    # Bucket distribution of clamped values
    bucket_counts = dr['days_rest'].value_counts().sort_index()
    print(f'    bucket counts: {dict(bucket_counts)}')
    # Coverage: rows with >= 2 prior starts (got a real measurement)
    real = (dr['n_prior_starts'] >= 2).mean()
    print(f'    pct with >= 2 prior starts (real signal): {real:.1%}')
    # How many of the raw values were clamped at low or high boundary?
    raw_ok = dr['days_rest_raw'].notna()
    raw = dr.loc[raw_ok, 'days_rest_raw']
    if len(raw) > 0:
        print(f'    raw distribution (where >=2 prior starts):')
        print(f'      <3 days: {(raw < CLAMP_LO).mean():.2%}')
        print(f'      3-7 days (preserved): {((raw >= CLAMP_LO) & (raw <= CLAMP_HI)).mean():.2%}')
        print(f'      >7 days: {(raw > CLAMP_HI).mean():.2%}')

    # Merge onto rolling
    rolling = rolling.copy()
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    rolling = rolling.merge(
        dr[['pitcher', 'year', 'cutoff_date', 'days_rest', 'n_prior_starts']],
        on=['pitcher', 'year', 'cutoff_date'], how='left',
    )
    rolling['days_rest'] = rolling['days_rest'].fillna(float(NEUTRAL_REST))
    rolling['n_prior_starts'] = rolling['n_prior_starts'].fillna(0).astype(int)
    print(f'  post-merge rolling: {len(rolling)}, '
          f'days_rest at neutral (5): {(rolling["days_rest"] == 5).mean():.1%}')

    print('Step 3: Rule-9 lift test...')
    result = evaluate_candidate(rolling, 'days_rest', fill_value=float(NEUTRAL_REST),
                                label='days_rest')
    print_report(result)

    print('Step 4: convergence at 30/44/58...')
    conv = per_split_day_lift(rolling, 'days_rest')
    for sd, c in conv.items():
        if c.get('skipped'):
            print(f'  sd={sd}: SKIPPED'); continue
        print(f'  sd={sd:>3}: r_base={c["r_baseline"]:.4f}  r_full={c["r_full"]:.4f}  '
              f'gain={c["r_gain"]:+.4f}  mae_gain={c["mae_gain"]:+.4f}  n={c["n_eval_full"]}')

    print('Step 5: partial r vs full baseline...')
    pr = partial_r_full_baseline(rolling, 'days_rest')
    print(f'  partial r = {pr["partial_r"]:+.4f}  (pooled n={pr["n"]})')

    print('Step 6: holdout MAE on 2024-2025...')
    py_b, ov_b = cross_year_eval(rolling, RP3_FEATS)
    py_f, ov_f = cross_year_eval(rolling, RP3_FEATS + ['days_rest'])
    holdout_mae_b = float(np.mean([py_b[y]['mae'] for y in [2024, 2025] if y in py_b]))
    holdout_mae_f = float(np.mean([py_f[y]['mae'] for y in [2024, 2025] if y in py_f]))
    print(f'  baseline: {holdout_mae_b:.4f}  full: {holdout_mae_f:.4f}  '
          f'gain: {holdout_mae_b - holdout_mae_f:+.4f}')

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
            'mean': float(rolling['days_rest'].mean()),
            'std': float(rolling['days_rest'].std()),
            'bucket_counts': {int(k): int(v) for k, v in
                              rolling['days_rest'].value_counts().sort_index().items()},
            'pct_neutral_default': float((rolling['days_rest'] == 5).mean()),
        },
    }
    out_json = OUT_DIR / 'days_rest_results.json'
    with open(out_json, 'w') as fh:
        json.dump(output, fh, indent=2, default=float)
    print(f'\nWrote {out_json}')


if __name__ == '__main__':
    main()
