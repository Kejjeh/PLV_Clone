"""audit_model_ceiling.py — empirical model-accuracy-ceiling audit.

For each production xFP model (rh3, rp3, rprs2), runs three ceiling fns:

  1. nonlinear_ceiling — Ridge vs XGB vs RF, same feats/target/cross-year split.
     Verdict: AT_CEILING | MILD_NONLINEARITY | SIGNIFICANT_NONLINEARITY.
  2. linear_ceiling — Ridge alpha sensitivity sweep over 13-point log grid.
     Verdict: STABLE | ALPHA_SENSITIVE.
  3. feature_ceiling — LassoCV on baseline + candidate columns.
     Verdict: BASELINE_OPTIMAL | ADD_CANDIDATES | REPLACE_BASELINE.

The driver re-runs each model's PREP pipeline (Marcel prior, shrinkage, etc.)
locally so the ceiling fns see the same substrate the production model sees.
It does NOT touch the production .pkl bundles or the FEATS lists.

Usage:
    python -X utf8 scripts/xfp/audit_model_ceiling.py --model rh3
    python -X utf8 scripts/xfp/audit_model_ceiling.py --all

Outputs:
    stdout: per-model ceiling summary (verdicts + headline numbers)
    file:   data/research/ceiling_audit_<YYYY-MM-DD>.md  (one section per model)
"""
from __future__ import annotations
import argparse
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path("c:/Users/Joshua/plv_clone")
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from plv_clone.models.xfp import rh3 as rh3_mod
from plv_clone.models.xfp import rp3 as rp3_mod
from plv_clone.models.xfp import rprs2 as rprs2_mod
from plv_clone.models.xfp.ceiling import (
    feature_ceiling,
    linear_ceiling,
    nonlinear_ceiling,
)

CACHE = ROOT / "data" / "research" / "xfp_cache"


# ---------------------------------------------------------------------------
# Substrate prep per model
# Replicates the prep portion of each model's main() up through shrinkage +
# feature derivation, without fitting or projecting.
# ---------------------------------------------------------------------------
def prep_rh3() -> pd.DataFrame:
    rolling = pd.read_csv(rh3_mod.ROLLING_CSV)
    multiyr = pd.read_csv(rh3_mod.MULTIYR_CSV)

    # Marcel prior
    years_needed = sorted(rolling["year"].unique())
    prior = rh3_mod.build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=["batter", "year"], how="left")
    league_mu = float(multiyr[multiyr["pa"] >= 200]["fp_per_pa_actual"].mean())
    rolling["prior_fp_per_pa"] = rolling["prior_fp_per_pa"].fillna(league_mu)
    rolling["prior_pa_eff"] = rolling["prior_pa_eff"].fillna(0.0)

    # H2-locked career profile feature (mirrors main())
    if rh3_mod.H2_LOCKED_CSV.exists():
        h2 = pd.read_csv(rh3_mod.H2_LOCKED_CSV)[["batter", "lift_h2_aug150"]]
        rolling = rolling.merge(h2, on="batter", how="left")
        rolling["lift_h2_aug150"] = rolling["lift_h2_aug150"].fillna(0.0)
    else:
        rolling["lift_h2_aug150"] = 0.0

    # xwOBA residual career
    if rh3_mod.XWOBA_RESID_CSV.exists():
        xw = pd.read_csv(rh3_mod.XWOBA_RESID_CSV)[["batter", "xwoba_residual_career"]]
        rolling = rolling.merge(xw, on="batter", how="left")
        rolling["xwoba_residual_career"] = rolling["xwoba_residual_career"].fillna(0.0)
    else:
        rolling["xwoba_residual_career"] = 0.0

    # xwoba_gap_to derivation (still computed even though removed from FEATS)
    if "xwoba_on_contact_to" in rolling.columns and "woba_d_sum_to" in rolling.columns:
        rolling["actual_woba_per_pa_to"] = np.where(
            rolling["woba_d_sum_to"] > 0,
            rolling["woba_v_sum_to"] / rolling["woba_d_sum_to"],
            np.nan,
        )
        rolling["xwoba_gap_to"] = (
            rolling["xwoba_on_contact_to"] - rolling["actual_woba_per_pa_to"]
        ).fillna(0.0)
    else:
        rolling["xwoba_gap_to"] = 0.0

    # career_stage
    first_year = multiyr.groupby("batter")["year"].min().to_dict()
    rolling["career_stage"] = rolling.apply(
        lambda r: r["year"] - first_year.get(r["batter"], r["year"]), axis=1
    )

    # Shrinkage on cumulative + last21
    pop_to = rh3_mod.compute_population_means(
        rolling, rh3_mod.TRAIN_YEARS, rh3_mod.SHRINK_SPEC_TO
    )
    pop_l21 = rh3_mod.compute_population_means(
        rolling, rh3_mod.TRAIN_YEARS, rh3_mod.SHRINK_SPEC_LAST21
    )
    rolling = rh3_mod.apply_shrinkage(rolling, pop_to, rh3_mod.SHRINK_SPEC_TO)
    rolling = rh3_mod.apply_shrinkage(rolling, pop_l21, rh3_mod.SHRINK_SPEC_LAST21)
    for col in (rate + "_sh" for rate in rh3_mod.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling["year"].isin(rh3_mod.TRAIN_YEARS), col].mean(
                skipna=True
            )
            rolling[col] = rolling[col].fillna(mu)
    rolling["pa_last21"] = rolling["pa_last21"].fillna(0).astype(float)

    # Apply eval filters (matches cross_year_eval)
    rolling = rolling[
        (rolling["pa_to"] >= rh3_mod.EVAL_PA_MIN)
        & (rolling["ros_pa"] >= rh3_mod.ROS_PA_MIN)
        & (rolling["year"] != 2020)
    ].copy()
    return rolling


