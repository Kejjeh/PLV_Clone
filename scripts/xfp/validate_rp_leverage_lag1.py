"""validate_rp_leverage_lag1.py — pre-registered 3-cell sweep of PRIOR-year
FanGraphs leverage features for rprs2.

Pre-registration: data/research/validation_runs/rp_leverage_lag1_2026-07-09.md
Cells (Bonferroni family of 3): pli_lag1, gmli_lag1, sd_md_per_g_lag1.

Gates per cell (feature-addition variant of rprs2's stratified gates):
  (1) overall pooled LOO cross-year r lift >= +0.005 vs FULL FEATS_RPRS2
  (2) role-change subset: no regression (delta r >= 0.0)
  (3) per-year sign consistency >= 5/6 usable TRAIN_YEARS
  (4) holdout 2024-2025 mean per-year lift > 0

Then a pre-declared redundancy step: best cell + each remaining cell, and
all three jointly, reported for context (not a gate).

Run:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_rp_leverage_lag1.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

import numpy as np
import pandas as pd

from _rprs2_validation_harness import (
    prep_rolling, attach_leverage_lag1, evaluate_candidate, print_report,
    TRAIN_YEARS, EVAL_G_MIN,
)

GATE = 0.005
CELLS = ['pli_lag1', 'gmli_lag1', 'sd_md_per_g_lag1']


def coverage_report(df: pd.DataFrame) -> None:
    print('=== Step 2.5 coverage (eval population: TRAIN_YEARS + 2026, g_to >= %d) ===' % EVAL_G_MIN)
    ev = df[df['g_to'] >= EVAL_G_MIN]
    py = ev.groupby(['pitcher', 'year'], as_index=False).agg(
        has_lev=('has_lev_lag1', 'max'),
        has_prior=('role_lag1', lambda s: s.notna().any()))
    tab = py.groupby('year').apply(lambda d: pd.Series({
        'n_pitcher_years': len(d),
        'lev_join_raw': d['has_lev'].mean(),
        'lev_join_given_prior': d.loc[d['has_prior'], 'has_lev'].mean()
                                if d['has_prior'].any() else np.nan,
    }), include_groups=False)
    print(tab.round(3).to_string())
    for c in CELLS:
        print(f'  {c}: imputed fill value = {df[c][df["has_lev_lag1"] == 0].iloc[0]:.4f} '
              f'(population mean of observed lags)')


def main():
    rolling = prep_rolling()
    rolling = attach_leverage_lag1(rolling)
    coverage_report(rolling)

    # ── Single-cell sweep ────────────────────────────────────────────────
    results = {}
    for cell in CELLS:
        res = evaluate_candidate(rolling, cell)
        results[cell] = res
        print_report(res, gate=GATE)

    # ── Redundancy step (pre-declared, context only) ─────────────────────
    best = max(CELLS, key=lambda c: results[c]['lift'])
    others = [c for c in CELLS if c != best]
    print(f'\n=== Redundancy step (best cell = {best}, lift {results[best]["lift"]:+.4f}) ===')
    for other in others:
        res = evaluate_candidate(rolling, other, baseline_extra=[best],
                                 label=f'{other} | given {best}')
        print(f'  + {other} on top of {best}: incremental lift {res["lift"]:+.4f} '
              f'(r {res["r_baseline"]} -> {res["r_full"]}), '
              f'rc delta {res["rc_lift"]:+.4f}')
    res_all = evaluate_candidate(rolling, CELLS, label='all three jointly')
    print(f'  all three jointly vs baseline: lift {res_all["lift"]:+.4f} '
          f'(r {res_all["r_baseline"]} -> {res_all["r_full"]}), '
          f'rc delta {res_all["rc_lift"]:+.4f}, '
          f'signs {res_all["sign_match_years"]}/{res_all["n_total_years"]}, '
          f'holdout {res_all["holdout_lift"]:+.4f}')

    # ── Verdict summary ──────────────────────────────────────────────────
    print('\n=== VERDICT SUMMARY (Bonferroni family of 3) ===')
    for cell in CELLS:
        r = results[cell]
        g1 = r['lift'] >= GATE
        g2 = r['rc_lift'] is not None and r['rc_lift'] >= 0.0
        g3 = r['sign_match_years'] >= 5
        g4 = r['holdout_lift'] is not None and r['holdout_lift'] > 0
        n_pass = sum([g1, g2, g3, g4])
        if all([g1, g2, g3, g4]):
            verdict = 'PASS (candidate for promotion; Bonferroni-3 caveat if marginal)'
        elif g1 and g2:
            verdict = 'MARGINAL'
        else:
            verdict = 'REJECTED'
        print(f'  {cell:<20s} lift {r["lift"]:+.4f}  rc {r["rc_lift"]:+.4f}  '
              f'signs {r["sign_match_years"]}/{r["n_total_years"]}  '
              f'holdout {r["holdout_lift"]:+.4f}  gates {n_pass}/4  -> {verdict}')


if __name__ == '__main__':
    main()
