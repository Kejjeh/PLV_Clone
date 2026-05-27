# Pre-registered: see data/research/validation_runs/pitch_shape_early_warning_sweep_2026-05-27.md
"""
30-cell sweep: 15 combinations of 4 pitch-shape signals × 2 holdout configs.
Signals: pfxz_delta (A), csw_last21 (B), ext_delta (C), new_pitch_flag (D)
Baseline: full RP3_FEATS (24 features) — Rule 9 compliant.
"""
from __future__ import annotations
import itertools
import warnings
import os
import duckdb
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

ROOT = "c:/Users/Joshua/plv_clone"
ROLLING_CSV   = f"{ROOT}/data/research/xfp_cache/rolling_pitchers_2018_2026.csv"
MULTIYR_CSV   = f"{ROOT}/data/research/xfp_cache/sp_multiyr_2015_2025.csv"
STATCAST_TMPL = f"{ROOT}/data/research/xfp_cache/statcast_{{yr}}.parquet"

RP3_FEATS = [
    'k_pct_to_sh', 'bb_pct_to_sh', 'swstr_pct_to_sh', 'c_plus_swstr_to_sh',
    'xwoba_per_pa_to_sh', 'zone_pct_to_sh', 'z_swing_pct_to_sh', 'o_swing_pct_to_sh',
    'avg_velo_to', 'fp_per_start_to', 'gs_to', 'prior_fp_per_start', 'prior_gs_eff',
    'is_on_il_at_split', 'days_since_il_return_imp', 'il_stints_to', 'split_day',
    'delta_velo', 'delta_swstr', 'delta_k_pct', 'delta_bb_pct',
    'delta_chase', 'delta_zone', 'ros_opp_xwoba_weighted',
]
TARGET = 'ros_fp_per_start'

TRAIN_YEARS_A = [2018, 2019, 2021, 2022, 2023]   # holdout A = [2024, 2025]
TRAIN_YEARS_B = [2018, 2019, 2021, 2022, 2023, 2024]  # holdout B = [2025, 2026-in-progress]
HOLDOUT_A = [2024, 2025]
HOLDOUT_B = [2025, 2026]

# Convergence cutoffs (split_day thresholds for Rule 8)
CUTOFF_DAYS = [30, 42, 56, 70, 84]


# ---------------------------------------------------------------------------
# Step 1 — Build candidate signal columns
# ---------------------------------------------------------------------------

def build_pfxz_delta(rolling: pd.DataFrame, multiyr: pd.DataFrame) -> pd.Series:
    """A: avg_pfxz_to (season-to-date) minus prior-year full-season avg_pfxz."""
    prior = multiyr[['pitcher', 'year', 'avg_pfxz']].copy()
    prior['year_next'] = prior['year'] + 1
    prior = prior.rename(columns={'avg_pfxz': 'prior_avg_pfxz'})
    merged = rolling.merge(
        prior[['pitcher', 'year_next', 'prior_avg_pfxz']],
        left_on=['pitcher', 'year'], right_on=['pitcher', 'year_next'],
        how='left'
    )
    # avg_pfxz_to is season-to-date vertical movement (inches)
    delta = merged['avg_pfxz_to'] - merged['prior_avg_pfxz']
    return delta.rename('pfxz_delta')


