"""validate_xwoba_contact_to.py

Pre-registered: data/research/validation_runs/xwoba_contact_to_2026-05-25.md

Signal: xwoba_contact_to = AVG(estimated_woba_using_speedangle) on batted balls
        (launch_speed IS NOT NULL) per pitcher, season-to-date at each split_day cutoff.

Outcome: ros_fp_per_start (rp3 production target)
Rule 9 baseline: full RP3_FEATS (24 features incl. ros_opp_xwoba_weighted)

No data leakage: each (pitcher, year, split_day) row gets xwoba_contact
computed from game_date <= that row's cutoff_date only.

Pitchers with < 15 BIP at cutoff: NaN → filled with per-year-split mean.
"""
from __future__ import annotations
import sys
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\Users\Joshua\plv_clone')

import duckdb
import pandas as pd
import numpy as np
from pathlib import Path

REPO = Path(r'c:\Users\Joshua\plv_clone')
CACHE = REPO / 'data' / 'research' / 'xfp_cache'
SCHED_CSV = CACHE / 'ros_schedule_features_2018_2026.csv'

# ── Step 1: compute xwoba_contact_to at each (year, cutoff_date) ─────────────

print("Computing xwoba_contact_to at each split_day cutoff (no leakage)...")

rolling_raw = pd.read_csv(CACHE / 'rolling_pitchers_2018_2026.csv')
# Get unique (year, split_day, cutoff_date) triplets we need to compute
cutoffs = (rolling_raw[['year', 'split_day', 'cutoff_date']]
           .drop_duplicates()
           .sort_values(['year', 'split_day']))
print(f"  {len(cutoffs)} unique (year, split_day, cutoff_date) combos to compute")

con = duckdb.connect()
contact_rows = []

for _, row in cutoffs.iterrows():
    yr = int(row['year'])
    sd = int(row['split_day'])
    cutoff = str(row['cutoff_date'])
    parq = str(CACHE / f'statcast_{yr}.parquet')

    try:
        df = con.execute(f"""
            SELECT pitcher,
              AVG(CASE WHEN launch_speed IS NOT NULL AND estimated_woba_using_speedangle IS NOT NULL
                       THEN estimated_woba_using_speedangle END) AS xwoba_contact_to,
              COUNT(CASE WHEN launch_speed IS NOT NULL AND estimated_woba_using_speedangle IS NOT NULL
                         THEN 1 END) AS bip_to
            FROM read_parquet('{parq}')
            WHERE game_date <= '{cutoff}'
            GROUP BY pitcher
        """).df()
        df['year'] = yr
        df['split_day'] = sd
        contact_rows.append(df)
    except Exception as e:
        print(f"  ERROR {yr} sd={sd}: {e}")

con.close()

contact_df = pd.concat(contact_rows, ignore_index=True)
print(f"  Computed {len(contact_df)} (pitcher, year, split_day) rows")

# NaN out pitchers with < 15 BIP (unstable estimate)
contact_df.loc[contact_df['bip_to'] < 15, 'xwoba_contact_to'] = np.nan

# Coverage report
n_total = len(contact_df)
n_valid = contact_df['xwoba_contact_to'].notna().sum()
print(f"  xwoba_contact_to coverage: {n_valid}/{n_total} ({n_valid/n_total*100:.1f}%) after BIP>=15 gate")
print(f"  Distribution: mean={contact_df['xwoba_contact_to'].mean():.3f} "
      f"p10={contact_df['xwoba_contact_to'].quantile(0.10):.3f} "
      f"p90={contact_df['xwoba_contact_to'].quantile(0.90):.3f}")

# ── Step 2: prep rolling via harness ─────────────────────────────────────────

print("\nPrepping rolling DataFrame via harness...")
from scripts.xfp._rp3_validation_harness import prep_rolling, evaluate_candidate, print_report
rolling = prep_rolling()

# Attach ros_opp_xwoba_weighted (in RP3_FEATS since rp3 v3)
sched = pd.read_csv(SCHED_CSV)[['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']]
rolling = rolling.merge(sched, on=['pitcher', 'year', 'split_day'], how='left')
yr_mean = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(yr_mean).fillna(
    rolling['ros_opp_xwoba_weighted'].mean())

print(f"  Rolling rows: {len(rolling)}, years: {sorted(rolling['year'].unique())}")

# ── Step 3: join xwoba_contact_to ──────────────────────────────────────────────

rolling = rolling.merge(
    contact_df[['pitcher', 'year', 'split_day', 'xwoba_contact_to']],
    on=['pitcher', 'year', 'split_day'],
    how='left',
)

# Fill NaN with per-(year, split_day) mean — same approach as ros_opp_xwoba_weighted
fill_mean = rolling.groupby(['year', 'split_day'])['xwoba_contact_to'].transform('mean')
rolling['xwoba_contact_to'] = rolling['xwoba_contact_to'].fillna(fill_mean)
rolling['xwoba_contact_to'] = rolling['xwoba_contact_to'].fillna(rolling['xwoba_contact_to'].mean())

