"""validate_age_curve_interactions.py

Tests whether age-curve × performance interaction terms add lift to the rp3 SP
model above the full RP3_FEATS baseline (Rule 9).

career_stage is constructed here as career_year: number of qualifying MLB SP
seasons (≥5 GS) the pitcher has accumulated in the multiyr data up to and
including the current year. This mirrors what a validated 'career_stage' feature
would look like — the multiyr data starts in 2015 so career_year counts from
that floor for pre-2015 veterans.

Rules:
  - Rule 9: full RP3_FEATS baseline always.
  - Training years: 2018, 2019, 2021, 2022, 2023.
  - Holdout: 2024, 2025 (off-limits for tuning).
  - Pass gate: lift ≥ +0.005, sign ≥ 5/7 training years, holdout lift > 0.
  - Do NOT modify RP3_FEATS or any production file.
"""
from __future__ import annotations
import sys
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

# Harness imports
_root = __import__('pathlib').Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root / 'src'))
sys.path.insert(0, str(_root / 'scripts' / 'xfp'))
from _rp3_validation_harness import (
    prep_rolling, evaluate_candidate,
)


def print_report(result: dict, gate: float = 0.005) -> None:
    """Local version — avoids non-ASCII unicode chars that break cp1252 console."""
    print(f"\n=== Candidate: {result['candidate']} ===")
    print(f"  Baseline (RP3_FEATS, 24 feats): r={result['r_baseline']} n={result['n_baseline']}")
    print(f"  Full     (+ candidate, 25 feats): r={result['r_full']} n={result['n_full']}")
    print(f"  LIFT = {result['lift']:+.4f}  (gate: >= +{gate:.3f})")
    print(f"\n  Per-year lift (full - baseline):")
    for y, d in result['per_year_lift'].items():
        marker = '+' if d > 0 else '-'
        print(f"    {y}: {d:+.4f}  {marker}")
    print(f"\n  Sign consistency: {result['sign_match_years']}/{result['n_total_years']} years positive")
    if result['holdout_lift'] is not None:
        print(f"  Holdout (2024-2025) avg lift: {result['holdout_lift']:+.4f}")
    print(f"\n  Gates:")
    print(f"    (a) Lift >= +{gate:.3f}? {'PASS' if result['lift'] >= gate else 'FAIL/MARGINAL'} ({result['lift']:+.4f})")
    print(f"    (b) Sign >= 5 of 7?      {'PASS' if result['sign_match_years'] >= 5 else 'FAIL'} ({result['sign_match_years']}/{result['n_total_years']})")
    if result['holdout_lift'] is not None:
        ho_pass = result['holdout_lift'] > 0
        print(f"    (c) Holdout sign +?     {'PASS' if ho_pass else 'FAIL'} ({result['holdout_lift']:+.4f})")
from plv_clone.models.xfp.rp3 import (
    MULTIYR_CSV, ROS_SCHED_CSV, cross_year_eval, RP3_FEATS,
)

# ── 1. Prep base rolling DataFrame ──────────────────────────────────────────
print("=" * 70)
print("STEP 1: prep_rolling()")
rolling = prep_rolling()
print(f"  rolling shape: {rolling.shape}")

# ── 2. Attach ros_opp_xwoba_weighted (production feature, in RP3_FEATS) ──────
print("\nSTEP 2: attach ros_opp_xwoba_weighted")
if ROS_SCHED_CSV.exists():
    sched_xw = pd.read_csv(ROS_SCHED_CSV)[
        ['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']
    ]
    rolling = rolling.merge(sched_xw, on=['pitcher', 'year', 'split_day'], how='left')
    year_means = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
    rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(year_means)
    rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(
        rolling['ros_opp_xwoba_weighted'].mean())
    print(f"  ros_opp_xwoba_weighted attached, missing filled with year mean")
else:
    raise FileNotFoundError(f"Missing {ROS_SCHED_CSV} — run build_ros_schedule_features.py")

# ── 3. Verify baseline r ─────────────────────────────────────────────────────
print("\nSTEP 3: baseline cross_year_eval on full RP3_FEATS")
py_base, ov_base = cross_year_eval(rolling, RP3_FEATS)
print(f"  Baseline r = {ov_base['r']:.4f}  n={ov_base['n']}")
for y, d in sorted(py_base.items()):
    print(f"    {y}: r={d['r']:.4f}  n={d['n']}")

