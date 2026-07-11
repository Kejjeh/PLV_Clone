"""Validation for the LIVE as-of SB feature + sprint-speed complement.

Pre-registered: data/research/validation_runs/sb_asof_feature_2026-07-10.md
(2 cells, Bonferroni 2):

  (a) sb_per_pa_to_sh LIVE — first real test ever (the prior registry PASS
      covered an all-zero column). The feature is ALREADY in RH3_FEATS, so
      the honest framing is FEATS-with-live-sb vs FEATS-with-sb-ZEROED
      (exact replica of the previous dead-column production state; expected
      to reproduce the r=0.6275 anchor).
  (b) sprint_speed_lag1 as COMPLEMENT on top of live-sb FEATS. Third look at
      holdout 2024-25 -> clear-pass bar >= +0.008 with >= 6/7 signs.

Run with:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_sb_asof_live.py
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plv_clone.models.xfp import rh3  # noqa: E402

# Shim: rh3.cross_year_eval returns a 3-tuple since 2026-07-04; the shared
# helper unpacks 2. Same pattern as validate_sprint_speed_lag1.py.
_orig_cross_year_eval = rh3.cross_year_eval


def _cross_year_eval_2tuple(df, feats):
    out = _orig_cross_year_eval(df, feats)
    return (out[0], out[1]) if isinstance(out, tuple) and len(out) == 3 else out


rh3.cross_year_eval = _cross_year_eval_2tuple

import _validate_rh3_v3_helper as helper  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
PRE_REG = (ROOT / "data" / "research" / "validation_runs" /
           "sb_asof_feature_2026-07-10.md")

SB_FEAT = "sb_per_pa_to_sh"
SS_FEAT = "sprint_speed_lag1"
HOLDOUT = [2024, 2025]


def attach_sprint(rolling: pd.DataFrame) -> pd.DataFrame:
    """sprint_speed_lag1: T-1 Savant season sprint speed, TRAIN_YEARS-mean
    filled. Identical construction to validate_sprint_speed_lag1.attach."""
    tables: dict[int, pd.Series] = {}
    for f in sorted(glob.glob(str(CACHE / "sprint_speed_*.csv"))):
        year = int(re.search(r"(\d{4})", Path(f).name).group(1))
        tables[year] = pd.read_csv(f).set_index("batter")["sprint_speed"]

    def one(row):
        tab = tables.get(int(row["year"]) - 1)
        return np.nan if tab is None else tab.get(int(row["batter"]), np.nan)

    lag1 = rolling.apply(one, axis=1)
    n_miss = int(lag1.isna().sum())
    mu = float(lag1[rolling["year"].isin(rh3.TRAIN_YEARS)].mean(skipna=True))
    rolling = rolling.copy()
    rolling[SS_FEAT] = lag1.fillna(mu)
    print(f"  {SS_FEAT}: missing pre-fill {n_miss}/{len(rolling)} "
          f"({n_miss / len(rolling):.1%}) — filled TRAIN_YEARS mean {mu:.2f}")
    return rolling


def eval_pair(df_base: pd.DataFrame, feats_base: list[str],
              df_ext: pd.DataFrame, feats_ext: list[str],
              label: str) -> dict:
    """Cross-year eval of extended vs baseline, per-year signs, holdout."""
    print(f"\n=== {label}: cross-year eval (all split_days) ===")
    base_py, base_ov = helper._cye(df_base, feats_base)
    ext_py, ext_ov = helper._cye(df_ext, feats_ext)
    print("Baseline:")
    for y, r in sorted(base_py.items()):
        print(f"  {y}: r={r['r']:.4f}  n={r['n']}")
    print(f"  Overall: r={base_ov['r']:.4f}  n={base_ov['n']}")
    print("Extended:")
    for y, r in sorted(ext_py.items()):
        print(f"  {y}: r={r['r']:.4f}  n={r['n']}")
    print(f"  Overall: r={ext_ov['r']:.4f}  n={ext_ov['n']}")

    delta = ext_ov["r"] - base_ov["r"]
    deltas = helper.per_year_signs(ext_py, base_py)
    positives = sum(1 for _, d in deltas if d > 0)
    h_deltas = [(y, d) for (y, d) in deltas if y in HOLDOUT]
    h_pos = sum(1 for _, d in h_deltas if d > 0)
    print(f"\n  Δr = {delta:+.4f}")
    for y, d in deltas:
        print(f"  {y}: Δr = {d:+.4f} {'(+)' if d > 0 else '(-)' if d < 0 else '(0)'}")
    print(f"  Positive years: {positives}/{len(deltas)}   "
          f"holdout 2024-25: {h_pos}/{len(h_deltas)}")
    return {"baseline_r": base_ov["r"], "candidate_r": ext_ov["r"],
            "delta_r": delta, "per_year": deltas, "positives": positives,
            "n_years": len(deltas), "holdout_pos": h_pos,
            "holdout_total": len(h_deltas), "n": base_ov["n"]}


def convergence(df_base, feats_base, df_ext, feats_ext) -> dict:
    """Rule 8 convergence curve per split_day (monthly anchors only, to keep
    runtime sane — 30/58/86/114/142/170 span the sample-size regimes)."""
    print("\n=== Rule 8: convergence curve (selected split_days) ===")
    out = {}
    for sd in (30, 58, 86, 114, 142, 170):
        sb = df_base[df_base["split_day"] == sd]
        se = df_ext[df_ext["split_day"] == sd]
        if len(sb) < 200:
            print(f"  split_day {sd}: n={len(sb)} < 200, skip")
            continue
        try:
            _, bo = helper._cye(sb, feats_base)
            _, eo = helper._cye(se, feats_ext)
            d = eo["r"] - bo["r"]
            out[sd] = d
            print(f"  split_day {sd}: base r={bo['r']:.4f}  ext r={eo['r']:.4f}"
                  f"  Δ={d:+.4f}  n={bo['n']}")
        except Exception as e:
            print(f"  split_day {sd}: eval failed — {e}")
    return out


def coef_sign(df: pd.DataFrame, feats: list[str], feat: str) -> float:
    pipe, _ = rh3.train_final(df, feats)
    return float(dict(zip(feats, pipe.named_steps["r"].coef_))[feat])


def main() -> None:
    print("=== /validate-feature: sb_per_pa_to_sh LIVE + sprint_speed_lag1 "
          "complement (Bonferroni 2) ===")
    print(f"Pre-reg: {PRE_REG.relative_to(ROOT)}")

    print("\nPrepping rh3 inputs (production-parity)...")
    live = helper.load_and_prep_rh3_inputs()
    # sanity: the live column must be non-degenerate now
    nz = float((live[SB_FEAT] != 0).mean())
    print(f"  {SB_FEAT}: non-zero share = {nz:.1%}  "
          f"mean = {live[SB_FEAT].mean():.5f}  max = {live[SB_FEAT].max():.4f}")
    assert nz > 0.5, "live sb column still looks degenerate — abort"

    dead = live.copy()
    dead[SB_FEAT] = 0.0   # exact replica of the previous production state

    feats = list(rh3.RH3_FEATS)
    assert SB_FEAT in feats

    # ---------------- CELL (a) ----------------
    print(f"\n{'#' * 70}\n### CELL (a): {SB_FEAT} LIVE vs ZEROED\n{'#' * 70}")
    res_a = eval_pair(dead, feats, live, feats, "cell a")
    conv_a = convergence(dead, feats, live, feats)
    coef_a = coef_sign(live, feats, SB_FEAT)
    sign_ok_a = coef_a > 0
    print(f"\n  final-pipeline coef({SB_FEAT}) = {coef_a:+.5f} "
          f"({'OK' if sign_ok_a else 'WRONG SIGN'})")
    pass_a = (res_a["delta_r"] >= 0.005 and res_a["positives"] >= 5
              and res_a["holdout_pos"] == res_a["holdout_total"] and sign_ok_a)
    verdict_a = ("PASS" if pass_a
                 else "MARGINAL" if 0 < res_a["delta_r"] < 0.005
                 else "REJECTED")

    # ---------------- CELL (b) ----------------
    print(f"\n{'#' * 70}\n### CELL (b): {SS_FEAT} on top of live-sb FEATS\n{'#' * 70}")
    live_ss = attach_sprint(live)
    feats_b = feats + [SS_FEAT]
    res_b = eval_pair(live_ss, feats, live_ss, feats_b, "cell b")
    conv_b = convergence(live_ss, feats, live_ss, feats_b)
    coef_b = coef_sign(live_ss, feats_b, SS_FEAT)
    sign_ok_b = coef_b > 0
    print(f"\n  final-pipeline coef({SS_FEAT}) = {coef_b:+.5f} "
          f"({'OK' if sign_ok_b else 'WRONG SIGN'})")
    clear_b = (res_b["delta_r"] >= 0.008 and res_b["positives"] >= 6
               and res_b["holdout_pos"] == res_b["holdout_total"] and sign_ok_b)
    verdict_b = ("PASS" if clear_b
                 else "MARGINAL" if res_b["delta_r"] >= 0.005
                 else "MARGINAL(sub-gate)" if res_b["delta_r"] > 0
                 else "REJECTED")

    # ---------------- summary ----------------
    print("\n=== VERDICT SUMMARY ===")
    for name, res, conv, coef, v, bar in (
            (f"(a) {SB_FEAT} live-vs-zeroed", res_a, conv_a, coef_a, verdict_a,
             ">= +0.005, >=5/7, holdout 2/2"),
            (f"(b) {SS_FEAT} complement", res_b, conv_b, coef_b, verdict_b,
             "CLEAR >= +0.008, >=6/7, holdout 2/2 (3rd look)")):
        print(f"\n  [{name}]  bar: {bar}")
        print(f"    Baseline r:            {res['baseline_r']:.4f}")
        print(f"    Candidate r:           {res['candidate_r']:.4f}")
        print(f"    Δr:                    {res['delta_r']:+.4f}")
        print(f"    Signs:                 {res['positives']}/{res['n_years']}")
        print(f"    Holdout 2024-25:       {res['holdout_pos']}/{res['holdout_total']}")
        print(f"    Coef:                  {coef:+.5f}")
        print(f"    Convergence Δ by split: "
              f"{ {k: round(v_, 4) for k, v_ in conv.items()} }")
        print(f"    VERDICT:               {v}")


if __name__ == "__main__":
    main()
