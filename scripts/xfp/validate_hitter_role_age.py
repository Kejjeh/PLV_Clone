# Pre-registered: data/research/validation_runs/hitter_role_age_2026-07-04.md
"""
rating_reimagine queue #3 — hitter ROLE+AGE construct for the ANNUAL total-FP
valuation layer (research-only target; in-season null vs rh3 pre-declared).

construct = -0.5*z(mean_lineup_spot) - 0.5*z(age)   (within year T)
outcome   = total FP in year T+1 (fp_per_pa * pa)
baseline  = fp_total(T) + OVERALL(T) + t1_fp_projection(T)  [strongest annual stack]
Gates: partial >= .10, sign-consistent 5/5 T+1 years, holdout(2024,2025) >= .05.
"""
from __future__ import annotations
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression

warnings.filterwarnings("ignore")
_ROOT = Path(__file__).resolve().parents[2]
PANEL = _ROOT / "data" / "research" / "hitter_archetype_career_panel.parquet"

TRAIN_T1 = [2018, 2019, 2021, 2022, 2023]
HOLDOUT_T1 = [2024, 2025]
MIN_PA_T, MIN_PA_T1 = 250, 150


def _z(g):
    return (g - g.mean()) / (g.std() or 1.0)


def partial_r(y, x, controls):
    """Partial correlation of x with y controlling for the control matrix."""
    C = np.column_stack(controls)
    rx = x - LinearRegression().fit(C, x).predict(C)
    ry = y - LinearRegression().fit(C, y).predict(C)
    return pearsonr(rx, ry)


def main():
    df = pd.read_parquet(PANEL)
    need = ["batter", "year", "pa", "fp_per_pa", "OVERALL", "mean_lineup_spot",
            "age", "t1_fp_projection"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        print(f"FATAL: panel missing {missing}\ncols: {sorted(df.columns)[:40]}")
        return
    df = df.dropna(subset=["pa", "fp_per_pa"]).copy()
    df["fp_total"] = df["fp_per_pa"] * df["pa"]
    df["role_age"] = (-0.5 * df.groupby("year")["mean_lineup_spot"].transform(_z)
                      - 0.5 * df.groupby("year")["age"].transform(_z))

    nxt = df[["batter", "year", "fp_total", "pa"]].copy()
    nxt["year"] -= 1
    pairs = df.merge(nxt, on=["batter", "year"], suffixes=("", "_t1"), how="inner")
    pairs = pairs[(pairs["pa"] >= MIN_PA_T) & (pairs["pa_t1"] >= MIN_PA_T1)]
    pairs = pairs.dropna(subset=["role_age", "OVERALL", "t1_fp_projection"])
    pairs["t1_year"] = pairs["year"] + 1
    print(f"pairs: {len(pairs)} (T+1 years {sorted(pairs['t1_year'].unique())})")

    def gate(sub, label):
        y = sub["fp_total_t1"].values
        x = sub["role_age"].values
        ctrl = [sub["fp_total"].values, sub["OVERALL"].values,
                sub["t1_fp_projection"].values]
        r, p = partial_r(y, x, ctrl)
        print(f"  {label}: partial r {r:+.3f} (p={p:.2g}, n={len(sub)})")
        return r

    print("\n[GATE a] pooled partial r beyond fp_total+OVERALL+t1_proj (train T+1 yrs):")
    train = pairs[pairs["t1_year"].isin(TRAIN_T1)]
    gate(train, "pooled")

    print("[GATE b] per-T+1-year sign:")
    signs = []
    for y in TRAIN_T1:
        sub = pairs[pairs["t1_year"] == y]
        if len(sub) >= 30:
            signs.append(gate(sub, str(y)) > 0)
    print(f"  sign-consistent: {sum(signs)}/{len(signs)}")

    print("[GATE c] holdout (T+1 in 2024/2025):")
    hold = pairs[pairs["t1_year"].isin(HOLDOUT_T1)]
    gate(hold, "holdout")

    # survivorship-honest variant: unconditional (dropouts scored 0 total FP)
    print("\n[HONESTY] unconditional variant (no T+1 appearance filter, dropouts=0):")
    nxt_all = df[["batter", "year", "fp_total"]].copy()
    nxt_all["year"] -= 1
    uncond = df[df["pa"] >= MIN_PA_T].merge(
        nxt_all, on=["batter", "year"], suffixes=("", "_t1"), how="left")
    uncond["fp_total_t1"] = uncond["fp_total_t1"].fillna(0.0)
    uncond = uncond.dropna(subset=["role_age", "OVERALL", "t1_fp_projection"])
    uncond["t1_year"] = uncond["year"] + 1
    gate(uncond[uncond["t1_year"].isin(TRAIN_T1)], "pooled-uncond")
    gate(uncond[uncond["t1_year"].isin(HOLDOUT_T1)], "holdout-uncond")


if __name__ == "__main__":
    main()
