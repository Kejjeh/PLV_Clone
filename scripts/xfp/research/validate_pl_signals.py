# Pre-registered: see data/research/validation_runs/pl_untested_signals_sweep_2026-05-27.md
"""
Validate 6 PL-roundup-derived SP signals (singletons + 2 bundles + 1 interaction
+ 1 subset test) against full 24-feature RP3_FEATS baseline. 28 total cells.

Signals:
  F = fps_pct_to                (first-pitch strike rate, season-to-date proxy)
  P = putaway_pct_to            (two-strike K rate)
  T = ttop_penalty_to           (3rd-TTO xwOBA - 1st-TTO xwOBA)
  O = out_pitch_whiff_delta     (per-pitcher modal breaking-ball whiff% YoY delta)
  R = velo_recovery_slope       (post-IL velo recovery slope)
  X = pitch_trim_flag           (inverse of new_pitch_flag)
"""
from __future__ import annotations
import os
import warnings
import duckdb
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

# Reuse the shared training-frame builder from the pitch-shape sweep.
import sys
sys.path.insert(0, os.path.dirname(__file__))
from validate_pitch_shape_early_warning import (
    build_full_training_frame, RP3_FEATS, TARGET,
    TRAIN_YEARS_A, TRAIN_YEARS_B, HOLDOUT_A, HOLDOUT_B,
    cross_year_r, holdout_r, partial_r_vs_baseline,
    convergence_curve, CUTOFF_DAYS,
    ROOT, ROLLING_CSV, MULTIYR_CSV, STATCAST_TMPL,
)

warnings.filterwarnings("ignore")

FPS_CSV = f"{ROOT}/data/research/xfp_cache/fp_strike_2015_2026.csv"

# ---------------------------------------------------------------------------
# Signal builders
# ---------------------------------------------------------------------------

def build_fps_pct(df: pd.DataFrame) -> pd.Series:
    """F: First-pitch strike rate. Reuse cached full-year value as season-to-date proxy."""
    fps = pd.read_csv(FPS_CSV)
    merged = df.merge(fps.rename(columns={'fp_strike_pct': 'fps_pct_to'}),
                      on=['pitcher', 'year'], how='left')
    return merged['fps_pct_to']


def build_putaway_pct(df: pd.DataFrame) -> pd.Series:
    """P: Two-strike K rate. = (Ks where strikes was 2 entering the pitch that ended the PA) / (PAs that reached 2 strikes).
    Computed full-year as proxy for season-to-date.
    """
    print("  [putaway] Computing two-strike K rate from Statcast...")
    con = duckdb.connect()
    rows = []
    for yr in sorted(df['year'].unique()):
        pq = STATCAST_TMPL.format(yr=int(yr))
        if not os.path.exists(pq):
            continue
        try:
            # A PA "reached 2 strikes" if ANY pitch in that PA had strikes==2 (count at start of pitch).
            # The K count = PAs that ended in 'strikeout' event AND reached 2 strikes (all Ks reach 2 strikes by definition).
            res = con.execute(f"""
                WITH pa_2k AS (
                    SELECT pitcher, game_pk, at_bat_number,
                           MAX(CASE WHEN strikes = 2 THEN 1 ELSE 0 END) AS reached_2k,
                           MAX(CASE WHEN events = 'strikeout' THEN 1 ELSE 0 END) AS is_k
                    FROM read_parquet('{pq}')
                    WHERE pitcher IS NOT NULL
                    GROUP BY pitcher, game_pk, at_bat_number
                )
                SELECT pitcher,
                       SUM(is_k) * 1.0 / NULLIF(SUM(reached_2k), 0) AS putaway_pct_to,
                       SUM(reached_2k) AS n_2k_pa
                FROM pa_2k
                GROUP BY pitcher
                HAVING SUM(reached_2k) >= 20
            """).df()
            res['year'] = int(yr)
            rows.append(res)
        except Exception as e:
            print(f"    Warning: {yr} putaway query failed: {e}")
    con.close()
    if not rows:
        return pd.Series(np.nan, index=df.index, name='putaway_pct_to')
    putaway = pd.concat(rows, ignore_index=True)
    merged = df.merge(putaway[['pitcher', 'year', 'putaway_pct_to']],
                      on=['pitcher', 'year'], how='left')
    return merged['putaway_pct_to']