def prep_rp3() -> pd.DataFrame:
    rolling = pd.read_csv(rp3_mod.ROLLING_CSV)
    multiyr = pd.read_csv(rp3_mod.MULTIYR_CSV)
    il = pd.read_csv(rp3_mod.IL_CSV)

    # Marcel prior
    prior = rp3_mod.build_prior_table(multiyr, sorted(rolling["year"].unique()))
    rolling = rolling.merge(prior, on=["pitcher", "year"], how="left")
    league_mu = float(multiyr[multiyr["gs"] >= 10]["fp_per_start_actual"].mean())
    rolling["prior_fp_per_start"] = rolling["prior_fp_per_start"].fillna(league_mu)
    rolling["prior_gs_eff"] = rolling["prior_gs_eff"].fillna(0.0)

    # IL merge
    rolling = rolling.merge(il, on=["pitcher", "year", "split_day"], how="left")
    rolling["il_stints_to"] = rolling["il_stints_to"].fillna(0).astype(int)
    rolling["is_on_il_at_split"] = rolling["is_on_il_at_split"].fillna(0).astype(int)
    max_dsr = float(rolling["days_since_il_return"].max(skipna=True) or 200)
    rolling["days_since_il_return_imp"] = rolling["days_since_il_return"].fillna(
        max_dsr + 1
    )

    # Shrinkage
    pop_to = rp3_mod.compute_population_means(
        rolling, rp3_mod.TRAIN_YEARS, rp3_mod.SHRINK_SPEC_TO
    )
    pop_l21 = rp3_mod.compute_population_means(
        rolling, rp3_mod.TRAIN_YEARS, rp3_mod.SHRINK_SPEC_LAST21
    )
    rolling = rp3_mod.apply_shrinkage(rolling, pop_to, rp3_mod.SHRINK_SPEC_TO)
    rolling = rp3_mod.apply_shrinkage(rolling, pop_l21, rp3_mod.SHRINK_SPEC_LAST21)

    # SP drift features
    rolling["delta_velo"] = rolling["avg_velo_last21"] - rolling["avg_velo_to"]
    rolling["delta_swstr"] = rolling["swstr_pct_last21"] - rolling["swstr_pct_to"]
    rolling["delta_k_pct"] = rolling["k_pct_last21"] - rolling["k_pct_to"]
    rolling["delta_bb_pct"] = rolling["bb_pct_last21"] - rolling["bb_pct_to"]
    rolling["delta_chase"] = (
        rolling["o_swing_pct_last21"] - rolling["o_swing_pct_to"]
    )
    rolling["delta_zone"] = rolling["zone_pct_last21"] - rolling["zone_pct_to"]
    for c in (
        "delta_velo",
        "delta_swstr",
        "delta_k_pct",
        "delta_bb_pct",
        "delta_chase",
        "delta_zone",
    ):
        rolling[c] = rolling[c].fillna(0.0)

    for col in (rate + "_sh" for rate in rp3_mod.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling["year"].isin(rp3_mod.TRAIN_YEARS), col].mean(
                skipna=True
            )
            rolling[col] = rolling[col].fillna(mu)
    rolling["gs_last21"] = rolling["gs_last21"].fillna(0)
    rolling["fp_per_start_last21"] = rolling["fp_per_start_last21"].fillna(
        rolling["fp_per_start_to"]
    )

    rolling = rolling[
        (rolling["gs_to"] >= rp3_mod.EVAL_GS_MIN)
        & (rolling["ros_gs"] >= rp3_mod.ROS_GS_MIN)
        & (rolling["year"] != 2020)
    ].copy()
    return rolling


