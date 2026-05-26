"""validate_pitch_mix_changes.py — within-season pitch mix change signals for rp3.

Tests 5 candidates above full RP3_FEATS (Rule 9):
  1. pitch_entropy_to       — Shannon entropy of pitch type distribution season-to-date
  2. delta_pitch_entropy    — entropy(L21d) - entropy(season-to-date); positive = more varied recently
  3. primary_pitch_pct_to   — fraction of pitches that are the most-used pitch type (season-to-date)
  4. delta_primary_pitch_pct — change in primary pitch fraction (L21d minus season-to-date)
  5. n_pitch_types_to       — count of distinct pitch types thrown ≥5% of pitches season-to-date

Computes features from raw statcast_{year}.parquet via DuckDB, one query per
unique (year, cutoff_date) pair. Joins back to rolling on (pitcher, year, split_day).

Prior rejection context: pitch_entropy_prior (prior-year full-season entropy) was
rejected 2026-05-23 — that's DIFFERENT from this. These are within-season deltas.

Run:
    python scripts/xfp/validate_pitch_mix_changes.py
"""
from __future__ import annotations
import sys
import time
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import numpy as np
import pandas as pd
import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))

from scripts.xfp._rp3_validation_harness import prep_rolling, evaluate_candidate, print_report
from plv_clone.models.xfp.rp3 import RP3_FEATS, TRAIN_YEARS

CACHE_DIR = ROOT / 'data' / 'research' / 'xfp_cache'
ROLLING_CSV = CACHE_DIR / 'rolling_pitchers_2018_2026.csv'

CANDIDATES = [
    'pitch_entropy_to',
    'delta_pitch_entropy',
    'primary_pitch_pct_to',
    'delta_primary_pitch_pct',
    'n_pitch_types_to',
]

# Minimum pitches for a pitch type to count toward the ≥5% threshold (n_pitch_types_to)
MIN_PCT_THRESHOLD = 0.05
# Minimum total pitches to compute reliable entropy (otherwise fill with mean)
MIN_PITCHES_SEASON = 30
MIN_PITCHES_L21 = 10


def shannon_entropy(probs):
    """Shannon entropy from an array of proportions (already summing to 1)."""
    probs = np.array(probs, dtype=float)
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log(probs)))


