# Pre-registered: see data/research/validation_runs/pl_untested_signals_sweep_2026-05-27.md
"""
V2 of PL signals validation — TRUE split-day-aware FPS_pct and putaway_pct.

Replaces the leaky v1 (full-year fp_strike_pct applied as season-to-date proxy).
Uses pl_signals_split_day_2018_2026.csv built by build_pl_signals_split_day.py.

T (TTOP), O (out_pitch_whiff), R (velo_recovery), X (pitch_trim) were already
rejected in v1 and stay rejected — only F and P need re-validation.
"""
from __future__ import annotations
import os
import sys
import warnings
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from validate_pitch_shape_early_warning import (
    build_full_training_frame, RP3_FEATS, TARGET,
    TRAIN_YEARS_A, TRAIN_YEARS_B, HOLDOUT_A, HOLDOUT_B,
    cross_year_r, holdout_r, partial_r_vs_baseline, convergence_curve,
    ROOT, ROLLING_CSV, MULTIYR_CSV,
)

warnings.filterwarnings("ignore")

PL_SD_CSV = f"{ROOT}/data/research/xfp_cache/pl_signals_split_day_2018_2026.csv"

CELLS = [
    ('F_sd',  ['fps_pct_to_sd']),
    ('P_sd',  ['putaway_pct_to_sd']),
    ('FP_sd', ['fps_pct_to_sd', 'putaway_pct_to_sd']),
]


def main():
    print("Loading data + building full RP3 training frame...")
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    full_df = build_full_training_frame(rolling, multiyr)

    # Merge split-day-aware signals
    sd = pd.read_csv(PL_SD_CSV)
    df = full_df.merge(sd[['pitcher', 'year', 'split_day',
                           'fps_pct_to_sd', 'putaway_pct_to_sd']],
                       on=['pitcher', 'year', 'split_day'], how='left')
    print(f"Joined shape: {df.shape}")
    print(f"  fps_pct_to_sd:     {df['fps_pct_to_sd'].notna().sum()} non-null ({df['fps_pct_to_sd'].notna().mean()*100:.1f}%)")
    print(f"  putaway_pct_to_sd: {df['putaway_pct_to_sd'].notna().sum()} non-null ({df['putaway_pct_to_sd'].notna().mean()*100:.1f}%)")

    print("\nRunning v2 sweep (split-day-aware)...")
    configs = [
        ('holdout_A', TRAIN_YEARS_A, HOLDOUT_A),
        ('holdout_B', TRAIN_YEARS_B, HOLDOUT_B),
    ]
    results = []
    for cfg_name, train_yrs, holdout_yrs in configs:
        print(f"\n=== {cfg_name} | train={train_yrs} | holdout={holdout_yrs} ===")
        base_cv = cross_year_r(df, RP3_FEATS, TARGET, train_yrs)
        base_ho = holdout_r(df, RP3_FEATS, TARGET, train_yrs, holdout_yrs)
        print(f"  BASELINE: cv_r={base_cv['pooled_r']:.4f}  holdout_r={base_ho:.4f}  n={base_cv['n']}")
        for cell_label, cand_feats in CELLS:
            df_c = df.dropna(subset=cand_feats + RP3_FEATS + [TARGET])
            if len(df_c) < 200:
                print(f"  [{cell_label:6s}] SKIPPED — n={len(df_c)}")
                continue
            base_r, full_r, lift, per_year, n = partial_r_vs_baseline(
                df_c, cand_feats, TARGET, train_yrs
            )
            ho_base = holdout_r(df_c, RP3_FEATS, TARGET, train_yrs, holdout_yrs)
            ho_full = holdout_r(df_c, RP3_FEATS + cand_feats, TARGET, train_yrs, holdout_yrs)
            ho_lift = ho_full - ho_base if not (np.isnan(ho_full) or np.isnan(ho_base)) else np.nan
            sign_consistent = sum(1 for v in per_year.values() if v > 0)
            n_train = len(train_yrs)
            passes = (lift >= 0.005 and sign_consistent >= max(4, n_train - 1)
                      and (not np.isnan(ho_lift) and ho_lift >= 0))
            row = {
                'config': cfg_name, 'cell': cell_label, 'signals': '+'.join(cand_feats),
                'cv_base_r': round(base_r, 4), 'cv_full_r': round(full_r, 4),
                'cv_lift': round(lift, 4),
                'ho_base_r': round(ho_base, 4), 'ho_full_r': round(ho_full, 4),
                'ho_lift': round(ho_lift, 4),
                'sign_consistent': f"{sign_consistent}/{n_train}",
                'per_year': ' '.join(f"{yr}:{v:+.3f}" for yr, v in sorted(per_year.items())),
                'n': n, 'PASS': passes,
            }
            results.append(row)
            flag = '✓ PASS' if passes else ''
            print(f"  [{cell_label:6s}] lift={lift:+.4f}  ho_lift={ho_lift:+.4f}  signs={sign_consistent}/{n_train}  n={n}  {flag}")

    rdf = pd.DataFrame(results)
    out_path = f"{ROOT}/data/research/pl_signals_v2_results_2026-05-27.csv"
    rdf.to_csv(out_path, index=False)
    print(f"\nResults → {out_path}")

    print("\n" + "="*80)
    print("V2 SUMMARY (split-day-aware)")
    print("="*80)
    print(rdf[['config','cell','cv_lift','ho_lift','sign_consistent','n','PASS']].to_string(index=False))

    print("\n=== CONVERGENCE CURVES (all cells, regardless of pass) ===")
    for cell_label, cand_feats in CELLS:
        for cfg_name, train_yrs, _ in configs:
            df_c = df.dropna(subset=RP3_FEATS + cand_feats + [TARGET])
            curve = convergence_curve(df_c, cand_feats, train_yrs)
            cstr = '  '.join(f"d{d}:{v:+.4f}" if not np.isnan(v) else f"d{d}:n/a"
                             for d, v in curve.items())
            print(f"  [{cfg_name}] {cell_label}: {cstr}")

    print("\n=== VERDICT (split-day-aware) ===")
    for cell in ['F_sd', 'P_sd', 'FP_sd']:
        rows = rdf[rdf['cell'] == cell]
        if rows.empty:
            print(f"  {cell}: no data"); continue
        best_cv = rows['cv_lift'].max()
        best_ho = rows.loc[rows['cv_lift'].idxmax(), 'ho_lift']
        if rows['PASS'].any():
            verdict = "PASS"
        elif best_cv >= 0.005 and best_ho >= 0:
            verdict = "PASS"
        elif best_cv > 0:
            verdict = "MARGINAL"
        else:
            verdict = "REJECTED"
        print(f"  {cell}: best cv_lift={best_cv:+.4f}  best ho_lift={best_ho:+.4f}  → {verdict}")


if __name__ == '__main__':
    main()
