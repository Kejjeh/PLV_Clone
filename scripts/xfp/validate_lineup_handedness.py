"""validate_lineup_handedness.py - test lineup_handedness_match as a candidate rp3 feature.

Pre-registered: data/research/validation_runs/lineup_handedness_2026-06-02.md

lineup_handedness_match at (pitcher, year, cutoff_date):
  fraction of pre-cutoff PAs vs the pitcher where batter `stand` matches
  the pitcher's modal `p_throws`. Switch hitters: statcast `stand` is
  already resolved per-PA.

Identifying a PA: one row per (pitcher, batter, game_pk, at_bat_number).
Pitchers with < 50 prior PAs at cutoff get a population-mean default
(computed from training-years data, computed only once).
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
MIN_PRIOR_PA = 50
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]


# ---------------------------------------------------------------------------
# Build per-PA-level handedness panel for one year
# ---------------------------------------------------------------------------
def load_pa_handedness(year: int) -> pd.DataFrame:
    """Return one row per (pitcher, game_date, game_pk, at_bat_number) with
    (stand, p_throws) flagged. Used to compute per-(pitcher, cutoff) handedness
    fractions."""
    p = CACHE / f'statcast_{year}.parquet'
    df = pd.read_parquet(
        p, columns=['game_date', 'pitcher', 'batter', 'game_pk',
                    'at_bat_number', 'stand', 'p_throws'],
    )
    df = df.dropna(subset=['game_date', 'pitcher', 'batter', 'game_pk',
                           'at_bat_number', 'stand', 'p_throws'])
    df['game_date'] = pd.to_datetime(df['game_date']).dt.date
    df['pitcher'] = df['pitcher'].astype('int64')
    # Reduce to one row per PA
    pa = df.drop_duplicates(subset=['pitcher', 'game_pk', 'at_bat_number']).copy()
    pa['same_handed'] = (pa['stand'] == pa['p_throws']).astype(int)
    pa = pa[['game_date', 'pitcher', 'same_handed']]
    return pa


def build_handedness_for_year(year: int, cutoffs: list[pd.Timestamp],
                              default_val: float) -> pd.DataFrame:
    """For each (pitcher, cutoff) compute pre-cutoff same-handed PA fraction."""
    print(f'  loading statcast {year}...')
    pa = load_pa_handedness(year)
    if pa.empty:
        return pd.DataFrame()
    cutoff_dates = [pd.Timestamp(c).date() for c in cutoffs]
    pa = pa.sort_values(['pitcher', 'game_date'])
    rows: list[dict] = []
    for p, sub in pa.groupby('pitcher', sort=False):
        sub_dates = sub['game_date'].values  # already sorted
        sub_sh = sub['same_handed'].values
        for cd in cutoff_dates:
            mask = sub_dates < cd
            n_prior = int(mask.sum())
            if n_prior < MIN_PRIOR_PA:
                rows.append({
                    'pitcher': int(p), 'year': year, 'cutoff_date': str(cd),
                    'lineup_handedness_match': float(default_val),
                    'n_prior_pa': n_prior,
                    'is_default': 1,
                })
                continue
            frac = float(sub_sh[mask].mean())
            rows.append({
                'pitcher': int(p), 'year': year, 'cutoff_date': str(cd),
                'lineup_handedness_match': frac,
                'n_prior_pa': n_prior,
                'is_default': 0,
            })
    return pd.DataFrame(rows)


def estimate_population_default(rolling: pd.DataFrame) -> float:
    """Compute population mean same-handedness from TRAIN_YEARS statcast only.
    A single scalar. Used as the neutral default for low-PA pitchers."""
    print('  estimating population-mean default from training years only...')
    fracs = []
    weights = []
    for y in TRAIN_YEARS:
        pa = load_pa_handedness(y)
        if pa.empty:
            continue
        n = len(pa)
        f = pa['same_handed'].mean()
        fracs.append(f)
        weights.append(n)
    # Weighted by n
    arr = np.array(fracs); w = np.array(weights, dtype=float)
    return float((arr * w).sum() / w.sum())


def build_full_handedness_panel(rolling: pd.DataFrame, default_val: float) -> pd.DataFrame:
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
        h = build_handedness_for_year(int(y), cutoffs, default_val=default_val)
        if not h.empty:
            out_frames.append(h)
    out = pd.concat(out_frames, ignore_index=True)
    out['cutoff_date'] = pd.to_datetime(out['cutoff_date'])
    return out


# ---------------------------------------------------------------------------
# Convergence and partial r (shared style)
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
    print('=== validate_lineup_handedness ===')
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

    print('Step 2: estimate population-mean handedness default (training years only)...')
    default_val = estimate_population_default(rolling)
    print(f'  population mean fraction same-handed (TRAIN_YEARS): {default_val:.4f}')

    print('Step 3: build lineup_handedness_match panel from statcast...')
    h = build_full_handedness_panel(rolling, default_val=default_val)
    print(f'  handedness rows: {len(h)}')
    print(f'  fraction at default (n_prior_pa < {MIN_PRIOR_PA}): {h["is_default"].mean():.1%}')
    real = h[h['is_default'] == 0]
    if len(real) > 0:
        print(f'  real (non-default) lineup_handedness_match dist:')
        print(f'    mean: {real["lineup_handedness_match"].mean():.4f}, '
              f'std: {real["lineup_handedness_match"].std():.4f}, '
              f'min: {real["lineup_handedness_match"].min():.4f}, '
              f'max: {real["lineup_handedness_match"].max():.4f}')

    rolling = rolling.copy()
    rolling['cutoff_date'] = pd.to_datetime(rolling['cutoff_date'])
    rolling = rolling.merge(
        h[['pitcher', 'year', 'cutoff_date', 'lineup_handedness_match', 'n_prior_pa']],
        on=['pitcher', 'year', 'cutoff_date'], how='left',
    )
    rolling['lineup_handedness_match'] = rolling['lineup_handedness_match'].fillna(default_val)
    rolling['n_prior_pa'] = rolling['n_prior_pa'].fillna(0).astype(int)
    print(f'  post-merge: {len(rolling)}, '
          f'pct at default: {(rolling["n_prior_pa"] < MIN_PRIOR_PA).mean():.1%}')

    print('Step 4: Rule-9 lift test...')
    result = evaluate_candidate(rolling, 'lineup_handedness_match',
                                fill_value=default_val,
                                label='lineup_handedness_match')
    print_report(result)

    print('Step 5: convergence at 30/44/58...')
    conv = per_split_day_lift(rolling, 'lineup_handedness_match')
    for sd, c in conv.items():
        if c.get('skipped'):
            print(f'  sd={sd}: SKIPPED'); continue
        print(f'  sd={sd:>3}: r_base={c["r_baseline"]:.4f}  r_full={c["r_full"]:.4f}  '
              f'gain={c["r_gain"]:+.4f}  mae_gain={c["mae_gain"]:+.4f}  n={c["n_eval_full"]}')

    print('Step 6: partial r vs full baseline...')
    pr = partial_r_full_baseline(rolling, 'lineup_handedness_match')
    print(f'  partial r = {pr["partial_r"]:+.4f}  (pooled n={pr["n"]})')

    print('Step 7: holdout MAE on 2024-2025...')
    py_b, ov_b = cross_year_eval(rolling, RP3_FEATS)
    py_f, ov_f = cross_year_eval(rolling, RP3_FEATS + ['lineup_handedness_match'])
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
        'population_default': default_val,
        'feature_distribution': {
            'mean': float(rolling['lineup_handedness_match'].mean()),
            'std': float(rolling['lineup_handedness_match'].std()),
            'pct_at_default': float((rolling['n_prior_pa'] < MIN_PRIOR_PA).mean()),
        },
    }
    out_json = OUT_DIR / 'lineup_handedness_results.json'
    with open(out_json, 'w') as fh:
        json.dump(output, fh, indent=2, default=float)
    print(f'\nWrote {out_json}')


if __name__ == '__main__':
    main()
