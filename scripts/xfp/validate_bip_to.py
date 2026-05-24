"""Validation script for `bip_to` as a rh3 v3 candidate feature.

Pre-registered: data/research/validation_runs/bip_to_2026-05-24.md.

Hypothesis: Cumulative balls-in-play count (season-to-date) adds
independent predictive lift on RoS FP/PA over the full RH3_FEATS baseline.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_bip_to.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_v3_helper import run_candidate_eval  # noqa: E402


def main() -> None:
    print("=== /validate-feature: bip_to (rh3 v3 candidate, ceiling audit 2026-05-24) ===")
    print("Pre-reg: data/research/validation_runs/bip_to_2026-05-24.md")
    print()
    result = run_candidate_eval(
        candidate="bip_to",
        expected_sign="+",
        pre_reg_path=Path(__file__).resolve().parents[2]
        / "data"
        / "research"
        / "validation_runs"
        / "bip_to_2026-05-24.md",
    )

    print("\n=== VERDICT SUMMARY ===")
    print(f"  baseline cross_year_r:     {result['baseline_r']:.4f}")
    print(f"  extended cross_year_r:     {result['candidate_r']:.4f}")
    print(f"  Δr (extended − baseline):  {result['delta_r']:+.4f}")
    print(f"  Per-year positives:        {result['positives']}/7")
    print(
        f"  Holdout (2024-25) positives: {result['holdout_positives']}/{result['holdout_total']}"
    )
    print(f"  Coef sign sanity:          {'OK' if result['sign_ok'] else 'WRONG'}")

    if result["delta_r"] >= 0.005 and result["positives"] >= 5 and result["sign_ok"]:
        verdict = "PASS"
    elif 0.0 < result["delta_r"] < 0.005:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")


if __name__ == "__main__":
    main()