def build_ttop_penalty(df: pd.DataFrame) -> pd.Series:
    """T: Times-Through-Order penalty. 3rd-TTO xwOBA-allowed minus 1st-TTO xwOBA-allowed.
    TTO assigned per PA via cumulative distinct batter count within game.
    """
    print("  [ttop] Computing TTO penalty from Statcast...")
    con = duckdb.connect()
    rows = []
    for yr in sorted(df['year'].unique()):
        pq = STATCAST_TMPL.format(yr=int(yr))
        if not os.path.exists(pq):
            continue
        try:
            # Per (pitcher, game_pk), assign TTO bucket per PA via DENSE_RANK of distinct
            # batters in batting order (using at_bat_number ordering). 1-9 = TTO 1,
            # 10-18 = TTO 2, 19-27 = TTO 3, 28+ = TTO 3+ (rare).
            # Simpler proxy: TTO = ceil(distinct_pa_count / 9) per game-pitcher.
            res = con.execute(f"""
                WITH pa_level AS (
                    SELECT pitcher, game_pk, at_bat_number, batter,
                           estimated_woba_using_speedangle AS xwoba_pa
                    FROM read_parquet('{pq}')
                    WHERE pitcher IS NOT NULL
                      AND events IS NOT NULL AND events != ''
                      AND estimated_woba_using_speedangle IS NOT NULL
                    GROUP BY pitcher, game_pk, at_bat_number, batter, xwoba_pa
                ),
                pa_with_tto AS (
                    SELECT pitcher, game_pk, at_bat_number, batter, xwoba_pa,
                           CAST(CEIL(ROW_NUMBER() OVER (PARTITION BY pitcher, game_pk
                                                        ORDER BY at_bat_number) / 9.0) AS INT) AS tto
                    FROM pa_level
                )
                SELECT pitcher,
                       AVG(CASE WHEN tto = 3 THEN xwoba_pa END) AS xwoba_3rd,
                       AVG(CASE WHEN tto = 1 THEN xwoba_pa END) AS xwoba_1st,
                       SUM(CASE WHEN tto = 3 THEN 1 ELSE 0 END) AS n_3rd,
                       SUM(CASE WHEN tto = 1 THEN 1 ELSE 0 END) AS n_1st
                FROM pa_with_tto
                GROUP BY pitcher
                HAVING SUM(CASE WHEN tto = 3 THEN 1 ELSE 0 END) >= 15
                   AND SUM(CASE WHEN tto = 1 THEN 1 ELSE 0 END) >= 30
            """).df()
            res['ttop_penalty_to'] = res['xwoba_3rd'] - res['xwoba_1st']
            res['year'] = int(yr)
            rows.append(res[['pitcher', 'year', 'ttop_penalty_to']])
        except Exception as e:
            print(f"    Warning: {yr} ttop query failed: {e}")
    con.close()
    if not rows:
        return pd.Series(np.nan, index=df.index, name='ttop_penalty_to')
    ttop = pd.concat(rows, ignore_index=True)
    merged = df.merge(ttop, on=['pitcher', 'year'], how='left')
    return merged['ttop_penalty_to']


