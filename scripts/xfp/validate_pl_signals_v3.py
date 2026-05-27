# Pre-registered: see data/research/validation_runs/pl_untested_signals_sweep_2026-05-27.md
"""
V3 of PL signals validation — rolling LAST-N-PA windows (not cumulative).

Tests whether recent-form vs season-average is more predictive than either
alone. Directly analogous to delta_swstr / delta_k_pct in RP3_FEATS.

Signals:
  F_lpa    = fps_pct_last100pa
  F_dlpa   = fps_pct_delta_l100        (= last100 - to_sd; recent vs season)
  P_lpa    = putaway_pct_last50pa
  P_dlpa   = putaway_pct_delta_l50     (= last50 - to_sd)
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

LPA_CSV = f"{ROOT}/data/research/xfp_cache/pl_signals_lastpa_2018_2026.csv"
SD_CSV  = f"{ROOT}/data/research/xfp_cache/pl_signals_split_day_2018_2026.csv"

CELLS = [
    ('F_lpa',       ['fps_pct_last100pa']),
    ('F_dlpa',      ['fps_pct_delta_l100']),
    ('P_lpa',       ['putaway_pct_last50pa']),
    ('P_dlpa',      ['putaway_pct_delta_l50']),
    ('FP_lpa',      ['fps_pct_last100pa', 'putaway_pct_last50pa']),
    ('FP_dlpa',     ['fps_pct_delta_l100', 'putaway_pct_delta_l50']),
    ('F_l_d',       ['fps_pct_last100pa', 'fps_pct_delta_l100']),
    ('P_l_d',       ['putaway_pct_last50pa', 'putaway_pct_delta_l50']),
    ('ALL_lpa',     ['fps_pct_last100pa', 'putaway_pct_last50pa',
                     'fps_pct_delta_l100', 'putaway_pct_delta_l50']),
]


def main():
    print("Loading data + building full RP3 training frame...")
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    full_df = build_full_training_frame(rolling, multiyr)

    lpa = pd.read_csv(LPA_CSV)
    sd  = pd.read_csv(SD_CSV)
    df = full_df.merge(
        lpa[['pitcher','year','split_day',
             'fps_pct_last100pa','putaway_pct_last50pa',
             'fps_pct_delta_l100','putaway_pct_delta_l50']],
        on=['pitcher','year','split_day'], how='left'
    ).merge(
        sd[['pitcher','year','split_day','fps_pct_to_sd','putaway_pct_to_sd']],
        on=['pitcher','year','split_day'], how='left'
    )
    print(f"Joined shape: {df.shape}")
    for c in ['fps_pct_last100pa','fps_pct_delta_l100',
              'putaway_pct_last50pa','putaway_pct_delta_l50']:
        n = df[c].notna().sum()
        print(f"  {c}: {n} non-null ({n/len(df)*100:.1f}%)")

    print("\nRunning v3 sweep (last-N-PA + delta variants)...")
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
                print(f"  [{cell_label:8s}] SKIPPED — n={len(df_c)}")
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
            print(f"  [{cell_label:8s}] lift={lift:+.4f}  ho_lift={ho_lift:+.4f}  "
                  f"signs={sign_consistent}/{n_train}  n={n}  {flag}")

    rdf = pd.DataFrame(results)
    out_path = f"{ROOT}/data/research/pl_signals_v3_results_2026-05-27.csv"
    rdf.to_csv(out_path, index=False)
    print(f"\nResults → {out_path}")

    print("\n" + "="*80)
    print("V3 SUMMARY (rolling-last-N-PA)")
    print("="*80)
    print(rdf[['config','cell','cv_lift','ho_lift','sign_consistent','n','PASS']]
          .sort_values(['PASS','cv_lift'], ascending=[False, False])
          .to_string(index=False))

    print("\n=== CONVERGENCE CURVES (all cells, with leakage check) ===")
    for cell_label, cand_feats in CELLS:
        for cfg_name, train_yrs, _ in configs:
            df_c = df.dropna(subset=RP3_FEATS + cand_feats + [TARGET])
            curve = convergence_curve(df_c, cand_feats, train_yrs)
            cstr = '  '.join(f"d{d}:{v:+.4f}" if not np.isnan(v) else f"d{d}:n/a"
                             for d, v in curve.items())
            # Leakage check: if d30 ≈ d56 ≈ d84 within 0.0005, flag
            vals = [v for v in curve.values() if not np.isnan(v)]
            leak_flag = ''
            if len(vals) >= 3 and (max(vals) - min(vals)) < 0.0005 and abs(vals[0]) > 0.003:
                leak_flag = '  ⚠ FLAT — possible leakage'
            print(f"  [{cfg_name}] {cell_label}: {cstr}{leak_flag}")

    print("\n=== VERDICT ===")
    for cell in ['F_lpa', 'F_dlpa', 'P_lpa', 'P_dlpa',
                 'FP_lpa', 'FP_dlpa', 'F_l_d', 'P_l_d', 'ALL_lpa']:
        rows = rdf[rdf['cell'] == cell]
        if rows.empty: continue
        best_cv = rows['cv_lift'].max()
        best_ho = rows.loc[rows['cv_lift'].idxmax(), 'ho_lift']
        if rows['PASS'].any():
            verdict = "PASS"
        elif best_cv >= 0.005 and best_ho >= 0:
            verdict = "PASS-clean"
        elif best_cv > 0:
            verdict = "MARGINAL"
        else:
            verdict = "REJECTED"
        print(f"  {cell}: best cv_lift={best_cv:+.4f}  best ho_lift={best_ho:+.4f}  → {verdict}")


if __name__ == '__main__':
    main()
