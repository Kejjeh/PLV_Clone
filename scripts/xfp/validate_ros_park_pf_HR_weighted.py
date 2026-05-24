"""Validation script for `ros_park_pf_HR_weighted` as a rp3 v3 candidate.

Pre-registered: data/research/validation_runs/ros_park_pf_HR_weighted_2026-05-24.md.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_ros_park_pf_HR_weighted.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _rp3_validation_harness import prep_rolling, evaluate_candidate, print_report  # noqa: E402
from plv_clone.models.xfp.rp3 import RP3_FEATS, train_final  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCHED_CSV = ROOT / "data" / "research" / "xfp_cache" / "ros_schedule_features_2018_2026.csv"


def attach(rolling: pd.DataFrame) -> pd.DataFrame:
    sched = pd.read_csv(SCHED_CSV)[["pitcher", "year", "split_day", "ros_park_pf_HR_weighted"]]
    merged = rolling.merge(sched, on=["pitcher", "year", "split_day"], how="left")
    n_missing = merged["ros_park_pf_HR_weighted"].isna().sum()
    merged["ros_park_pf_HR_weighted"] = merged["ros_park_pf_HR_weighted"].fillna(1.00)
    print(f"  ros_park_pf_HR_weighted missing pre-fill: {n_missing}/{len(merged)} "
          f"({n_missing / max(len(merged), 1):.1%}) — filled with neutral 1.00")
    return merged


def main() -> None:
    print("=== /validate-feature: ros_park_pf_HR_weighted (rp3 v3 candidate) ===")
    print("Pre-reg: data/research/validation_runs/ros_park_pf_HR_weighted_2026-05-24.md")
    print()
    rolling = prep_rolling()
    rolling = attach(rolling)

    result = evaluate_candidate(rolling, "ros_park_pf_HR_weighted", fill_value=1.00)
    print_report(result, gate=0.005)

    print("\n=== Coefficient sign sanity check (expected -) ===")
    pipe, _ = train_final(rolling, RP3_FEATS + ["ros_park_pf_HR_weighted"])
    coefs = dict(zip(RP3_FEATS + ["ros_park_pf_HR_weighted"], pipe.named_steps["r"].coef_))
    coef = coefs["ros_park_pf_HR_weighted"]
    sign_ok = coef < 0
    print(f"  ros_park_pf_HR_weighted: coef={coef:+.4f}  {'OK' if sign_ok else 'WRONG SIGN'}")

    print("\n=== VERDICT SUMMARY ===")
    lift = result["lift"]
    signs = result["sign_match_years"]
    print(f"  Δr (lift):                 {lift:+.4f}")
    print(f"  Per-year positives:        {signs}/{result['n_total_years']}")
    print(f"  Holdout (2024-25) lift:    {result['holdout_lift']}")
    print(f"  Coef sign:                 {'OK' if sign_ok else 'WRONG'}")

    if lift >= 0.005 and signs >= 5 and sign_ok:
        verdict = "PASS"
    elif 0.0 < lift < 0.005:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")


if __name__ == "__main__":
    main()