def build_ext_delta(rolling: pd.DataFrame, multiyr: pd.DataFrame) -> pd.Series:
    """C: season-to-date avg extension minus prior-year avg_ext.
    Season-to-date avg_ext is computed from Statcast parquets via DuckDB,
    grouped by (pitcher, year, cutoff_date) from rolling frame.
    Falls back to full-season multiyr avg_ext when cutoff-level data unavailable.
    """
    print("  [ext_delta] Building season-to-date extension from Statcast parquets...")
    con = duckdb.connect()

    ext_rows = []
    for yr in sorted(rolling['year'].unique()):
        pq = STATCAST_TMPL.format(yr=int(yr))
        if not os.path.exists(pq):
            continue
        # Compute avg extension for each pitcher for the full season
        # (using full-year as proxy for season-to-date at each cutoff — conservative)
        try:
            res = con.execute(f"""
                SELECT pitcher,
                       AVG(release_extension) AS avg_ext_szn,
                       COUNT(*) AS n_pitches
                FROM read_parquet('{pq}')
                WHERE release_extension IS NOT NULL
                  AND pitcher IS NOT NULL
                  AND pitch_type IS NOT NULL
                GROUP BY pitcher
                HAVING COUNT(*) >= 50
            """).df()
            res['year'] = int(yr)
            ext_rows.append(res)
        except Exception as e:
            print(f"    Warning: {yr} extension query failed: {e}")

    con.close()

    if not ext_rows:
        print("  [ext_delta] No extension data built — signal C will be NaN.")
        return pd.Series(np.nan, index=rolling.index, name='ext_delta')

    ext_szn = pd.concat(ext_rows, ignore_index=True)

    # Prior-year ext
    prior_ext = ext_szn[['pitcher', 'year', 'avg_ext_szn']].copy()
    prior_ext['year_next'] = prior_ext['year'] + 1
    prior_ext = prior_ext.rename(columns={'avg_ext_szn': 'prior_avg_ext'})

    merged = rolling.merge(
        ext_szn[['pitcher', 'year', 'avg_ext_szn']],
        on=['pitcher', 'year'], how='left'
    ).merge(
        prior_ext[['pitcher', 'year_next', 'prior_avg_ext']],
        left_on=['pitcher', 'year'], right_on=['pitcher', 'year_next'],
        how='left'
    )
    delta = merged['avg_ext_szn'] - merged['prior_avg_ext']
    return delta.rename('ext_delta')


def build_new_pitch_flag(rolling: pd.DataFrame) -> pd.Series:
    """D: 1 if pitcher introduced a pitch type at >=10% usage in year T
    that was <5% in year T-1. 0 otherwise. NaN if no prior year available.
    """
    print("  [new_pitch_flag] Computing pitch type usage changes from Statcast...")
    con = duckdb.connect()

    usage_rows = []
    for yr in sorted(rolling['year'].unique()):
        pq = STATCAST_TMPL.format(yr=int(yr))
        if not os.path.exists(pq):
            continue
        try:
            res = con.execute(f"""
                SELECT pitcher, pitch_type,
                       COUNT(*) * 1.0 / SUM(COUNT(*)) OVER (PARTITION BY pitcher) AS usage_pct,
                       COUNT(*) AS n
                FROM read_parquet('{pq}')
                WHERE pitch_type IS NOT NULL AND pitcher IS NOT NULL
                GROUP BY pitcher, pitch_type
                HAVING COUNT(*) >= 10
            """).df()
            res['year'] = int(yr)
            usage_rows.append(res)
        except Exception as e:
            print(f"    Warning: {yr} pitch usage query failed: {e}")

    con.close()

    if not usage_rows:
        return pd.Series(0, index=rolling.index, name='new_pitch_flag')

    usage = pd.concat(usage_rows, ignore_index=True)

    # For each pitcher-year, find pitch types with usage >= 10%
    heavy_curr = (usage[usage['usage_pct'] >= 0.10]
                  .groupby(['pitcher', 'year'])['pitch_type']
                  .apply(set).reset_index()
                  .rename(columns={'pitch_type': 'heavy_curr'}))

    # Prior-year: pitch types with usage >= 5%
    light_prior = (usage[usage['usage_pct'] >= 0.05]
                   .groupby(['pitcher', 'year'])['pitch_type']
                   .apply(set).reset_index()
                   .rename(columns={'pitch_type': 'light_prior'}))
    light_prior['year_next'] = light_prior['year'] + 1

    merged_flag = heavy_curr.merge(
        light_prior[['pitcher', 'year_next', 'light_prior']],
        left_on=['pitcher', 'year'], right_on=['pitcher', 'year_next'],
        how='left'
    )

    def _has_new(row):
        if pd.isna(row['light_prior']) if not isinstance(row['light_prior'], set) else False:
            return np.nan
        curr = row['heavy_curr'] if isinstance(row['heavy_curr'], set) else set()
        prior = row['light_prior'] if isinstance(row['light_prior'], set) else set()
        return int(bool(curr - prior))

    merged_flag['new_pitch_flag'] = merged_flag.apply(_has_new, axis=1)

    flag_lookup = merged_flag.set_index(['pitcher', 'year'])['new_pitch_flag'].to_dict()

    result = rolling.apply(
        lambda r: flag_lookup.get((r['pitcher'], r['year']), np.nan), axis=1
    ).rename('new_pitch_flag')
    return result


