"""validate_trajectory_slopes.py — Research: do within-season trajectory slopes
add lift above the full RP3_FEATS baseline?

For each (pitcher, year), fit a linear slope across split_days for key metrics.
Hypothesis: slope captures sustained improvement better than a one-lag delta.

Steps:
  1. Build slope features per (pitcher, year) via linregress across split_days
  2. Test each slope individually vs full RP3_FEATS baseline (Rule 9)
  3. Test a bundle of any slopes that clear the +0.005 gate
  4. Test slope × split_day interaction for the best slope
  5. Convergence curve: lift by split_day subgroup for best slope

Run: python scripts/xfp/validate_trajectory_slopes.py
"""
from __future__ import annotations
import sys
import warnings
warnings.filterwarnings('ignore')
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import linregress

# Repo root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))

from scripts.xfp._rp3_validation_harness import (
    prep_rolling, evaluate_candidate, print_report,
)
from plv_clone.models.xfp.rp3 import (
    RP3_FEATS, cross_year_eval, ROS_SCHED_CSV, TRAIN_YEARS,
)

# ---------------------------------------------------------------------------
# 1. Prep rolling (production data-prep)
# ---------------------------------------------------------------------------
print("=== validate_trajectory_slopes.py ===")
print("\n[1] Prepping rolling data...")
rolling = prep_rolling()
print(f"    rolling shape: {rolling.shape}")

# Attach ros_opp_xwoba_weighted (required for RP3_FEATS baseline)
sched_xw = pd.read_csv(ROS_SCHED_CSV)[['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']]
rolling = rolling.merge(sched_xw, on=['pitcher', 'year', 'split_day'], how='left')
year_means = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(year_means)
rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(
    rolling['ros_opp_xwoba_weighted'].mean()
)
print(f"    ros_opp_xwoba_weighted attached. Missing: {rolling['ros_opp_xwoba_weighted'].isna().sum()}")

# ---------------------------------------------------------------------------
# 2. Compute slope features per (pitcher, year)
# ---------------------------------------------------------------------------
print("\n[2] Computing trajectory slopes...")

SLOPE_METRICS = [
    'k_pct_to',
    'swstr_pct_to',
    'avg_velo_to',
    'o_swing_pct_to',
    'fp_per_start_to',
]

