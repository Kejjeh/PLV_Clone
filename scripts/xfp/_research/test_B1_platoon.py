"""
Test B1 — Hitter platoon splits.

For each (batter, year, p_throws): aggregate PA-level xwOBA from statcast
parquets 2018-2026. Compute |xwoba_vs_L - xwoba_vs_R| as the absolute split,
and a "platoon advantage" oriented split (positive = exploits platoon).

Tests:
 - YoY stability of the split (literature predicts r ≈ 0.20-0.40)
 - R² gain over CONTACT/POWER/DISCIPLINE on current-year and T+1
"""

from __future__ import annotations

import glob
import json

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from sklearn.linear_model import LinearRegression
from scipy.stats import norm, t as student_t

ROOT = "c:/Users/Joshua/plv_clone"
STATCAST_GLOB = f"{ROOT}/data/research/xfp_cache/statcast_*.parquet"
HITTER_MASTER = f"{ROOT}/data/research/hitter_ratings_master.csv"
OUT = f"{ROOT}/scripts/xfp/_research/test_B1_results.json"


def rate_2080(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    valid = s.notna()
    if valid.sum() < 5:
        return pd.Series(np.nan, index=s.index)
    pct = s.rank(pct=True).clip(1e-3, 1 - 1e-3)
    out = pd.Series(50 + 10 * norm.ppf(pct), index=s.index).clip(20, 80)
    out[~valid] = np.nan
    return out


def run_reg(df: pd.DataFrame, y: str, x_cols: list[str]) -> dict:
    d = df[[y] + x_cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(d) < 30:
        return {"n": int(len(d)), "r2": None}
    X = d[x_cols].values.astype(float)
    yv = d[y].values.astype(float)
    model = LinearRegression().fit(X, yv)
    yhat = model.predict(X)
    sse = float(((yv - yhat) ** 2).sum())
    sst = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1 - sse / sst if sst > 0 else float("nan")
    n, k = X.shape
    r2_adj = 1 - (1 - r2) * (n - 1) / max(n - k - 1, 1)
    Xc = np.column_stack([np.ones(n), X])
    try:
        XtX_inv = np.linalg.inv(Xc.T @ Xc)
        sigma2 = sse / max(n - k - 1, 1)
        se = np.sqrt(np.diag(XtX_inv) * sigma2)
        params = np.concatenate([[model.intercept_], model.coef_])
        tstats = params / se
        pvals = 2 * (1 - student_t.cdf(np.abs(tstats), df=max(n - k - 1, 1)))
        coef_dict = {"const": float(model.intercept_), **{c: float(v) for c, v in zip(x_cols, model.coef_)}}
        pval_dict = {"const": float(pvals[0]), **{c: float(p) for c, p in zip(x_cols, pvals[1:])}}
    except np.linalg.LinAlgError:
        coef_dict, pval_dict = {}, {}
    return {"n": int(n), "r2": float(r2), "r2_adj": float(r2_adj), "coefs": coef_dict, "pvals": pval_dict}


def yoy(panel: pd.DataFrame, col: str) -> dict:
    p = panel[["batter", "year", col]].dropna()
    p2 = p.copy()
    p2["year"] = p2["year"] - 1
    p2 = p2.rename(columns={col: f"{col}_next"})
    merged = p.merge(p2, on=["batter", "year"], how="inner")
    if len(merged) < 30:
        return {"n_pairs": int(len(merged)), "pearson_r": None}
    return {"n_pairs": int(len(merged)), "pearson_r": float(merged[col].corr(merged[f"{col}_next"]))}


def build_panel() -> pd.DataFrame:
    paths = sorted(glob.glob(STATCAST_GLOB))
    paths = [p for p in paths if "bak" not in p.lower()]
    print(f"Found {len(paths)} statcast files")
    out = []
    for path in paths:
        norm_p = path.replace("\\", "/")
        year_str = norm_p.split("statcast_")[1].split(".")[0]
        try:
            year = int(year_str)
        except ValueError:
            continue
        if year < 2018:
            continue
        print(f"  reading {year}...")
        cols = ["batter", "p_throws", "stand", "woba_value", "woba_denom",
                "estimated_woba_using_speedangle", "description", "events"]
        d = ds.dataset(path).to_table(columns=cols).to_pandas()
        d = d.dropna(subset=["batter", "p_throws", "stand"])
        # PA = rows where woba_denom == 1 (end-of-PA rows)
        d_pa = d[d["woba_denom"] == 1].copy()
        agg = (
            d_pa.groupby(["batter", "p_throws", "stand"], observed=True)
            .agg(pa=("woba_value", "count"),
                 woba=("woba_value", "mean"),
                 xwoba=("estimated_woba_using_speedangle", "mean"))
            .reset_index()
        )
        agg["year"] = year
        out.append(agg)
    big = pd.concat(out, ignore_index=True)

    # Pivot to wide on p_throws so each batter-year has vs_L and vs_R columns
    wide = big.pivot_table(
        index=["batter", "year", "stand"],
        columns="p_throws",
        values=["pa", "woba", "xwoba"],
        aggfunc="first",
    )
    wide.columns = [f"{a}_vs_{b}" for a, b in wide.columns]
    wide = wide.reset_index()

    # Need a stable handedness — take the stand value that appears more.
    # (Switch hitters have both — for them treat as switch.)
    # We use 'stand' to orient platoon advantage.
    # Sample threshold: both pa_vs_L >= 50 and pa_vs_R >= 100
    wide = wide[(wide.get("pa_vs_L", 0) >= 50) & (wide.get("pa_vs_R", 0) >= 100)].copy()

    # absolute split
    wide["xwoba_abs_split"] = (wide["xwoba_vs_L"] - wide["xwoba_vs_R"]).abs()
    wide["woba_abs_split"] = (wide["woba_vs_L"] - wide["woba_vs_R"]).abs()

    # Platoon-advantage-oriented split:
    # RHB normally weaker vs RHP, so RHB advantage = xwoba_vs_L - xwoba_vs_R should be POSITIVE.
    # LHB normally weaker vs LHP, so LHB advantage = xwoba_vs_R - xwoba_vs_L should be POSITIVE.
    # We define "neutralization" = how SMALL the disadvantage is, or how POSITIVE
    # the actual platoon advantage is on the disadvantaged side.
    def advantage(row):
        if row["stand"] == "R":
            # standard advantage = xwoba_vs_L - xwoba_vs_R (usually positive)
            return row["xwoba_vs_L"] - row["xwoba_vs_R"]
        elif row["stand"] == "L":
            return row["xwoba_vs_R"] - row["xwoba_vs_L"]
        else:
            return np.nan  # switch

    wide["xwoba_platoon_adv"] = wide.apply(advantage, axis=1)

    # If a batter has multiple stand entries (switch hitter handled differently), keep one
    # by aggregating to max PA
    wide["total_pa"] = wide["pa_vs_L"] + wide["pa_vs_R"]
    wide = wide.sort_values("total_pa", ascending=False).drop_duplicates(["batter", "year"])

    # 20-80 ratings
    wide["r_PlatoonNeutral"] = wide.groupby("year")["xwoba_abs_split"].transform(rate_2080)
    # invert: low split = better (more neutral). Higher r = bigger split.
    wide["r_PlatoonAdv"] = wide.groupby("year")["xwoba_platoon_adv"].transform(rate_2080)

    return wide


def main():
    panel = build_panel()
    print(f"Panel rows: {len(panel)}")

    print("\nYoY stability:")
    yoy_abs = yoy(panel, "xwoba_abs_split")
    yoy_adv = yoy(panel, "xwoba_platoon_adv")
    yoy_rabs = yoy(panel, "r_PlatoonNeutral")
    print("  xwoba_abs_split:", yoy_abs)
    print("  xwoba_platoon_adv:", yoy_adv)
    print("  r_PlatoonNeutral:", yoy_rabs)

    h = pd.read_csv(HITTER_MASTER)
    h = h.merge(panel[["batter", "year", "xwoba_abs_split", "xwoba_platoon_adv",
                        "r_PlatoonNeutral", "r_PlatoonAdv", "pa_vs_L", "pa_vs_R"]],
                on=["batter", "year"], how="left")

    # T+1
    h_next = h[["batter", "year", "fp_per_pa"]].rename(columns={"year": "y_next", "fp_per_pa": "fp_per_pa_t1_actual"})
    h_next["year"] = h_next["y_next"] - 1
    h = h.merge(h_next[["batter", "year", "fp_per_pa_t1_actual"]], on=["batter", "year"], how="left")

    h_reg = h[(h["pa"].fillna(0) >= 200) & h["xwoba_abs_split"].notna()].copy()
    print(f"\nRegression sample: {len(h_reg)} batter-years")

    base_curr = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE"])
    test_abs = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "xwoba_abs_split"])
    test_adv = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "xwoba_platoon_adv"])
    test_radv = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "r_PlatoonAdv"])

    print(f"\nCurrent baseline: R²={base_curr['r2']}, n={base_curr['n']}")
    print(f"+xwoba_abs_split: R²={test_abs['r2']}")
    print(f"+xwoba_platoon_adv: R²={test_adv['r2']}")
    print(f"+r_PlatoonAdv: R²={test_radv['r2']}")

    base_t1 = run_reg(h_reg, "fp_per_pa_t1_actual", ["CONTACT", "POWER", "DISCIPLINE", "age", "fp_per_pa"])
    test_t1_abs = run_reg(h_reg, "fp_per_pa_t1_actual", ["CONTACT", "POWER", "DISCIPLINE", "age", "fp_per_pa", "xwoba_abs_split"])
    test_t1_adv = run_reg(h_reg, "fp_per_pa_t1_actual", ["CONTACT", "POWER", "DISCIPLINE", "age", "fp_per_pa", "xwoba_platoon_adv"])

    print(f"\nT+1 baseline: R²={base_t1['r2']}, n={base_t1['n']}")
    print(f"T+1 +xwoba_abs_split: R²={test_t1_abs['r2']}")
    print(f"T+1 +xwoba_platoon_adv: R²={test_t1_adv['r2']}")

    results = {
        "n_panel": int(len(panel)),
        "yoy": {
            "xwoba_abs_split": yoy_abs,
            "xwoba_platoon_adv": yoy_adv,
            "r_PlatoonNeutral": yoy_rabs,
        },
        "current_year": {
            "baseline": base_curr,
            "test_abs_split": test_abs,
            "test_platoon_adv": test_adv,
            "test_r_PlatoonAdv": test_radv,
            "delta_r2_abs": test_abs["r2"] - base_curr["r2"] if test_abs["r2"] else None,
            "delta_r2_adv": test_adv["r2"] - base_curr["r2"] if test_adv["r2"] else None,
        },
        "t1": {
            "baseline": base_t1,
            "test_abs_split": test_t1_abs,
            "test_platoon_adv": test_t1_adv,
            "delta_r2_abs": test_t1_abs["r2"] - base_t1["r2"] if test_t1_abs["r2"] else None,
            "delta_r2_adv": test_t1_adv["r2"] - base_t1["r2"] if test_t1_adv["r2"] else None,
        },
    }
    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
