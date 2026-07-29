"""Validation script for `ros_park_factor_weighted` as a candidate for
BOTH rh3 (expected +) and rp3 (expected -).

Pre-registered:
  data/research/validation_runs/ros_park_factor_weighted_rh3_2026-07-09.md
  data/research/validation_runs/ros_park_factor_weighted_rp3_2026-07-09.md

Multiple testing: 2 model targets tested in one run (Bonferroni family
size 2, disclosed in both pre-registrations; effect-size gate Δr ≥ +0.005
per repo convention).

Run with:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_ros_park_factor.py [rh3|rp3|both]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
CACHE = ROOT / "data" / "research" / "xfp_cache"
HITTER_CSV = CACHE / "ros_park_factor_per_hitter.csv"
PITCHER_CSV = CACHE / "ros_park_factor_per_pitcher.csv"
CANDIDATE = "ros_park_factor_weighted"
NEUTRAL = 1.00


def _attach(rolling: pd.DataFrame, csv: Path, id_col: str) -> pd.DataFrame:
    feat = pd.read_csv(csv)[[id_col, "year", "split_day", CANDIDATE]]
    merged = rolling.merge(feat, on=[id_col, "year", "split_day"], how="left")
    n_missing = merged[CANDIDATE].isna().sum()
    merged[CANDIDATE] = merged[CANDIDATE].fillna(NEUTRAL)
    print(f"  {CANDIDATE} missing pre-fill: {n_missing}/{len(merged)} "
          f"({n_missing / max(len(merged), 1):.1%}) — filled with neutral "
          f"{NEUTRAL:.2f}")
    return merged


def _verdict(lift: float, positives: int, sign_ok: bool,
             holdout_ok: bool) -> str:
    if lift >= 0.005 and positives >= 5 and sign_ok and holdout_ok:
        return "PASS"
    if 0.0 < lift < 0.005:
        return "MARGINAL"
    if lift >= 0.005:  # lift clears but a secondary gate failed
        return "MARGINAL"
    return "REJECTED"


def _cye2(cross_year_eval, df, feats):
    """Tolerant unpack: rh3/rp3 cross_year_eval grew a third `detail`
    return in the 2026-07-04 refactor; the shared validation helpers
    still 2-unpack. Take the first two values whatever the arity."""
    out = cross_year_eval(df, feats)
    return out[0], out[1]


def run_rh3() -> str:
    print("=" * 70)
    print(f"=== /validate-feature: {CANDIDATE} (rh3 candidate, expected +) ===")
    print("Pre-reg: data/research/validation_runs/"
          "ros_park_factor_weighted_rh3_2026-07-09.md")
    print()

    # NOTE: _validate_rh3_v3_helper.run_candidate_eval is stale vs the
    # 2026-07-04 rh3 refactor (cross_year_eval 3-value return). We reuse
    # its production prep (load_and_prep_rh3_inputs) and mirror its eval
    # logic here with the tolerant unpack — additive, no shared edits.
    from _validate_rh3_v3_helper import load_and_prep_rh3_inputs
    from plv_clone.models.xfp import rh3

    rolling = _attach(load_and_prep_rh3_inputs(), HITTER_CSV, "batter")
    feats_base = list(rh3.RH3_FEATS)
    feats_ext = feats_base + [CANDIDATE]

    print("\n=== Headline cross-year eval (all split_days, matches rh3 "
          "production) ===")
    base_py, base_ov = _cye2(rh3.cross_year_eval, rolling, feats_base)
    ext_py, ext_ov = _cye2(rh3.cross_year_eval, rolling, feats_ext)

    print(f"Baseline RH3_FEATS ({len(feats_base)}): "
          f"r={base_ov['r']:.4f} n={base_ov['n']}")
    print(f"Extended (+{CANDIDATE}): r={ext_ov['r']:.4f} n={ext_ov['n']}")
    lift = ext_ov["r"] - base_ov["r"]
    print(f"  Δr (extended − baseline) = {lift:+.4f}  (gate ≥ +0.005)")

    print("\n=== Rule 2(b): per-year sign consistency ===")
    deltas = [(y, ext_py[y]["r"] - base_py[y]["r"])
              for y in sorted(set(ext_py) & set(base_py))]
    positives = sum(1 for _, d in deltas if d > 0)
    for y, d in deltas:
        print(f"  {y}: Δr = {d:+.4f} {'(+)' if d > 0 else '(-)'}")
    print(f"  Positive years: {positives}/{len(deltas)}  (need ≥ 5/7)")

    holdout = [2024, 2025]
    h_deltas = [(y, d) for (y, d) in deltas if y in holdout]
    h_pos = sum(1 for _, d in h_deltas if d > 0)
    h_tot = len(h_deltas)
    print(f"  Holdout (2024-2025): {h_pos}/{h_tot} positive")

    print("\n=== Rule 8: convergence-curve (per split_day) ===")
    for sd in sorted(rolling["split_day"].dropna().unique()):
        sub = rolling[rolling["split_day"] == int(sd)]
        if len(sub) < 200:
            continue
        try:
            _, bo = _cye2(rh3.cross_year_eval, sub, feats_base)
            _, eo = _cye2(rh3.cross_year_eval, sub, feats_ext)
            print(f"  split_day {int(sd)}: base r={bo['r']:.4f}  "
                  f"ext r={eo['r']:.4f}  Δ={eo['r'] - bo['r']:+.4f}  "
                  f"n={bo['n']}")
        except Exception as e:  # noqa: BLE001
            print(f"  split_day {int(sd)}: eval failed — {e}")

    print("\n=== Coefficient sign sanity check (expected +) ===")
    pipe, _n = rh3.train_final(rolling, feats_ext)
    coef = dict(zip(feats_ext, pipe.named_steps["r"].coef_))[CANDIDATE]
    sign_ok = coef > 0
    print(f"  {CANDIDATE}: coef={coef:+.4f}  "
          f"{'OK' if sign_ok else 'WRONG SIGN'}")

    holdout_ok = h_pos == h_tot and h_tot > 0
    print("\n=== VERDICT SUMMARY (rh3) ===")
    print(f"  Baseline r:                {base_ov['r']:.4f}")
    print(f"  Candidate r:               {ext_ov['r']:.4f}")
    print(f"  Δr (lift):                 {lift:+.4f}")
    print(f"  Per-year positives:        {positives}/{len(deltas)}")
    print(f"  Holdout (2024-2025) pos:   {h_pos}/{h_tot}")
    print(f"  Coef:                      {coef:+.4f}  "
          f"({'OK' if sign_ok else 'WRONG SIGN'})")
    verdict = _verdict(lift, positives, sign_ok, holdout_ok)
    print(f"\n  Proposed verdict (rh3): {verdict}")
    return verdict


def run_rp3() -> str:
    print("=" * 70)
    print(f"=== /validate-feature: {CANDIDATE} (rp3 candidate, expected -) ===")
    print("Pre-reg: data/research/validation_runs/"
          "ros_park_factor_weighted_rp3_2026-07-09.md")
    print()

    # NOTE: _rp3_validation_harness.evaluate_candidate is stale vs the
    # 2026-07-04 rp3 refactor (cross_year_eval now returns a third
    # `detail` frame). We use its prep_rolling but run the Rule-9 eval
    # directly here with the 3-value unpack — additive, no shared-infra
    # edits.
    from _rp3_validation_harness import prep_rolling
    from plv_clone.models.xfp.rp3 import (
        RP3_FEATS, cross_year_eval, train_final,
    )
    from plv_clone.paths import ROOT as _R
    sys.path.insert(0, str(_R))
    from scripts.xfp.lib.rule9 import rule9_lift

    rolling = prep_rolling()
    # prep_rolling does not merge the production schedule feature — attach
    # it for Rule 9 baseline parity (mirrors rp3.main() lines ~316-340).
    if "ros_opp_xwoba_weighted" not in rolling.columns:
        sched = pd.read_csv(
            CACHE / "ros_schedule_features_2018_2026.csv"
        )[["pitcher", "year", "split_day", "ros_opp_xwoba_weighted"]]
        rolling = rolling.merge(
            sched, on=["pitcher", "year", "split_day"], how="left"
        )
        year_means = rolling.groupby("year")[
            "ros_opp_xwoba_weighted"
        ].transform("mean")
        rolling["ros_opp_xwoba_weighted"] = rolling[
            "ros_opp_xwoba_weighted"
        ].fillna(year_means)
        rolling["ros_opp_xwoba_weighted"] = rolling[
            "ros_opp_xwoba_weighted"
        ].fillna(rolling["ros_opp_xwoba_weighted"].mean())

    rolling = _attach(rolling, PITCHER_CSV, "pitcher")

    py_base, ov_base, _ = cross_year_eval(rolling, RP3_FEATS)
    py_full, ov_full, _ = cross_year_eval(rolling, RP3_FEATS + [CANDIDATE])
    r9 = rule9_lift(py_base, py_full,
                    r_base=ov_base["r"], r_full=ov_full["r"])
    result = {
        "r_baseline": round(ov_base["r"], 4),
        "r_full": round(ov_full["r"], 4),
        "lift": round(r9["lift"], 4),
        "per_year_lift": r9["per_year_lift"],
        "sign_match_years": r9["sign_match_years"],
        "n_total_years": r9["n_total_years"],
        "holdout_lift": (round(r9["holdout_lift"], 4)
                         if r9["holdout_lift"] is not None else None),
    }

    print(f"\n=== Candidate: {CANDIDATE} (rp3) ===")
    print(f"  Baseline (RP3_FEATS, {len(RP3_FEATS)} feats): "
          f"r={result['r_baseline']} n={ov_base['n']}")
    print(f"  Full     (+ candidate, {len(RP3_FEATS) + 1} feats): "
          f"r={result['r_full']} n={ov_full['n']}")
    print(f"  LIFT = {result['lift']:+.4f}  (gate: >= +0.005)")
    print("\n  Per-year lift (full - baseline):")
    for y, d in result["per_year_lift"].items():
        print(f"    {y}: {d:+.4f}  {'+' if d > 0 else '-'}")
    print(f"\n  Sign consistency: {result['sign_match_years']}/"
          f"{result['n_total_years']} years positive")
    print(f"  Holdout (2024-2025) avg lift: {result['holdout_lift']}")

    print("\n=== Coefficient sign sanity check (expected -) ===")
    pipe, _ = train_final(rolling, RP3_FEATS + [CANDIDATE])
    coefs = dict(zip(RP3_FEATS + [CANDIDATE], pipe.named_steps["r"].coef_))
    coef = coefs[CANDIDATE]
    sign_ok = coef < 0
    print(f"  {CANDIDATE}: coef={coef:+.4f}  "
          f"{'OK' if sign_ok else 'WRONG SIGN'}")

    lift = result["lift"]
    positives = result["sign_match_years"]
    holdout = result["holdout_lift"]
    holdout_ok = holdout is not None and holdout > 0

    print("\n=== VERDICT SUMMARY (rp3) ===")
    print(f"  Baseline r:                {result['r_baseline']:.4f}")
    print(f"  Candidate r:               {result['r_full']:.4f}")
    print(f"  Δr (lift):                 {lift:+.4f}")
    print(f"  Per-year positives:        {positives}/{result['n_total_years']}")
    print(f"  Holdout (2024-25) lift:    {holdout}")
    print(f"  Coef:                      {coef:+.4f}  "
          f"({'OK' if sign_ok else 'WRONG SIGN'})")
    verdict = _verdict(lift, positives, sign_ok, holdout_ok)
    print(f"\n  Proposed verdict (rp3): {verdict}")
    return verdict


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    verdicts = {}
    if which in ("rh3", "both"):
        verdicts["rh3"] = run_rh3()
    if which in ("rp3", "both"):
        verdicts["rp3"] = run_rp3()
    print("\n" + "=" * 70)
    print("=== FINAL (Bonferroni family = 2 targets, both reported) ===")
    for k, v in verdicts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