# ── 4. Build career_stage ────────────────────────────────────────────────────
print("\nSTEP 4: build career_stage from multiyr (career_year = qualifying SP seasons)")
multiyr = pd.read_csv(MULTIYR_CSV)
# career_year: cumulative qualifying seasons (≥5 GS) per pitcher ordered by year
career_df = (
    multiyr[multiyr['gs'] >= 5]
    .sort_values(['pitcher', 'year'])
    .copy()
)
career_df['career_year'] = career_df.groupby('pitcher').cumcount() + 1
# We use the career_year AT each year (so a pitcher gets their experience for that season)
career_map = career_df[['pitcher', 'year', 'career_year']].copy()

# Merge into rolling (join on pitcher + year)
rolling = rolling.merge(career_map, on=['pitcher', 'year'], how='left')
# Rookies / sub-5GS years get career_year=0
rolling['career_year'] = rolling['career_year'].fillna(0).astype(int)

# Rename to career_stage for clarity
rolling = rolling.rename(columns={'career_year': 'career_stage'})

print("\n  career_stage distribution:")
desc = rolling['career_stage'].describe()
for k in ['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']:
    print(f"    {k}: {desc[k]:.2f}")

pct_33 = float(rolling['career_stage'].quantile(0.33))
pct_67 = float(rolling['career_stage'].quantile(0.67))
print(f"  33rd pct: {pct_33:.1f}   67th pct: {pct_67:.1f}")

vc = rolling['career_stage'].value_counts().sort_index()
print("  value counts (career_stage):")
for v, c in vc.items():
    print(f"    {v}: {c}")

# ── 5. Compute all interaction features ─────────────────────────────────────
print("\nSTEP 5: compute interaction features")

rolling['career_stage_x_delta_swstr']     = rolling['career_stage'] * rolling['delta_swstr']
rolling['career_stage_x_delta_velo']      = rolling['career_stage'] * rolling['delta_velo']
rolling['career_stage_x_swstr_pct_to_sh'] = rolling['career_stage'] * rolling['swstr_pct_to_sh']
rolling['career_stage_x_fp_per_start_to'] = rolling['career_stage'] * rolling['fp_per_start_to']

# recency_gap = last21 FP - cumulative FP (positive = hot recently)
rolling['recency_gap'] = rolling['fp_per_start_last21'] - rolling['fp_per_start_to']
rolling['career_stage_x_recency_gap']    = rolling['career_stage'] * rolling['recency_gap']

# is_young = career_stage at or below 33rd percentile
rolling['is_young'] = (rolling['career_stage'] <= pct_33).astype(int)
rolling['is_young_x_delta_swstr']        = rolling['is_young'] * rolling['delta_swstr']

CANDIDATES = [
    ('career_stage_x_delta_swstr',     0.0),
    ('career_stage_x_delta_velo',      0.0),
    ('career_stage_x_swstr_pct_to_sh', None),
    ('career_stage_x_fp_per_start_to', None),
    ('career_stage_x_recency_gap',     0.0),
    ('is_young',                       0),
    ('is_young_x_delta_swstr',         0.0),
]

# ── 6. Individual candidate evaluation ───────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 6: individual candidate evaluation (Rule 9 baseline)")
results = {}
for col, fill in CANDIDATES:
    res = evaluate_candidate(rolling, col, fill_value=fill, label=col)
    print_report(res)
    results[col] = res

# ── 7. Summary table ─────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY TABLE — all candidates vs full RP3_FEATS baseline")
print(f"  Baseline r = {ov_base['r']:.4f}")
print(f"{'Candidate':<38}  {'Lift':>7}  {'Sign':>6}  {'Holdout':>8}  {'PASS?'}")
for col, _ in CANDIDATES:
    r = results[col]
    lift   = r['lift']
    sign   = f"{r['sign_match_years']}/{r['n_total_years']}"
    ho     = f"{r['holdout_lift']:+.4f}" if r['holdout_lift'] is not None else "  N/A  "
    passed = (lift >= 0.005 and r['sign_match_years'] >= 5
              and (r['holdout_lift'] is None or r['holdout_lift'] > 0))
    print(f"  {col:<38}  {lift:>+7.4f}  {sign:>6}  {ho:>8}  {'PASS' if passed else 'FAIL'}")

