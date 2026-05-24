"""Shared helper for MiLB-prior rh3 v3 candidate-feature validation.

Wraps `_validate_rh3_v3_helper.load_and_prep_rh3_inputs()` and merges the
prior-year AAA features (built by build_milb_aaa_priors.py) into the
rolling DataFrame before delegating the actual cross-year evaluation
back into the rh3 helper machinery.

NaN-fill choice (documented in pre-reg): population MEDIAN computed on
the subset of rows that have a prior-year AAA stint (so the fill value
represents "a typical AAA hitter" rather than zero). Baseline and
extended eval run on identical row sets — the only difference is whether
the candidate column is in the feature list.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_v3_helper import load_and_prep_rh3_inputs, per_year_signs  # noqa: E402

from plv_clone.models.xfp import rh3  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PRIORS_CSV = ROOT / "data" / "research" / "xfp_cache" / "milb_aaa_priors.csv"

CANDIDATE_COLS = [
    "milb_aaa_pa_prior",
    "milb_aaa_iso_prior",
    "milb_aaa_kpct_prior",
    "milb_aaa_bbpct_prior",
]


def load_with_milb_priors() -> pd.DataFrame:
    rolling = load_and_prep_rh3_inputs()
    priors = pd.read_csv(PRIORS_CSV)
    rolling = rolling.merge(priors, on=["batter", "year"], how="left")
    # Population MEDIAN over rows that HAVE a prior AAA stint, restricted to
    # training years (no leakage of holdout-year distributions into fill).
    train_mask = rolling["year"].isin(rh3.TRAIN_YEARS)
    for col in CANDIDATE_COLS:
        med = rolling.loc[train_mask & rolling[col].notna(), col].median()
        if pd.isna(med):
            med = 0.0
        rolling[col] = rolling[col].fillna(med)
    return rolling


def run_milb_candidate_eval(candidate: str, *, expected_sign: str) -> dict:
    """Mirror `_validate_rh3_v3_helper.run_candidate_eval` but use the
    rolling DataFrame augmented with prior-year AAA features.
    """
    rolling = load_with_milb_priors()
    assert candidate in rolling.columns, candidate

    feats_base = list(rh3.RH3_FEATS)
    feats_ext = feats_base + [candidate]

    n_missing = rolling[candidate].isna().sum()
    n_with_prior = (
        (rolling[candidate] != rolling.loc[rolling[candidate].notna(), candidate].iloc[0]).sum()
        if len(rolling) > 0
        else 0
    )
    print(f"  candidate '{candidate}': NaN count post-fill = {n_missing}")

    # Headline cross-year eval (all split_days, matches rh3 production)
    print("\n=== Headline cross-year eval (all split_days, matches rh3 production) ===")
    base_per_year, base_overall = rh3.cross_year_eval(rolling, feats_base)
    ext_per_year, ext_overall = rh3.cross_year_eval(rolling, feats_ext)

    print("Baseline RH3_FEATS:")
    for y, r in sorted(base_per_year.items()):
        print(f"  {y}: r={r['r']:.4f}  n={r['n']}")
    print(f"  Overall: r={base_overall['r']:.4f}  n={base_overall['n']}")

    print(f"\nExtended (RH3_FEATS + {candidate}):")
    for y, r in sorted(ext_per_year.items()):
        print(f"  {y}: r={r['r']:.4f}  n={r['n']}")
    print(f"  Overall: r={ext_overall['r']:.4f}  n={ext_overall['n']}")

    delta_r = ext_overall["r"] - base_overall["r"]
    print(f"\n  Δr (extended − baseline) = {delta_r:+.4f}")
    print("  Production gate: >= +0.005 (Rule 9 hard assert).")

    deltas = per_year_signs(ext_per_year, base_per_year)
    positives = sum(1 for _, d in deltas if d > 0)
    print("\n=== Rule 2(b): per-year sign consistency ===")
    for y, d in deltas:
        sym = "(+)" if d > 0 else "(-)" if d < 0 else "(0)"
        print(f"  {y}: Δr = {d:+.4f} {sym}")
    print(f"  Positive years: {positives}/{len(deltas)}  (need >= 5/7 per Rule 2b)")

    holdout = [2024, 2025]
    h_deltas = [(y, d) for (y, d) in deltas if y in holdout]
    h_positives = sum(1 for _, d in h_deltas if d > 0)
    print(f"  Holdout (2024-2025): {h_positives}/{len(h_deltas)} positive")

    # Coefficient sign sanity
    print(f"\n=== Coefficient sign sanity check (expected {expected_sign}) ===")
    pipe, n_train = rh3.train_final(rolling, feats_ext)
    coefs = dict(zip(feats_ext, pipe.named_steps["r"].coef_))
    actual_coef = coefs[candidate]
    sign_ok = (
        (expected_sign == "+" and actual_coef > 0)
        or (expected_sign == "-" and actual_coef < 0)
    )
    print(
        f"  {candidate}: coef={actual_coef:+.4f}  expected={expected_sign}  "
        f"{'OK' if sign_ok else 'WRONG SIGN'}"
    )

    return {
        "baseline_r": base_overall["r"],
        "candidate_r": ext_overall["r"],
        "delta_r": delta_r,
        "per_year_delta": deltas,
        "positives": positives,
        "n_train": base_overall["n"],
        "actual_coef": actual_coef,
        "sign_ok": sign_ok,
        "holdout_positives": h_positives,
        "holdout_total": len(h_deltas),
    }


def emit_verdict(result: dict) -> str:
    if result["delta_r"] >= 0.005 and result["positives"] >= 5 and result["sign_ok"]:
        return "PASS"
    if 0.0 < result["delta_r"] < 0.005:
        return "MARGINAL"
    return "REJECTED"