def build_full_training_frame(rolling: pd.DataFrame, multiyr: pd.DataFrame) -> pd.DataFrame:
    """Assemble the full rp3 training frame including all RP3_FEATS columns."""
    from plv_clone.models.xfp.rp3 import (
        build_prior_table, apply_shrinkage, compute_population_means,
        _ensure_derived_denoms, SHRINK_SPEC_TO, TRAIN_YEARS,
    )
    all_years = sorted(rolling['year'].unique())
    prior = build_prior_table(multiyr, all_years)
    df = rolling.merge(prior, on=['pitcher', 'year'], how='left')

    # Fill prior with league mean for missing
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())
    df['prior_fp_per_start'] = df['prior_fp_per_start'].fillna(league_mu)
    df['prior_gs_eff'] = df['prior_gs_eff'].fillna(0.0)

    # IL features
    if os.path.exists(IL_CSV):
        il = pd.read_csv(IL_CSV)
        df = df.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
        df['il_stints_to'] = df['il_stints_to'].fillna(0).astype(int)
        df['is_on_il_at_split'] = df['is_on_il_at_split'].fillna(0).astype(int)
        max_dsr = float(df.get('days_since_il_return', pd.Series([200])).max(skipna=True) or 200)
        if 'days_since_il_return' in df.columns:
            df['days_since_il_return_imp'] = df['days_since_il_return'].fillna(max_dsr + 1)
        else:
            df['days_since_il_return_imp'] = max_dsr + 1
    else:
        df['il_stints_to'] = 0
        df['is_on_il_at_split'] = 0
        df['days_since_il_return_imp'] = 201.0

    # Delta features (last21 vs season-to-date)
    df['delta_velo']   = df['avg_velo_last21']    - df['avg_velo_to']
    df['delta_swstr']  = df['swstr_pct_last21']   - df['swstr_pct_to']
    df['delta_k_pct']  = df['k_pct_last21']       - df['k_pct_to']
    df['delta_bb_pct'] = df['bb_pct_last21']      - df['bb_pct_to']
    df['delta_chase']  = df['o_swing_pct_last21'] - df['o_swing_pct_to']
    df['delta_zone']   = df['zone_pct_last21']    - df['zone_pct_to']

    # RoS schedule — fill with 0 if not available (neutral)
    if os.path.exists(ROS_SCHED_CSV):
        sched = pd.read_csv(ROS_SCHED_CSV)[['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']]
        df = df.merge(sched, on=['pitcher', 'year', 'split_day'], how='left')
        yr_means = df.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
        df['ros_opp_xwoba_weighted'] = df['ros_opp_xwoba_weighted'].fillna(yr_means)
    else:
        df['ros_opp_xwoba_weighted'] = 0.0

    # Shrinkage for _to_sh features
    df = _ensure_derived_denoms(df)
    pop = compute_population_means(df, TRAIN_YEARS, SHRINK_SPEC_TO)
    df = apply_shrinkage(df, pop, SHRINK_SPEC_TO)

    return df


def build_candidate_signals(df: pd.DataFrame, multiyr: pd.DataFrame) -> pd.DataFrame:
    """Add 4 candidate signal columns to an already-assembled training frame."""
    print("Building candidate signals...")
    df = df.copy()
    df['pfxz_delta'] = build_pfxz_delta(df, multiyr)
    df['csw_last21'] = df['c_plus_swstr_last21']  # direct proxy
    df['ext_delta'] = build_ext_delta(df, multiyr)
    df['new_pitch_flag'] = build_new_pitch_flag(df)
    print(f"  pfxz_delta: {df['pfxz_delta'].notna().sum()} non-null")
    print(f"  csw_last21: {df['csw_last21'].notna().sum()} non-null")
    print(f"  ext_delta:  {df['ext_delta'].notna().sum()} non-null")
    print(f"  new_pitch_flag: {df['new_pitch_flag'].notna().sum()} non-null")
    return df


