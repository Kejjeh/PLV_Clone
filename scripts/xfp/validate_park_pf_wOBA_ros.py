"""Validation script for `park_pf_wOBA_ros` as a rh3 v3 candidate feature.

Pre-registered: data/research/validation_runs/park_pf_wOBA_ros_2026-05-24.md.

Hypothesis: A hitter's home-park wOBA factor (v1 proxy for RoS park
exposure) adds independent predictive lift on RoS FP/PA over the full
RH3_FEATS baseline.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_park_pf_wOBA_ros.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_v3_helper import (  # noqa: E402
    load_and_prep_rh3_inputs,
    run_candidate_eval,
)
from plv_clone.models.xfp import rh3  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PARK_CSV = ROOT / "data" / "research" / "xfp_cache" / "park_factors_2018_2026.csv"
MULTIYR_CSV = ROOT / "data" / "research" / "xfp_cache" / "hitters_multiyr_2015_2026.csv"


def attach_park_pf(rolling: pd.DataFrame) -> pd.DataFrame:
    pf = pd.read_csv(PARK_CSV)[["year", "team_abbr", "pf_wOBA"]]
    team_map = pd.read_csv(MULTIYR_CSV, usecols=["batter", "year", "team"])
    team_map = team_map.rename(columns={"team": "team_abbr"})
    merged = rolling.merge(team_map, on=["batter", "year"], how="left")
    merged = merged.merge(pf, on=["year", "team_abbr"], how="left")
    merged = merged.rename(columns={"pf_wOBA": "park_pf_wOBA_ros"})
    # Fill missing (e.g. multi-team-traded mid-year) with 1.00 (neutral)
    n_missing = merged["park_pf_wOBA_ros"].isna().sum()
    print(f"  park_pf_wOBA_ros missing after join: {n_missing} / {len(merged)} "
          f"({n_missing / max(len(merged), 1):.1%}) — filled with 1.00")
    merged["park_pf_wOBA_ros"] = merged["park_pf_wOBA_ros"].fillna(1.00)
    return merged


def main() -> None:
    print("=== /validate-feature: park_pf_wOBA_ros (rh3 v3 candidate) ===")
    print("Pre-reg: data/research/validation_runs/park_pf_wOBA_ros_2026-05-24.md")
    print()

    # Monkey-patch: helper's run_candidate_eval calls load_and_prep_rh3_inputs
    # internally. We need the candidate attached before its eval, so we
    # replicate the full eval flow inline using the helper's primitives.
    rolling = load_and_prep_rh3_inputs()
    rolling = attach_park_pf(rolling)

    candidate = "park_pf_wOBA_ros"
    feats_base = list(rh3.RH3_FEATS)
    feats_ext = feats_base + [candidate]

    print("\n=== Headline cross-year eval (all split_days) ===")
    base_per_year, base_overall = rh3.cross_year_eval(rolling, feats_base)
    ext_per_year, ext_overall = rh3.cross_year_eval(rolling, feats_ext)

    print("Baseline RH3_FEATS:")
    for y, r in sorted(base_per_year.items()):
        print(f"  {y}: r={r['r']:.4f}  n={r['n']}")
    print(f"  Overall: r={base_overall['r']:.4f}  n={base_overall['n']}")

    print(f"\nExtended (+ {candidate}):")
    for y, r in sorted(ext_per_year.items()):
        print(f"  {y}: r={r['r']:.4f}  n={r['n']}")
    print(f"  Overall: r={ext_overall['r']:.4f}  n={ext_overall['n']}")

    delta_r = ext_overall["r"] - base_overall["r"]
    print(f"\n  Δr (extended − baseline) = {delta_r:+.4f}")

    print("\n=== Rule 2(b): per-year sign consistency ===")
    deltas = []
    for y in sorted(set(ext_per_year) & set(base_per_year)):
        d = ext_per_year[y]["r"] - base_per_year[y]["r"]
        deltas.append((y, d))
        print(f"  {y}: Δr = {d:+.4f} {'(+)' if d > 0 else '(-)' if d < 0 else '(0)'}")
    positives = sum(1 for _, d in deltas if d > 0)
    print(f"  Positive years: {positives}/{len(deltas)}  (need >= 5/7 per Rule 2b)")

    holdout = [2024, 2025]
    h_deltas = [(y, d) for (y, d) in deltas if y in holdout]
    h_positives = sum(1 for _, d in h_deltas if d > 0)
    print(f"  Holdout (2024-2025): {h_positives}/{len(h_deltas)} positive")

    print(f"\n=== Coefficient sign sanity check (expected +) ===")
    pipe, n_train = rh3.train_final(rolling, feats_ext)
    coefs = dict(zip(feats_ext, pipe.named_steps["r"].coef_))
    actual_coef = coefs[candidate]
    sign_ok = actual_coef > 0
    print(f"  {candidate}: coef={actual_coef:+.4f}  {'OK' if sign_ok else 'WRONG SIGN'}")

    print("\n=== VERDICT SUMMARY ===")
    print(f"  baseline cross_year_r:     {base_overall['r']:.4f}")
    print(f"  extended cross_year_r:     {ext_overall['r']:.4f}")
    print(f"  Δr:                        {delta_r:+.4f}")
    print(f"  Per-year positives:        {positives}/{len(deltas)}")
    print(f"  Holdout (2024-25):         {h_positives}/{len(h_deltas)}")
    print(f"  Coef sign:                 {'OK' if sign_ok else 'WRONG'}")

    if delta_r >= 0.005 and positives >= 5 and sign_ok:
        verdict = "PASS"
    elif 0.0 < delta_r < 0.005:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")


if __name__ == "__main__":
    main()
