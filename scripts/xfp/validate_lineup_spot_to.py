"""Validation script for `lineup_spot_to` as a rh3 v3 candidate feature.

Pre-registered: data/research/validation_runs/lineup_spot_to_2026-05-23.md.

Hypothesis: Season-to-date PA-weighted lineup spot adds independent
predictive lift on RoS FP/PA over the full RH3_FEATS baseline.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_lineup_spot_to.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sibling helper importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_v3_helper import run_candidate_eval  # noqa: E402


def main() -> None:
    print("=== /validate-feature: lineup_spot_to (rh3 v3 candidate) ===")
    print("Pre-reg: data/research/validation_runs/lineup_spot_to_2026-05-23.md")
    print()
    result = run_candidate_eval(
        candidate="lineup_spot_to",
        expected_sign="-",
        pre_reg_path=Path(__file__).resolve().parents[2]
        / "data"
        / "research"
        / "validation_runs"
        / "lineup_spot_to_2026-05-23.md",
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

    # Verdict logic
    if result["delta_r"] >= 0.005 and result["positives"] >= 5 and result["sign_ok"]:
        verdict = "PASS"
    elif 0.0 < result["delta_r"] < 0.005:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")
    print("  (User reviews + writes verdict to pre-reg frontmatter.)")


if __name__ == "__main__":
    main()
