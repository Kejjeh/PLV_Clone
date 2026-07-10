"""Validation script for `sprint_speed_lag1` (+ secondary cell
`sprint_speed_delta`) as rh3 candidates.

Pre-registered: data/research/validation_runs/sprint_speed_lag1_2026-07-09.md
(2 cells, Bonferroni 2 — component-test alpha 0.025 per cell; Δr gate
unchanged at +0.005, effect-size based).

Order of operations (per prereg):
  1. Rule 4 component test — partial r of sprint_speed_lag1 with RoS
     SB/PA controlling for sb_per_pa_to_sh + prior_fp_per_pa.
  2. Rule 9 integration — cross_year_eval Δr vs FULL RH3_FEATS via the
     shared helper (production-parity prep).

Run with:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_sprint_speed_lag1.py
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

# ---------------------------------------------------------------------------
# Shim: rh3.cross_year_eval grew a 3rd return value (per-row detail frame,
# audit 2026-07-04) but _validate_rh3_v3_helper still unpacks 2. Wrap the
# module attribute to a 2-tuple BEFORE importing the helper so every helper
# call keeps working. No shared file is modified.
# ---------------------------------------------------------------------------
_orig_cross_year_eval = rh3.cross_year_eval


def _cross_year_eval_2tuple(df, feats):
    out = _orig_cross_year_eval(df, feats)
    return (out[0], out[1]) if isinstance(out, tuple) and len(out) == 3 else out


rh3.cross_year_eval = _cross_year_eval_2tuple

import _validate_rh3_v3_helper as helper  # noqa: E402
from _validate_rh3_v3_helper import run_candidate_eval  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
PRE_REG = (ROOT / "data" / "research" / "validation_runs" /
           "sprint_speed_lag1_2026-07-09.md")
MULTIYR_CSV = CACHE / "hitters_multiyr_2015_2026.csv"

PRIMARY = "sprint_speed_lag1"
SECONDARY = "sprint_speed_delta"


def load_sprint_tables() -> dict[int, pd.Series]:
    tables: dict[int, pd.Series] = {}
    for f in sorted(glob.glob(str(CACHE / "sprint_speed_*.csv"))):
        year = int(re.search(r"(\d{4})", Path(f).name).group(1))
        df = pd.read_csv(f)
        tables[year] = df.set_index("batter")["sprint_speed"]
    return tables


def attach(rolling: pd.DataFrame) -> pd.DataFrame:
    """Attach sprint_speed_lag1 (mean-filled over TRAIN_YEARS merged values)
    and sprint_speed_delta (T-1 minus T-2, 0-filled). Joins by MLBAM id."""
    ss = load_sprint_tables()

    def lookup(offset: int) -> pd.Series:
        def one(row):
            tab = ss.get(int(row["year"]) - offset)
            if tab is None:
                return np.nan
            return tab.get(int(row["batter"]), np.nan)
        return rolling.apply(one, axis=1)

    lag1 = lookup(1)
    lag2 = lookup(2)

    rolling = rolling.copy()
    rolling["_ss_lag1_raw"] = lag1  # pre-fill copy for the component test
    n_miss1 = int(lag1.isna().sum())
    train_mask = rolling["year"].isin(rh3.TRAIN_YEARS)
    mu = float(lag1[train_mask].mean(skipna=True))
    rolling[PRIMARY] = lag1.fillna(mu)
    print(f"  {PRIMARY}: missing pre-fill {n_miss1}/{len(rolling)} "
          f"({n_miss1 / len(rolling):.1%}) — filled with TRAIN_YEARS mean "
          f"{mu:.2f} ft/s")

    delta = lag1 - lag2
    n_missd = int(delta.isna().sum())
    rolling[SECONDARY] = delta.fillna(0.0)
    print(f"  {SECONDARY}: missing pre-fill {n_missd}/{len(rolling)} "
          f"({n_missd / len(rolling):.1%}) — filled 0.0 (neutral)")
    return rolling


def component_test(rolling: pd.DataFrame) -> dict:
    """Rule 4: partial r of raw sprint_speed_lag1 with RoS SB per PA,
    controlling for sb_per_pa_to_sh + prior_fp_per_pa.

    Outcome: (season_sb − sb_to) / ros_pa, clipped ≥ 0, from multiyr season
    SB totals. Eval-eligible TRAIN_YEARS rows with a REAL (non-filled) lag1.
    """
    multiyr = pd.read_csv(MULTIYR_CSV, usecols=["batter", "year", "sb"])
    df = rolling.merge(multiyr.rename(columns={"sb": "season_sb"}),
                       on=["batter", "year"], how="left")
    df = df[(df["pa_to"] >= rh3.EVAL_PA_MIN) & (df["ros_pa"] >= rh3.ROS_PA_MIN)
            & (df["year"].isin(rh3.TRAIN_YEARS)) & (df["year"] != 2020)]
    df = df.dropna(subset=["_ss_lag1_raw", "season_sb", "sb_per_pa_to_sh",
                           "prior_fp_per_pa"])
    df["ros_sb_per_pa"] = ((df["season_sb"] - df["sb_to"]).clip(lower=0)
                           / df["ros_pa"])

    y = df["ros_sb_per_pa"].values
    x = df["_ss_lag1_raw"].values
    C = np.column_stack([np.ones(len(df)),
                         df["sb_per_pa_to_sh"].values,
                         df["prior_fp_per_pa"].values])

    def resid(v):
        beta, *_ = np.linalg.lstsq(C, v, rcond=None)
        return v - C @ beta

    rx, ry = resid(x), resid(y)
    r = float(np.corrcoef(rx, ry)[0, 1])
    n = len(df)
    dof = n - 2 - (C.shape[1] - 1)
    t = r * np.sqrt(dof / max(1e-12, 1 - r * r))
    try:
        from scipy import stats
        p = float(2 * stats.t.sf(abs(t), dof))
    except ImportError:
        from math import erfc, sqrt
        p = float(erfc(abs(t) / sqrt(2)))  # normal approx at this n

    # Context: raw correlation and the control-only benchmark
    r_raw = float(np.corrcoef(x, y)[0, 1])
    r_ctrl = float(np.corrcoef(df["sb_per_pa_to_sh"].values, y)[0, 1])
    print(f"  n = {n} eval-eligible TRAIN_YEARS rows with real lag1")
    print(f"  raw r(sprint_speed_lag1, ros_sb_per_pa)        = {r_raw:+.4f}")
    print(f"  raw r(sb_per_pa_to_sh,  ros_sb_per_pa)         = {r_ctrl:+.4f}")
    print(f"  PARTIAL r (controls: sb_per_pa_to_sh + prior)  = {r:+.4f}  "
          f"t = {t:+.2f}  p = {p:.2e}")
    print(f"  Pre-registered bar: partial r > 0, p < 0.025 (Bonferroni 2) — "
          f"{'PASS' if (r > 0 and p < 0.025) else 'FAIL'}")
    return {"partial_r": r, "p": p, "n": n, "raw_r": r_raw,
            "mechanism_pass": bool(r > 0 and p < 0.025)}


def verdict_for(result: dict) -> str:
    lift = result["delta_r"]
    if (lift >= 0.005 and result["positives"] >= 5 and result["sign_ok"]
            and result["holdout_positives"] == result["holdout_total"]):
        return "PASS"
    if 0.0 < lift < 0.005:
        return "MARGINAL"
    return "REJECTED"


def main() -> None:
    print("=== /validate-feature: sprint_speed_lag1 + sprint_speed_delta "
          "(rh3 candidates, Bonferroni 2) ===")
    print(f"Pre-reg: {PRE_REG.relative_to(ROOT)}")

    # Memoized prep so both cells + component test share one expensive prep.
    _cache: dict[str, pd.DataFrame] = {}
    orig_load = helper.load_and_prep_rh3_inputs

    def patched_load() -> pd.DataFrame:
        if "df" not in _cache:
            _cache["df"] = attach(orig_load())
        return _cache["df"]

    helper.load_and_prep_rh3_inputs = patched_load

    print("\n=== Rule 4: component-level mechanism test (FIRST, per prereg) ===")
    comp = component_test(patched_load())

    results = {}
    for cell in (PRIMARY, SECONDARY):
        print(f"\n{'#' * 70}\n### CELL: {cell}\n{'#' * 70}")
        results[cell] = run_candidate_eval(
            cell, expected_sign="+", pre_reg_path=PRE_REG,
        )

    print("\n=== VERDICT SUMMARY ===")
    print(f"  Component (Rule 4): partial r = {comp['partial_r']:+.4f} "
          f"(p = {comp['p']:.2e}, n = {comp['n']}) — "
          f"{'mechanism PASS' if comp['mechanism_pass'] else 'mechanism FAIL'}")
    for cell, res in results.items():
        v = verdict_for(res)
        print(f"\n  [{cell}]")
        print(f"    Baseline r:              {res['baseline_r']:.4f}")
        print(f"    Candidate r:             {res['candidate_r']:.4f}")
        print(f"    Δr (lift):               {res['delta_r']:+.4f}  (gate ≥ +0.005)")
        print(f"    Per-year positives:      {res['positives']}/{len(res['per_year_delta'])}")
        print(f"    Holdout (2024-25) pos:   {res['holdout_positives']}/{res['holdout_total']}")
        print(f"    Coef:                    {res['actual_coef']:+.6f}  "
              f"({'OK' if res['sign_ok'] else 'WRONG SIGN'})")
        print(f"    Proposed verdict:        {v}")
        if comp["mechanism_pass"] and v != "PASS":
            print("    NOTE (Rule 4): mechanism passed but composite failed — "
                  "diagnostic tie-breaker candidate, do NOT promote.")


if __name__ == "__main__":
    main()
