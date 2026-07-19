"""
validate_bx_sp_composite.py — ONE pre-registered cell: rp3 + bx_sp_composite.
Prereg (written before this script):
data/research/validation_runs/bx_sp_composite_2026-07-10.md

Construction (fixed a priori, no sweep):
  bx_sp_composite = bx_prior_sp + (bx_age_mult_sp - mean_year(bx_age_mult_sp))
computed on the bx CSV's SP prediction rows before the merge.

Elevated gates (2nd look at the 2024-25 holdout for this family):
  (1) pooled lift >= +0.005 vs FULL RP3_FEATS
  (2) per-year signs >= 6/7
  (3) holdout 2024 AND 2025 EACH individually positive
  (4) final-pipe coef +

Run: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_bx_sp_composite.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

BX_CSV = ROOT / "data" / "research" / "xfp_cache" / "bx_priors_2018_2026.csv"
OUT_JSON = (ROOT / "data" / "research" / "validation_runs"
            / "bx_sp_composite_results_2026-07-10.json")
HOLDOUT = (2024, 2025)
CAND = "bx_sp_composite"


def build_composite() -> pd.DataFrame:
    """Composite on the CSV's SP prediction rows (pre-merge, per prereg)."""
    bx = pd.read_csv(BX_CSV)
    sp = bx.dropna(subset=["bx_prior_sp"]).copy()
    yr_mean = sp.groupby("year")["bx_age_mult_sp"].transform("mean")
    sp[CAND] = sp["bx_prior_sp"] + (sp["bx_age_mult_sp"] - yr_mean)
    # rows with a prior but (theoretically) no age level: fall back to prior
    sp[CAND] = sp[CAND].fillna(sp["bx_prior_sp"])
    return sp[["mlbam", "year", CAND]]


def main():
    from _rp3_validation_harness import prep_rolling, _cye
    from plv_clone.models.xfp import rp3

    rolling = prep_rolling()  # rolling CSV loaded ONCE
    print(f"rolling_pitchers loaded once: {len(rolling)} rows")

    comp = build_composite()
    print(f"composite built on {len(comp)} SP CSV rows "
          f"(mean={comp[CAND].mean():.4f}, std={comp[CAND].std():.4f})")

    merged = rolling.merge(comp.rename(columns={"mlbam": "pitcher"}),
                           on=["pitcher", "year"], how="left")
    join_stats = {}
    for y, sub in merged.groupby("year"):
        join_stats[int(y)] = {
            "n_rows": int(len(sub)),
            "match_rate": round(float(sub[CAND].notna().mean()), 4),
        }
    overall_rate = round(float(merged[CAND].notna().mean()), 4)
    print(f"join rate before fill: overall {overall_rate:.1%}")
    for y, s in join_stats.items():
        print(f"  {y}: {s['match_rate']:.1%} of {s['n_rows']}")
    # per-year mean fill, then global mean (prereg'd, mirrors _merge_bx)
    year_means = merged.groupby("year")[CAND].transform("mean")
    merged[CAND] = merged[CAND].fillna(year_means)
    merged[CAND] = merged[CAND].fillna(merged[CAND].mean())

    feats_base = list(rp3.RP3_FEATS)
    print(f"\nBaseline eval (FULL RP3_FEATS, {len(feats_base)} feats)...")
    b_py, b_ov = _cye(merged, feats_base)
    print(f"  baseline r={b_ov['r']:.4f} n={b_ov['n']}")

    print(f"\nExtended eval (+ {CAND})...")
    e_py, e_ov = _cye(merged, feats_base + [CAND])
    print(f"  extended r={e_ov['r']:.4f} n={e_ov['n']}")

    pipe, _ = rp3.train_final(merged, feats_base + [CAND])
    coef = float(dict(zip(feats_base + [CAND],
                          pipe.named_steps["r"].coef_))[CAND])

    lift = e_ov["r"] - b_ov["r"]
    per_year = {int(y): round(e_py[y]["r"] - b_py[y]["r"], 4)
                for y in sorted(set(b_py) & set(e_py))}
    pos = sum(1 for d in per_year.values() if d > 0)
    ho = {int(y): per_year[y] for y in HOLDOUT if y in per_year}
    ho_each_pos = bool(ho) and all(d > 0 for d in ho.values())
    ho_mean = float(np.mean(list(ho.values()))) if ho else float("nan")

    gates = {
        "g1_lift_ge_0.005": bool(lift >= 0.005),
        "g2_signs_6of7_elevated": f"{pos}/{len(per_year)} -> {pos >= 6}",
        "g3_holdout_each_year_positive_elevated":
            f"{ho} -> {ho_each_pos} (mean={ho_mean:+.4f})",
        "g4_coef_positive": f"{coef:+.6f} -> {coef > 0}",
    }
    verdict = ("PASS" if (lift >= 0.005 and pos >= 6 and ho_each_pos
                          and coef > 0) else "FAIL")

    print(f"\n=== bx_sp_composite (ONE pre-registered cell, elevated bar) ===")
    print(f"  baseline r={b_ov['r']:.4f}  extended r={e_ov['r']:.4f}  "
          f"LIFT={lift:+.4f}")
    for y, d in per_year.items():
        print(f"    {y}: {d:+.4f} {'+' if d > 0 else '-'}")
    for g, v in gates.items():
        print(f"  {g}: {v}")
    print(f"  VERDICT: {verdict}")

    results = {
        "cell": CAND,
        "construction": "bx_prior_sp + (bx_age_mult_sp - mean_year(bx_age_mult_sp))",
        "baseline_r": round(float(b_ov["r"]), 4),
        "extended_r": round(float(e_ov["r"]), 4),
        "lift": round(float(lift), 4),
        "n_baseline": int(b_ov["n"]),
        "n_extended": int(e_ov["n"]),
        "per_year_lift": per_year,
        "positives": pos,
        "holdout_lifts": ho,
        "holdout_mean_lift": round(ho_mean, 4),
        "holdout_each_year_positive": ho_each_pos,
        "coef": round(coef, 6),
        "join_rate_overall": overall_rate,
        "join_rate_per_year": join_stats,
        "gates": gates,
        "verdict": verdict,
    }
    OUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