nan_left = rolling['xwoba_contact_to'].isna().sum()
print(f"  xwoba_contact_to NaN after fill: {nan_left}")
print(f"  In rolling — mean={rolling['xwoba_contact_to'].mean():.3f} "
      f"std={rolling['xwoba_contact_to'].std():.3f}")

# ── Step 4: verify baseline r matches expected ────────────────────────────────

from plv_clone.models.xfp.rp3 import RP3_FEATS, cross_year_eval
py_base, ov_base = cross_year_eval(rolling, RP3_FEATS)
print(f"\nBaseline cross_year_r = {ov_base['r']:.4f}  (expected ~0.5654)  n={ov_base['n']}")

# ── Step 5: evaluate xwoba_contact_to ─────────────────────────────────────────

print("\n--- xwoba_contact_to (proper split-day, no leakage) ---")
result = evaluate_candidate(rolling, 'xwoba_contact_to', label='xwoba_contact_to')
print_report(result, gate=0.005)

# ── Step 6: per-year breakdown ────────────────────────────────────────────────

print("\n--- Per-year r ---")
print(f"{'Year':<6} {'Base r':<10} {'Full r':<10} {'Lift':<10} {'n'}")
for yr in sorted(result['per_year_lift']):
    base_r = result['per_year_baseline'].get(yr, float('nan'))
    full_r = result['per_year_full'].get(yr, float('nan'))
    lift = result['per_year_lift'][yr]
    print(f"  {yr}  {base_r:.4f}    {full_r:.4f}    {lift:+.4f}")

# ── Step 7: coefficient direction check ───────────────────────────────────────

from plv_clone.models.xfp.rp3 import train_final
pipe, _ = train_final(rolling, RP3_FEATS + ['xwoba_contact_to'])
coefs = dict(zip(RP3_FEATS + ['xwoba_contact_to'], pipe.named_steps['r'].coef_))
xwoba_coef = coefs['xwoba_contact_to']
print(f"\nRidge coefficient on xwoba_contact_to: {xwoba_coef:.4f}")
print(f"Expected sign: negative (lower xwOBA-on-contact → better pitcher)")
print(f"Sign correct: {'YES' if xwoba_coef < 0 else 'NO — unexpected, investigate'}")

# Top-5 coefficients for context
print("\nTop-5 abs coefficients in full model:")
for k, v in sorted(coefs.items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
    print(f"  {k}: {v:.4f}")

# ── Step 8: convergence curve across split_days ───────────────────────────────

print("\n--- Convergence curve: lift by split_day ---")
for sd in sorted(rolling['split_day'].unique()):
    sub = rolling[rolling['split_day'] == sd].copy()
    if len(sub) < 100:
        print(f"  split_day={sd}: n={len(sub)} (too small, skip)")
        continue
    py_b, ov_b = cross_year_eval(sub, RP3_FEATS)
    py_f, ov_f = cross_year_eval(sub, RP3_FEATS + ['xwoba_contact_to'])
    print(f"  split_day={sd:3d}: baseline r={ov_b['r']:.4f}  +xwoba_contact r={ov_f['r']:.4f}  Δ={ov_f['r']-ov_b['r']:+.4f}  n={ov_b['n']}")

# ── Step 9: verdict ───────────────────────────────────────────────────────────

print("\n=== FINAL VERDICT ===")
lift = result['lift']
sign = result['sign_match_years']
n_yr = result['n_total_years']
ho = result['holdout_lift']
ho_str = f"{ho:+.4f}" if ho is not None else "n/a"

if lift >= 0.005 and sign >= 5 and ho is not None and ho > 0:
    verdict = 'PASS'
elif 0 < lift < 0.005 and sign >= 5:
    verdict = 'MARGINAL'
elif lift <= 0:
    verdict = 'REJECTED (negative lift)'
else:
    verdict = 'MARGINAL (mixed gates)'

print(f"  {verdict}")
print(f"  Lift={lift:+.4f}  Sign={sign}/{n_yr}  Holdout={ho_str}")
print(f"  Coef sign correct: {'YES' if xwoba_coef < 0 else 'NO'}")
print(f"\n  Gate (a) lift >= +0.005:  {'PASS' if lift >= 0.005 else 'FAIL'} ({lift:+.4f})")
print(f"  Gate (b) sign >= 5/7:    {'PASS' if sign >= 5 else 'FAIL'} ({sign}/{n_yr})")
if ho is not None:
    print(f"  Gate (c) holdout > 0:    {'PASS' if ho > 0 else 'FAIL'} ({ho_str})")

print(f"\n  (Bonferroni: single hypothesis, full α=0.05 — no adjustment)")
print(f"  (Data leakage: none — cutoff_date used for all statcast queries)")
if verdict == 'PASS':
    print(f"\n  Next step: production integration plan in pre-registration file.")
    print(f"  Add xwoba_contact_to_sh to RP3_FEATS → rp3 v4.")