def prep_rprs2() -> pd.DataFrame:
    rolling = pd.read_csv(rprs2_mod.ROLLING_CSV)
    rolling = rolling[
        rolling["year"].isin(rprs2_mod.TRAIN_YEARS) & (rolling["g_to"] >= rprs2_mod.EVAL_G_MIN)
    ].copy()
    return rolling


# ---------------------------------------------------------------------------
# Candidate feature selection
# ---------------------------------------------------------------------------
# Exclude these substrings from the candidate set as "circular" or
# "post-cutoff outcome" — they would trivially correlate with the target.
_CIRCULAR_PATTERNS = (
    "ros_",            # post-cutoff = future = the target side
    "_after",          # post-cutoff totals
    "fp_total_",       # raw FP-formula output
    "core_fp_per_pa",  # the per-PA core target
    "fp_per_start_",   # per-start FP rate (target side for SP)
    "fp_year_total",   # target for rprs2
    "fp_actual",       # actual realized FP (target-side outcome)
    "actual_woba_per_pa_to",  # derivation byproduct (close to target by construction)
)
_ID_OR_TIME_COLS = {
    "year", "split_day", "cutoff_date", "batter", "pitcher",
}


def _is_circular(col: str) -> bool:
    return any(p in col for p in _CIRCULAR_PATTERNS)


def build_candidate_feats(df: pd.DataFrame, baseline_feats: list[str], target_col: str) -> list[str]:
    """Numeric columns NOT in baseline, NOT circular, NOT id/time."""
    baseline_set = set(baseline_feats)
    out = []
    for c in df.columns:
        if c == target_col or c in baseline_set or c in _ID_OR_TIME_COLS:
            continue
        if _is_circular(c):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# Per-model audit