def compute_pitch_mix_features(rolling_raw: pd.DataFrame) -> pd.DataFrame:
    """Compute per-(pitcher, year, split_day) pitch mix features from statcast parquet.

    Strategy:
      - Get all unique (year, cutoff_date) pairs from rolling
      - For each pair, query statcast_{year}.parquet with game_date <= cutoff_date
        AND game_date >= (cutoff_date - 21 days for L21d window)
      - Aggregate pitch_type counts per pitcher
      - Compute entropy, primary pct, n_pitch_types for [season-to-date] and [L21d]
      - Compute delta features
    """
    pairs = (rolling_raw[['year', 'split_day', 'cutoff_date']]
             .drop_duplicates()
             .sort_values(['year', 'split_day']))

    results = []
    con = duckdb.connect()

    for _, row in pairs.iterrows():
        year = int(row['year'])
        split_day = int(row['split_day'])
        cutoff_date = str(row['cutoff_date'])
        parq = CACHE_DIR / f'statcast_{year}.parquet'
        if not parq.exists():
            print(f'  [WARN] Missing {parq.name}, skipping')
            continue

        # L21d start date
        cutoff_ts = pd.Timestamp(cutoff_date)
        l21_start = str((cutoff_ts - pd.Timedelta(days=21)).date())

        print(f'  Computing year={year} split_day={split_day} cutoff={cutoff_date}', end='', flush=True)
        t0 = time.time()

        try:
            # Season-to-date pitch type counts per pitcher
            q_season = f"""
                SELECT
                    pitcher,
                    pitch_type,
                    COUNT(*) AS n_pitches
                FROM read_parquet('{str(parq).replace(chr(92), '/')}')
                WHERE game_date <= '{cutoff_date}'
                  AND pitch_type IS NOT NULL
                  AND pitch_type != ''
                  AND pitch_type != 'PO'
                  AND pitch_type != 'IN'
                GROUP BY pitcher, pitch_type
            """
            df_season = con.execute(q_season).df()

            # L21d pitch type counts per pitcher
            q_l21 = f"""
                SELECT
                    pitcher,
                    pitch_type,
                    COUNT(*) AS n_pitches_l21
                FROM read_parquet('{str(parq).replace(chr(92), '/')}')
                WHERE game_date <= '{cutoff_date}'
                  AND game_date >= '{l21_start}'
                  AND pitch_type IS NOT NULL
                  AND pitch_type != ''
                  AND pitch_type != 'PO'
                  AND pitch_type != 'IN'
                GROUP BY pitcher, pitch_type
            """
            df_l21 = con.execute(q_l21).df()

        except Exception as e:
            print(f' ERROR: {e}')
            continue

        elapsed = time.time() - t0
        print(f' ({elapsed:.1f}s)')

        # Compute per-pitcher season-to-date features
        if df_season.empty:
            continue

        season_rows = []
        for pitcher, grp in df_season.groupby('pitcher'):
            total = grp['n_pitches'].sum()
            if total < MIN_PITCHES_SEASON:
                continue
            probs = (grp['n_pitches'] / total).values
            entropy = shannon_entropy(probs)
            primary_pct = float(probs.max())
            n_types = int((probs >= MIN_PCT_THRESHOLD).sum())
            season_rows.append({
                'pitcher': int(pitcher),
                'pitch_entropy_to': entropy,
                'primary_pitch_pct_to': primary_pct,
                'n_pitch_types_to': n_types,
                'total_pitches_season': total,
            })
        df_season_feats = pd.DataFrame(season_rows)

        # Compute per-pitcher L21d features
        l21_rows = []
        if not df_l21.empty:
            for pitcher, grp in df_l21.groupby('pitcher'):
                total_l21 = grp['n_pitches_l21'].sum()
                if total_l21 < MIN_PITCHES_L21:
                    continue
                probs_l21 = (grp['n_pitches_l21'] / total_l21).values
                entropy_l21 = shannon_entropy(probs_l21)
                primary_pct_l21 = float(probs_l21.max())
                l21_rows.append({
                    'pitcher': int(pitcher),
                    'pitch_entropy_l21': entropy_l21,
                    'primary_pitch_pct_l21': primary_pct_l21,
                    'total_pitches_l21': total_l21,
                })
        df_l21_feats = pd.DataFrame(l21_rows) if l21_rows else pd.DataFrame(
            columns=['pitcher', 'pitch_entropy_l21', 'primary_pitch_pct_l21', 'total_pitches_l21'])

        # Merge and compute deltas
        if df_season_feats.empty:
            continue
        merged = df_season_feats.merge(df_l21_feats, on='pitcher', how='left')
        merged['delta_pitch_entropy'] = merged['pitch_entropy_l21'] - merged['pitch_entropy_to']
        merged['delta_primary_pitch_pct'] = merged['primary_pitch_pct_l21'] - merged['primary_pitch_pct_to']

        merged['year'] = year
        merged['split_day'] = split_day
        results.append(merged)

    con.close()

    if not results:
        raise RuntimeError('No pitch mix features computed — check parquet paths.')

    all_feats = pd.concat(results, ignore_index=True)
    return all_feats


def print_distribution_stats(rolling: pd.DataFrame, col: str) -> None:
    vals = rolling[col].dropna()
    if vals.empty:
        print(f'  {col}: NO DATA')
        return
    p10, p90 = np.percentile(vals, [10, 90])
    print(f'  {col}: n={len(vals)}  mean={vals.mean():.4f}  std={vals.std():.4f}  '
          f'p10={p10:.4f}  p90={p90:.4f}  '
          f'min={vals.min():.4f}  max={vals.max():.4f}  '
          f'nan_frac={rolling[col].isna().mean():.3f}')


def convergence_by_split_day(rolling: pd.DataFrame, candidate_col: str) -> None:
    """Print lift broken down by split_day for a candidate feature."""
    from plv_clone.models.xfp.rp3 import cross_year_eval, TRAIN_YEARS
    TARGET = 'ros_fp_per_start'
    EVAL_GS_MIN = 2
    ROS_GS_MIN = 5

    print(f'\n  Convergence curve for {candidate_col} (lift by split_day):')
    df = rolling.copy()
    df[candidate_col] = df[candidate_col].fillna(df.groupby(['year','split_day'])[candidate_col].transform('mean'))
    df = df.dropna(subset=RP3_FEATS + [candidate_col, TARGET])

    for sd in sorted(df['split_day'].unique()):
        sub = df[df['split_day'] == sd]
        if len(sub) < 50:
            continue
        _, ov_base = cross_year_eval(sub, RP3_FEATS)
        _, ov_full = cross_year_eval(sub, RP3_FEATS + [candidate_col])
        lift = ov_full['r'] - ov_base['r']
        print(f'    split_day={sd:3d}: baseline_r={ov_base["r"]:.4f}  full_r={ov_full["r"]:.4f}  lift={lift:+.4f}  n={ov_full["n"]}')