# ── 8. Bundle test: top 2-3 interactions together ───────────────────────────
print("\n" + "=" * 70)
print("STEP 8: bundle tests")

# Bundle A: stage × delta_swstr + stage × delta_velo
bundle_a = ['career_stage_x_delta_swstr', 'career_stage_x_delta_velo']
for col in bundle_a:
    rolling[col] = rolling[col].fillna(0.0)
py_ba, ov_ba = cross_year_eval(rolling, RP3_FEATS + bundle_a)
lift_ba = ov_ba['r'] - ov_base['r']
print(f"\nBundle A ({', '.join(bundle_a)}):")
print(f"  r = {ov_ba['r']:.4f}  lift = {lift_ba:+.4f}")

# Bundle B: stage × delta_swstr + is_young_x_delta_swstr
bundle_b = ['career_stage_x_delta_swstr', 'is_young_x_delta_swstr']
for col in bundle_b:
    rolling[col] = rolling[col].fillna(0.0)
py_bb, ov_bb = cross_year_eval(rolling, RP3_FEATS + bundle_b)
lift_bb = ov_bb['r'] - ov_base['r']
print(f"\nBundle B ({', '.join(bundle_b)}):")
print(f"  r = {ov_bb['r']:.4f}  lift = {lift_bb:+.4f}")

# Bundle C: all 5 continuous interactions
bundle_c = [
    'career_stage_x_delta_swstr',
    'career_stage_x_delta_velo',
    'career_stage_x_swstr_pct_to_sh',
    'career_stage_x_fp_per_start_to',
    'career_stage_x_recency_gap',
]
for col in bundle_c:
    rolling[col] = rolling[col].fillna(0.0)
py_bc, ov_bc = cross_year_eval(rolling, RP3_FEATS + bundle_c)
lift_bc = ov_bc['r'] - ov_base['r']
print(f"\nBundle C (all 5 continuous interactions):")
print(f"  r = {ov_bc['r']:.4f}  lift = {lift_bc:+.4f}")

# ── 9. Best candidate: convergence curve (lift by split_day) ─────────────────
# Find best candidate by lift
best_col = max(results, key=lambda c: results[c]['lift'])
best_res = results[best_col]
print("\n" + "=" * 70)
print(f"STEP 9: convergence curve for best candidate = {best_col}")
print(f"  (lift = {best_res['lift']:+.4f})")

from plv_clone.models.xfp.rp3 import EVAL_GS_MIN, ROS_GS_MIN, TARGET
df_eval = rolling.dropna(subset=RP3_FEATS + [best_col, TARGET]).copy()
df_eval = df_eval[
    (df_eval['gs_to'] >= EVAL_GS_MIN) &
    (df_eval['ros_gs'] >= ROS_GS_MIN) &
    (df_eval['year'] != 2020)
].copy()

split_days = sorted(df_eval['split_day'].unique())
print(f"\n  Convergence by split_day:")
print(f"  {'split_day':>10}  {'r_base':>7}  {'r_full':>7}  {'lift':>7}  {'n':>5}")

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

for sd in split_days:
    sub = df_eval[df_eval['split_day'] == sd]
    if len(sub) < 30:
        continue
    # LOO across training years (2018,2019,2021,2022,2023,2024,2025) within this split
    all_train_years = [y for y in [2018,2019,2021,2022,2023,2024,2025]
                       if y in sub['year'].values]
    preds_base, preds_full, acts = [], [], []
    for held in all_train_years:
        tr = sub[sub['year'] != held]
        te = sub[sub['year'] == held]
        if len(tr) < 20 or len(te) < 5:
            continue
        # baseline
        pipe_b = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,40), cv=5))])
        pipe_b.fit(tr[RP3_FEATS].values, tr[TARGET].values)
        pb = pipe_b.predict(te[RP3_FEATS].values)
        # full
        feats_full = RP3_FEATS + [best_col]
        pipe_f = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,40), cv=5))])
        pipe_f.fit(tr[feats_full].values, tr[TARGET].values)
        pf = pipe_f.predict(te[feats_full].values)
        preds_base.extend(pb.tolist())
        preds_full.extend(pf.tolist())
        acts.extend(te[TARGET].tolist())
    if len(acts) < 10:
        continue
    r_b = float(np.corrcoef(preds_base, acts)[0,1])
    r_f = float(np.corrcoef(preds_full, acts)[0,1])
    print(f"  {sd:>10}  {r_b:>7.4f}  {r_f:>7.4f}  {r_f - r_b:>+7.4f}  {len(acts):>5}")

