"""validate_l1_whiff_final.py — final LOYO gate for L1+Whiff feature set.

For cutoffs 4, 6, 8, 10, 12 weeks: full leave-one-year-out test.
Promote if 5/7 years beat baseline AND mean gain ≥ +0.005 at most cutoffs.
Also report coefficient stability across cutoffs/years.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
RES = ROOT / 'data' / 'research'

from scripts.xfp.validate_pitch_shape_convergence import build_panel_at_cutoff

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
FEATS = ['d_velo_all', 'd_ext_all', 'd_ivb_all', 'd_whiff_per_swing']


def fit_eval(panel, features, train_years, test_years):
    features = [f for f in features if f in panel.columns]
    sub = panel.dropna(subset=features + ['ros_fp_per_start', 'prior_fp_per_start'])
    train = sub[sub['year'].isin(train_years)]
    test = sub[sub['year'].isin(test_years)]
    if len(train) < 30 or len(test) < 20:
        return None, None, len(test)
    X = np.column_stack([np.ones(len(train)), train['prior_fp_per_start'].values]
                          + [train[c].values for c in features])
    y = train['ros_fp_per_start'].values
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    Xt = np.column_stack([np.ones(len(test)), test['prior_fp_per_start'].values]
                            + [test[c].values for c in features])
    pred = Xt @ coefs
    r = float(np.corrcoef(pred, test['ros_fp_per_start'].values)[0, 1])
    return r, coefs, len(test)


def main():
    print('FINAL LOYO GATE — L1+Whiff at each cutoff')
    print('='*78)

    all_results = []
    for wks in [4, 6, 8, 10, 12]:
        print(f'\n  --- Week-{wks} cutoff ---')
        panel = build_panel_at_cutoff(wks)
        print(f'  panel: {len(panel)} rows')
        if len(panel) < 100: continue

        gains = []
        coefs_per_year = []
        print(f'  {"YEAR":<6s} {"N":>5s} {"BASE r":>8s} {"L1+W r":>8s} {"GAIN":>8s}')
        for year in YEARS:
            train = [y for y in YEARS if y != year]
            test = [year]
            r_b, _, n = fit_eval(panel, [], train, test)
            r_w, coefs, _ = fit_eval(panel, FEATS, train, test)
            if r_b is None or r_w is None: continue
            gain = r_w - r_b
            gains.append((year, gain, n))
            if coefs is not None:
                coefs_per_year.append(coefs)
            print(f'  {year:<6d} {n:>5d} {r_b:>8.4f} {r_w:>8.4f} {gain:>+8.4f}')

        n_pos = sum(1 for _, g, _ in gains if g > 0)
        mean_gain = np.mean([g for _, g, _ in gains])
        passes = (n_pos >= 5) and (mean_gain >= 0.005)
        print(f'\n  Week-{wks}: {n_pos}/{len(gains)} years positive, mean +{mean_gain:.4f}')
        print(f'  → {"PASS" if passes else "FAIL"}')

        # Coefficient stability
        if coefs_per_year:
            arr = np.array(coefs_per_year)
            names = ['α', 'prior_fp'] + FEATS
            print(f'\n  Coefficient stability (mean ± std across LOYO folds):')
            for i, n_ in enumerate(names):
                m_, s_ = arr[:, i].mean(), arr[:, i].std()
                sign_consistent = 100 * np.mean(np.sign(arr[:, i]) == np.sign(m_))
                print(f'    {n_:<25s} {m_:+.4f} ± {s_:.4f}  ({sign_consistent:.0f}% sign-consistent)')

        all_results.append({'weeks': wks, 'n_pos': n_pos, 'total': len(gains),
                              'mean_gain': mean_gain, 'pass': passes})

    print('\n' + '='*78)
    print('  SUMMARY')
    print('='*78)
    for r in all_results:
        print(f"  Week {r['weeks']:>2d}: {r['n_pos']}/{r['total']} positive, "
              f"mean +{r['mean_gain']:.4f}, {'PASS' if r['pass'] else 'FAIL'}")
    n_pass = sum(1 for r in all_results if r['pass'])
    print(f'\n  PASSES AT {n_pass}/{len(all_results)} CUTOFFS')
    if n_pass >= 4:
        print('  → GREEN LIGHT for production integration')


if __name__ == '__main__':
    main()