def bundle_test(rolling: pd.DataFrame, best_candidates: list[str]) -> None:
    """Test bundle of multiple candidates together vs full RP3_FEATS baseline."""
    from plv_clone.models.xfp.rp3 import cross_year_eval
    if not best_candidates:
        print('\n  No bundle to test (no candidates passed individual gate).')
        return
    # Fill NaN with per-(year, split_day) mean
    df = rolling.copy()
    for col in best_candidates:
        if col in df.columns:
            df[col] = df[col].fillna(df.groupby(['year', 'split_day'])[col].transform('mean'))
    py_base, ov_base = cross_year_eval(df, RP3_FEATS)
    py_full, ov_full = cross_year_eval(df, RP3_FEATS + best_candidates)
    lift = ov_full['r'] - ov_base['r']
    print(f'\n=== BUNDLE TEST: {best_candidates} ===')
    print(f'  Baseline (RP3_FEATS, {len(RP3_FEATS)} feats): r={ov_base["r"]}')
    print(f'  Full bundle ({len(RP3_FEATS) + len(best_candidates)} feats): r={ov_full["r"]}')
    print(f'  LIFT = {lift:+.4f}')
    print(f'  Per-year:')
    for y in sorted(py_full.keys()):
        if y in py_base:
            d = py_full[y]['r'] - py_base[y]['r']
            print(f'    {y}: {d:+.4f}')