def compute_slopes(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Fit linear slope across split_days per (pitcher, year) for each metric.

    Returns a DataFrame indexed by (pitcher, year) with slope_<metric> columns.
    Pitchers with only 1 split_day obs → NaN slope (filled with 0 downstream).
    """
    records = []
    for (pitcher, year), grp in df.groupby(['pitcher', 'year']):
        row = {'pitcher': pitcher, 'year': year}
        days = grp['split_day'].values
        for m in metrics:
            vals = grp[m].values
            # Drop NaN pairs
            mask = ~np.isnan(vals)
            if mask.sum() >= 2:
                slope = linregress(days[mask], vals[mask]).slope
            else:
                slope = np.nan
            row[f'slope_{m}'] = slope
        records.append(row)
    return pd.DataFrame(records)

slopes_df = compute_slopes(rolling, SLOPE_METRICS)
print(f"    Slope table shape: {slopes_df.shape}")

# Summary: how many (pitcher, year) pairs have >= 2 split_days?
n_pairs = rolling.groupby(['pitcher', 'year'])['split_day'].count()
print(f"    Pairs with 1 split_day: {(n_pairs == 1).sum()}, >=2: {(n_pairs >= 2).sum()}")
for m in SLOPE_METRICS:
    col = f'slope_{m}'
    n_nan = slopes_df[col].isna().sum()
    print(f"    {col}: {n_nan} NaN ({n_nan/len(slopes_df):.1%})")

# Join slopes back to rolling (broadcast to all split_day rows per pitcher/year)
rolling = rolling.merge(slopes_df, on=['pitcher', 'year'], how='left')

# Fill NaN with 0 (no trend signal for 1-obs pitchers)
slope_cols = [f'slope_{m}' for m in SLOPE_METRICS]
for c in slope_cols:
    rolling[c] = rolling[c].fillna(0.0)

print(f"\n    Slope columns added: {slope_cols}")

# ---------------------------------------------------------------------------
# 3. Verify baseline r matches expected ~0.5654
# ---------------------------------------------------------------------------
print("\n[3] Verifying baseline RP3_FEATS r...")
_, ov_base = cross_year_eval(rolling, RP3_FEATS)
print(f"    Baseline r = {ov_base['r']:.4f}  n = {ov_base['n']}")
expected = 0.5654
delta_from_expected = abs(ov_base['r'] - expected)
if delta_from_expected > 0.010:
    print(f"    WARNING: baseline deviates from expected {expected} by {delta_from_expected:.4f}")
else:
    print(f"    OK (within 0.010 of expected {expected})")

# ---------------------------------------------------------------------------
# 4. Test each slope individually
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print("[4] Individual slope tests vs full RP3_FEATS baseline")
print("="*60)

results = {}
for col in slope_cols:
    result = evaluate_candidate(rolling, col, fill_value=0.0, label=col)
    results[col] = result
    print_report(result)

# ---------------------------------------------------------------------------
# 5. Summary table
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print("[5] Summary table (all slopes)")
print("="*60)
print(f"{'Candidate':<25} {'Baseline r':>10} {'Full r':>8} {'Lift':>8} {'Sign':>6} {'HO lift':>8} {'Gate':>6}")
print("-"*75)
GATE = 0.005
passers = []
for col, r in sorted(results.items(), key=lambda x: -x[1]['lift']):
    ho = r['holdout_lift']
    ho_str = f"{ho:+.4f}" if ho is not None else "  N/A"
    gate_str = "PASS" if (r['lift'] >= GATE and r['sign_match_years'] >= 5 and (ho or 0) > 0) else "FAIL"
    if gate_str == "PASS":
        passers.append(col)
    print(f"{col:<25} {r['r_baseline']:>10.4f} {r['r_full']:>8.4f} {r['lift']:>+8.4f} "
          f"{r['sign_match_years']}/{r['n_total_years']:>2} {ho_str:>8} {gate_str:>6}")

# ---------------------------------------------------------------------------
# 6. Bundle test (if any individual slopes pass)
# ---------------------------------------------------------------------------
if passers:
    print("\n" + "="*60)
    print(f"[6] Bundle test: {passers}")
    print("="*60)
    bundle_cols = passers
    bundle_feats = RP3_FEATS + bundle_cols
    py_base, ov_base2 = cross_year_eval(rolling, RP3_FEATS)
    py_bun, ov_bun = cross_year_eval(rolling, bundle_feats)
    lift_bun = ov_bun['r'] - ov_base2['r']
    print(f"  Baseline r: {ov_base2['r']:.4f}")
    print(f"  Bundle  r: {ov_bun['r']:.4f}")
    print(f"  Bundle lift: {lift_bun:+.4f}  (gate: >= +{GATE:.3f})")
    print(f"\n  Per-year:")
    for y in sorted(py_bun.keys()):
        d = py_bun[y]['r'] - py_base.get(y, {}).get('r', np.nan) if y in py_base else np.nan
        print(f"    {y}: base={py_base.get(y, {}).get('r', 'N/A'):.4f}  "
              f"bundle={py_bun[y]['r']:.4f}  lift={d:+.4f}")
else:
    print("\n[6] Bundle test: skipped (no individual slopes cleared all 3 gates)")

# ---------------------------------------------------------------------------
# 7. Interaction test: best slope × split_day
# ---------------------------------------------------------------------------
# Pick the best slope by raw lift regardless of gate
best_col = max(results, key=lambda c: results[c]['lift'])
best_lift = results[best_col]['lift']
print("\n" + "="*60)
print(f"[7] Interaction test: {best_col} × split_day")
print("="*60)
interact_col = f'{best_col}_x_split'
rolling[interact_col] = rolling[best_col] * rolling['split_day']
interact_result = evaluate_candidate(rolling, interact_col, fill_value=0.0, label=interact_col)
print_report(interact_result)

# ---------------------------------------------------------------------------
# 8. Convergence curve: lift by split_day subgroup for best slope
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print(f"[8] Convergence curve: {best_col} lift by split_day")
print("="*60)

from plv_clone.models.xfp.rp3 import EVAL_GS_MIN, ROS_GS_MIN, TARGET
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

split_days = sorted(rolling['split_day'].dropna().unique())
print(f"  Split days available: {split_days}")
print(f"  {'split_day':>10} {'n_rows':>8} {'base_r':>8} {'full_r':>8} {'lift':>8}")
print(f"  {'-'*50}")

for sd in split_days:
    sub = rolling[rolling['split_day'] == sd].copy()
    sub = sub.dropna(subset=RP3_FEATS + [best_col, TARGET])
    sub = sub[(sub['gs_to'] >= EVAL_GS_MIN) & (sub['ros_gs'] >= ROS_GS_MIN) & (sub['year'] != 2020)]
    if len(sub) < 50:
        print(f"  {sd:>10} {len(sub):>8}  (skip — < 50 rows)")
        continue

    # LOO cross-year on this split_day subset
    preds_base, acts_base = [], []
    preds_full, acts_full = [], []
    for held in TRAIN_YEARS:
        tr = sub[sub['year'] != held]
        te = sub[sub['year'] == held]
        if len(tr) < 20 or len(te) < 5:
            continue
        for feats, preds_list in [(RP3_FEATS, preds_base), (RP3_FEATS + [best_col], preds_full)]:
            pipe = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            tr2 = tr.dropna(subset=feats + [TARGET])
            te2 = te.dropna(subset=feats + [TARGET])
            if len(tr2) < 20 or len(te2) < 3:
                continue
            pipe.fit(tr2[feats].values, tr2[TARGET].values)
            preds_list.extend(pipe.predict(te2[feats].values).tolist())
            if preds_list is preds_base:
                acts_base.extend(te2[TARGET].tolist())
            else:
                acts_full.extend(te2[TARGET].tolist())

    if not preds_base or not preds_full:
        print(f"  {sd:>10} {len(sub):>8}  (skip — insufficient folds)")
        continue

    r_base = float(np.corrcoef(preds_base, acts_base)[0, 1]) if len(preds_base) > 1 else np.nan
    r_full = float(np.corrcoef(preds_full, acts_full)[0, 1]) if len(preds_full) > 1 else np.nan
    lift_sd = r_full - r_base if not (np.isnan(r_base) or np.isnan(r_full)) else np.nan
    lift_str = f"{lift_sd:+.4f}" if not np.isnan(lift_sd) else "  N/A"
    print(f"  {sd:>10} {len(sub):>8} {r_base:>8.4f} {r_full:>8.4f} {lift_str:>8}")

# ---------------------------------------------------------------------------
# 9. Final interpretation
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print("[9] Interpretation")
print("="*60)
print(f"  Baseline RP3_FEATS r = {ov_base['r']:.4f}")
print(f"  Slopes tested: {slope_cols}")
print()
for col, r in sorted(results.items(), key=lambda x: -x[1]['lift']):
    ho = r['holdout_lift']
    all_pass = r['lift'] >= GATE and r['sign_match_years'] >= 5 and (ho or 0) > 0
    verdict = "PROMOTE candidate" if all_pass else (
        "marginal — review" if r['lift'] > 0 else "no lift / absorbed"
    )
    print(f"  {col:<25}: lift={r['lift']:+.4f}  sign={r['sign_match_years']}/{r['n_total_years']}  "
          f"ho={ho:+.4f if ho is not None else '  N/A'}  → {verdict}")
print()
print("  Key delta features already in RP3_FEATS (L21d − season-to-date):")
delta_cols = ['delta_velo', 'delta_swstr', 'delta_k_pct', 'delta_bb_pct', 'delta_chase', 'delta_zone']
print(f"    {delta_cols}")
print("  If slope lifts are small, it suggests the delta features absorb")
print("  most of the within-season trajectory signal.")
print("\nDone.")
