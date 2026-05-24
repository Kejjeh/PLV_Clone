"""Validation script for the rh3 opportunity bundle (3-feature joint test).

Pre-registered: data/research/validation_runs/rh3_opportunity_bundle_2026-05-24.md.

Hypothesis: Three independent signal axes (volume / context / venue) — each
individually MARGINAL or sub-gate vs the full RH3_FEATS baseline — may
clear the +0.005 production gate when fit jointly because Ridge can
compress their collinearity differently than the sum of individual lifts.

Components:
  - pa_per_started_game_to     (volume axis; pre-existing column)
  - lineup_spot_x_split_day    (context axis; interaction lineup_spot_to * split_day)
  - park_pf_wOBA_ros           (venue axis; team-park factor join)

Run with:
    PYTHONIOENCODING=utf-8 python scripts/xfp/validate_rh3_opportunity_bundle.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Make sibling helper importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_v3_helper import load_and_prep_rh3_inputs  # noqa: E402

from plv_clone.models.xfp import rh3  # noqa: E402

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
PARK_FACTOR_CSV = ROOT / "data" / "research" / "xfp_cache" / "park_factors.csv"
MULTIYR_CSV = ROOT / "data" / "research" / "xfp_cache" / "hitters_multiyr_2015_2026.csv"

BUNDLE_FEATS = [
    "pa_per_started_game_to",
    "lineup_spot_x_split_day",
    "park_pf_wOBA_ros",
]


def add_bundle_columns(rolling: pd.DataFrame) -> pd.DataFrame:
    """Compute the 3 bundle columns onto the prepared rolling DataFrame.

    Reuses logic from the 3 individual validation runs:
      - pa_per_started_game_to: already present in rolling cache.
      - lineup_spot_x_split_day: interaction of lineup_spot_to * split_day.
      - park_pf_wOBA_ros: team -> park_factor join via hitters multiyr team
        column for the matching year.
    """
    df = rolling.copy()

    # 1) pa_per_started_game_to — already exists in rolling cache
    assert "pa_per_started_game_to" in df.columns, (
        "pa_per_started_game_to missing from rolling cache; pre-existing column expected"
    )
    n_miss = df["pa_per_started_game_to"].isna().sum()
    if n_miss:
        # Per the pa_per_started_game_to pre-reg, fill NaN with 0 (player never started)
        df["pa_per_started_game_to"] = df["pa_per_started_game_to"].fillna(0.0)

    # 2) lineup_spot_x_split_day = lineup_spot_to * split_day
    assert {"lineup_spot_to", "split_day"}.issubset(df.columns), (
        "lineup_spot_to and/or split_day missing from rolling cache"
    )
    # If lineup_spot_to is NaN (player didn't start), treat as 9 (bottom of lineup)
    df["lineup_spot_to"] = df["lineup_spot_to"].fillna(9.0)
    df["lineup_spot_x_split_day"] = (
        df["lineup_spot_to"].astype(float) * df["split_day"].astype(float)
    )

    # 3) park_pf_wOBA_ros — team -> park factor (static, no year dimension in cache)
    park = pd.read_csv(PARK_FACTOR_CSV)
    park = park.rename(columns={"team_abbr": "team", "park_factor": "park_pf_wOBA_ros"})
    multiyr = pd.read_csv(MULTIYR_CSV, usecols=["batter", "year", "team"])
    # Some batters have multiple rows per (batter,year) when traded mid-year; take
    # the row with most PA. multiyr is at season grain so we just dedupe.
    multiyr = multiyr.drop_duplicates(subset=["batter", "year"], keep="first")
    df = df.merge(multiyr, on=["batter", "year"], how="left")
    df = df.merge(park[["team", "park_pf_wOBA_ros"]], on="team", how="left")
    # Players with unknown team → league-mean park factor (1.0 = neutral)
    league_pf = float(park["park_pf_wOBA_ros"].mean())
    df["park_pf_wOBA_ros"] = df["park_pf_wOBA_ros"].fillna(league_pf)

    return df


def per_year_signs(per_year: dict, baseline_per_year: dict):
    out = []
    for y in sorted(set(per_year) & set(baseline_per_year)):
        out.append((y, per_year[y]["r"] - baseline_per_year[y]["r"]))
    return out


def eval_one(rolling: pd.DataFrame, feats_base: list[str], feats_ext: list[str], label: str):
    print(f"\n--- {label} ---")
    base_per_year, base_overall = rh3.cross_year_eval(rolling, feats_base)
    ext_per_year, ext_overall = rh3.cross_year_eval(rolling, feats_ext)
    delta_r = ext_overall["r"] - base_overall["r"]
    deltas = per_year_signs(ext_per_year, base_per_year)
    positives = sum(1 for _, d in deltas if d > 0)
    print(f"  base r={base_overall['r']:.4f}  ext r={ext_overall['r']:.4f}  Δr={delta_r:+.4f}  n={base_overall['n']}")
    for y, d in deltas:
        print(f"    {y}: Δr={d:+.4f} {'(+)' if d > 0 else '(-)' if d < 0 else '(0)'}")
    print(f"  positives: {positives}/{len(deltas)}")
    holdout = [2024, 2025]
    h_pos = sum(1 for y, d in deltas if y in holdout and d > 0)
    h_tot = sum(1 for y, _ in deltas if y in holdout)
    print(f"  holdout 2024-25: {h_pos}/{h_tot} positive")
    return {
        "delta_r": delta_r,
        "base_r": base_overall["r"],
        "ext_r": ext_overall["r"],
        "deltas": deltas,
        "positives": positives,
        "holdout_positives": h_pos,
        "holdout_total": h_tot,
    }


def main() -> None:
    print("=== /validate-feature: rh3_opportunity_bundle (3-feat joint) ===")
    print("Pre-reg: data/research/validation_runs/rh3_opportunity_bundle_2026-05-24.md")
    print()

    rolling = load_and_prep_rh3_inputs()
    rolling = add_bundle_columns(rolling)

    for col in BUNDLE_FEATS:
        assert col in rolling.columns, f"bundle column '{col}' missing"
        n_miss = rolling[col].isna().sum()
        print(f"  {col}: NaN count = {n_miss}, mean={rolling[col].mean():.4f}, std={rolling[col].std():.4f}")

    feats_base = list(rh3.RH3_FEATS)
    feats_ext = feats_base + BUNDLE_FEATS

    print("\n=== Headline cross-year eval: baseline vs baseline+bundle ===")
    headline = eval_one(rolling, feats_base, feats_ext, "BASELINE vs BASELINE+BUNDLE")

    # Joint-fit coefficients for each bundle component
    print("\n=== Joint-fit coefficients (Rule 9: full-baseline + bundle) ===")
    pipe, _ = rh3.train_final(rolling, feats_ext)
    coefs = dict(zip(feats_ext, pipe.named_steps["r"].coef_))
    for c in BUNDLE_FEATS:
        print(f"  {c}: coef={coefs[c]:+.6f}")

    # Per-split_day breakdown (Rule 8)
    print("\n=== Rule 8: per-split_day Δr breakdown ===")
    for sd in sorted(rolling["split_day"].dropna().unique()):
        sd = int(sd)
        sub = rolling[rolling["split_day"] == sd]
        if len(sub) < 200:
            print(f"  split_day {sd}: n={len(sub)} < 200, skip")
            continue
        try:
            _, bo = rh3.cross_year_eval(sub, feats_base)
            _, eo = rh3.cross_year_eval(sub, feats_ext)
            d = eo["r"] - bo["r"]
            print(f"  split_day {sd}: base r={bo['r']:.4f}  ext r={eo['r']:.4f}  Δ={d:+.4f}  n={bo['n']}")
        except Exception as e:
            print(f"  split_day {sd}: eval failed — {e}")

    # Verdict
    print("\n=== VERDICT SUMMARY ===")
    print(f"  baseline cross_year_r:     {headline['base_r']:.4f}")
    print(f"  extended cross_year_r:     {headline['ext_r']:.4f}")
    print(f"  Δr (bundle - baseline):    {headline['delta_r']:+.4f}")
    print(f"  per-year positives:        {headline['positives']}/{len(headline['deltas'])}")
    print(f"  holdout (2024-25) pos:     {headline['holdout_positives']}/{headline['holdout_total']}")
    print(f"  sum-of-marginals (prior):  +0.0046")
    print(f"  joint-vs-sum delta:        {headline['delta_r'] - 0.0046:+.4f}")

    if headline["delta_r"] >= 0.005 and headline["positives"] >= 5:
        verdict = "PASS"
    elif headline["delta_r"] >= 0.005 and headline["positives"] == 4:
        verdict = "MARGINAL"
    elif 0.0 < headline["delta_r"] < 0.005:
        verdict = "MARGINAL"
    else:
        verdict = "REJECTED"
    print(f"\n  Proposed verdict: {verdict}")

    # Drop-one analysis if PASS
    if verdict == "PASS":
        print("\n=== Rule 6: drop-one analysis (which component is load-bearing) ===")
        for drop in BUNDLE_FEATS:
            sub_ext = feats_base + [c for c in BUNDLE_FEATS if c != drop]
            res = eval_one(rolling, feats_base, sub_ext, f"BUNDLE minus {drop}")
            attrib = headline["delta_r"] - res["delta_r"]
            print(f"  attribution to {drop}: Δr_full - Δr_drop = {attrib:+.4f}")
    else:
        print("  (drop-one analysis skipped — not PASS)")

    print("\n  (User reviews + writes verdict to pre-reg frontmatter.)")


if __name__ == "__main__":
    main()
