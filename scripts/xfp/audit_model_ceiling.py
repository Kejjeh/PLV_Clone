"""audit_model_ceiling.py — empirical model-accuracy-ceiling audit.

For each production xFP model (rh3, rp3, rprs2), runs three ceiling fns:

  1. nonlinear_ceiling — Ridge vs XGB vs RF, same feats/target/cross-year split.
     Verdict: AT_CEILING | MILD_NONLINEARITY | SIGNIFICANT_NONLINEARITY.
  2. linear_ceiling — Ridge alpha sensitivity sweep over 13-point log grid.
     Verdict: STABLE | ALPHA_SENSITIVE.
  3. feature_ceiling — LassoCV on baseline + candidate columns.
     Verdict: BASELINE_OPTIMAL | ADD_CANDIDATES | REPLACE_BASELINE.

The driver builds each model's substrate through the SHARED canonical assembly
(`plv_clone.models.xfp.frames`) — the same code production's `rh3.main()` runs —
so the ceiling fns see exactly the substrate the production model sees. It does
NOT touch the production .pkl bundles or the FEATS lists.

It does not carry its own copy of the prep any more. Before 2026-07-29 it did,
and that copy had silently fallen 2 features + 1 prior-blend behind production
while still reading the LIVE FEATS list (KeyError on rh3/rp3, and a silent-zero
fallback on the #2 and #5 most important rh3 features). See
`docs/rh3_harness_root_bug_2026-07-28.md` for why a copied baseline is a
baseline that will eventually be wrong.

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
import time
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path("c:/Users/Joshua/plv_clone")

from plv_clone.models.xfp import rh3 as rh3_mod
from plv_clone.models.xfp import rp3 as rp3_mod
from plv_clone.models.xfp import rprs2 as rprs2_mod
from plv_clone.models.xfp.ceiling import (
    feature_ceiling,
    linear_ceiling,
    nonlinear_ceiling,
)
from plv_clone.models.xfp.frames import (
    assert_feats_present,
    build_rh3_frame,
    build_rp3_frame,
)

CACHE = ROOT / "data" / "research" / "xfp_cache"


# ---------------------------------------------------------------------------
# Substrate prep per model
#
# 2026-07-29: prep_rh3 / prep_rp3 used to carry their OWN transcription of each
# model's main() prep. Both had rotted behind production — prep_rh3 never
# attached `ros_opp_sp_xwoba_weighted` (promoted 2026-05-24) or `bx_prior_h`
# (2026-07-10), never called `blend_callup_prior` (2026-07-19), and still used
# the `if CSV.exists(): merge else: col = 0.0` SILENT-ZERO fallback on
# `lift_h2_aug150` / `xwoba_residual_career` (ranked #2 and #5 of 22 by
# held-out permutation importance). prep_rp3 was missing
# `ros_opp_xwoba_weighted`. Both now delegate to the ONE canonical assembly in
# `plv_clone.models.xfp.frames`, which raises on a missing cache instead of
# defaulting and self-checks that every FEATS name is a real column.
#
# What remains here is the only thing that is genuinely the audit's business:
# the per-model eval ROW filter (matches each model's cross_year_eval).
# ---------------------------------------------------------------------------
def prep_rh3() -> pd.DataFrame:
    rolling = build_rh3_frame(verbose=False).rolling
    # Apply eval filters (matches cross_year_eval)
    rolling = rolling[
        (rolling["pa_to"] >= rh3_mod.EVAL_PA_MIN)
        & (rolling["ros_pa"] >= rh3_mod.ROS_PA_MIN)
        & (rolling["year"] != 2020)
    ].copy()
    _assert_audit_substrate(rolling, rh3_mod.RH3_FEATS, rh3_mod.TARGET, "rh3")
    return rolling


def prep_rp3() -> pd.DataFrame:
    rolling = build_rp3_frame(verbose=False).rolling
    rolling = rolling[
        (rolling["gs_to"] >= rp3_mod.EVAL_GS_MIN)
        & (rolling["ros_gs"] >= rp3_mod.ROS_GS_MIN)
        & (rolling["year"] != 2020)
    ].copy()
    _assert_audit_substrate(rolling, rp3_mod.RP3_FEATS, rp3_mod.TARGET, "rp3")
    return rolling


def _assert_audit_substrate(
    df: pd.DataFrame, feats: list[str], target: str, name: str
) -> None:
    """Fail loudly if the filtered substrate can't support the audit.

    The point of a ceiling audit is that its baseline r IS the production
    baseline r. A short feature list, a missing target, or an empty frame all
    make the reported number a different quantity wearing the same name — so
    none of them may pass silently.
    """
    assert_feats_present(df, list(feats), label=f"prep_{name}")
    if target not in df.columns:
        raise KeyError(f"prep_{name}: target column '{target}' missing from substrate")
    if df.empty:
        raise RuntimeError(f"prep_{name}: eval filters left 0 rows")
    usable = len(df.dropna(subset=list(feats) + [target]))
    if usable < 500:
        raise RuntimeError(
            f"prep_{name}: only {usable} rows have all {len(feats)} features "
            f"AND the target non-null — too few to audit a ceiling against."
        )


def prep_rprs2() -> pd.DataFrame:
    # rprs2 reads its features straight off its own rolling cache — there is no
    # multi-source assembly to share, and this prep was already producing all
    # 28/28 FEATS. Left as-is; only the substrate assertion is added.
    rolling = pd.read_csv(rprs2_mod.ROLLING_CSV)
    rolling = rolling[
        rolling["year"].isin(rprs2_mod.TRAIN_YEARS) & (rolling["g_to"] >= rprs2_mod.EVAL_G_MIN)
    ].copy()
    _assert_audit_substrate(rolling, rprs2_mod.FEATS_RPRS2, rprs2_mod.TARGET, "rprs2")
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

    print(f"\n=== {name} ceiling audit ===", flush=True)
    print(f"  substrate rows: {len(df)} | baseline feats: {len(feats)} | "
          f"candidate feats considered: {len(candidates)}", flush=True)

    common = dict(
        df=df,
        target_col=target,
        train_years=train_years,
        min_train=min_train,
        min_test=min_test,
    )

    # Progress + timing. The three ceilings take minutes each on the 2026
    # substrate (rh3 is 38k rows x 22 feats, and feature_ceiling refits LassoCV
    # per held year over 70+ columns). A silent multi-minute run is
    # indistinguishable from a hang, so say where we are.
    def _timed(label, fn):
        t0 = time.perf_counter()
        print(f"  [{label}] running...", flush=True)
        out = fn()
        print(f"  [{label}] done in {time.perf_counter() - t0:.0f}s", flush=True)
        return out

    nl = _timed("nonlinear", lambda: nonlinear_ceiling(feats=feats, **common))
    lc = _timed("linear", lambda: linear_ceiling(feats=feats, **common))
    fc = _timed("feature", lambda: feature_ceiling(
        baseline_feats=feats,
        candidate_feats=candidates,
        **common,
    ))

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
        f"Models covered by THIS run: **{', '.join(r['name'] for r in results)}**. "
        "Substrate built through the shared canonical assembly "
        "(`plv_clone.models.xfp.frames`) — the same code `rh3.main()` runs."
    )
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
    parser.add_argument(
        "--models",
        default=None,
        help="comma-separated subset, e.g. 'rh3,rp3' — one report covering just those",
    )
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="skip writing the markdown report (stdout only)",
    )
    args = parser.parse_args()

    known = ["rh3", "rp3", "rprs2"]
    if args.all:
        targets = known
    elif args.models:
        targets = [m.strip() for m in args.models.split(",") if m.strip()]
        bad = [m for m in targets if m not in known]
        if bad:
            parser.error(f"unknown model(s) {bad}; choose from {known}")
    elif args.model:
        targets = [args.model]
    else:
        parser.error("must pass --model X, --models a,b or --all")
    results = []
    for name in targets:
        try:
            results.append(audit_one(name))  # noqa: PERF401
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