# ---------------------------------------------------------------------------
def audit_one(name: str):
    if name == "rh3":
        df = prep_rh3()
        feats = list(rh3_mod.RH3_FEATS)
        target = rh3_mod.TARGET
        min_train, min_test = 100, 30
    elif name == "rp3":
        df = prep_rp3()
        feats = list(rp3_mod.RP3_FEATS)
        target = rp3_mod.TARGET
        min_train, min_test = 50, 10
    elif name == "rprs2":
        df = prep_rprs2()
        feats = list(rprs2_mod.FEATS_RPRS2)
        target = rprs2_mod.TARGET
        min_train, min_test = 100, 30
    else:
        raise ValueError(f"unknown model: {name}")

    train_years = {
        "rh3": rh3_mod.TRAIN_YEARS,
        "rp3": rp3_mod.TRAIN_YEARS,
        "rprs2": rprs2_mod.TRAIN_YEARS,
    }[name]

    candidates = build_candidate_feats(df, feats, target)
    # Drop candidate columns with extensive NaN — they'd be dropped from
    # cross_year_eval anyway and slow the LassoCV refit. Keep cols where
    # >= 60% of training rows are non-null.
    train_mask = df["year"].isin(train_years)
    keep = []
    for c in candidates:
        valid_share = df.loc[train_mask, c].notna().mean()
        if valid_share >= 0.60:
            keep.append(c)
    candidates = keep
    # Cap candidate count to keep feature_ceiling tractable (<10 min).
    # If we have > 50 candidates, deterministically take the first 50 by name.
    if len(candidates) > 50:
        candidates = sorted(candidates)[:50]

    print(f"\n=== {name} ceiling audit ===")
    print(f"  substrate rows: {len(df)} | baseline feats: {len(feats)} | "
          f"candidate feats considered: {len(candidates)}")

    common = dict(
        df=df,
        target_col=target,
        train_years=train_years,
        min_train=min_train,
        min_test=min_test,
    )
    nl = nonlinear_ceiling(feats=feats, **common)
    lc = linear_ceiling(feats=feats, **common)
    fc = feature_ceiling(
        baseline_feats=feats,
        candidate_feats=candidates,
        **common,
    )

    print(
        f"  nonlinear: ridge={nl.ridge_r:+.4f}  xgb={nl.xgb_r:+.4f}  rf={nl.rf_r:+.4f}  "
        f"xgb_gap={nl.xgb_gap:+.4f}  rf_gap={nl.rf_gap:+.4f}  {nl.verdict}"
    )
    print(
        f"  linear:    alpha={lc.alpha_chosen:.4f}  r_at_chosen={lc.r_at_chosen:+.4f}  "
        f"r_std={lc.r_std_across_alphas:.4f}  {lc.verdict}"
    )
    n_zeroed_baseline = len(set(feats) - set(fc.survived_features))
    print(
        f"  feature:   baseline={fc.baseline_r:+.4f}  extended={fc.extended_r:+.4f}  "
        f"delta={fc.delta_r:+.4f}  {fc.verdict}"
    )
    print(
        f"             survived: {len(fc.survived_features)}/{len(feats) + len(candidates)} feats  "
        f"baseline zeroed: {n_zeroed_baseline}  new feats kept: {len(fc.new_features_kept)}"
    )
    if fc.new_features_kept:
        kept_preview = ", ".join(fc.new_features_kept[:8])
        more = "" if len(fc.new_features_kept) <= 8 else f", +{len(fc.new_features_kept)-8} more"
        print(f"             kept: {kept_preview}{more}")

    zeroed_baseline_feats = sorted(set(feats) - set(fc.survived_features))
    return {
        "name": name,
        "n_rows": len(df),
        "n_feats": len(feats),
        "n_candidates": len(candidates),
        "nonlinear": nl,
        "linear": lc,
        "feature": fc,
        "n_zeroed_baseline": n_zeroed_baseline,
        "zeroed_baseline_feats": zeroed_baseline_feats,
        "feats": feats,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------
def render_md(results: list[dict]) -> str:
    today = date.today().isoformat()
    lines: list[str] = []
    lines.append(f"# xFP model accuracy-ceiling audit — {today}")
    lines.append("")
    lines.append(
        "Per-model empirical ceiling audit using the `plv_clone.models.xfp.ceiling` "
        "toolkit (added 2026-05-23). Three ceilings per model:"
    )
    lines.append("")
    lines.append(
        "1. **NONLINEAR** — Ridge vs XGB vs RF on the same FEATS/target/cross-year "
        "split. Verdict thresholds: max(xgb_gap, rf_gap) < 0.003 → AT_CEILING; "
        "0.003–0.010 → MILD_NONLINEARITY; > 0.010 → SIGNIFICANT_NONLINEARITY."
    )
    lines.append(
        "2. **LINEAR** — Ridge alpha sensitivity across a 13-point log-spaced grid "
        "(`logspace(-1, 5, 13)`). r_std measured over the \"reasonable zone\" "
        "(alphas within 0.05 of peak r). r_std < 0.005 → STABLE."
    )
    lines.append(
        "3. **FEATURE** — LassoCV over (baseline + candidates). Candidates = all "
        "numeric substrate cols not already in baseline, excluding circular ones "
        "(ros_*, *_after, fp_total_*, core_fp_per_pa, fp_per_start_*, etc.) and "
        "candidates with > 40% NaN in training. Up to 50 candidates retained."
    )
    lines.append("")

    for r in results:
        nl = r["nonlinear"]
        lc = r["linear"]
        fc = r["feature"]
        lines.append(f"## {r['name']}")
        lines.append("")
        lines.append(
            f"- substrate rows: **{r['n_rows']}** | baseline feats: **{r['n_feats']}** "
            f"| candidates considered: **{r['n_candidates']}**"
        )
        lines.append("")
        lines.append("### Nonlinear ceiling")
        lines.append("")
        lines.append(f"- ridge_r: `{nl.ridge_r:+.4f}`")
        lines.append(f"- xgb_r:   `{nl.xgb_r:+.4f}` (gap `{nl.xgb_gap:+.4f}`)")
        lines.append(f"- rf_r:    `{nl.rf_r:+.4f}` (gap `{nl.rf_gap:+.4f}`)")
        lines.append(f"- **verdict:** `{nl.verdict}`")
        lines.append("")
        lines.append("### Linear ceiling (alpha sensitivity)")
        lines.append("")
        lines.append(f"- alpha_chosen: `{lc.alpha_chosen:.4f}`")
        lines.append(f"- r_at_chosen:  `{lc.r_at_chosen:+.4f}`")
        lines.append(f"- r_std (reasonable zone): `{lc.r_std_across_alphas:.4f}`")
        lines.append(f"- **verdict:** `{lc.verdict}`")
        lines.append("")
        lines.append("### Feature ceiling (LassoCV)")
        lines.append("")
        lines.append(f"- baseline_r: `{fc.baseline_r:+.4f}`")
        lines.append(f"- extended_r: `{fc.extended_r:+.4f}` (delta `{fc.delta_r:+.4f}`)")
        lines.append(
            f"- baseline feats zeroed: **{r['n_zeroed_baseline']}** / {r['n_feats']}"
        )
        if r["n_zeroed_baseline"] > 0:
            lines.append(
                f"  - zeroed baseline feats: {', '.join(r['zeroed_baseline_feats'])}"
            )
        lines.append(f"- new candidates kept: **{len(fc.new_features_kept)}**")
        if fc.new_features_kept:
            lines.append(f"  - kept: {', '.join(fc.new_features_kept)}")
        lines.append(f"- **verdict:** `{fc.verdict}`")
        lines.append("")

    # Summary table
    lines.append("## Headline summary")
    lines.append("")
    lines.append("| model | ridge_r | xgb_gap | rf_gap | alpha r_std | feat delta | nonlinear | linear | feature |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        nl, lc, fc = r["nonlinear"], r["linear"], r["feature"]
        lines.append(
            f"| {r['name']} | {nl.ridge_r:+.4f} | {nl.xgb_gap:+.4f} | {nl.rf_gap:+.4f} | "
            f"{lc.r_std_across_alphas:.4f} | {fc.delta_r:+.4f} | {nl.verdict} | "
            f"{lc.verdict} | {fc.verdict} |"
        )
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["rh3", "rp3", "rprs2"], default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="skip writing the markdown report (stdout only)",
    )
    args = parser.parse_args()

    if not args.all and args.model is None:
        parser.error("must pass --model {rh3|rp3|rprs2} or --all")

    targets = ["rh3", "rp3", "rprs2"] if args.all else [args.model]
    results = []
    for name in targets:
        try:
            results.append(audit_one(name))
        except Exception as e:
            print(f"\n!!! {name} audit FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            raise

    if not args.no_report:
        md = render_md(results)
        out_path = ROOT / "data" / "research" / f"ceiling_audit_{date.today().isoformat()}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
