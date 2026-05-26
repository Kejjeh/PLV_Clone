"""validate_stuff_contact_composite.py

Pre-registered: data/research/validation_runs/stuff_contact_composite_2026-05-25.md

Signal: stuff_contact_flag = (whiff_pct_to >= 26.0) AND (xwoba_contact_to <= 0.320)
Outcome: ros_fp_per_start (rp3 production target, cross-year r)
Rule 9 baseline: full RP3_FEATS (23 features, r=0.5509 expected)

Data note: whiff_pct and xwoba_contact are computed from full-season statcast
parquets (2018-2025) and joined on (pitcher, year). This uses the full season
as a "to-date" proxy — a slight optimism bias. If the flag fails even here,
it fails cleanly. If it passes, a proper split-day re-run is needed.

whiff_pct  = (swinging_strike + foul_tip) / all swings
xwoba_contact = avg(estimated_woba_using_speedangle) on events with launch_speed IS NOT NULL

Minimum BF to count: >= 50 (ensures stable whiff estimate; pitchers below this
get NaN → filled with 0 / no-flag).
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
PARQ_GLOB = str(CACHE / 'statcast_{year}.parquet')
YEARS = list(range(2018, 2026))  # 2018-2025 (2026 is holdout / current season)

# ── Step 1: compute full-season whiff% and xwoba_contact per (pitcher, year) ──

print("Computing whiff_pct and xwoba_contact from statcast parquets (2018-2025)...")
rows = []
con = duckdb.connect()
for yr in YEARS:
    parq = PARQ_GLOB.format(year=yr)
    try:
        df = con.execute(f"""
            SELECT pitcher,
              COUNT(CASE WHEN description IN
                ('swinging_strike','swinging_strike_bounded','foul_tip') THEN 1 END) AS whiff_n,
              COUNT(CASE WHEN description IN (
                'swinging_strike','swinging_strike_bounded','foul_tip',
                'foul','hit_into_play','foul_bunt','missed_bunt'
              ) THEN 1 END) AS swing_n,
              AVG(CASE WHEN launch_speed IS NOT NULL AND estimated_woba_using_speedangle IS NOT NULL
                       THEN estimated_woba_using_speedangle END) AS xwoba_contact,
              COUNT(CASE WHEN launch_speed IS NOT NULL AND estimated_woba_using_speedangle IS NOT NULL
                         THEN 1 END) AS bip_n,
              COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf_total
            FROM read_parquet('{parq}')
            GROUP BY pitcher
            HAVING COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 50
        """).df()
        df['year'] = yr
        df['whiff_pct'] = df['whiff_n'] / df['swing_n'].replace(0, np.nan) * 100.0
        rows.append(df[['pitcher', 'year', 'whiff_pct', 'xwoba_contact', 'swing_n', 'bip_n']])
        print(f"  {yr}: {len(df)} pitchers with >= 50 BF")
    except Exception as e:
        print(f"  {yr}: ERROR — {e}")
con.close()

statcast_feats = pd.concat(rows, ignore_index=True)
print(f"Total rows: {len(statcast_feats)}")

# Coverage check
print("\n--- Coverage check ---")
print(f"whiff_pct NaN: {statcast_feats['whiff_pct'].isna().sum()}/{len(statcast_feats)}")
print(f"xwoba_contact NaN: {statcast_feats['xwoba_contact'].isna().sum()}/{len(statcast_feats)}")
both_ok = statcast_feats.dropna(subset=['whiff_pct', 'xwoba_contact'])
print(f"Both non-null: {len(both_ok)} rows ({len(both_ok)/len(statcast_feats)*100:.1f}%)")

# Threshold distribution sanity check
print(f"\nwhiff_pct >= 26: {(both_ok['whiff_pct'] >= 26.0).sum()} rows ({(both_ok['whiff_pct'] >= 26.0).mean()*100:.1f}%)")
print(f"xwoba_contact <= 0.320: {(both_ok['xwoba_contact'] <= 0.320).sum()} rows ({(both_ok['xwoba_contact'] <= 0.320).mean()*100:.1f}%)")
flag_both = (both_ok['whiff_pct'] >= 26.0) & (both_ok['xwoba_contact'] <= 0.320)
print(f"BOTH (composite flag): {flag_both.sum()} rows ({flag_both.mean()*100:.1f}%)")

# ── Step 2: prep rolling via harness ─────────────────────────────────────────

print("\nPrepping rolling DataFrame via harness...")
from scripts.xfp._rp3_validation_harness import prep_rolling, evaluate_candidate, print_report
rolling = prep_rolling()

# Attach ros_opp_xwoba_weighted (required since it joined RP3_FEATS in rp3 v3)
SCHED_CSV = REPO / 'data' / 'research' / 'xfp_cache' / 'ros_schedule_features_2018_2026.csv'
sched = pd.read_csv(SCHED_CSV)[['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']]
rolling = rolling.merge(sched, on=['pitcher', 'year', 'split_day'], how='left')
yr_mean = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(yr_mean)
rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(rolling['ros_opp_xwoba_weighted'].mean())

print(f"  Rolling rows: {len(rolling)}, years: {sorted(rolling['year'].unique())}")

# ── Step 3: join statcast features onto rolling ───────────────────────────────

statcast_merge = statcast_feats[['pitcher', 'year', 'whiff_pct', 'xwoba_contact']].copy()
rolling = rolling.merge(statcast_merge, on=['pitcher', 'year'], how='left')

# Build binary flag; NaN rows (rookie / below-BF-threshold) → 0 (no flag)
rolling['stuff_contact_flag'] = (
    (rolling['whiff_pct'] >= 26.0) & (rolling['xwoba_contact'] <= 0.320)
).astype(float)
rolling['stuff_contact_flag'] = rolling['stuff_contact_flag'].where(
    rolling['whiff_pct'].notna() & rolling['xwoba_contact'].notna(), 0.0
)

flag_rate = rolling['stuff_contact_flag'].mean()
print(f"  Flag fire rate in rolling: {flag_rate*100:.1f}%")
print(f"  whiff_pct NaN in rolling: {rolling['whiff_pct'].isna().sum()}")
print(f"  xwoba_contact NaN in rolling: {rolling['xwoba_contact'].isna().sum()}")

# ── Step 4: also test the continuous features separately ──────────────────────
# These are orthogonal to RP3_FEATS (no whiff_pct_to or xwoba_contact_to exists)
# Test them individually first to understand where the flag's lift comes from.

print("\n--- Continuous features individually (Rule 9 baseline = full RP3_FEATS) ---")
for col, fill in [('whiff_pct', 20.0), ('xwoba_contact', 0.350)]:
    rolling_f = rolling.copy()
    rolling_f[col] = rolling_f[col].fillna(fill)
    result = evaluate_candidate(rolling_f, col, label=col)
    print_report(result, gate=0.005)

# ── Step 5: binary flag ───────────────────────────────────────────────────────

print("\n--- Binary composite flag ---")
result_flag = evaluate_candidate(rolling, 'stuff_contact_flag', fill_value=0.0, label='stuff_contact_flag')
print_report(result_flag, gate=0.005)

# ── Step 6: both continuous + flag together ───────────────────────────────────

print("\n--- Bundle: whiff_pct + xwoba_contact + flag ---")
rolling_bundle = rolling.copy()
rolling_bundle['whiff_pct'] = rolling_bundle['whiff_pct'].fillna(20.0)
rolling_bundle['xwoba_contact'] = rolling_bundle['xwoba_contact'].fillna(0.350)
from plv_clone.models.xfp.rp3 import RP3_FEATS, cross_year_eval
py_base, ov_base = cross_year_eval(rolling_bundle, RP3_FEATS)
py_bun, ov_bun = cross_year_eval(rolling_bundle, RP3_FEATS + ['whiff_pct', 'xwoba_contact', 'stuff_contact_flag'])
print(f"  Baseline r={ov_base['r']:.4f}  Full r={ov_bun['r']:.4f}  Lift={ov_bun['r']-ov_base['r']:+.4f}")

# ── Step 7: per-year breakdown for registry writeup ───────────────────────────

print("\n--- Per-year result summary (flag only) ---")
from plv_clone.models.xfp.rp3 import TRAIN_YEARS
print(f"Training years: {TRAIN_YEARS}")
print(f"\n{'Year':<6} {'Base r':<10} {'Flag r':<10} {'Lift':<10} {'n':<6}")
for yr in sorted(result_flag['per_year_lift']):
    base_r = result_flag['per_year_baseline'].get(yr, float('nan'))
    full_r = result_flag['per_year_full'].get(yr, float('nan'))
    lift = result_flag['per_year_lift'][yr]
    print(f"  {yr}  {base_r:.4f}    {full_r:.4f}    {lift:+.4f}")

print("\n=== VERDICT ===")
lift = result_flag['lift']
sign = result_flag['sign_match_years']
n = result_flag['n_total_years']
ho = result_flag['holdout_lift']
if lift >= 0.005 and sign >= 5 and ho is not None and ho > 0:
    verdict = 'PASS'
elif 0 < lift < 0.005 and sign >= 5:
    verdict = 'MARGINAL'
else:
    verdict = 'REJECTED'
ho_str = f"{ho:+.4f}" if ho is not None else "n/a"
print(f"  {verdict}: lift={lift:+.4f}, sign={sign}/{n}, holdout={ho_str}")
print(f"  Note: full-season statcast as 'to-date' proxy — slight optimism bias.")
print(f"  If PASS, re-run with proper split-day computation before rp3 integration.")
