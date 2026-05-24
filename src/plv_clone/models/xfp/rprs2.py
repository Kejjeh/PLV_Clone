"""xfp_rprs2 — RP RoS model with in-season role-usage features.

Adds (vs RP-RS1):
  - gf_pct_to        (current-year games-finished % through cutoff)
  - sv_per_g_to      (current-year saves per appearance through cutoff)
  - hld_per_g_to     (current-year holds per appearance through cutoff)
  - sv_plus_hld_to   (raw count, captures total high-leverage usage)
  - sv_per_g_lag1    (prior year saves rate)
  - hld_per_g_lag1   (prior year holds rate)
  - fp_with_role_to  (FP-to-date with SV/HLD bonuses included — closer to actual)

These were identified by comparing PL Top 50 ranking correlations: PL leans
heavily on gf_pct_now / sv_pct_now (ρ ≈ -0.74) which our prior model didn't see.

Stratified validation gate:
  1. OVERALL LOO cross-year r must NOT regress vs RP-RS1 baseline (gate >= 0.0)
  2. ROLE-CHANGE SUBSET cross-year r MUST improve by >= +0.05.
     Subset definition: rows where current-season SV pace differs from
     prior-year SV/G by > 0.10 SV/G in absolute terms (excluding pitchers with
     no lag data — those are pure rookies, separate problem).

If both pass, ship as production. If overall regresses, hard fail (don't trade
overall accuracy for niche signal). If only role-change fails, document the
negative result and revert.

ADR-0001: this module owns its own fit_and_project orchestration. The shared
`engine.py` is a toolkit composed at load-bearing steps, not an orchestrator.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import json
import numpy as np
import pandas as pd
import joblib

from plv_clone.models.xfp import engine as _engine
from plv_clone.models.xfp.engine import lookup_sigma  # re-export
from plv_clone.league_config import RP_REPLACEMENT_RANK as REPLACEMENT_RANK_RP

warnings.filterwarnings('ignore')

# Path anchors: this file lives at src/plv_clone/models/xfp/rprs2.py, so parents[4]
# is the repo root (rprs2.py → xfp → models → plv_clone → src → repo root).
ROOT = Path(__file__).resolve().parents[4]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_relievers_2018_2026.csv'
COUNTING_DIR = ROOT / 'data' / 'research' / 'xfp_cache'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_rprs2_pipeline.pkl'
PROJ_CSV  = ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv'

TARGET = 'fp_year_total'
EVAL_G_MIN = 5
TRAIN_YEARS = [2019, 2021, 2022, 2023, 2024, 2025]

# Baseline (RP-RS1) feature set — for the gate comparison
BASE_FEATS = [
    'k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'c_plus_swstr_to',
    'xwoba_per_pa_to', 'avg_velo_to', 'zone_pct_to', 'o_swing_pct_to',
    'g_to', 'ip_to', 'fp_skill_to',
    'role_closer_lag1', 'role_setup_lag1', 'role_middle_lag1',
    'sv_lag1', 'hld_lag1', 'g_lag1', 'ip_lag1',
    'fp_per_g_lag1', 'fp_lag1',
    'split_day',
]
# New features added in RP-RS2
NEW_FEATS = [
    'gf_pct_to', 'sv_per_g_to', 'hld_per_g_to', 'sv_plus_hld_to',
    'fp_with_role_to',
    'sv_per_g_lag1', 'hld_per_g_lag1',
]
FEATS_RPRS2 = BASE_FEATS + NEW_FEATS

# ADR-0003 phase-5 hard assert: every FEATS entry must have a PASS
# validation_runs record. Backfill completed 2026-05-23.
from plv_clone.models.xfp.validated_signals import check_feats_validated as _check_feats_validated
with warnings.catch_warnings():
    warnings.simplefilter("default", UserWarning)
    _check_feats_validated(FEATS_RPRS2, target="rprs2", strict=True)


def cross_year_eval(df: pd.DataFrame, feats: list[str], subset_mask=None):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[df['year'].isin(TRAIN_YEARS) & (df['g_to'] >= EVAL_G_MIN)]
    per_year, preds_all, acts_all = {}, [], []
    test_indices = []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
        mae = float(np.mean(np.abs(preds - test[TARGET].values)))
        per_year[held] = {'r': round(r, 4), 'mae': round(mae, 2), 'n': len(test)}
        preds_all.extend(preds.tolist())
        acts_all.extend(test[TARGET].tolist())
        test_indices.extend(test.index.tolist())
    if subset_mask is not None:
        preds_arr = np.array(preds_all); acts_arr = np.array(acts_all)
        idx_arr = np.array(test_indices)
        keep = subset_mask.reindex(idx_arr).fillna(False).values
        preds_arr = preds_arr[keep]; acts_arr = acts_arr[keep]
        if len(preds_arr) < 30:
            return per_year, {'r': np.nan, 'mae': np.nan, 'n': len(preds_arr)}
        r = float(np.corrcoef(preds_arr, acts_arr)[0, 1])
        mae = float(np.mean(np.abs(preds_arr - acts_arr)))
        return per_year, {'r': round(r, 4), 'mae': round(mae, 2), 'n': len(preds_arr)}
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 2),
                      'n': len(preds_all)}


def role_change_mask(df: pd.DataFrame) -> pd.Series:
    """Identify rows where current-year SV pace differs from prior-year SV pace
    by > 0.10 SV/G in absolute terms. Excludes rows with no lag data (sv_per_g_lag1
    will be 0 if no prior). For role-change detection, both sides should be > 0
    OR have a meaningful gap."""
    sv_now_per_g = df['sv_to'] / df['g_to'].replace(0, np.nan)
    sv_lag_per_g = df['sv_per_g_lag1']
    gap = (sv_now_per_g - sv_lag_per_g).abs()
    has_lag = df['sv_per_g_lag1'].notna() & (df['g_lag1'] >= 20)
    return (gap > 0.10) & has_lag


def fit_residual_ci(df, feats):
    sub = df.dropna(subset=feats + [TARGET]).copy()
    sub = sub[sub['year'].isin(TRAIN_YEARS) & (sub['g_to'] >= EVAL_G_MIN)]
    res = _engine.train_residual_table(
        df=sub, feats=feats, target_col=TARGET, train_years=TRAIN_YEARS,
        min_train=100, min_test=30,
    )
    out: dict[tuple[int, int], float] = {}
    for split in sorted(res['split_day'].unique()):
        sub2 = res[res['split_day'] == split]
        if len(sub2) < 30:
            continue
        qs = pd.qcut(sub2['pred'], q=4, duplicates='drop', labels=False)
        for q in sorted(sub2.groupby(qs).groups.keys()):
            ix = (qs == q)
            sigma = float(sub2.loc[ix, 'resid'].std())
            out[(int(split), int(q))] = sigma
    overall_sigma = float(res['resid'].std())
    return out, overall_sigma


def train_final(df, feats):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=feats + [TARGET])
    train = train[train['year'].isin(TRAIN_YEARS) & (train['g_to'] >= EVAL_G_MIN)]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[feats].values, train[TARGET].values)
    return pipe, len(train)


def main():
    print('=== xfp_rprs2_pipeline (RoS RP + role-usage features) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    print(f'rolling substrate: {len(rolling)} rows')

    # Identify the role-change subset (validation cohort)
    rc_mask = role_change_mask(rolling)
    print(f'\nRole-change subset (|sv/g_now − sv/g_lag1| > 0.10 AND has lag): {rc_mask.sum()} rows')

    # Baseline RP-RS1: BASE_FEATS only
    print('\n--- BASELINE RP-RS1 (BASE_FEATS only) ---')
    _per, baseline_overall = cross_year_eval(rolling, BASE_FEATS)
    _per, baseline_rc = cross_year_eval(rolling, BASE_FEATS, subset_mask=rc_mask)
    print(f'  Overall:        r={baseline_overall["r"]}  mae={baseline_overall["mae"]}  n={baseline_overall["n"]}')
    print(f'  Role-change:    r={baseline_rc["r"]}       mae={baseline_rc["mae"]}      n={baseline_rc["n"]}')

    # RP-RS2: BASE + NEW
    print('\n--- RP-RS2 (BASE + role-usage features) ---')
    per_year, overall = cross_year_eval(rolling, FEATS_RPRS2)
    _per, overall_rc = cross_year_eval(rolling, FEATS_RPRS2, subset_mask=rc_mask)
    for y, m in sorted(per_year.items()):
        print(f'  {y}: r={m["r"]:.4f}  mae={m["mae"]:.2f}  n={m["n"]}')
    print(f'  Overall:        r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')
    print(f'  Role-change:    r={overall_rc["r"]}       mae={overall_rc["mae"]}      n={overall_rc["n"]}')

    delta_overall = overall['r'] - baseline_overall['r']
    delta_rc      = overall_rc['r'] - baseline_rc['r']
    print(f'\n--- GATE EVALUATION ---')
    print(f'  Δr overall (gate ≥ 0.0):       {delta_overall:+.4f}  '
          f'{"PASS" if delta_overall >= 0.0 else "FAIL"}')
    print(f'  Δr role-change (gate ≥ +0.05): {delta_rc:+.4f}  '
          f'{"PASS" if delta_rc >= 0.05 else "FAIL"}')

    overall_pass = (delta_overall >= 0.0)
    rc_pass = (delta_rc >= 0.05)
    if not overall_pass:
        print('\nOVERALL r REGRESSED — rejecting RP-RS2 (would degrade general accuracy).')
        return
    if not rc_pass:
        print('\nROLE-CHANGE subset DID NOT IMPROVE — features have no signal where it matters.')
        print('Documenting negative result; not promoting.')
        return

    print('\n[BOTH GATES PASSED] Promoting RP-RS2 to production.')

    # Residual CI + final train
    ci_table, overall_sigma = fit_residual_ci(rolling, FEATS_RPRS2)
    pipe, n_train = train_final(rolling, FEATS_RPRS2)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final RP-RS2 (n={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}, '
          f'{len(FEATS_RPRS2)} features) ---')
    print('  Top 12 coefficients:')
    for f, c in sorted(zip(FEATS_RPRS2, coefs), key=lambda x: -abs(x[1]))[:12]:
        print(f'    {f:<22s} {c:+.4f}')
    print('  NEW feature coefficients:')
    for f, c in zip(FEATS_RPRS2, coefs):
        if f in NEW_FEATS:
            print(f'    {f:<22s} {c:+.4f}')

    # Project 2026
    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['g_to'] >= EVAL_G_MIN)]
    valid = df_26.dropna(subset=FEATS_RPRS2).copy()
    valid['xfp_full_year'] = pipe.predict(valid[FEATS_RPRS2].values).round(1)

    train_for_buckets = rolling.dropna(subset=FEATS_RPRS2 + [TARGET])
    train_for_buckets = train_for_buckets[
        train_for_buckets['year'].isin(TRAIN_YEARS) & (train_for_buckets['g_to'] >= EVAL_G_MIN)]
    train_pred = pipe.predict(train_for_buckets[FEATS_RPRS2].values)
    pred_buckets = {}
    for split in sorted(train_for_buckets['split_day'].unique()):
        ix = (train_for_buckets['split_day'].values == split)
        if ix.sum() < 30:
            continue
        cuts = np.quantile(train_pred[ix], [0.25, 0.5, 0.75])
        pred_buckets[int(split)] = cuts

    Z25 = 0.6745
    sigmas = []
    for _, row in valid.iterrows():
        sigmas.append(lookup_sigma(ci_table, overall_sigma, latest_split,
                                   row['xfp_full_year'], pred_buckets))
    valid['xfp_sigma'] = sigmas
    valid['xfp_p25'] = (valid['xfp_full_year'] - Z25 * valid['xfp_sigma']).clip(lower=0)
    valid['xfp_p75'] = valid['xfp_full_year'] + Z25 * valid['xfp_sigma']

    cnt = json.loads((COUNTING_DIR / 'pitcher_counting_stats_2026.json').read_text())
    cnt_df = pd.DataFrame(cnt)
    def parse_ip(v):
        if v is None or pd.isna(v): return np.nan
        s = str(v)
        if '.' in s:
            whole, frac = s.split('.', 1)
            return float(whole) + (1/3 if frac.startswith('1') else 2/3 if frac.startswith('2') else 0)
        return float(v)
    cnt_df['ip'] = cnt_df['inningsPitched'].map(parse_ip)
    cnt_df['fp_actual_2026'] = (
        cnt_df['strikeOuts'] + cnt_df['ip']*3.3 + cnt_df['saves']*5
        + cnt_df['holds']*3 - cnt_df['baseOnBalls'] - 2*cnt_df['earnedRuns']
        - cnt_df['hits'] - cnt_df['hitByPitch']
    ).round(1)
    cnt_df = cnt_df[['pitcher','name','saves','holds','fp_actual_2026']].rename(
        columns={'name':'name_api','saves':'sv_2026','holds':'hld_2026'})
    valid = valid.merge(cnt_df, on='pitcher', how='left')
    valid['fp_actual_2026'] = valid['fp_actual_2026'].fillna(0)
    valid['xfp_ros'] = (valid['xfp_full_year'] - valid['fp_actual_2026']).round(1)
    valid['xfp_ros_p25'] = (valid['xfp_p25'] - valid['fp_actual_2026']).round(1).clip(lower=0)
    valid['xfp_ros_p75'] = (valid['xfp_p75'] - valid['fp_actual_2026']).round(1)

    sorted_by_total = valid.sort_values('xfp_full_year', ascending=False).reset_index(drop=True)
    if len(sorted_by_total) >= REPLACEMENT_RANK_RP:
        repl = float(sorted_by_total['xfp_full_year'].iloc[REPLACEMENT_RANK_RP - 1])
    else:
        repl = float(sorted_by_total['xfp_full_year'].median())
    valid['replacement_xfp'] = round(repl, 1)
    valid['replacement_delta'] = (valid['xfp_full_year'] - repl).round(1)

    def signal(row):
        rd = row.get('replacement_delta')
        p25 = row.get('xfp_p25')
        p75 = row.get('xfp_p75')
        rep = row.get('replacement_xfp')
        if pd.isna(rd) or pd.isna(rep): return 'hold'
        if pd.notna(p25) and p25 > rep: return 'add'
        if pd.notna(p75) and p75 < rep: return 'drop'
        return 'hold'
    valid['signal'] = valid.apply(signal, axis=1)
    valid = valid.sort_values('xfp_full_year', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1

    bundle = {
        'pipeline': pipe,
        'features': FEATS_RPRS2,
        'features_baseline': BASE_FEATS,
        'features_new': NEW_FEATS,
        'target': TARGET,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rprs1_r': baseline_overall['r'],
        'role_change_subset_r': overall_rc['r'],
        'role_change_subset_baseline_r': baseline_rc['r'],
        'delta_overall': round(delta_overall, 4),
        'delta_role_change': round(delta_rc, 4),
        'per_year_r': per_year,
        'ci_table': ci_table,
        'pred_buckets': {k: v.tolist() for k, v in pred_buckets.items()},
        'overall_sigma': overall_sigma,
        'training_years': TRAIN_YEARS,
        'min_g_to': EVAL_G_MIN,
        'replacement_rank': REPLACEMENT_RANK_RP,
        'gate_overall': 0.0,
        'gate_role_change': 0.05,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rprs2',
        'note': 'RP RoS model with statcast-derived in-season role-usage features '
                '(GF%, SV/G, HLD/G, SV+HLD, FP-with-role). Stratified-validated.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    keep = ['rank','pitcher','name_api','role_lag1','sv_lag1','hld_lag1',
            'g_to','sv_to','hld_to','gf_to','gf_pct_to','sv_per_g_to',
            'sv_2026','hld_2026',
            'fp_actual_2026','xfp_full_year','xfp_p25','xfp_p75',
            'xfp_ros','xfp_ros_p25','xfp_ros_p75',
            'replacement_xfp','replacement_delta','signal']
    keep = [c for c in keep if c in valid.columns]
    valid[keep].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(valid)} 2026 RP RoS projections')

    print('\nTop 15 by projected RoS FP:')
    show = valid.sort_values('xfp_ros', ascending=False).head(15)
    cols_show = ['rank','name_api','role_lag1','g_to','sv_to','gf_to','sv_2026',
                 'fp_actual_2026','xfp_full_year','xfp_ros','signal','replacement_delta']
    print(show[cols_show].to_string(index=False))


if __name__ == '__main__':
    main()
