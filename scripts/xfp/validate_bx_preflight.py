"""
validate_bx_preflight.py — B1 (rh3 + bx_prior_h) pre-flight rerun on the
CURRENT rolling cache (BUILDER_VERSION 3, live sb_per_pa_to_sh).

Recipe step 6 of data/research/validation_runs/bx_ensemble_2026-07-10.md:
re-run B1 on the post-SB substrate before promotion. Decision rule (written
into that doc BEFORE this script ran):

  PROMOTE            iff lift >= +0.005 AND holdout MEAN (2024-2025) > 0
  MARGINAL-ON-PREFLIGHT  if lift in [+0.003, +0.005)  -> STOP, no promotion
  SUPERSEDED-BY-SB       if lift <  +0.003            -> STOP

Focused B1-only rerun reusing validate_bx_ensemble.py machinery; writes
data/research/validation_runs/bx_preflight_results_2026-07-10.json (the
original bx_ensemble_results_rh3_2026-07-10.json is NOT overwritten).

Run: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -X utf8 scripts/xfp/validate_bx_preflight.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(ROOT / "src"))

from validate_bx_ensemble import _merge_bx, _gate_eval, _print_cell, OUT_DIR  # noqa: E402
from _validate_rh3_v3_helper import load_and_prep_rh3_inputs, _cye  # noqa: E402
from plv_clone.models.xfp import rh3  # noqa: E402


def main() -> None:
    rolling = load_and_prep_rh3_inputs()  # loads rolling CSV ONCE
    sb_nonzero = float((rolling["sb_per_pa_to"].fillna(0) != 0).mean())
    print(f"rolling_hitters loaded once: {len(rolling)} rows | "
          f"sb_per_pa_to non-zero fraction = {sb_nonzero:.4f} "
          f"({'post-SB-fix vintage' if sb_nonzero > 0.01 else 'pre-SB vintage'})")

    rolling, join_stats = _merge_bx(rolling, "batter", ["bx_prior_h"])

    feats_base = list(rh3.RH3_FEATS)
    print(f"\nBaseline eval (FULL RH3_FEATS, {len(feats_base)} features, "
          f"incl. live sb_per_pa_to_sh)...")
    b_py, b_ov = _cye(rolling, feats_base)
    print(f"  baseline r={b_ov['r']:.4f} n={b_ov['n']} (expected ~0.6343)")

    print("\nExtended eval (B1_preflight: + bx_prior_h)...")
    e_py, e_ov = _cye(rolling, feats_base + ["bx_prior_h"])
    pipe, _ = rh3.train_final(rolling, feats_base + ["bx_prior_h"])
    coef = dict(zip(feats_base + ["bx_prior_h"],
                    pipe.named_steps["r"].coef_))["bx_prior_h"]
    res = _gate_eval("B1_PREFLIGHT_bx_prior_h", b_py, b_ov, e_py, e_ov, coef)
    _print_cell(res)

    lift = res["lift"]
    ho_mean = res["holdout_mean_lift"]
    if lift >= 0.005 and ho_mean is not None and ho_mean > 0:
        decision = "PROMOTE"
    elif 0.003 <= lift < 0.005:
        decision = "MARGINAL-ON-PREFLIGHT (STOP, no promotion)"
    elif lift < 0.003:
        decision = "SUPERSEDED-BY-SB (STOP)"
    else:  # lift >= 0.005 but holdout mean non-positive
        decision = "STOP (lift clears but holdout mean non-positive)"
    print(f"\nPRE-FLIGHT DECISION: {decision}")

    out = {
        "run": "B1 pre-flight on BUILDER_VERSION-3 (live-SB) rolling cache",
        "sb_per_pa_to_nonzero_frac": sb_nonzero,
        "join_stats": join_stats,
        "cell": res,
        "decision_rule": ("PROMOTE iff lift >= +0.005 AND holdout mean "
                          "(2024-2025) > 0; [+0.003,+0.005) MARGINAL-STOP; "
                          "< +0.003 superseded-by-SB"),
        "decision": decision,
    }
    path = OUT_DIR / "bx_preflight_results_2026-07-10.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
