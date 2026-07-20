"""
xfp_h_eval.py — cross-year + OOY validation harness for hitter xFP models.

Mirrors `scripts/xfp/xfp_v7_pipeline.py:153-188` but for batters. Evaluates
candidate feature sets against `fp_per_pa_actual` from
`data/research/xfp_cache/hitters_multiyr_2015_2026.csv`.

Two thresholds (matches the plan):
- ≥ 200 PA per season for *training* inclusion
- ≥ 300 PA per season for cross-year *evaluation* rows

Baselines reported alongside any candidate model:
- B_lag:   prior-year fp_per_pa as the prediction (the "do nothing" floor)
- V0:      current hitter_points.project() — only on years where
           master_hitter_{year}.csv exists (2023-2026), so a partial signal

Bias metrics:
- power_bias_hi:    mean residual on hitters with hr_per_pa > 0.05
- team_context_bias: mean residual gap between top-quartile-team-fp / bottom-quartile-team-fp

Run as:
    python scripts/xfp/xfp_h_eval.py
    python scripts/xfp/xfp_h_eval.py --baseline v0
"""
from __future__ import annotations
import argparse
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'

# Skip 2020 short season entirely from training pool.
TRAIN_MIN_PA = 200
EVAL_MIN_PA  = 300
TRAIN_YEARS = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]  # no 2020
TRANSITIONS = [(2018, 2019), (2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025)]


def load_substrate() -> pd.DataFrame:
    df = pd.read_csv(SUBSTRATE)
    return df


def power_bias_hi(res_df: pd.DataFrame, hr_col: str = '_hr_per_pa_test') -> float:
    """Mean residual on hitters with hr_per_pa > 0.05 (top-power tier).

    Uses the test-side `_hr_per_pa_test` column which is renamed in
    cross_year_evaluate to avoid colliding with `hr_per_pa` when it's a feature.
    Falls back to `hr_per_pa` for the lag baseline path which doesn't rename.
    """
    col = hr_col if hr_col in res_df.columns else 'hr_per_pa'
    sub = res_df[res_df[col] > 0.05]
    return float(sub['resid'].mean()) if len(sub) > 0 else 0.0


