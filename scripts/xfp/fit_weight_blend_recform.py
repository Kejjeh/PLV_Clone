"""fit_weight_blend_recform.py — Phase 3 Agent 5 Part A fit.

Re-fit the within-season SP blend at split_day=90 WITH and WITHOUT
recform_hot_z. LOYO across years 2018-2025 (excl. 2020). Print apples-
to-apples lift on the matched sample.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

import sys
sys.path.insert(0, str(Path('c:/Users/Joshua/plv_clone/scripts/xfp')))
from fit_weight_blend_within_season import load_panel, fit_loyo, drop_test  # noqa

ROOT = Path('c:/Users/Joshua/plv_clone')
RECFORM = ROOT / 'data' / 'research' / 'historical_panel' / 'recform_hot_retroactive.parquet'
OUT_DIR = ROOT / 'data' / 'research' / 'validation_runs'


def main():
    rec = pd.read_parquet(RECFORM)
    print(f'recform panel n={len(rec):,}')

    all_results = {}
    for sd in [60, 90, 120]:
        print(f'\n--- split_day={sd} ---')
        sub, features = load_panel('SP', sd)
        print(f'  baseline n={len(sub):,}  features={len(features)}')

        # Join recform on (pitcher, year) for this split_day
        rec_sd = rec[rec['split_day'] == sd][['pitcher', 'year', 'recform_hot_z']]
        sub2 = sub.merge(rec_sd, on=['pitcher', 'year'], how='inner')
        sub2 = sub2.dropna(subset=['recform_hot_z'])
        print(f'  matched n with recform={len(sub2):,}')

        if len(sub2) < 300:
            print('  SKIP — n too low')
            continue

        # Baseline on matched sample
        r_base = fit_loyo(sub2, features)
        # +recform
        features_rec = features + ['recform_hot_z']
        r_rec = fit_loyo(sub2, features_rec)

        print(f'  baseline (matched): pooled R²={r_base["pooled_r2_blend"]:.4f}  lift={r_base["pooled_lift"]:+.4f}  conv={r_base["convergence"]}')
        print(f'  +recform:           pooled R²={r_rec["pooled_r2_blend"]:.4f}  lift={r_rec["pooled_lift"]:+.4f}  conv={r_rec["convergence"]}')
        print(f'  delta R2 from recform: {r_rec["pooled_r2_blend"] - r_base["pooled_r2_blend"]:+.4f}')

        # Drop-test recform contribution
        contrib = drop_test(sub2, features_rec)
        rec_contrib = contrib.get('recform_hot_z', float('nan'))
        print(f'  recform partial R² (full-sample drop-test): {rec_contrib:+.4f}')

        # Correlation of recform with existing features
        corrs = {f: round(sub2[['recform_hot_z', f]].corr().iloc[0, 1], 3)
                 for f in features
                 if sub2[f].dtype != object and sub2[f].notna().any()}
        top_corr = dict(sorted(corrs.items(), key=lambda x: -abs(x[1]))[:8])
        print(f'  top correlations with recform_hot_z: {top_corr}')

        all_results[sd] = {
            'n_matched': len(sub2),
            'baseline_pooled_r2': r_base['pooled_r2_blend'],
            'baseline_pooled_lift': r_base['pooled_lift'],
            'baseline_convergence': r_base['convergence'],
            'plus_recform_pooled_r2': r_rec['pooled_r2_blend'],
            'plus_recform_pooled_lift': r_rec['pooled_lift'],
            'plus_recform_convergence': r_rec['convergence'],
            'delta_r2': r_rec['pooled_r2_blend'] - r_base['pooled_r2_blend'],
            'recform_partial_r2': rec_contrib,
            'top_correlations': top_corr,
            'fold_lifts_baseline': r_base['folds'],
            'fold_lifts_plus_recform': r_rec['folds'],
        }

    out_json = OUT_DIR / 'weight_blend_recform_2026-06-04.json'
    out_json.write_text(json.dumps(all_results, indent=2, default=str))
    print(f'\nWrote {out_json}')
    return all_results


if __name__ == '__main__':
    main()