def build_out_pitch_whiff_delta(df: pd.DataFrame) -> pd.Series:
    """O: Modal breaking ball whiff% in year T minus year T-1.
    Breaking ball = {SL, CU, KC, ST, SV}. Modal = most-thrown pitch type in that bucket
    for that pitcher-year (min 50 thrown).
    """
    print("  [out_pitch_whiff] Computing breaking-ball whiff delta from Statcast...")
    BB_TYPES = ('SL', 'CU', 'KC', 'ST', 'SV')
    con = duckdb.connect()
    rows = []
    for yr in sorted(df['year'].unique()):
        pq = STATCAST_TMPL.format(yr=int(yr))
        if not os.path.exists(pq):
            continue
        try:
            res = con.execute(f"""
                WITH bb AS (
                    SELECT pitcher, pitch_type,
                           SUM(CASE WHEN description = 'swinging_strike' THEN 1 ELSE 0 END) AS whiffs,
                           SUM(CASE WHEN description IN ('swinging_strike','foul','foul_tip','hit_into_play',
                                                          'foul_bunt','missed_bunt') THEN 1 ELSE 0 END) AS swings,
                           COUNT(*) AS n
                    FROM read_parquet('{pq}')
                    WHERE pitch_type IN {BB_TYPES}
                      AND pitcher IS NOT NULL
                    GROUP BY pitcher, pitch_type
                    HAVING COUNT(*) >= 50
                ),
                ranked AS (
                    SELECT pitcher, pitch_type, whiffs, swings, n,
                           ROW_NUMBER() OVER (PARTITION BY pitcher ORDER BY n DESC) AS rk
                    FROM bb
                )
                SELECT pitcher, pitch_type AS modal_bb,
                       whiffs * 1.0 / NULLIF(swings, 0) AS whiff_rate_bb
                FROM ranked
                WHERE rk = 1
            """).df()
            res['year'] = int(yr)
            rows.append(res)
        except Exception as e:
            print(f"    Warning: {yr} out_pitch_whiff query failed: {e}")
    con.close()
    if not rows:
        return pd.Series(np.nan, index=df.index, name='out_pitch_whiff_delta')
    bb = pd.concat(rows, ignore_index=True)
    # YoY delta: current year whiff_rate_bb minus prior-year whiff_rate_bb (matched on
    # same modal_bb pitcher; if pitcher changed modal BB, still compare current rate to prior rate).
    prior = bb[['pitcher', 'year', 'whiff_rate_bb']].copy()
    prior['year_next'] = prior['year'] + 1
    prior = prior.rename(columns={'whiff_rate_bb': 'prior_whiff_rate_bb'})
    merged = df.merge(bb[['pitcher', 'year', 'whiff_rate_bb']], on=['pitcher', 'year'], how='left') \
               .merge(prior[['pitcher', 'year_next', 'prior_whiff_rate_bb']],
                      left_on=['pitcher', 'year'], right_on=['pitcher', 'year_next'], how='left')
    delta = merged['whiff_rate_bb'] - merged['prior_whiff_rate_bb']
    return delta.rename('out_pitch_whiff_delta')


def build_velo_recovery_slope(df: pd.DataFrame) -> pd.Series:
    """R: For IL returners (is_on_il_at_split==0 but days_since_il_return finite and < 200),
    proxy slope as (current avg_velo_last21 - avg_velo_to) / days_since_il_return_imp.
    Positive = velo trending UP relative to season-to-date (good).
    NaN for non-IL-returners.
    """
    print("  [velo_recovery_slope] Computing post-IL velocity recovery proxy...")
    # We're operating per-row (each row is a (pitcher, year, split_day) cutoff snapshot).
    # Slope proxy: short-window velo minus season-to-date velo, normalized by recency.
    is_returner = (df.get('is_on_il_at_split', 0) == 0) & \
                  (df.get('days_since_il_return_imp', 999) < 60) & \
                  (df.get('il_stints_to', 0) >= 1)
    velo_delta = df['avg_velo_last21'] - df['avg_velo_to']
    days = df.get('days_since_il_return_imp', pd.Series(60.0, index=df.index)).clip(lower=7)
    slope = velo_delta / days
    result = pd.Series(np.nan, index=df.index)
    result[is_returner] = slope[is_returner]
    return result.rename('velo_recovery_slope')


