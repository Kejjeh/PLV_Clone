"""Validation script for `ros_opp_sp_xwoba_weighted` as a rh3 v3 candidate.

Pre-registered: data/research/validation_runs/ros_opp_sp_xwoba_weighted_2026-05-24.md.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_ros_opp_sp_xwoba_weighted.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_v3_helper import (  # noqa: E402
    load_and_prep_rh3_inputs, run_candidate_eval,
)

ROOT = Path(__file__).resolve().parents[2]
SCHED_CSV = (
    ROOT / "data" / "research" / "xfp_cache" / "ros_opp_sp_xwoba_per_hitter.csv"
)
CANDIDATE = "ros_opp_sp_xwoba_weighted"


def attach(rolling: pd.DataFrame) -> pd.DataFrame:
    sched = pd.read_csv(SCHED_CSV)[
        ["batter", "year", "split_day", CANDIDATE]
    ]
    merged = rolling.merge(sched, on=["batter", "year", "split_day"], how="left")
    n_missing = merged[CANDIDATE].isna().sum()
    year_means = merged.groupby("year")[CANDIDATE].transform("mean")
    merged[CANDIDATE] = merged[CANDIDATE].fillna(year_means)
    merged[CANDIDATE] = merged[CANDIDATE].fillna(merged[CANDIDATE].mean())
    print(f"  {CANDIDATE} missing pre-fill: {n_missing}/{len(merged)} "
          f"({n_missing / max(len(merged), 1):.1%}) — filled with year mean")
    return merged


def main() -> None:
    print(f"=== /validate-feature: {CANDIDATE} (rh3 v3 candidate) ===")
    print(f"Pre-reg: data/research/validation_runs/{CANDIDATE}_2026-05-24.md")
    print()

    # Monkey-patch the helper's load to inject our candidate after rh3 prep.
    import _validate_rh3_v3_helper as helper
    orig_load = helper.load_and_prep_rh3_inputs

    def patched_load() -> pd.DataFrame:
        rolling = orig_load()
        return attach(rolling)

    helper.load_and_prep_rh3_inputs = patched_load

    result = run_candidate_eval(
        CANDIDATE,
        expected_sign="+",
        pre_reg_path=ROOT / "data" / "research" / "validation_runs" /
                     f"{CANDIDATE}_2026-05-24.md",
    )

    print("\n=== VERDICT SUMMARY ===")
    lift = result["delta_r"]
    positives = result["positives"]
    n_years = len(result["per_year_delta"])
    sign_ok = result["sign_ok"]
    h_pos = result["holdout_positives"]
    h_tot = result["holdout_total"]
    print(f"  Baseline r:                {result['baseline_r']:.4f}")
    print(f"  Candidate r:               {result['candidate_r']:.4f}")
    print(f"  Δr (lift):                 {lift:+.4f}")
    print(f"  Per-year positives:        {positives}/{n_years}")
    print(f"  Holdout (2024-2025) pos:   {h_pos}/{h_tot}")
    print(f"  Coef:                      {result['actual_coef']:+.4f}  "
          f"({'OK' if sign_ok else 'WRONG SIGN'})")

    if lift >= 0.005 and positives >= 5 and sign_ok:
        verdict = "PASS"
    elif 0.0 < lift < 0.005:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")


if __name__ == "__main__":
    main()
