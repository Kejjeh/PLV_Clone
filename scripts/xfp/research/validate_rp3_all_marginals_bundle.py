"""validate_rp3_all_marginals_bundle.py — 4-feature MARGINAL bundle test.

Pre-registered: data/research/validation_runs/rp3_all_marginals_bundle_2026-05-24.md

Tests whether the 4 individually MARGINAL rp3 candidates, added jointly to
the full RP3_FEATS baseline, clear the +0.005 lift gate as a bundle. The
hypothesis is that the four signals sit in partially-independent axes
(release / recent-CSW / recent-velo / venue) so a joint Ridge fit may
extract more variance than the sum of individual lifts (+0.0034) suggests.

Bundle:
  1. avg_ext_prior          (prior-year mean release extension, ft)
  2. c_plus_swstr_last21    (raw L21 CSW per pitch)
  3. avg_velo_last21        (raw L21 fastball velo, mph)
  4. park_pf_HR_ros         (SP home-park HR factor, v1 proxy)

If PASS: drop-one analysis to identify load-bearing components.
DOES NOT modify RP3_FEATS regardless of verdict.

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_rp3_all_marginals_bundle.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _rp3_validation_harness import prep_rolling, attach_prior_year_feature  # noqa: E402
from validate_park_pf_HR_ros import attach_park_pf  # noqa: E402
from plv_clone.models.xfp.rp3 import RP3_FEATS, cross_year_eval, train_final  # noqa: E402

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
SP_MULTIYR = ROOT / "data" / "research" / "xfp_cache" / "sp_multiyr_2015_2025.csv"

BUNDLE = [
    "avg_ext_prior",
    "c_plus_swstr_last21",
    "avg_velo_last21",
    "park_pf_HR_ros",
]

HOLDOUT = [2024, 2025]


def build_bundle_frame() -> pd.DataFrame:
    print("\nPreparing rolling SP substrate (production rp3 data-prep)...")
    rolling = prep_rolling()
    print(f"  rolling rows: {len(rolling)}")

    # 1. avg_ext_prior
    print("\nAttaching avg_ext_prior from sp_multiyr...")
    rolling = attach_prior_year_feature(
        rolling, str(SP_MULTIYR),
        source_col="avg_ext", new_col="avg_ext_prior", min_gs=5,
    )
    mu_ext = float(rolling["avg_ext_prior"].mean())
    rolling["avg_ext_prior"] = rolling["avg_ext_prior"].fillna(mu_ext)
    print(f"  filled avg_ext_prior NaN with mu={mu_ext:.3f} ft")

    # 2. c_plus_swstr_last21 — already on rolling
    mu_csw = float(rolling["c_plus_swstr_last21"].mean())
    rolling["c_plus_swstr_last21"] = rolling["c_plus_swstr_last21"].fillna(mu_csw)
    print(f"  filled c_plus_swstr_last21 NaN with mu={mu_csw:.4f}")

    # 3. avg_velo_last21 — already on rolling
    mu_velo = float(rolling["avg_velo_last21"].mean())
    rolling["avg_velo_last21"] = rolling["avg_velo_last21"].fillna(mu_velo)
    print(f"  filled avg_velo_last21 NaN with mu={mu_velo:.3f} mph")

    # 4. park_pf_HR_ros — needs team + park join
    print("\nAttaching park_pf_HR_ros...")
    rolling = attach_park_pf(rolling)
    # attach_park_pf already fills NaN with 1.00

    # Sanity: confirm all bundle cols present + no NaN
    for c in BUNDLE:
        if c not in rolling.columns:
            raise RuntimeError(f"bundle column missing: {c}")
        n_nan = int(rolling[c].isna().sum())
        if n_nan:
            raise RuntimeError(f"bundle column {c} has {n_nan} NaN")
    print("\n  All 4 bundle columns present, no NaN remaining.")
    return rolling


def evaluate_bundle(rolling: pd.DataFrame, bundle: list[str], label: str) -> dict:
    py_base, ov_base = cross_year_eval(rolling, RP3_FEATS)
    py_full, ov_full = cross_year_eval(rolling, RP3_FEATS + bundle)
    lift = ov_full["r"] - ov_base["r"]

    sign_match = 0
    n_total = 0
    per_year_lift = {}
    for y in sorted(py_full.keys()):
        if y in py_base:
            d = py_full[y]["r"] - py_base[y]["r"]
            per_year_lift[y] = round(d, 4)
            n_total += 1
            if d > 0:
                sign_match += 1
    ho_full = [py_full[y]["r"] for y in HOLDOUT if y in py_full]
    ho_base = [py_base[y]["r"] for y in HOLDOUT if y in py_base]
    holdout_lift = (
        float(np.mean(ho_full) - np.mean(ho_base))
        if ho_full and ho_base else None
    )
    return {
        "label": label,
        "r_baseline": round(ov_base["r"], 4),
        "r_full": round(ov_full["r"], 4),
        "lift": round(lift, 4),
        "per_year_baseline": {y: round(info["r"], 4) for y, info in sorted(py_base.items())},
        "per_year_full": {y: round(info["r"], 4) for y, info in sorted(py_full.items())},
        "per_year_lift": per_year_lift,
        "sign_match_years": sign_match,
        "n_total_years": n_total,
        "holdout_lift": round(holdout_lift, 4) if holdout_lift is not None else None,
        "n_baseline": ov_base["n"],
        "n_full": ov_full["n"],
    }


def print_report(res: dict, gate: float = 0.005) -> None:
    print(f"\n=== Bundle: {res['label']} ===")
    print(f"  Baseline (RP3_FEATS, {len(RP3_FEATS)} feats):     r={res['r_baseline']} n={res['n_baseline']}")
    print(f"  Full     (+ {len(BUNDLE)} bundle, {len(RP3_FEATS)+len(BUNDLE)} feats): r={res['r_full']} n={res['n_full']}")
    print(f"  LIFT = {res['lift']:+.4f}  (gate: >= +{gate:.3f})")
    print("\n  Per-year lift:")
    for y, d in res["per_year_lift"].items():
        marker = "+" if d > 0 else "-"
        print(f"    {y}: baseline={res['per_year_baseline'].get(y):.4f}  full={res['per_year_full'].get(y):.4f}  Δ={d:+.4f}  {marker}")
    print(f"\n  Sign consistency: {res['sign_match_years']}/{res['n_total_years']} years positive")
    if res["holdout_lift"] is not None:
        print(f"  Holdout (2024-2025) avg lift: {res['holdout_lift']:+.4f}")


def main() -> None:
    print("=== /validate-feature: rp3_all_marginals_bundle ===")
    print("Pre-reg: data/research/validation_runs/rp3_all_marginals_bundle_2026-05-24.md")
    print(f"Bundle ({len(BUNDLE)} features): {BUNDLE}")

    rolling = build_bundle_frame()

    res = evaluate_bundle(rolling, BUNDLE, label="all_marginals_bundle")
    print_report(res, gate=0.005)

    # Joint-fit coefficients
    print("\n=== Joint-fit Ridge coefficients (full RP3_FEATS + bundle) ===")
    pipe, _ = train_final(rolling, RP3_FEATS + BUNDLE)
    coefs = dict(zip(RP3_FEATS + BUNDLE, pipe.named_steps["r"].coef_))
    for c in BUNDLE:
        print(f"  {c:28s}: coef={coefs[c]:+.4f}")

    # Verdict
    lift = res["lift"]
    signs = res["sign_match_years"]
    if lift >= 0.005 and signs >= 5:
        verdict = "PASS"
    elif lift > 0.0 and (lift < 0.005 or signs == 4):
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"

    print("\n=== VERDICT SUMMARY ===")
    print(f"  Bundle Δr (lift):     {lift:+.4f}")
    print(f"  Per-year positives:   {signs}/{res['n_total_years']}")
    print(f"  Holdout (2024-25):    {res['holdout_lift']}")
    print(f"\n  Proposed verdict: {verdict}")

    # Drop-one analysis only on PASS
    if verdict == "PASS":
        print("\n=== Drop-one analysis (identify load-bearing components) ===")
        full_r = res["r_full"]
        for drop in BUNDLE:
            remain = [c for c in BUNDLE if c != drop]
            sub = evaluate_bundle(rolling, remain, label=f"bundle_minus_{drop}")
            delta_vs_full = sub["r_full"] - full_r
            print(f"  drop {drop:28s}: r={sub['r_full']:.4f}  Δ vs full bundle={delta_vs_full:+.4f}  "
                  f"(more negative => more load-bearing)")
    else:
        print("\n  Skipping drop-one analysis (verdict != PASS).")

    print("\n  RP3_FEATS NOT modified — research-only test.")


if __name__ == "__main__":
    main()