def build_pitch_trim_flag(df: pd.DataFrame) -> pd.Series:
    """X: 1 if pitcher had a pitch type at >=10% usage in year T-1 that is <5% in year T.
    Inverse of new_pitch_flag.
    """
    print("  [pitch_trim_flag] Computing dropped-pitch flag from Statcast...")
    con = duckdb.connect()
    usage_rows = []
    for yr in sorted(df['year'].unique()):
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
        return pd.Series(0, index=df.index, name='pitch_trim_flag')
    usage = pd.concat(usage_rows, ignore_index=True)
    heavy_prior = (usage[usage['usage_pct'] >= 0.10]
                   .groupby(['pitcher', 'year'])['pitch_type']
                   .apply(set).reset_index()
                   .rename(columns={'pitch_type': 'heavy_prior'}))
    heavy_prior['year_next'] = heavy_prior['year'] + 1
    light_curr = (usage[usage['usage_pct'] >= 0.05]
                  .groupby(['pitcher', 'year'])['pitch_type']
                  .apply(set).reset_index()
                  .rename(columns={'pitch_type': 'light_curr'}))
    merged_flag = light_curr.merge(
        heavy_prior[['pitcher', 'year_next', 'heavy_prior']],
        left_on=['pitcher', 'year'], right_on=['pitcher', 'year_next'], how='left'
    )

    def _has_dropped(row):
        prior = row['heavy_prior'] if isinstance(row['heavy_prior'], set) else None
        curr = row['light_curr'] if isinstance(row['light_curr'], set) else set()
        if prior is None:
            return np.nan
        # Pitches in prior at >=10% that are NOT in current at >=5% = dropped
        return int(bool(prior - curr))

    merged_flag['pitch_trim_flag'] = merged_flag.apply(_has_dropped, axis=1)
    flag_lookup = merged_flag.set_index(['pitcher', 'year'])['pitch_trim_flag'].to_dict()
    result = df.apply(lambda r: flag_lookup.get((r['pitcher'], r['year']), np.nan), axis=1)
    return result.rename('pitch_trim_flag')


def build_all_signals(df: pd.DataFrame) -> pd.DataFrame:
    print("Building 6 PL-derived signals...")
    df = df.copy()
    df['fps_pct_to']             = build_fps_pct(df)
    df['putaway_pct_to']         = build_putaway_pct(df)
    df['ttop_penalty_to']        = build_ttop_penalty(df)
    df['out_pitch_whiff_delta']  = build_out_pitch_whiff_delta(df)
    df['velo_recovery_slope']    = build_velo_recovery_slope(df)
    df['pitch_trim_flag']        = build_pitch_trim_flag(df)
    # R interaction
    df['velo_recovery_x_il']     = df['velo_recovery_slope'].fillna(0) * df['is_on_il_at_split']

    for c in ['fps_pct_to', 'putaway_pct_to', 'ttop_penalty_to',
              'out_pitch_whiff_delta', 'velo_recovery_slope', 'pitch_trim_flag',
              'velo_recovery_x_il']:
        n = df[c].notna().sum()
        print(f"  {c}: {n} non-null ({n/len(df)*100:.1f}%)")
    return df


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

CELLS = [
    ('F',     ['fps_pct_to']),
    ('P',     ['putaway_pct_to']),
    ('T',     ['ttop_penalty_to']),
    ('O',     ['out_pitch_whiff_delta']),
    ('R',     ['velo_recovery_slope']),
    ('X',     ['pitch_trim_flag']),
    ('FP',    ['fps_pct_to', 'putaway_pct_to']),
    ('TOX',   ['ttop_penalty_to', 'out_pitch_whiff_delta', 'pitch_trim_flag']),
    ('FPT',   ['fps_pct_to', 'putaway_pct_to', 'ttop_penalty_to']),
    ('FPTO',  ['fps_pct_to', 'putaway_pct_to', 'ttop_penalty_to', 'out_pitch_whiff_delta']),
    ('FPTOX', ['fps_pct_to', 'putaway_pct_to', 'ttop_penalty_to',
               'out_pitch_whiff_delta', 'pitch_trim_flag']),
    ('ALL',   ['fps_pct_to', 'putaway_pct_to', 'ttop_penalty_to',
               'out_pitch_whiff_delta', 'velo_recovery_slope', 'pitch_trim_flag']),
    ('R_int', ['velo_recovery_x_il']),
]

