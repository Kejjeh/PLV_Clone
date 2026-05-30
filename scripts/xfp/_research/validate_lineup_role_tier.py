"""Validate lineup_role_tier_prior (+ continuous mean_lineup_spot_prior +
top5_share_prior) as candidate features for rh3.

Pre-registered: data/research/validation_runs/lineup_role_tier_rh3_2026-05-30.md.

Treatments tested vs full RH3_FEATS baseline (Rule 9):
  A: baseline only
  B: + mean_lineup_spot_prior         (continuous)
  C: + top5_share_prior               (continuous)
  D: + tier one-hots (5 cols, MIDDLE_ORDER as dropped baseline)
  E: + B + C + D combined

For each: compute pooled cross-year r (rh3.cross_year_eval), per-year delta
vs baseline, holdout (2024, 2025) deltas, and coefficient signs. Verdict
follows the standard 3-part gate.

Run:
    PYTHONIOENCODING=utf-8 python scripts/xfp/_research/validate_lineup_role_tier.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Reach into scripts/xfp/ for the rh3 v3 helper
THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR.parent))  # scripts/xfp/
from _validate_rh3_v3_helper import load_and_prep_rh3_inputs, per_year_signs  # noqa: E402

from plv_clone.models.xfp import rh3  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
LINEUP_CSV = ROOT / "data" / "research" / "xfp_cache" / "hitter_lineup_features_2018_2026.csv"

TIER_CATEGORIES = [
    "LEADOFF",
    "TOP_ORDER",
    "HEART_OF_ORDER",
    "MIDDLE_ORDER",  # treated as baseline (dropped one-hot)
    "BOTTOM_ORDER",
    "ROTATIONAL",
]
TIER_ONEHOTS = [
    f"lineup_role_tier_prior__{t}"
    for t in TIER_CATEGORIES
    if t != "MIDDLE_ORDER"
]


def attach_ros_opp_sp_xwoba(rolling: pd.DataFrame) -> pd.DataFrame:
    """Merge the ros_opp_sp_xwoba_weighted feature — the helper omits this,
    but it IS in RH3_FEATS, so any baseline eval must include it (Rule 9).
    Mirrors src/plv_clone/models/xfp/rh3.py lines ~325-337.
    """
    if not rh3.ROS_OPP_SP_CSV.exists():
        raise FileNotFoundError(rh3.ROS_OPP_SP_CSV)
    opp_sp = pd.read_csv(rh3.ROS_OPP_SP_CSV)[
        ["batter", "year", "split_day", "ros_opp_sp_xwoba_weighted"]
    ]
    rolling = rolling.merge(opp_sp, on=["batter", "year", "split_day"], how="left")
    year_means = rolling.groupby("year")["ros_opp_sp_xwoba_weighted"].transform("mean")
    rolling["ros_opp_sp_xwoba_weighted"] = rolling["ros_opp_sp_xwoba_weighted"].fillna(
        year_means
    )
    rolling["ros_opp_sp_xwoba_weighted"] = rolling["ros_opp_sp_xwoba_weighted"].fillna(
        rolling["ros_opp_sp_xwoba_weighted"].mean()
    )
    return rolling


def build_prior_lineup_features(rolling: pd.DataFrame) -> pd.DataFrame:
    """Merge prior-year (T-1) lineup features onto rolling DataFrame.

    Returns rolling augmented with:
      - mean_lineup_spot_prior (continuous, NaN-filled with train-year median)
      - top5_share_prior      (continuous, NaN-filled with train-year median)
      - lineup_role_tier_prior (categorical, NaN-filled with 'MIDDLE_ORDER')
      - one-hot encodings for TIER_ONEHOTS (5 cols)
    """
    lf = pd.read_csv(LINEUP_CSV)
    # Build a (batter, year_target) view where year_target = year_lineup + 1
    prior = lf.rename(
        columns={
            "year": "_lineup_year",
            "mean_lineup_spot": "mean_lineup_spot_prior",
            "top5_share": "top5_share_prior",
            "lineup_role_tier": "lineup_role_tier_prior",
        }
    )[
        [
            "batter",
            "_lineup_year",
            "mean_lineup_spot_prior",
            "top5_share_prior",
            "lineup_role_tier_prior",
        ]
    ].copy()
    prior["year"] = prior["_lineup_year"] + 1
    prior = prior.drop(columns="_lineup_year")

    merged = rolling.merge(prior, on=["batter", "year"], how="left")

    # NaN fill on continuous columns: training-year median computed only
    # on rows with a real prior (avoid contaminating fill with holdout dist).
    train_mask = merged["year"].isin(rh3.TRAIN_YEARS)
    for col in ("mean_lineup_spot_prior", "top5_share_prior"):
        med = merged.loc[train_mask & merged[col].notna(), col].median()
        if pd.isna(med):
            med = 0.0
        merged[col] = merged[col].fillna(med)
        merged[f"_{col}_was_missing"] = merged[col].isna().astype(int)  # informational

    # Categorical fill: MIDDLE_ORDER (all one-hots zero)
    merged["lineup_role_tier_prior"] = merged["lineup_role_tier_prior"].fillna(
        "MIDDLE_ORDER"
    )

    # One-hot encode (drop MIDDLE_ORDER as reference)
    for t in TIER_CATEGORIES:
        col = f"lineup_role_tier_prior__{t}"
        merged[col] = (merged["lineup_role_tier_prior"] == t).astype(int)

    return merged


def eval_treatment(
    rolling: pd.DataFrame, feats_base: list[str], add_feats: list[str], label: str
) -> dict:
    feats_ext = feats_base + add_feats
    # Drop any rows with NaN in either feat list — use a unified row mask so
    # baseline + extended are evaluated on the same N.
    all_feats = list(set(feats_base) | set(feats_ext))
    sub = rolling.dropna(subset=all_feats + [rh3.TARGET]).copy()
    sub = sub[
        (sub["pa_to"] >= rh3.EVAL_PA_MIN)
        & (sub["ros_pa"] >= rh3.ROS_PA_MIN)
        & (sub["year"] != 2020)
    ]
    base_per_year, base_overall = rh3.cross_year_eval(sub, feats_base)
    ext_per_year, ext_overall = rh3.cross_year_eval(sub, feats_ext)

    deltas = per_year_signs(ext_per_year, base_per_year)
    positives = sum(1 for _, d in deltas if d > 0)
    holdout = [2024, 2025]
    h_deltas = [(y, d) for (y, d) in deltas if y in holdout]
    h_positives = sum(1 for _, d in h_deltas if d > 0)
    h_year_d = dict(h_deltas)

    return {
        "label": label,
        "baseline_r": base_overall["r"],
        "candidate_r": ext_overall["r"],
        "delta_r": ext_overall["r"] - base_overall["r"],
        "per_year_delta": deltas,
        "positives": positives,
        "n_train": base_overall["n"],
        "holdout_2024_delta": h_year_d.get(2024, np.nan),
        "holdout_2025_delta": h_year_d.get(2025, np.nan),
        "holdout_positives": h_positives,
        "holdout_total": len(h_deltas),
        "add_feats": add_feats,
    }


def emit_verdict(result: dict) -> str:
    """Standard 3-part gate.

    PASS: Δr ≥ +0.005 AND per-year positives ≥ 5/7 AND holdout 2/2.
    MARGINAL: 0 < Δr < 0.005.
    REJECTED: Δr ≤ 0 OR fails per-year or holdout.
    """
    dr = result["delta_r"]
    if dr >= 0.005 and result["positives"] >= 5 and result["holdout_positives"] == 2:
        return "PASS"
    if 0.0 < dr < 0.005:
        return "MARGINAL"
    if dr >= 0.005 and (result["positives"] < 5 or result["holdout_positives"] < 2):
        return "MARGINAL (lift OK but secondary gate failed)"
    return "REJECTED"


def main() -> None:
    print("=" * 78)
    print("/validate-feature: lineup_role_tier_prior (rh3 v3 candidate)")
    print("Pre-reg: data/research/validation_runs/lineup_role_tier_rh3_2026-05-30.md")
    print("=" * 78)

    print("\nStep 1: Load rh3 production data prep (RH3_FEATS baseline)...")
    rolling = load_and_prep_rh3_inputs()
    rolling = attach_ros_opp_sp_xwoba(rolling)
    print(f"  rolling rows: {len(rolling):,}")

    print("\nStep 2: Build prior-year lineup features...")
    rolling = build_prior_lineup_features(rolling)

    # Coverage diagnostic
    cov = rolling.groupby("year").agg(
        n_rows=("batter", "size"),
        mean_spot_filled=("mean_lineup_spot_prior", lambda s: s.notna().mean()),
    )
    print("  Coverage by year (mean_lineup_spot_prior non-null fraction):")
    print(cov.to_string())

    # Show tier distribution at year T-1
    tier_dist = rolling.groupby("lineup_role_tier_prior").size().sort_values(ascending=False)
    print("\n  Prior-year tier distribution (full rolling rows):")
    print(tier_dist.to_string())

    feats_base = list(rh3.RH3_FEATS)
    print(f"\nStep 3: Baseline RH3_FEATS ({len(feats_base)} features):")
    for f in feats_base:
        print(f"  - {f}")

    treatments = [
        ("B: + mean_lineup_spot_prior", ["mean_lineup_spot_prior"]),
        ("C: + top5_share_prior", ["top5_share_prior"]),
        ("D: + tier one-hots", TIER_ONEHOTS),
        (
            "E: + mean_spot + top5_share + tier one-hots",
            ["mean_lineup_spot_prior", "top5_share_prior"] + TIER_ONEHOTS,
        ),
    ]

    results = []
    for label, add_feats in treatments:
        print("\n" + "-" * 78)
        print(f"TREATMENT {label}")
        print(f"  add: {add_feats}")
        res = eval_treatment(rolling, feats_base, add_feats, label)
        results.append(res)
        print(f"  baseline r = {res['baseline_r']:.4f}")
        print(f"  extended r = {res['candidate_r']:.4f}")
        print(f"  delta_r    = {res['delta_r']:+.4f}")
        print(f"  per-year:")
        for y, d in res["per_year_delta"]:
            sym = "(+)" if d > 0 else "(-)" if d < 0 else "(0)"
            print(f"    {y}: Δr = {d:+.4f} {sym}")
        print(f"  positives:        {res['positives']}/{len(res['per_year_delta'])}")
        print(f"  holdout 2024 Δr:  {res['holdout_2024_delta']:+.4f}")
        print(f"  holdout 2025 Δr:  {res['holdout_2025_delta']:+.4f}")
        print(f"  holdout positives: {res['holdout_positives']}/{res['holdout_total']}")
        print(f"  verdict: {emit_verdict(res)}")

    # Summary table
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'Treatment':<46} {'Δr':>8} {'pos/7':>6} {'h24':>8} {'h25':>8} {'verdict':<20}")
    for r in results:
        print(
            f"{r['label']:<46} {r['delta_r']:>+8.4f} "
            f"{r['positives']:>2}/{len(r['per_year_delta'])} "
            f"{r['holdout_2024_delta']:>+8.4f} {r['holdout_2025_delta']:>+8.4f} "
            f"{emit_verdict(r):<20}"
        )

    # Coefficient sanity on combined treatment E (the most informative fit)
    print("\nStep 4: Coefficient sanity check on Treatment E (combined)...")
    feats_E = (
        feats_base + ["mean_lineup_spot_prior", "top5_share_prior"] + TIER_ONEHOTS
    )
    sub = rolling.dropna(subset=feats_E + [rh3.TARGET]).copy()
    sub = sub[
        (sub["pa_to"] >= rh3.EVAL_PA_MIN)
        & (sub["ros_pa"] >= rh3.ROS_PA_MIN)
        & (sub["year"] != 2020)
    ]
    pipe, n_train = rh3.train_final(sub, feats_E)
    coefs = dict(zip(feats_E, pipe.named_steps["r"].coef_))
    print(f"  n train = {n_train}")
    for f in ["mean_lineup_spot_prior", "top5_share_prior"] + TIER_ONEHOTS:
        print(f"    {f:<46} coef = {coefs[f]:+.4f}")

    print("\nDone. Update pre-reg with the results + verdict.")


if __name__ == "__main__":
    main()
