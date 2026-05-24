"""Validation script for the rp3 v3 schedule-strength BUNDLE candidate.

Pre-registered: data/research/validation_runs/rp3_schedule_strength_bundle_2026-05-24.md.

Joint Rule-9-honest evaluation of [ros_opp_xwoba_weighted,
ros_park_pf_HR_weighted] added together to RP3_FEATS. Reports
bundle Δr, compares to sum of marginals, prints per-feature coefs.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_rp3_schedule_strength_bundle.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _rp3_validation_harness import prep_rolling  # noqa: E402
from plv_clone.models.xfp.rp3 import RP3_FEATS, cross_year_eval, train_final  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCHED_CSV = ROOT / "data" / "research" / "xfp_cache" / "ros_schedule_features_2018_2026.csv"

CANDIDATES = ["ros_opp_xwoba_weighted", "ros_park_pf_HR_weighted"]


def attach(rolling: pd.DataFrame) -> pd.DataFrame:
    sched = pd.read_csv(SCHED_CSV)[["pitcher", "year", "split_day", *CANDIDATES]]
    merged = rolling.merge(sched, on=["pitcher", "year", "split_day"], how="left")
    # opp xwoba: per-year-mean fill (3.8% missing)
    yrm = merged.groupby("year")["ros_opp_xwoba_weighted"].transform("mean")
    merged["ros_opp_xwoba_weighted"] = merged["ros_opp_xwoba_weighted"].fillna(yrm)
    merged["ros_opp_xwoba_weighted"] = merged["ros_opp_xwoba_weighted"].fillna(
        merged["ros_opp_xwoba_weighted"].mean()
    )
    merged["ros_park_pf_HR_weighted"] = merged["ros_park_pf_HR_weighted"].fillna(1.00)
    return merged


def main() -> None:
    print("=== /validate-feature: rp3_schedule_strength_bundle (rp3 v3 candidate) ===")
    print("Pre-reg: data/research/validation_runs/rp3_schedule_strength_bundle_2026-05-24.md")
    print()
    rolling = attach(prep_rolling())

    py_base, ov_base = cross_year_eval(rolling, RP3_FEATS)
    py_opp, ov_opp = cross_year_eval(rolling, RP3_FEATS + ["ros_opp_xwoba_weighted"])
    py_park, ov_park = cross_year_eval(rolling, RP3_FEATS + ["ros_park_pf_HR_weighted"])
    py_bun, ov_bun = cross_year_eval(rolling, RP3_FEATS + CANDIDATES)

    print(f"  Baseline RP3_FEATS ({len(RP3_FEATS)} feats):     r={ov_base['r']:.4f}  n={ov_base['n']}")
    print(f"  + opp_xwoba only:                  r={ov_opp['r']:.4f}  Δr={ov_opp['r']-ov_base['r']:+.4f}")
    print(f"  + park_pf_HR only:                 r={ov_park['r']:.4f}  Δr={ov_park['r']-ov_base['r']:+.4f}")
    print(f"  + BUNDLE (both):                   r={ov_bun['r']:.4f}  Δr={ov_bun['r']-ov_base['r']:+.4f}")

    sum_marg = (ov_opp['r']-ov_base['r']) + (ov_park['r']-ov_base['r'])
    bundle_lift = ov_bun['r']-ov_base['r']
    redundancy = sum_marg - bundle_lift
    print(f"\n  Sum-of-marginals Δr:   {sum_marg:+.4f}")
    print(f"  Bundle Δr:             {bundle_lift:+.4f}")
    print(f"  Redundancy (sum-bun):  {redundancy:+.4f}  "
          f"({'additive' if redundancy < 0.001 else 'mild overlap' if redundancy < 0.003 else 'redundant'})")

    print("\n=== Per-year bundle lift ===")
    sign_match = 0; n_total = 0
    for y in sorted(py_bun):
        if y in py_base:
            d = py_bun[y]['r'] - py_base[y]['r']
            n_total += 1
            sign_match += int(d > 0)
            print(f"  {y}: Δr = {d:+.4f}  {'+' if d>0 else '-'}")
    print(f"  Sign consistency: {sign_match}/{n_total} positive")

    HOLDOUT = [2024, 2025]
    h_full = [py_bun[y]['r'] for y in HOLDOUT if y in py_bun]
    h_base = [py_base[y]['r'] for y in HOLDOUT if y in py_base]
    holdout_lift = float(np.mean(h_full)-np.mean(h_base))
    print(f"  Holdout (2024-25) avg lift: {holdout_lift:+.4f}")

    print("\n=== Coefficient signs (expected: both -) ===")
    pipe, _ = train_final(rolling, RP3_FEATS + CANDIDATES)
    coefs = dict(zip(RP3_FEATS + CANDIDATES, pipe.named_steps["r"].coef_))
    sign_ok = True
    for c in CANDIDATES:
        cf = coefs[c]
        ok = cf < 0
        sign_ok &= ok
        print(f"  {c:35s} coef={cf:+.4f}  {'OK' if ok else 'WRONG SIGN'}")

    print("\n=== VERDICT SUMMARY ===")
    print(f"  Bundle Δr:                 {bundle_lift:+.4f}")
    print(f"  Per-year positives:        {sign_match}/{n_total}")
    print(f"  Holdout (2024-25):         {holdout_lift:+.4f}")
    print(f"  All coef signs OK:         {sign_ok}")
    print(f"  Joint > sum-of-marginals?  {'YES' if bundle_lift > sum_marg else 'NO (some overlap)'}")

    if bundle_lift >= 0.005 and sign_match >= 5 and sign_ok and holdout_lift > 0:
        verdict = "PASS (bundle)"
    elif bundle_lift >= 0.005 and sign_match >= 5 and sign_ok:
        verdict = "PASS-NO-HOLDOUT"
    elif bundle_lift > 0:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")


if __name__ == "__main__":
    main()
