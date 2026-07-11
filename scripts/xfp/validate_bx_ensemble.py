"""
validate_bx_ensemble.py — 4-cell bx-ensemble validation against the FULL
production rh3/rp3 baselines. Prereg (written before this script ran):
data/research/validation_runs/bx_ensemble_2026-07-10.md

Cells: B1 rh3+bx_prior_h | B2 rp3+bx_prior_sp | B3 rh3+bx_age_mult_h |
B4 rp3+bx_age_mult_sp. Joint reports: B1+B3 (rh3), B2+B4 (rp3).

Gates per cell (Bonferroni-4 declared; Δr criterion unchanged, effect-size
based): (1) Δr >= +0.005 vs FULL baseline; (2) per-year sign >= 5/7;
(3) holdout 2024-2025 positive; (4) coef sign '+'.

Run (one leg per invocation to bound runtime):
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_bx_ensemble.py --leg rh3
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_bx_ensemble.py --leg rp3

Results JSON: data/research/validation_runs/bx_ensemble_results_{leg}_2026-07-10.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(ROOT / "src"))

BX_CSV = ROOT / "data" / "research" / "xfp_cache" / "bx_priors_2018_2026.csv"
OUT_DIR = ROOT / "data" / "research" / "validation_runs"

HOLDOUT = (2024, 2025)


def _merge_bx(rolling: pd.DataFrame, key: str, cols: list[str]) -> tuple[pd.DataFrame, dict]:
    """mlbam+year join of bx prior columns; per-year mean fill; join stats."""
    bx = pd.read_csv(BX_CSV)[["mlbam", "year"] + cols].copy()
    bx = bx.rename(columns={"mlbam": key})
    merged = rolling.merge(bx, on=[key, "year"], how="left")
    stats = {}
    for c in cols:
        per_year = {}
        for y, sub in merged.groupby("year"):
            per_year[int(y)] = {
                "n_rows": int(len(sub)),
                "n_matched": int(sub[c].notna().sum()),
                "match_rate": round(float(sub[c].notna().mean()), 4),
            }
        overall = round(float(merged[c].notna().mean()), 4)
        stats[c] = {"overall_match_rate": overall, "per_year": per_year}
        # population-mean fill (per-year mean; prereg'd fallback)
        year_means = merged.groupby("year")[c].transform("mean")
        merged[c] = merged[c].fillna(year_means)
        merged[c] = merged[c].fillna(merged[c].mean())
    return merged, stats


def _gate_eval(name: str, base_py: dict, base_ov: dict, ext_py: dict,
               ext_ov: dict, coef: float, expected_sign: str = "+") -> dict:
    lift = ext_ov["r"] - base_ov["r"]
    per_year = {}
    for y in sorted(set(base_py) & set(ext_py)):
        per_year[int(y)] = round(ext_py[y]["r"] - base_py[y]["r"], 4)
    pos = sum(1 for d in per_year.values() if d > 0)
    ho = [per_year[y] for y in HOLDOUT if y in per_year]
    # Canonical Rule-9 holdout gate (lib/rule9.rule9_lift, used by the rp3
    # harness + every validate_*.py): MEAN lift over 2024-2025 > 0. Per-year
    # holdout values are also reported so a split holdout stays visible.
    ho_mean = float(np.mean(ho)) if ho else np.nan
    ho_pos = bool(ho and ho_mean > 0)
    ho_each_pos = bool(ho and all(d > 0 for d in ho))
    sign_ok = (coef > 0) if expected_sign == "+" else (coef < 0)
    gates = {
        "g1_lift_ge_0.005": bool(lift >= 0.005),
        "g2_signs_5of7": f"{pos}/{len(per_year)} -> {pos >= 5}",
        "g3_holdout_mean_positive": f"mean={ho_mean:+.4f} -> {ho_pos}"
                                    f" (each-year-positive: {ho_each_pos})",
        "g4_coef_sign": f"{coef:+.6f} expected {expected_sign} -> {sign_ok}",
    }
    verdict = "PASS" if (lift >= 0.005 and pos >= 5 and ho_pos and sign_ok) else "REJECTED"
    return {
        "cell": name,
        "r_baseline": base_ov["r"],
        "r_extended": ext_ov["r"],
        "lift": round(lift, 4),
        "n_baseline": base_ov["n"],
        "n_extended": ext_ov["n"],
        "per_year_lift": per_year,
        "positives": pos,
        "holdout_lifts": {int(y): per_year[y] for y in HOLDOUT if y in per_year},
        "holdout_mean_lift": round(ho_mean, 4) if ho else None,
        "holdout_each_year_positive": ho_each_pos,
        "coef": round(float(coef), 6),
        "gates": gates,
        "verdict": verdict,
    }


def _print_cell(res: dict):
    print(f"\n=== {res['cell']} ===")
    print(f"  baseline r={res['r_baseline']:.4f} (n={res['n_baseline']})  "
          f"extended r={res['r_extended']:.4f} (n={res['n_extended']})  "
          f"LIFT={res['lift']:+.4f}")
    for y, d in res["per_year_lift"].items():
        print(f"    {y}: {d:+.4f} {'+' if d > 0 else '-'}")
    for g, v in res["gates"].items():
        print(f"  {g}: {v}")
    print(f"  VERDICT: {res['verdict']}")


def run_rh3() -> dict:
    from _validate_rh3_v3_helper import load_and_prep_rh3_inputs, _cye
    from plv_clone.models.xfp import rh3

    rolling = load_and_prep_rh3_inputs()  # loads the rolling CSV ONCE
    sb_nonzero = float((rolling["sb_per_pa_to"].fillna(0) != 0).mean())
    print(f"rolling_hitters loaded once: {len(rolling)} rows | "
          f"sb_per_pa_to non-zero fraction = {sb_nonzero:.4f} "
          f"({'post-SB-fix vintage' if sb_nonzero > 0.01 else 'pre-SB vintage'})")

    rolling, join_stats = _merge_bx(rolling, "batter",
                                    ["bx_prior_h", "bx_age_mult_h"])

    feats_base = list(rh3.RH3_FEATS)
    print("\nBaseline eval (FULL RH3_FEATS)...")
    b_py, b_ov = _cye(rolling, feats_base)
    print(f"  baseline r={b_ov['r']:.4f} n={b_ov['n']}")

    results = {"leg": "rh3", "sb_per_pa_to_nonzero_frac": sb_nonzero,
               "baseline_r": b_ov["r"], "join_stats": join_stats, "cells": {}}

    for cell, cand in [("B1_bx_prior_h", "bx_prior_h"),
                       ("B3_bx_age_mult_h", "bx_age_mult_h")]:
        print(f"\nExtended eval ({cell})...")
        e_py, e_ov = _cye(rolling, feats_base + [cand])
        pipe, _ = rh3.train_final(rolling, feats_base + [cand])
        coef = dict(zip(feats_base + [cand], pipe.named_steps["r"].coef_))[cand]
        res = _gate_eval(cell, b_py, b_ov, e_py, e_ov, coef)
        _print_cell(res)
        results["cells"][cell] = res

    print("\nJoint eval (B1+B3)...")
    joint_feats = feats_base + ["bx_prior_h", "bx_age_mult_h"]
    j_py, j_ov = _cye(rolling, joint_feats)
    pipe, _ = rh3.train_final(rolling, joint_feats)
    coefs = dict(zip(joint_feats, pipe.named_steps["r"].coef_))
    res = _gate_eval("JOINT_B1_B3", b_py, b_ov, j_py, j_ov,
                     coefs["bx_prior_h"])
    res["joint_coefs"] = {k: round(float(coefs[k]), 6)
                          for k in ("bx_prior_h", "bx_age_mult_h")}
    _print_cell(res)
    results["joint"] = res
    return results


def run_rp3() -> dict:
    from _rp3_validation_harness import prep_rolling, _cye
    from plv_clone.models.xfp import rp3

    rolling = prep_rolling()  # loads the rolling CSV ONCE
    print(f"rolling_pitchers loaded once: {len(rolling)} rows")

    rolling, join_stats = _merge_bx(rolling, "pitcher",
                                    ["bx_prior_sp", "bx_age_mult_sp"])

    feats_base = list(rp3.RP3_FEATS)
    print("\nBaseline eval (FULL RP3_FEATS)...")
    b_py, b_ov = _cye(rolling, feats_base)
    print(f"  baseline r={b_ov['r']:.4f} n={b_ov['n']}")

    results = {"leg": "rp3", "baseline_r": b_ov["r"],
               "join_stats": join_stats, "cells": {}}

    for cell, cand in [("B2_bx_prior_sp", "bx_prior_sp"),
                       ("B4_bx_age_mult_sp", "bx_age_mult_sp")]:
        print(f"\nExtended eval ({cell})...")
        e_py, e_ov = _cye(rolling, feats_base + [cand])
        pipe, _ = rp3.train_final(rolling, feats_base + [cand])
        coef = dict(zip(feats_base + [cand], pipe.named_steps["r"].coef_))[cand]
        res = _gate_eval(cell, b_py, b_ov, e_py, e_ov, coef)
        _print_cell(res)
        results["cells"][cell] = res

    print("\nJoint eval (B2+B4)...")
    joint_feats = feats_base + ["bx_prior_sp", "bx_age_mult_sp"]
    j_py, j_ov = _cye(rolling, joint_feats)
    pipe, _ = rp3.train_final(rolling, joint_feats)
    coefs = dict(zip(joint_feats, pipe.named_steps["r"].coef_))
    res = _gate_eval("JOINT_B2_B4", b_py, b_ov, j_py, j_ov,
                     coefs["bx_prior_sp"])
    res["joint_coefs"] = {k: round(float(coefs[k]), 6)
                          for k in ("bx_prior_sp", "bx_age_mult_sp")}
    _print_cell(res)
    results["joint"] = res
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg", choices=["rh3", "rp3"], required=True)
    args = ap.parse_args()
    if not BX_CSV.exists():
        raise FileNotFoundError(f"{BX_CSV} missing — run build_bx_priors.py first")
    results = run_rh3() if args.leg == "rh3" else run_rp3()
    out = OUT_DIR / f"bx_ensemble_results_{args.leg}_2026-07-10.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