def run_sweep(df: pd.DataFrame):
    configs = [
        ('holdout_A', TRAIN_YEARS_A, HOLDOUT_A),
        ('holdout_B', TRAIN_YEARS_B, HOLDOUT_B),
    ]
    results = []
    for cfg_name, train_yrs, holdout_yrs in configs:
        print(f"\n=== Config {cfg_name} | train={train_yrs} | holdout={holdout_yrs} ===")
        base_cv = cross_year_r(df, RP3_FEATS, TARGET, train_yrs)
        base_ho = holdout_r(df, RP3_FEATS, TARGET, train_yrs, holdout_yrs)
        print(f"  BASELINE: cv_r={base_cv['pooled_r']:.4f}  holdout_r={base_ho:.4f}  n={base_cv['n']}")

        for cell_label, cand_feats in CELLS:
            df_c = df.dropna(subset=cand_feats + RP3_FEATS + [TARGET])
            if len(df_c) < 200:
                print(f"  [{cell_label:6s}] SKIPPED — n={len(df_c)} after NaN drop")
                continue
            base_r, full_r, lift, per_year, n = partial_r_vs_baseline(
                df_c, cand_feats, TARGET, train_yrs
            )
            ho_base = holdout_r(df_c, RP3_FEATS, TARGET, train_yrs, holdout_yrs)
            ho_full = holdout_r(df_c, RP3_FEATS + cand_feats, TARGET, train_yrs, holdout_yrs)
            ho_lift = ho_full - ho_base if not (np.isnan(ho_full) or np.isnan(ho_base)) else np.nan
            sign_consistent = sum(1 for v in per_year.values() if v > 0)
            n_train = len(train_yrs)
            sign_str = ' '.join(f"{yr}:{'+' if v>0 else '-'}{abs(v):.3f}"
                                for yr, v in sorted(per_year.items()))
            passes = (lift >= 0.005 and sign_consistent >= max(4, n_train - 1)
                      and (not np.isnan(ho_lift) and ho_lift >= 0))
            row = {
                'config': cfg_name, 'cell': cell_label, 'signals': '+'.join(cand_feats),
                'cv_base_r': round(base_r, 4), 'cv_full_r': round(full_r, 4),
                'cv_lift': round(lift, 4),
                'ho_base_r': round(ho_base, 4) if not np.isnan(ho_base) else np.nan,
                'ho_full_r': round(ho_full, 4) if not np.isnan(ho_full) else np.nan,
                'ho_lift': round(ho_lift, 4) if not np.isnan(ho_lift) else np.nan,
                'sign_consistent': f"{sign_consistent}/{n_train}",
                'per_year': sign_str, 'n': n, 'PASS': passes,
            }
            results.append(row)
            flag = '✓ PASS' if passes else ''
            print(f"  [{cell_label:6s}] lift={lift:+.4f}  ho_lift={ho_lift:+.4f}  "
                  f"signs={sign_consistent}/{n_train}  n={n}  {flag}")
    return pd.DataFrame(results)


