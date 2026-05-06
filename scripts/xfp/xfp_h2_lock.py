"""
xfp_h2_lock.py — production lock for the H2 hitter xFP model.

Trains the H2 Ridge on 2018-2025 (drop 2020, PA ≥ 200), generates the
mid-season-blended 2026 input set, and writes:

  data/models/xfp_h2_pipeline.pkl   — production bundle (full + core models)
  data/outputs/xfp_h2_projections.csv — per-batter projections for 2026

Bundle keys:
  pipeline_full, pipeline_core, features, cross_year_r, power_bias_hi,
  team_context_bias, score_T1, formula, trained_date, n_train, version='h2',
  ytd_r_2026, ytd_mae_2026, prior_xwoba, prior_contact

Mirrors `scripts/xfp/xfp_v11_lock.py` for hitters.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
MASTER_HITTER = ROOT / 'data' / 'outputs' / 'master_hitter_2026.csv'
MODEL_OUT = ROOT / 'data' / 'models' / 'xfp_h2_pipeline.pkl'
PROJ_OUT = ROOT / 'data' / 'outputs' / 'xfp_h2_projections.csv'

import sys
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from xfp_h_eval import cross_year_evaluate, score_fn  # noqa
from xfp_h2_midseason import (
    H2_FEATS, train_h2, blend_hitter, project_set, evaluate_ytd,
    PRIOR_XWOBA, PRIOR_CONTACT, TRAIN_YEARS, TRAIN_MIN_PA, YTD_MIN_PA,
)

PA_PER_GAME = 3.5  # league average — matches build_fantasy_exports default


def train_core_h2(df: pd.DataFrame, feats: list[str]):
    """Same H2 features but predicting core_fp_per_pa_actual (skill-only)."""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    train = df[
        (df['year'].isin(TRAIN_YEARS))
        & (df['pa'] >= TRAIN_MIN_PA)
    ].dropna(subset=feats + ['core_fp_per_pa_actual']).copy()
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    pipe.fit(train[feats].values, train['core_fp_per_pa_actual'].values)
    return pipe, len(train)


def main():
    df = pd.read_csv(SUBSTRATE)
    print(f'=== xfp_h2_lock — substrate {SUBSTRATE.name}: {len(df)} rows ===')
    print(f'Features ({len(H2_FEATS)}): {H2_FEATS}\n')

    # Cross-year metrics for reproducibility (re-evaluated, written into bundle)
    cy = cross_year_evaluate(df.dropna(subset=H2_FEATS + ['fp_per_pa_actual']), H2_FEATS, label='H2')
    score_t1 = score_fn(cy['r'], cy['power_bias_hi'])
    print(f'Cross-year r: {cy["r"]}  power_bias_hi: {cy["power_bias_hi"]}  '
          f'team_context_bias: {cy["team_context_bias"]}  score(T=1): {score_t1:.4f}')

    # Train final pipelines
    pipe_full, n_train = train_h2(df, H2_FEATS)
    pipe_core, n_core  = train_core_h2(df, H2_FEATS)
    print(f'\nTrained full FP pipeline: {n_train} rows | core FP pipeline: {n_core} rows')

    # Build mid-season-blended 2026 inputs
    df_25 = df[df['year'] == 2025].copy().set_index('batter', drop=True)
    df_26 = df[df['year'] == 2026].copy().set_index('batter', drop=True)
    df_25.index.name = '_idx'
    df_26.index.name = '_idx'

    all_ids = set(df_25.index) | set(df_26.index)
    rows = []
    for b in all_ids:
        r25 = df_25.loc[b] if b in df_25.index else None
        r26 = df_26.loc[b] if b in df_26.index else None
        if isinstance(r25, pd.DataFrame): r25 = r25.iloc[0]
        if isinstance(r26, pd.DataFrame): r26 = r26.iloc[0]
        out = blend_hitter(r25, r26)
        if out is not None:
            out['batter'] = b
            # Carry FG bat-tracking flag
            has_bt = pd.notna(r26.get('blast_rate')) if r26 is not None else False
            out['has_bat_tracking'] = bool(has_bt)
            rows.append(out)
    inputs = pd.DataFrame(rows)
    print(f'Mid-season blended inputs: {len(inputs)} hitters; cohorts = {inputs["cohort"].value_counts().to_dict()}')

    # Project both targets
    valid = inputs.dropna(subset=H2_FEATS).copy()
    valid['xfp_h2_per_pa']      = pipe_full.predict(valid[H2_FEATS].values)
    valid['core_xfp_per_pa']    = pipe_core.predict(valid[H2_FEATS].values)
    valid['xfp_h2_full_fp']     = (valid['xfp_h2_per_pa']   * PA_PER_GAME).round(3)
    valid['core_xfp_full_fp']   = (valid['core_xfp_per_pa'] * PA_PER_GAME).round(3)
    print(f'Projected: {len(valid)} hitters')

    # Merge back 2026 actuals (for the dashboard "2026 FP/PA actual" column)
    actuals = df[df['year'] == 2026][['batter', 'pa', 'fp_per_pa_actual', 'fp_total', 'r', 'rbi', 'hr', 'team']].rename(
        columns={'pa': 'pa_2026', 'fp_per_pa_actual': 'fp_per_pa_actual_2026',
                 'fp_total': 'fp_total_actual_2026', 'r': 'r_2026', 'rbi': 'rbi_2026',
                 'hr': 'hr_2026', 'team': 'team_2026'}
    )
    out = valid.merge(actuals, on='batter', how='left')

    # Position map: hijack the 2026 master_hitter (the latest position-enriched file)
    if MASTER_HITTER.exists():
        mh = pd.read_csv(MASTER_HITTER)
        if 'primary_position' in mh.columns:
            mh_keep = ['batter', 'batter_name', 'primary_position', 'fantasy_positions',
                       'fantasy_positions_display']
            mh_keep = [c for c in mh_keep if c in mh.columns]
            out = out.merge(mh[mh_keep], on='batter', how='left')
        # Use master_hitter's batter_name if present, otherwise fall back to substrate player_name
        if 'batter_name' in out.columns:
            out['player_name'] = out['batter_name'].fillna(out['player_name'])
            out = out.drop(columns=['batter_name'])

    # PA premium — playing-time bonus relative to league avg of 3.5 PA/game.
    # Approximate games played from PA / 3.5 (rough). For a hitter with PA close to
    # team_games × 3.5, premium ≈ 0; high-PA leadoff/2-hole hitters get a bonus.
    # Skip when no 2026 PA data (premium = 0).
    out['pa_premium'] = 0.0
    has_pa = out['pa_2026'].notna() & (out['pa_2026'] > 0)
    if has_pa.any():
        # Estimate team games — assume 35 (today is 2026-05-06 ≈ 35 games into season)
        approx_games = 35
        out.loc[has_pa, 'pa_premium'] = (
            (out.loc[has_pa, 'pa_2026'] / approx_games - PA_PER_GAME)
            * out.loc[has_pa, 'xfp_h2_per_pa']
        ).round(3)

    # Round display-side fields
    for c in ('xfp_h2_per_pa', 'core_xfp_per_pa', 'fp_per_pa_actual_2026'):
        if c in out.columns:
            out[c] = out[c].astype(float).round(4)
    out['cohort'] = out['cohort'].fillna('—')
    out['weight_2026'] = out['weight_2026'].fillna(0.0).round(3)
    out['rank'] = out['xfp_h2_per_pa'].rank(ascending=False, method='min').astype(int)

    # YTD metrics for the bundle
    ytd = evaluate_ytd(out.rename(columns={'xfp_h2_per_pa': 'xfp_h2_per_pa'}), df, H2_FEATS, min_pa=YTD_MIN_PA)

    # Final column order
    cols = [
        'rank', 'batter', 'player_name',
        'primary_position', 'fantasy_positions_display', 'team_2026',
        'xfp_h2_per_pa', 'core_xfp_per_pa', 'xfp_h2_full_fp', 'core_xfp_full_fp',
        'pa_premium',
        'pa_2026', 'fp_per_pa_actual_2026', 'fp_total_actual_2026',
        'r_2026', 'rbi_2026', 'hr_2026',
        'cohort', 'weight_2026', 'has_bat_tracking',
    ]
    cols = [c for c in cols if c in out.columns]
    out = out[cols].sort_values('xfp_h2_per_pa', ascending=False).reset_index(drop=True)
    out['rank'] = out.index + 1

    PROJ_OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROJ_OUT, index=False)
    print(f'\nWrote {PROJ_OUT}: {len(out)} rows, {len(cols)} cols')

    # Bundle
    bundle = {
        'pipeline_full': pipe_full,
        'pipeline_core': pipe_core,
        'features': H2_FEATS,
        'cross_year_r': cy['r'],
        'power_bias_hi': cy['power_bias_hi'],
        'team_context_bias': cy['team_context_bias'],
        'cross_year_rmse': cy['rmse'],
        'cross_year_mae': cy['mae'],
        'cross_year_n': cy['n'],
        'score_T1': round(score_t1, 5),
        'formula': 'r * 3 - max(0, |power_bias_hi| - 1.0) * 0.5  (T=1.0 production)',
        'trained_date': str(date.today()),
        'n_train_full': n_train,
        'n_train_core': n_core,
        'training_years': TRAIN_YEARS,
        'train_min_pa': TRAIN_MIN_PA,
        'eval_min_pa': 300,
        'pa_per_game': PA_PER_GAME,
        'prior_xwoba': PRIOR_XWOBA,
        'prior_contact': PRIOR_CONTACT,
        'ytd_r_2026': ytd['r'],
        'ytd_mae_2026': ytd['mae'],
        'ytd_n_2026': ytd['n'],
        'version': 'h2',
        'note': 'H2 = Ridge on 13 hitter features (rate-stat lags + sprint speed + bat-tracking proxies). Mid-season blend ships per H3 gate.',
    }
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_OUT)
    print(f'Wrote {MODEL_OUT}')

    # Verify reload + predict matches
    bundle2 = joblib.load(MODEL_OUT)
    sample = valid[H2_FEATS].head(5).values
    p1 = pipe_full.predict(sample)
    p2 = bundle2['pipeline_full'].predict(sample)
    diff = float(np.max(np.abs(p1 - p2)))
    assert diff < 1e-6, f'reload mismatch: {diff}'
    print(f'\nReload verify: max diff {diff:.2e} ✓')

    # Spot-check top 10
    print(f'\nTop 10 by xFP H2 per PA:')
    show_cols = ['rank', 'player_name', 'primary_position', 'team_2026', 'pa_2026',
                 'xfp_h2_per_pa', 'core_xfp_per_pa', 'fp_per_pa_actual_2026', 'cohort']
    show_cols = [c for c in show_cols if c in out.columns]
    print(out.head(10)[show_cols].to_string(index=False))

    print(f'\nFinal:')
    print(f'  cross-year r: {cy["r"]:.4f}  score(T=1): {score_t1:.4f}')
    print(f'  YTD r: {ytd["r"]}  MAE: {ytd["mae"]}  n: {ytd["n"]}')


if __name__ == '__main__':
    main()
