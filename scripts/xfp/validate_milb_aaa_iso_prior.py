"""Validation: milb_aaa_iso_prior as a rh3 v3 candidate feature.

Pre-reg: data/research/validation_runs/milb_aaa_iso_prior_2026-05-24.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_milb_helper import emit_verdict, run_milb_candidate_eval  # noqa: E402


def main() -> None:
    print("=== /validate-feature: milb_aaa_iso_prior (rh3 v3 candidate, MiLB data layer 2026-05-24) ===")
    print("Pre-reg: data/research/validation_runs/milb_aaa_iso_prior_2026-05-24.md")
    print()
    result = run_milb_candidate_eval("milb_aaa_iso_prior", expected_sign="+")

    print("\n=== VERDICT SUMMARY ===")
    print(f"  baseline cross_year_r:       {result['baseline_r']:.4f}")
    print(f"  extended cross_year_r:       {result['candidate_r']:.4f}")
    print(f"  delta r:                     {result['delta_r']:+.4f}")
    print(f"  Per-year positives:          {result['positives']}/7")
    print(
        f"  Holdout (2024-25) positives: {result['holdout_positives']}/{result['holdout_total']}"
    )
    print(f"  Coef sign sanity:            {'OK' if result['sign_ok'] else 'WRONG'}")
    print(f"\n  Proposed verdict: {emit_verdict(result)}")


if __name__ == "__main__":
    main()