# ── 10. Stratified sanity check ──────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 10: stratified sanity check")
print("  Does delta_swstr > 0 predict higher ros_fp_per_start differently for young vs vet?")

df_san = rolling.dropna(subset=['is_young', 'delta_swstr', 'ros_fp_per_start']).copy()
df_san = df_san[
    (df_san['gs_to'] >= EVAL_GS_MIN) &
    (df_san['ros_gs'] >= ROS_GS_MIN) &
    (df_san['year'] != 2020)
].copy()

for group_name, mask in [
    ('is_young=1, delta_swstr>0 (young improving)',    (df_san['is_young']==1) & (df_san['delta_swstr']>0)),
    ('is_young=1, delta_swstr≤0 (young NOT improving)',(df_san['is_young']==1) & (df_san['delta_swstr']<=0)),
    ('is_young=0, delta_swstr>0 (vet improving)',      (df_san['is_young']==0) & (df_san['delta_swstr']>0)),
    ('is_young=0, delta_swstr≤0 (vet NOT improving)',  (df_san['is_young']==0) & (df_san['delta_swstr']<=0)),
]:
    sub = df_san[mask]
    if len(sub) == 0:
        continue
    m = sub['ros_fp_per_start'].mean()
    med = sub['ros_fp_per_start'].median()
    print(f"  {group_name}")
    print(f"    n={len(sub):4d}  mean={m:+.3f}  median={med:+.3f}")

# Also check for career_stage x delta_swstr correlation with target
corr_ix = df_san['career_stage_x_delta_swstr'].corr(df_san['ros_fp_per_start'])
corr_cs = df_san['career_stage'].corr(df_san['ros_fp_per_start'])
corr_ds = df_san['delta_swstr'].corr(df_san['ros_fp_per_start'])
print(f"\n  Raw correlations with ros_fp_per_start:")
print(f"    career_stage alone:             {corr_cs:+.4f}")
print(f"    delta_swstr alone:              {corr_ds:+.4f}")
print(f"    career_stage_x_delta_swstr:     {corr_ix:+.4f}")

# check if young improving pitchers actually outperform vets improving
young_up = df_san[(df_san['is_young']==1) & (df_san['delta_swstr']>0)]['ros_fp_per_start'].mean()
vet_up   = df_san[(df_san['is_young']==0) & (df_san['delta_swstr']>0)]['ros_fp_per_start'].mean()
print(f"\n  Asymmetry check: young improving ({young_up:+.3f}) vs vet improving ({vet_up:+.3f})")
print(f"  Δ = {young_up - vet_up:+.3f}  (positive = young outperform theory holds)")

# ── 11. Interpretation ───────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 11: interpretation")
best_lift = best_res['lift']
best_sign = best_res['sign_match_years']
best_ho   = best_res['holdout_lift']
asymmetry_gap = young_up - vet_up

gate_lift = best_lift >= 0.005
gate_sign = best_sign >= 5
gate_ho   = (best_ho is not None and best_ho > 0)

print(f"\n  Best individual candidate: {best_col}")
print(f"    Lift:       {best_lift:+.4f}  ({'≥0.005 PASS' if gate_lift else '<0.005 FAIL'})")
print(f"    Sign:       {best_sign}/{best_res['n_total_years']}  ({'≥5 PASS' if gate_sign else '<5 FAIL'})")
print(f"    Holdout:    {best_ho:+.4f}  ({'+ve PASS' if gate_ho else 'FAIL'})" if best_ho else "    Holdout:    N/A")
print(f"\n  Raw asymmetry in data: young improving vs vet improving Δ = {asymmetry_gap:+.3f}")
if abs(asymmetry_gap) < 0.1:
    print("  → No meaningful asymmetry in raw data at all.")
elif asymmetry_gap > 0:
    print("  → Asymmetry EXISTS in raw data (young improving pitchers do outperform).")
    if not (gate_lift and gate_sign and gate_ho):
        print("  → But does NOT clear model lift gate — interaction adds collinear noise.")
    else:
        print("  → AND clears model lift gate — consider promoting to validated registry.")
else:
    print("  → Reverse asymmetry: vets improving actually outperform young improving in raw data.")

print("\nDone.")
