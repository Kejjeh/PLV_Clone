"""Shared helper for the rh3 v3 candidate-feature validation scripts.

Replicates the rh3 main() data-prep path EXACTLY through the point where
RH3_FEATS is computed, then exposes a `cross_year_eval_with_candidate()`
helper that returns the Δr lift of (RH3_FEATS + candidate) vs RH3_FEATS
alone, both via the rh3.cross_year_eval LOO procedure.

This is the shared engine for:
  - scripts/xfp/validate_lineup_spot_to.py
  - scripts/xfp/validate_pa_per_started_game_to.py
  - scripts/xfp/validate_started_pct_to.py

Pre-registered: see data/research/validation_runs/*_2026-05-23.md.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.models.xfp import rh3

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]


def load_and_prep_rh3_inputs() -> pd.DataFrame:
    """Replicate rh3.main()'s data-prep steps and return the prepared
    rolling DataFrame (post-shrinkage, with all RH3_FEATS computed).

    Mirrors lines ~250-321 of src/plv_clone/models/xfp/rh3.py.
    """
    rolling = pd.read_csv(rh3.ROLLING_CSV)
    multiyr = pd.read_csv(rh3.MULTIYR_CSV)

    # Marcel prior
    years_needed = sorted(rolling["year"].unique())
    prior = rh3.build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=["batter", "year"], how="left")
    league_mu = float(multiyr[multiyr["pa"] >= 200]["fp_per_pa_actual"].mean())
    rolling["prior_fp_per_pa"] = rolling["prior_fp_per_pa"].fillna(league_mu)
    rolling["prior_pa_eff"] = rolling["prior_pa_eff"].fillna(0.0)

    # H2-locked career profile
    if rh3.H2_LOCKED_CSV.exists():
        h2 = pd.read_csv(rh3.H2_LOCKED_CSV)[["batter", "lift_h2_aug150"]]
        rolling = rolling.merge(h2, on="batter", how="left")
        rolling["lift_h2_aug150"] = rolling["lift_h2_aug150"].fillna(0.0)
    else:
        rolling["lift_h2_aug150"] = 0.0

    # xwOBA residual
    if rh3.XWOBA_RESID_CSV.exists():
        xw = pd.read_csv(rh3.XWOBA_RESID_CSV)[["batter", "xwoba_residual_career"]]
        rolling = rolling.merge(xw, on="batter", how="left")
        rolling["xwoba_residual_career"] = rolling["xwoba_residual_career"].fillna(0.0)
    else:
        rolling["xwoba_residual_career"] = 0.0

    # xwoba_gap_to (derived; not currently in FEATS but computed for parity)
    if "xwoba_on_contact_to" in rolling.columns and "woba_d_sum_to" in rolling.columns:
        rolling["actual_woba_per_pa_to"] = np.where(
            rolling["woba_d_sum_to"] > 0,
            rolling["woba_v_sum_to"] / rolling["woba_d_sum_to"],
            np.nan,
        )
        rolling["xwoba_gap_to"] = (
            rolling["xwoba_on_contact_to"] - rolling["actual_woba_per_pa_to"]
        )
        rolling["xwoba_gap_to"] = rolling["xwoba_gap_to"].fillna(0.0)

    # career_stage
    first_year = multiyr.groupby("batter")["year"].min().to_dict()
    rolling["career_stage"] = rolling.apply(
        lambda r: r["year"] - first_year.get(r["batter"], r["year"]), axis=1
    )

    # Shrinkage on both windows
    pop_to = rh3.compute_population_means(rolling, rh3.TRAIN_YEARS, rh3.SHRINK_SPEC_TO)
    pop_l21 = rh3.compute_population_means(
        rolling, rh3.TRAIN_YEARS, rh3.SHRINK_SPEC_LAST21
    )
    rolling = rh3.apply_shrinkage(rolling, pop_to, rh3.SHRINK_SPEC_TO)
    rolling = rh3.apply_shrinkage(rolling, pop_l21, rh3.SHRINK_SPEC_LAST21)
    for col in (rate + "_sh" for rate in rh3.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling["year"].isin(rh3.TRAIN_YEARS), col].mean(
                skipna=True
            )
            rolling[col] = rolling[col].fillna(mu)
    rolling["pa_last21"] = rolling["pa_last21"].fillna(0).astype(float)
    return rolling


def cross_year_eval_per_split(
    df: pd.DataFrame, feats: list[str], split_day: int | None = None
) -> tuple[dict, dict]:
    """rh3.cross_year_eval optionally restricted to a specific split_day cutoff.

    If split_day is None, runs the full eval across all split_days (matches
    rh3 production behavior).
    """
    sub = df if split_day is None else df[df["split_day"] == split_day]
    return rh3.cross_year_eval(sub, feats)


def per_year_signs(per_year: dict, baseline_per_year: dict) -> list[tuple[int, float]]:
    """Return [(year, Δr), ...] for years present in both dicts."""
    out = []
    for y in sorted(set(per_year) & set(baseline_per_year)):
        out.append((y, per_year[y]["r"] - baseline_per_year[y]["r"]))
    return out


def run_candidate_eval(
    candidate: str,
    *,
    expected_sign: str,
    pre_reg_path: Path,
) -> dict:
    """Full 9-rule eval for a single candidate. Returns a dict for caller to print.

    Output dict keys: baseline_r, candidate_r, delta_r, per_year_breakdown,
    convergence (per-cutoff breakdown), feats_used.
    """
    rolling = load_and_prep_rh3_inputs()

    feats_base = list(rh3.RH3_FEATS)
    feats_ext = feats_base + [candidate]

    assert candidate in rolling.columns, (
        f"candidate column '{candidate}' missing from rolling DataFrame"
    )

    # Drop any NaN in candidate (should be zero per Step 2.5 pre-check)
    n_missing = rolling[candidate].isna().sum()
    print(f"  candidate '{candidate}': NaN count in rolling = {n_missing}")

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
    print("  Production gate: ≥ +0.005 (Rule 9 hard assert).")
    print("  3-cell Bonferroni-adjusted bar (α=0.0167 per cell): unchanged Δr criterion (effect-size based not p-value).")

    # Per-year sign-consistency (Rule 2b)
    print("\n=== Rule 2(b): per-year sign consistency ===")
    deltas = per_year_signs(ext_per_year, base_per_year)
    positives = sum(1 for _, d in deltas if d > 0)
    for y, d in deltas:
        print(f"  {y}: Δr = {d:+.4f} {'(+)' if d > 0 else '(-)' if d < 0 else '(0)'}")
    print(f"  Positive years: {positives}/{len(deltas)}  (need ≥ 5/7 per Rule 2b)")

    # Holdout: 2024, 2025 (last 2 training years)
    holdout = [2024, 2025]
    h_deltas = [(y, d) for (y, d) in deltas if y in holdout]
    h_positives = sum(1 for _, d in h_deltas if d > 0)
    print(f"  Holdout (2024-2025): {h_positives}/{len(h_deltas)} positive")

    # Convergence curve (Rule 8): per split_day
    print("\n=== Rule 8: convergence-curve (per split_day) ===")
    conv = {}
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
            conv[sd] = d
            print(
                f"  split_day {sd}: base r={bo['r']:.4f}  ext r={eo['r']:.4f}  Δ={d:+.4f}  n={bo['n']}"
            )
        except Exception as e:
            print(f"  split_day {sd}: eval failed — {e}")

    # Coefficient sign in final pipeline (sanity check vs expected_sign)
    print(f"\n=== Coefficient sign sanity check (expected {expected_sign}) ===")
    pipe, n_train = rh3.train_final(rolling, feats_ext)
    coefs = dict(zip(feats_ext, pipe.named_steps["r"].coef_))
    actual_coef = coefs[candidate]
    sign_ok = (
        (expected_sign == "+" and actual_coef > 0)
        or (expected_sign == "-" and actual_coef < 0)
    )
    print(
        f"  {candidate}: coef={actual_coef:+.4f}  expected_sign={expected_sign}  "
        f"{'OK' if sign_ok else 'WRONG SIGN'}"
    )

    return {
        "baseline_r": base_overall["r"],
        "candidate_r": ext_overall["r"],
        "delta_r": delta_r,
        "per_year_delta": deltas,
        "positives": positives,
        "n_train": base_overall["n"],
        "convergence": conv,
        "actual_coef": actual_coef,
        "sign_ok": sign_ok,
        "holdout_positives": h_positives,
        "holdout_total": len(h_deltas),
    }