def run_il_subset_test(df: pd.DataFrame):
    """R_il_subset: standalone velo_recovery_slope on the IL-returner subset only."""
    print("\n=== R_il_subset (IL returners only) ===")
    sub = df[df['velo_recovery_slope'].notna()].copy()
    print(f"  Subset size: {len(sub)} rows ({sub['velo_recovery_slope'].notna().sum()} non-null)")
    if len(sub) < 100:
        print("  SKIPPED — N too small for subset analysis")
        return {}
    cfg = [('holdout_A', TRAIN_YEARS_A, HOLDOUT_A), ('holdout_B', TRAIN_YEARS_B, HOLDOUT_B)]
    out = {}
    for cfg_name, train_yrs, holdout_yrs in cfg:
        base = cross_year_r(sub, RP3_FEATS, TARGET, train_yrs)
        full = cross_year_r(sub, RP3_FEATS + ['velo_recovery_slope'], TARGET, train_yrs)
        ho_base = holdout_r(sub, RP3_FEATS, TARGET, train_yrs, holdout_yrs)
        ho_full = holdout_r(sub, RP3_FEATS + ['velo_recovery_slope'], TARGET, train_yrs, holdout_yrs)
        lift = full['pooled_r'] - base['pooled_r']
        ho_lift = ho_full - ho_base if not (np.isnan(ho_full) or np.isnan(ho_base)) else np.nan
        print(f"  [{cfg_name}] cv_lift={lift:+.4f}  ho_lift={ho_lift:+.4f}  n_train={base['n']}")
        out[cfg_name] = {'cv_lift': lift, 'ho_lift': ho_lift}
    return out


def main():
    print("Loading data + building full RP3 training frame...")
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    full_df = build_full_training_frame(rolling, multiyr)
    print(f"Full training frame shape: {full_df.shape}")

    df = build_all_signals(full_df)

    print("\nRunning 26-cell sweep (13 cells × 2 configs)...")
    results = run_sweep(df)

    print("\nRunning R IL-subset test...")
    il_subset = run_il_subset_test(df)

    out_path = f"{ROOT}/data/research/pl_signals_sweep_results_2026-05-27.csv"
    results.to_csv(out_path, index=False)
    print(f"\nFull results → {out_path}")

    print("\n" + "="*80)
    print("SWEEP SUMMARY")
    print("="*80)
    print(results[['config', 'cell', 'cv_lift', 'ho_lift', 'sign_consistent', 'n', 'PASS']]
          .sort_values(['PASS', 'cv_lift'], ascending=[False, False])
          .to_string(index=False))

    passes = results[results['PASS']]
    print(f"\n{len(passes)} / {len(results)} cells PASS (lift >= +0.005, signs consistent, holdout positive)")

    # Convergence curve for any passing cell
    if len(passes) > 0:
        print("\n=== CONVERGENCE CURVES for PASSING cells ===")
        for _, row in passes.iterrows():
            feats = row['signals'].split('+')
            train_yrs = TRAIN_YEARS_A if row['config'] == 'holdout_A' else TRAIN_YEARS_B
            df_c = df.dropna(subset=RP3_FEATS + feats + [TARGET])
            curve = convergence_curve(df_c, feats, train_yrs)
            curve_str = '  '.join(f"d{d}:{v:+.4f}" if not np.isnan(v) else f"d{d}:n/a"
                                  for d, v in curve.items())
            print(f"  [{row['config']}] {row['cell']}: {curve_str}")
            sign_flip = any((not np.isnan(v)) and v < 0 for v in curve.values())
            if sign_flip:
                print(f"    ⚠ SIGN FLIP — Rule 8 FAIL")

    # Per-signal verdict
    print("\n" + "="*80)
    print("PER-SIGNAL VERDICT")
    print("="*80)
    singleton_cells = ['F', 'P', 'T', 'O', 'R', 'X']
    for cell in singleton_cells:
        rows = results[results['cell'] == cell]
        if rows.empty:
            print(f"  {cell}: NO DATA")
            continue
        best_cv = rows['cv_lift'].max()
        best_ho = rows.loc[rows['cv_lift'].idxmax(), 'ho_lift']
        any_pass = rows['PASS'].any()
        if any_pass:
            verdict = "PASS"
        elif best_cv >= 0.005 and best_ho >= 0:
            verdict = "PASS (clean)"
        elif best_cv > 0 and best_cv < 0.005:
            verdict = "MARGINAL"
        else:
            verdict = "REJECTED"
        print(f"  {cell}: best cv_lift={best_cv:+.4f}  best ho_lift={best_ho:+.4f}  → {verdict}")


if __name__ == '__main__':
    main()