def main():
    t_start = time.time()
    print('=== validate_pitch_mix_changes.py ===')
    print(f'Rule 9 baseline: full RP3_FEATS ({len(RP3_FEATS)} features)')
    print(f'Candidates: {CANDIDATES}\n')

    # Step 1: prep rolling (standard harness)
    print('--- Step 1: prep_rolling() ---')
    rolling = prep_rolling()

    # Step 1b: attach ros_opp_xwoba_weighted (it's in RP3_FEATS, needed for baseline eval)
    from plv_clone.models.xfp.rp3 import ROS_SCHED_CSV
    if ROS_SCHED_CSV.exists():
        sched_xw = pd.read_csv(ROS_SCHED_CSV)[['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']]
        rolling = rolling.merge(sched_xw, on=['pitcher', 'year', 'split_day'], how='left')
        year_means = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
        rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(year_means)
        rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(
            rolling['ros_opp_xwoba_weighted'].mean())
        print(f'  ros_opp_xwoba_weighted joined OK')
    else:
        raise FileNotFoundError(f'Missing {ROS_SCHED_CSV}')

    print(f'  Rolling shape: {rolling.shape}')

    # Step 2: compute pitch mix features from statcast parquets
    print('\n--- Step 2: compute pitch mix features from statcast ---')
    rolling_raw = pd.read_csv(ROLLING_CSV)
    pitch_mix = compute_pitch_mix_features(rolling_raw)
    print(f'  Pitch mix features shape: {pitch_mix.shape}')
    print(f'  Unique (year, split_day) pairs in pitch_mix: {pitch_mix[["year","split_day"]].drop_duplicates().shape[0]}')

    # Step 3: join back to rolling on (pitcher, year, split_day)
    print('\n--- Step 3: join pitch mix features to rolling ---')
    join_cols = ['pitcher', 'year', 'split_day'] + CANDIDATES + ['pitch_entropy_l21', 'primary_pitch_pct_l21']
    join_cols = [c for c in join_cols if c in pitch_mix.columns]
    rolling = rolling.merge(pitch_mix[join_cols], on=['pitcher', 'year', 'split_day'], how='left')
    print(f'  Rolling shape after join: {rolling.shape}')
    for col in CANDIDATES:
        n_non_null = rolling[col].notna().sum() if col in rolling.columns else 0
        print(f'  {col}: {n_non_null}/{len(rolling)} non-null ({n_non_null/len(rolling):.1%})')

    # Step 4: distribution stats
    print('\n--- Step 4: Distribution statistics ---')
    for col in CANDIDATES:
        if col in rolling.columns:
            print_distribution_stats(rolling, col)

    # Step 5: evaluate each candidate individually
    print('\n--- Step 5: Individual candidate evaluation (Rule 9) ---')
    results = {}
    for col in CANDIDATES:
        if col not in rolling.columns:
            print(f'  SKIP {col} — not in rolling (computation failed?)')
            continue
        # Fill NaN with per-(year, split_day) mean before eval
        fill_val = None  # evaluate_candidate handles fill via fill_value param;
                         # but we also need group-mean for NaN rows that have no
                         # same-(year,split_day) mean, so fill first manually.
        df_eval = rolling.copy()
        group_mean = df_eval.groupby(['year', 'split_day'])[col].transform('mean')
        df_eval[col] = df_eval[col].fillna(group_mean)
        # Any remaining NaN (e.g. whole split has no data) → global train mean
        train_mask = df_eval['year'].isin(TRAIN_YEARS)
        global_mean = float(df_eval.loc[train_mask, col].mean(skipna=True))
        df_eval[col] = df_eval[col].fillna(global_mean)

        result = evaluate_candidate(df_eval, col, label=col)
        results[col] = result
        print_report(result, gate=0.005)

    # Step 6: convergence curve for best candidate
    print('\n--- Step 6: Convergence curve for best candidate ---')
    if results:
        best_col = max(results, key=lambda c: results[c]['lift'])
        print(f'  Best candidate: {best_col} (lift={results[best_col]["lift"]:+.4f})')
        # Prep rolling with group-mean fill for the best col
        df_curve = rolling.copy()
        if best_col in df_curve.columns:
            group_mean = df_curve.groupby(['year', 'split_day'])[best_col].transform('mean')
            df_curve[best_col] = df_curve[best_col].fillna(group_mean)
            train_mask = df_curve['year'].isin(TRAIN_YEARS)
            global_mean = float(df_curve.loc[train_mask, best_col].mean(skipna=True))
            df_curve[best_col] = df_curve[best_col].fillna(global_mean)
            convergence_by_split_day(df_curve, best_col)

    # Step 7: bundle of any candidates that show positive lift
    print('\n--- Step 7: Bundle test ---')
    positive_lift_cols = [c for c in results if results[c]['lift'] > 0]
    gate_pass_cols = [c for c in results if results[c]['lift'] >= 0.005
                      and results[c]['sign_match_years'] >= 5
                      and (results[c]['holdout_lift'] or 0) > 0]
    print(f'  Candidates with positive lift: {positive_lift_cols}')
    print(f'  Candidates passing all 3 gates: {gate_pass_cols}')

    df_bundle = rolling.copy()
    bundle_cols = positive_lift_cols if positive_lift_cols else []
    for col in bundle_cols:
        if col in df_bundle.columns:
            group_mean = df_bundle.groupby(['year', 'split_day'])[col].transform('mean')
            df_bundle[col] = df_bundle[col].fillna(group_mean)
            train_mask = df_bundle['year'].isin(TRAIN_YEARS)
            global_mean = float(df_bundle.loc[train_mask, col].mean(skipna=True))
            df_bundle[col] = df_bundle[col].fillna(global_mean)
    bundle_test(df_bundle, bundle_cols)

    # Step 8: summary table
    print('\n--- Step 8: Summary ---')
    print(f'  {"Candidate":<26}  {"Lift":>7}  {"Sign":>5}  {"Holdout":>8}  {"Gate?"}')
    print(f'  {"-"*26}  {"-"*7}  {"-"*5}  {"-"*8}  {"-"*6}')
    for col in CANDIDATES:
        if col not in results:
            print(f'  {col:<26}  {"N/A":>7}  {"N/A":>5}  {"N/A":>8}  SKIP')
            continue
        r = results[col]
        sign_str = f'{r["sign_match_years"]}/{r["n_total_years"]}'
        holdout_str = f'{r["holdout_lift"]:+.4f}' if r['holdout_lift'] is not None else 'N/A'
        gate = ('PASS' if r['lift'] >= 0.005 and r['sign_match_years'] >= 5
                and (r['holdout_lift'] or 0) > 0 else 'FAIL')
        print(f'  {col:<26}  {r["lift"]:>+7.4f}  {sign_str:>5}  {holdout_str:>8}  {gate}')

    print(f'\n  Baseline r (RP3_FEATS, 24 feats): {list(results.values())[0]["r_baseline"] if results else "N/A"}')
    print(f'\n=== Total elapsed: {time.time()-t_start:.1f}s ===')

    # Step 9: Interpretation
    print('\n--- Step 9: Interpretation ---')
    any_pass = bool(gate_pass_cols)
    print(f'  Gate-passing candidates: {gate_pass_cols if gate_pass_cols else "NONE"}')
    print()
    if any_pass:
        print('  INTERPRETATION: At least one pitch mix change signal PASSES the 3-gate bar.')
        print('  These are within-season signals distinct from the rejected pitch_entropy_prior')
        print('  (which was prior-year full-season entropy). Consider promoting the passing')
        print('  candidate(s) to the validated registry via /validate-feature.')
    else:
        print('  INTERPRETATION: No pitch mix change signal clears the +0.005 lift gate')
        print('  above the full 24-feature RP3_FEATS baseline. This is consistent with the')
        print('  existing delta_velo/delta_swstr/delta_k_pct/delta_bb_pct/delta_chase/')
        print('  delta_zone features already capturing the actionable within-season signal.')
        print('  Pitch mix entropy and primary pitch usage add orthogonal but low-variance')
        print('  signal that the existing rate-based drift features likely absorb.')
        print()
        print('  Note: If highest lift is 0.001-0.004 range, pitch type diversity may have')
        print('  modest collinearity with swstr_pct and k_pct (pitchers who add a new pitch')
        print('  typically also see swstr improvements captured by delta_swstr).')


if __name__ == '__main__':
    main()