def team_context_bias(res_df: pd.DataFrame, team_col: str = '_team_test',
                      fp_col: str = '_fp_per_pa_actual_test') -> float:
    """Mean residual gap between top-quartile-team-fp/PA hitters vs bottom-quartile.

    Uses the test-side renamed columns from cross_year_evaluate. Falls back
    to canonical names for the lag baseline path which doesn't rename.
    """
    tcol = team_col if team_col in res_df.columns else 'team'
    fcol = fp_col   if fp_col   in res_df.columns else 'fp_per_pa_actual'
    if tcol not in res_df.columns or res_df[tcol].isna().all():
        return 0.0
    team_fp = res_df.groupby(tcol)[fcol].mean().sort_values()
    n = len(team_fp)
    if n < 4:
        return 0.0
    bot = set(team_fp.iloc[: n // 4].index)
    top = set(team_fp.iloc[-n // 4:].index)
    top_resid = res_df[res_df[tcol].isin(top)]['resid'].mean()
    bot_resid = res_df[res_df[tcol].isin(bot)]['resid'].mean()
    return float(top_resid - bot_resid) if pd.notna(top_resid) and pd.notna(bot_resid) else 0.0


def cross_year_evaluate(df: pd.DataFrame, feats: list[str], label: str = '') -> dict:
    """Year T metrics → year T+1 fp_per_pa_actual.

    Train on all rows with year < yr_test (≥ TRAIN_MIN_PA, year != 2020).
    Evaluate on shared (batter) ∩ (yr_train, yr_test) where test row has ≥ EVAL_MIN_PA.
    """
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    preds_all, acts_all, res_rows = [], [], []
    for yr_train, yr_test in TRANSITIONS:
        train_pool = df[
            (df['year'] < yr_test)
            & (df['year'] != 2020)
            & (df['pa'] >= TRAIN_MIN_PA)
        ].dropna(subset=feats + ['fp_per_pa_actual'])
        if len(train_pool) < 50:
            continue

        # Test rows: in yr_test AND in yr_train AND ≥ EVAL_MIN_PA in yr_test
        train_year = df[(df['year'] == yr_train) & (df['pa'] >= TRAIN_MIN_PA)]
        test_year  = df[(df['year'] == yr_test)  & (df['pa'] >= EVAL_MIN_PA)]
        shared = set(train_year['batter']) & set(test_year['batter'])
        train_year = train_year[train_year['batter'].isin(shared)]
        test_year  = test_year [test_year ['batter'].isin(shared)].copy()

        # Rename the test-side cohort/team columns so they don't collide with
        # any feature names that overlap (e.g. hr_per_pa is both a feature and
        # the cohort-defining metric for power_bias_hi).
        test_meta = test_year[['batter','fp_per_pa_actual','hr_per_pa','team']].rename(
            columns={'hr_per_pa': '_hr_per_pa_test', 'team': '_team_test',
                     'fp_per_pa_actual': '_fp_per_pa_actual_test'})
        merged = test_meta.merge(
            train_year[['batter'] + feats], on='batter', how='inner'
        ).dropna(subset=feats + ['_fp_per_pa_actual_test'])
        if len(merged) < 10:
            continue

        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train_pool[feats].values, train_pool['fp_per_pa_actual'].values)
        merged['pred'] = pipe.predict(merged[feats].values)
        merged['transition'] = f'{yr_train}->{yr_test}'
        preds_all.extend(merged['pred'].tolist())
        acts_all.extend(merged['_fp_per_pa_actual_test'].tolist())
        res_rows.append(merged)

    if not res_rows:
        return {'type': 'cross_year', 'r': np.nan, 'n': 0, 'label': label or ','.join(feats)}

    res = pd.concat(res_rows, ignore_index=True)
    res['resid'] = res['pred'] - res['_fp_per_pa_actual_test']  # positive = over-projection
    r = float(np.corrcoef(preds_all, acts_all)[0, 1])
    bias_hi = power_bias_hi(res)
    bias_team = team_context_bias(res)
    rmse = float(np.sqrt(np.mean(res['resid']**2)))
    mae  = float(np.mean(res['resid'].abs()))
    return {
        'type': 'cross_year',
        'r': round(r, 5),
        'power_bias_hi': round(bias_hi, 4),
        'team_context_bias': round(bias_team, 4),
        'rmse': round(rmse, 4),
        'mae': round(mae, 4),
        'n': len(res),
        'n_transitions': res['transition'].nunique(),
        'label': label or ','.join(feats),
    }


def lag_baseline_evaluate(df: pd.DataFrame) -> dict:
    """Naive baseline: predict year T+1 fp_per_pa = year T fp_per_pa."""
    preds_all, acts_all, res_rows = [], [], []
    for yr_train, yr_test in TRANSITIONS:
        train_year = df[(df['year'] == yr_train) & (df['pa'] >= TRAIN_MIN_PA)]
        test_year  = df[(df['year'] == yr_test)  & (df['pa'] >= EVAL_MIN_PA)]
        shared = set(train_year['batter']) & set(test_year['batter'])
        train_year = train_year[train_year['batter'].isin(shared)][['batter', 'fp_per_pa_actual']].rename(
            columns={'fp_per_pa_actual': 'pred'})
        test_year  = test_year [test_year ['batter'].isin(shared)].copy()
        merged = test_year[['batter','fp_per_pa_actual','hr_per_pa','team']].merge(
            train_year, on='batter', how='inner'
        ).dropna(subset=['pred', 'fp_per_pa_actual'])
        if len(merged) < 10:
            continue
        merged['transition'] = f'{yr_train}->{yr_test}'
        preds_all.extend(merged['pred'].tolist())
        acts_all.extend(merged['fp_per_pa_actual'].tolist())
        res_rows.append(merged)

    if not res_rows:
        return {'type': 'lag_baseline', 'r': np.nan, 'n': 0, 'label': 'B_lag (prior_year_fp)'}

    res = pd.concat(res_rows, ignore_index=True)
    res['resid'] = res['pred'] - res['fp_per_pa_actual']
    r = float(np.corrcoef(preds_all, acts_all)[0, 1])
    return {
        'type': 'lag_baseline',
        'r': round(r, 5),
        'power_bias_hi': round(power_bias_hi(res), 4),
        'team_context_bias': round(team_context_bias(res), 4),
        'rmse': round(float(np.sqrt(np.mean(res['resid']**2))), 4),
        'mae': round(float(np.mean(res['resid'].abs())), 4),
        'n': len(res),
        'n_transitions': res['transition'].nunique(),
        'label': 'B_lag (prior_year_fp)',
    }


def v0_evaluate(df: pd.DataFrame) -> dict:
    """Evaluate the current hitter_points.project() on the (limited) years where
    master_hitter_{year}.csv exists (2023-2026). Predicts full_fp_per_pa.

    Falls back gracefully when master_hitter rows aren't available for both
    sides of a transition.
    """
    from plv_clone.fantasy.hitter_points import project as hp_project, load_calibration
    from plv_clone.fantasy.scoring import LeagueScoring

    scoring = LeagueScoring.load(ROOT / 'data' / 'models' / 'league_scoring.json')
    coefs = load_calibration(ROOT / 'data' / 'models')

    preds_all, acts_all, res_rows = [], [], []
    # Only 2023→2024 and 2024→2025 transitions are eligible (master_hitter exists for both)
    for yr_train, yr_test in [(2023, 2024), (2024, 2025)]:
        mh_train = ROOT / 'data' / 'outputs' / f'master_hitter_{yr_train}.csv'
        if not mh_train.exists():
            continue
        mh = pd.read_csv(mh_train)
        # Use V0 to project FP/PA from year T inputs
        try:
            proj = hp_project(mh, scoring=scoring, coefs=coefs).rename(
                columns={'batter': 'batter', 'full_fp_per_pa': 'pred'})
        except Exception as exc:
            print(f'  V0 project failed for {yr_train}: {exc}', flush=True)
            continue
        proj = proj[['batter', 'pred']]

        # Year T+1 actuals from substrate
        test_year = df[(df['year'] == yr_test) & (df['pa'] >= EVAL_MIN_PA)]
        merged = test_year[['batter','fp_per_pa_actual','hr_per_pa','team']].merge(
            proj, on='batter', how='inner'
        ).dropna(subset=['pred', 'fp_per_pa_actual'])
        if len(merged) < 10:
            continue
        merged['transition'] = f'{yr_train}->{yr_test}'
        preds_all.extend(merged['pred'].tolist())
        acts_all.extend(merged['fp_per_pa_actual'].tolist())
        res_rows.append(merged)

    if not res_rows:
        return {'type': 'v0_baseline', 'r': np.nan, 'n': 0,
                'label': 'V0 (hitter_points.project)', 'note': 'no eligible transitions'}

    res = pd.concat(res_rows, ignore_index=True)
    res['resid'] = res['pred'] - res['fp_per_pa_actual']
    r = float(np.corrcoef(preds_all, acts_all)[0, 1])
    return {
        'type': 'v0_baseline',
        'r': round(r, 5),
        'power_bias_hi': round(power_bias_hi(res), 4),
        'team_context_bias': round(team_context_bias(res), 4),
        'rmse': round(float(np.sqrt(np.mean(res['resid']**2))), 4),
        'mae': round(float(np.mean(res['resid'].abs())), 4),
        'n': len(res),
        'n_transitions': res['transition'].nunique(),
        'label': 'V0 (hitter_points.project) on 2023→2024 + 2024→2025',
    }


def score_fn(r: float, bias: float, T: float = 1.0, coef: float = 0.5) -> float:
    """Same scoring formula as V11 production (T=1.0 tolerance)."""
    if pd.isna(r):
        return float('nan')
    return r * 3 - max(0.0, abs(bias) - T) * coef


def fmt_result(res: dict) -> str:
    if pd.isna(res.get('r')):
        return f"{res.get('label', ''):<48s} | n={res.get('n', 0)} (no eval rows)"
    return (
        f"{res['label']:<60s} | "
        f"r={res['r']:.4f}  pwr_bias={res['power_bias_hi']:+.3f}  "
        f"team_bias={res['team_context_bias']:+.3f}  "
        f"rmse={res['rmse']:.4f}  mae={res['mae']:.4f}  "
        f"n={res['n']}/{res['n_transitions']}t  "
        f"score(T=1)={score_fn(res['r'], res['power_bias_hi']):.3f}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', choices=['lag', 'v0', 'all'], default='all',
                    help='Which baseline to print (default all).')
    args = ap.parse_args()

    df = load_substrate()
    print(f'=== xfp_h_eval — substrate {SUBSTRATE.name}: {len(df)} rows ===')
    print(f'  ≥{TRAIN_MIN_PA} PA: {(df["pa"] >= TRAIN_MIN_PA).sum()}')
    print(f'  ≥{EVAL_MIN_PA} PA: {(df["pa"] >= EVAL_MIN_PA).sum()}')
    print(f'  Transitions: {TRANSITIONS}')
    print()
    print('--- baselines ---')
    if args.baseline in ('lag', 'all'):
        print(fmt_result(lag_baseline_evaluate(df)))
    if args.baseline in ('v0', 'all'):
        print(fmt_result(v0_evaluate(df)))


if __name__ == '__main__':
    main()