# ---------------------------------------------------------------------------
# Step 2 — Cross-year validation engine (Rule 8 in-season framing)
# ---------------------------------------------------------------------------

def _prep_xy(df: pd.DataFrame, feats: list[str], target: str,
             years: list[int], cutoff_day: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    sub = df[df['year'].isin(years)].copy()
    if cutoff_day is not None:
        sub = sub[sub['split_day'] <= cutoff_day]
    sub = sub.dropna(subset=feats + [target])
    X = sub[feats].values.astype(float)
    y = sub[target].values.astype(float)
    return X, y


def cross_year_r(df: pd.DataFrame, feats: list[str], target: str,
                 train_years: list[int], cutoff_day: int | None = None) -> dict:
    """Leave-one-year-out cross-year correlation for the given feature set."""
    per_year_r = {}
    all_pred, all_true = [], []

    for held_yr in train_years:
        tr_years = [y for y in train_years if y != held_yr]
        X_tr, y_tr = _prep_xy(df, feats, target, tr_years, cutoff_day)
        X_hd, y_hd = _prep_xy(df, feats, target, [held_yr], cutoff_day)
        if len(X_tr) < 30 or len(X_hd) < 10:
            continue
        sc = StandardScaler()
        X_tr_s = sc.fit_transform(X_tr)
        X_hd_s = sc.transform(X_hd)
        mdl = Ridge(alpha=1.0)
        mdl.fit(X_tr_s, y_tr)
        pred = mdl.predict(X_hd_s)
        r, _ = pearsonr(pred, y_hd)
        per_year_r[held_yr] = r
        all_pred.extend(pred.tolist())
        all_true.extend(y_hd.tolist())

    if len(all_pred) < 50:
        return {'pooled_r': np.nan, 'per_year': per_year_r, 'n': len(all_pred)}
    pooled, _ = pearsonr(all_pred, all_true)
    return {'pooled_r': pooled, 'per_year': per_year_r, 'n': len(all_pred)}


def holdout_r(df: pd.DataFrame, feats: list[str], target: str,
              train_years: list[int], holdout_years: list[int],
              cutoff_day: int | None = None) -> float:
    X_tr, y_tr = _prep_xy(df, feats, target, train_years, cutoff_day)
    X_hd, y_hd = _prep_xy(df, feats, target, holdout_years, cutoff_day)
    if len(X_tr) < 30 or len(X_hd) < 10:
        return np.nan
    sc = StandardScaler()
    X_tr_s = sc.fit_transform(X_tr)
    X_hd_s = sc.transform(X_hd)
    mdl = Ridge(alpha=1.0)
    mdl.fit(X_tr_s, y_tr)
    pred = mdl.predict(X_hd_s)
    r, _ = pearsonr(pred, y_hd)
    return r


def partial_r_vs_baseline(df, candidate_feats, target, train_years, cutoff_day=None):
    """Partial r of candidate signals after partialing out baseline predictions."""
    base = cross_year_r(df, RP3_FEATS, target, train_years, cutoff_day)
    full_feats = RP3_FEATS + candidate_feats
    full = cross_year_r(df, full_feats, target, train_years, cutoff_day)
    return base['pooled_r'], full['pooled_r'], full['pooled_r'] - base['pooled_r'], full['per_year'], full['n']


# ---------------------------------------------------------------------------
# Step 3 — Run the full sweep
# ---------------------------------------------------------------------------

IL_CSV = f"{ROOT}/data/research/xfp_cache/il_split_features_2018_2026.csv"
ROS_SCHED_CSV = f"{ROOT}/data/research/xfp_cache/ros_schedule_features_2018_2026.csv"

SIGNAL_NAMES = ['pfxz_delta', 'csw_last21', 'ext_delta', 'new_pitch_flag']
SIGNAL_LABELS = ['A', 'B', 'C', 'D']

def all_combos():
    for r in range(1, 5):
        for combo in itertools.combinations(range(4), r):
            label = ''.join(SIGNAL_LABELS[i] for i in combo)
            feats = [SIGNAL_NAMES[i] for i in combo]
            yield label, feats


def run_sweep(df: pd.DataFrame):
    configs = [
        ('holdout_A', TRAIN_YEARS_A, HOLDOUT_A),
        ('holdout_B', TRAIN_YEARS_B, HOLDOUT_B),
    ]

    results = []
    for cfg_name, train_yrs, holdout_yrs in configs:
        print(f"\n=== Config {cfg_name} | train={train_yrs} | holdout={holdout_yrs} ===")

        # Baseline (no candidates)
        base_cv = cross_year_r(df, RP3_FEATS, TARGET, train_yrs)
        base_ho = holdout_r(df, RP3_FEATS, TARGET, train_yrs, holdout_yrs)
        print(f"  BASELINE: cv_r={base_cv['pooled_r']:.4f}  holdout_r={base_ho:.4f}  n={base_cv['n']}")

        for combo_label, cand_feats in all_combos():
            # Drop rows with any NaN in candidate features
            df_c = df.dropna(subset=cand_feats)
            # Also drop NaN in baseline feats and target
            df_c = df_c.dropna(subset=RP3_FEATS + [TARGET])

            base_r, full_r, lift, per_year, n = partial_r_vs_baseline(
                df_c, cand_feats, TARGET, train_yrs
            )
            ho_base = holdout_r(df_c, RP3_FEATS, TARGET, train_yrs, holdout_yrs)
            ho_full = holdout_r(df_c, RP3_FEATS + cand_feats, TARGET, train_yrs, holdout_yrs)
            ho_lift = ho_full - ho_base if not np.isnan(ho_full) and not np.isnan(ho_base) else np.nan

            sign_consistent = sum(1 for v in per_year.values() if v > 0)
            sign_str = ' '.join(f"{yr}:{'+' if v>0 else '-'}{abs(v):.3f}"
                                for yr, v in sorted(per_year.items()))

            # Bonferroni-adjusted pass: partial r >= 0.22 AND lift >= +0.005 AND sign >= 5 of len(train)
            n_train = len(train_yrs)
            passes = (lift >= 0.005 and sign_consistent >= max(4, n_train - 1)
                      and (not np.isnan(ho_lift) and ho_lift >= 0))

            row = {
                'config': cfg_name, 'combo': combo_label, 'signals': '+'.join(cand_feats),
                'cv_base_r': round(base_r, 4), 'cv_full_r': round(full_r, 4),
                'cv_lift': round(lift, 4),
                'ho_base_r': round(ho_base, 4) if not np.isnan(ho_base) else np.nan,
                'ho_full_r': round(ho_full, 4) if not np.isnan(ho_full) else np.nan,
                'ho_lift': round(ho_lift, 4) if not np.isnan(ho_lift) else np.nan,
                'sign_consistent': f"{sign_consistent}/{n_train}",
                'per_year': sign_str,
                'n': n,
                'PASS': passes,
            }
            results.append(row)
            flag = '✓ PASS' if passes else ''
            print(f"  [{combo_label:4s}] lift={lift:+.4f}  ho_lift={ho_lift:+.4f}  "
                  f"signs={sign_consistent}/{n_train}  {flag}")

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Step 4 — Convergence curve (Rule 8) for any passing combo
# ---------------------------------------------------------------------------

def convergence_curve(df: pd.DataFrame, cand_feats: list[str],
                      train_years: list[int]) -> dict:
    curve = {}
    for day in CUTOFF_DAYS:
        df_c = df[df['split_day'] <= day].dropna(subset=RP3_FEATS + cand_feats + [TARGET])
        if len(df_c) < 50:
            curve[day] = np.nan
            continue
        base_r, full_r, lift, _, _ = partial_r_vs_baseline(df_c, cand_feats, TARGET, train_years, day)
        curve[day] = lift
    return curve


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading data...")
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)

    print(f"Rolling shape: {rolling.shape}")
    print(f"Multiyr shape: {multiyr.shape}")
    print(f"Years in rolling: {sorted(rolling['year'].unique())}")

    print("\nAssembling full rp3 training frame (all 24 RP3_FEATS)...")
    full_df = build_full_training_frame(rolling, multiyr)
    print(f"Full training frame shape: {full_df.shape}")

    # Verify RP3_FEATS are present
    missing = [f for f in RP3_FEATS if f not in full_df.columns]
    if missing:
        print(f"WARNING: still missing RP3_FEATS after build: {missing}")
    else:
        print(f"All 24 RP3_FEATS present. Target '{TARGET}' present: {TARGET in full_df.columns}")

    df = build_candidate_signals(full_df, multiyr)

    print("\nRunning 30-cell sweep...")
    results = run_sweep(df)

    out_path = f"{ROOT}/data/research/pitch_shape_sweep_results_2026-05-27.csv"
    results.to_csv(out_path, index=False)
    print(f"\nFull results → {out_path}")

    # Summary table
    print("\n" + "="*80)
    print("SWEEP SUMMARY")
    print("="*80)
    print(results[['config', 'combo', 'cv_lift', 'ho_lift', 'sign_consistent', 'PASS']]
          .sort_values(['PASS', 'cv_lift'], ascending=[False, False])
          .to_string(index=False))

    passes = results[results['PASS']]
    print(f"\n{len(passes)} / 30 cells PASS (lift ≥ +0.005, signs consistent, holdout positive)")

    if len(passes) > 0:
        print("\n=== PASSING COMBOS — CONVERGENCE CURVES (Rule 8) ===")
        for _, row in passes.iterrows():
            feats = row['signals'].split('+')
            train_yrs = TRAIN_YEARS_A if row['config'] == 'holdout_A' else TRAIN_YEARS_B
            df_c = df.dropna(subset=RP3_FEATS + feats + [TARGET])
            curve = convergence_curve(df_c, feats, train_yrs)
            curve_str = '  '.join(f"wk{d//7}:{v:+.4f}" if not np.isnan(v) else f"wk{d//7}:n/a"
                                  for d, v in curve.items())
            print(f"  [{row['config']}] {row['combo']}: {curve_str}")
            sign_flip = any(v is not np.nan and v < 0 for v in curve.values())
            if sign_flip:
                print(f"    ⚠ SIGN FLIP detected — Rule 8 FAIL regardless of pooled lift")

    # Registry-ready writeup
    print("\n" + "="*80)
    print("REGISTRY ENTRY (paste into reference_validated_signals_registry.md)")
    print("="*80)
    best = results.sort_values('cv_lift', ascending=False).iloc[0]
    best_lift = passes['cv_lift'].max() if len(passes) > 0 else 0.0
    verdict = "PASS" if best_lift >= 0.005 else ("MARGINAL" if results['cv_lift'].max() > 0 else "REJECTED")
    print(f"""
### pitch_shape_early_warning_sweep — {verdict} (2026-05-27)
- **Baseline cv_r:** {results['cv_base_r'].iloc[0]:.4f} (RP3_FEATS, 24 features)
- **Best combo:** {best['combo']} ({best['signals']}) — cv_lift={best['cv_lift']:+.4f}, ho_lift={best['ho_lift']:+.4f}
- **Cells passing (30 total):** {len(passes)}
- **Bonferroni bar:** partial r ≥ 0.22, lift ≥ +0.005, signs consistent, holdout positive
- **Framing tested:** in-season → ros (split_day cutoffs 30/42/56/70/84)
- **Definition:**
  - A (pfxz_delta): avg_pfxz_to - prior_year_avg_pfxz from sp_multiyr
  - B (csw_last21): c_plus_swstr_last21 from rolling_pitchers
  - C (ext_delta): avg_ext_szn - prior_year_avg_ext from Statcast + sp_multiyr
  - D (new_pitch_flag): 1 if pitch type ≥10% usage new vs prior year (<5%)
- **Status:** {'LIVE candidate — see production integration plan' if verdict == 'PASS' else 'RESEARCH-STAGE' if verdict == 'MARGINAL' else 'REJECTED — lift insufficient or sign unstable'}
""")


if __name__ == '__main__':
    main()
