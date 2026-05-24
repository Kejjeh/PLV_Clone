"""Shared helper for rh3 PIECEWISE candidate validation.

Extends `_validate_rh3_interaction_helper` to support a custom
piecewise/decay transform of an existing rolling-cache column.

The transform is provided as a callable `(df) -> pd.Series`. This
lets us validate step-function (`I[split_day <= X]`) and exponential
decay (`exp(-split_day/τ)`) framings of `lineup_spot_to` without
duplicating the eval/Rule-2b/Rule-8 scaffolding.

Pre-registered: data/research/validation_runs/lineup_spot_early*_2026-05-24.md
and lineup_spot_decay_2026-05-24.md.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_v3_helper import (  # noqa: E402
    load_and_prep_rh3_inputs,
    per_year_signs,
)

from plv_clone.models.xfp import rh3  # noqa: E402


def run_piecewise_eval(
    *,
    name: str,
    transform: Callable[[pd.DataFrame], pd.Series],
    expected_sign: str,
    description: str = "",
) -> dict:
    """Eval a piecewise candidate column `name` = transform(rolling) vs full RH3_FEATS."""
    rolling = load_and_prep_rh3_inputs()

    rolling[name] = transform(rolling).astype(float)

    if rolling[name].isna().any():
        mu = rolling.loc[rolling["year"].isin(rh3.TRAIN_YEARS), name].mean(skipna=True)
        rolling[name] = rolling[name].fillna(mu)

    n_missing = rolling[name].isna().sum()
    print(f"  candidate '{name}' ({description}): NaN after fill = {n_missing}")
    print(
        f"  range: [{rolling[name].min():.4f}, {rolling[name].max():.4f}]  "
        f"mean={rolling[name].mean():.4f}  nonzero={int((rolling[name] != 0).sum())}"
    )

    feats_base = list(rh3.RH3_FEATS)
    feats_ext = feats_base + [name]

    print("\n=== Headline cross-year eval (all split_days) ===")
    base_per_year, base_overall = rh3.cross_year_eval(rolling, feats_base)
    ext_per_year, ext_overall = rh3.cross_year_eval(rolling, feats_ext)

    print("Baseline RH3_FEATS:")
    for y, r in sorted(base_per_year.items()):
        print(f"  {y}: r={r['r']:.4f}  n={r['n']}")
    print(f"  Overall: r={base_overall['r']:.4f}  n={base_overall['n']}")

    print(f"\nExtended (RH3_FEATS + {name}):")
    for y, r in sorted(ext_per_year.items()):
        print(f"  {y}: r={r['r']:.4f}  n={r['n']}")
    print(f"  Overall: r={ext_overall['r']:.4f}  n={ext_overall['n']}")

    delta_r = ext_overall["r"] - base_overall["r"]
    print(f"\n  Δr (extended − baseline) = {delta_r:+.4f}")
    print("  Production gate: ≥ +0.005 (Rule 9).")

    print("\n=== Rule 2(b): per-year sign consistency ===")
    deltas = per_year_signs(ext_per_year, base_per_year)
    positives = sum(1 for _, d in deltas if d > 0)
    for y, d in deltas:
        print(f"  {y}: Δr = {d:+.4f} {'(+)' if d > 0 else '(-)' if d < 0 else '(0)'}")
    print(f"  Positive years: {positives}/{len(deltas)}  (need ≥ 5/7 per Rule 2b)")

    holdout = [2024, 2025]
    h_deltas = [(y, d) for (y, d) in deltas if y in holdout]
    h_positives = sum(1 for _, d in h_deltas if d > 0)
    print(f"  Holdout (2024-2025): {h_positives}/{len(h_deltas)} positive")

    print("\n=== Rule 8: convergence-curve (per split_day) ===")
    conv = {}
    for sd in sorted(rolling["split_day"].dropna().unique()):
        sd = int(sd)
        sub = rolling[rolling["split_day"] == sd]
        if len(sub) < 200:
            continue
        try:
            _, bo = rh3.cross_year_eval(sub, feats_base)
            _, eo = rh3.cross_year_eval(sub, feats_ext)
            d = eo["r"] - bo["r"]
            conv[sd] = d
            print(
                f"  split_day {sd}: base r={bo['r']:.4f}  ext r={eo['r']:.4f}  Δ={d:+.4f}  n={bo['n']}"
            )
        except Exception as e:
            print(f"  split_day {sd}: eval failed — {e}")

    print(f"\n=== Coefficient sign sanity (expected {expected_sign}) ===")
    pipe, _ = rh3.train_final(rolling, feats_ext)
    coefs = dict(zip(feats_ext, pipe.named_steps["r"].coef_))
    actual_coef = float(coefs[name])
    sign_ok = (
        (expected_sign == "+" and actual_coef > 0)
        or (expected_sign == "-" and actual_coef < 0)
    )
    print(
        f"  {name}: coef={actual_coef:+.6f}  expected={expected_sign}  "
        f"{'OK' if sign_ok else 'WRONG SIGN'}"
    )

    if delta_r >= 0.005 and positives >= 5 and sign_ok:
        verdict = "PASS"
    elif delta_r > 0.0 and (positives >= 4 or delta_r < 0.005):
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"

    print("\n=== PROPOSED VERDICT ===")
    print(
        f"  Δr={delta_r:+.4f}  positives={positives}/7  holdout={h_positives}/{len(h_deltas)}  "
        f"sign_ok={sign_ok}  =>  {verdict}"
    )

    return {
        "baseline_r": base_overall["r"],
        "candidate_r": ext_overall["r"],
        "delta_r": delta_r,
        "per_year_delta": deltas,
        "positives": positives,
        "holdout_positives": h_positives,
        "holdout_total": len(h_deltas),
        "n_train": base_overall["n"],
        "convergence": conv,
        "actual_coef": actual_coef,
        "sign_ok": sign_ok,
        "verdict": verdict,
    }
