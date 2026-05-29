"""
Test A2 — Hitter per-pitch-type performance.

For each (batter, year, pitch_type): aggregate BIP count and xwOBA-on-contact
(estimated_woba_using_speedangle averaged over in-play rows). Then per
(batter, year):
  best_pitch_xwoba = max(xwoba over pitch_types with >= 50 BIP)
  worst_pitch_xwoba = min(same)
  spread = best - worst
Rate within-year 20-80 → r_BestPitchXwoba, r_PitchSpread.

Tests YoY stability and R² gain over CONTACT/POWER/DISCIPLINE.
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
PF_GLOB = f"{ROOT}/data/processed/pitch_features/year=*/*.parquet"
HITTER_MASTER = f"{ROOT}/data/research/hitter_ratings_master.csv"
OUT = f"{ROOT}/scripts/xfp/_research/test_A2_results.json"


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
    d = df[[y] + x_cols].dropna()
    if len(d) < 30:
        return {"n": int(len(d)), "r2": None}
    X = d[x_cols].values
    yv = d[y].values
    model = LinearRegression().fit(X, yv)
    yhat = model.predict(X)
    sse = float(((yv - yhat) ** 2).sum())
    sst = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1 - sse / sst if sst > 0 else float("nan")
    n, k = X.shape
    r2_adj = 1 - (1 - r2) * (n - 1) / max(n - k - 1, 1)
    # SEs
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


def yoy_stability(panel: pd.DataFrame, col: str) -> dict:
    p = panel[["batter", "year", col]].dropna()
    p2 = p.copy()
    p2["year"] = p2["year"] - 1
    p2 = p2.rename(columns={col: f"{col}_next"})
    merged = p.merge(p2, on=["batter", "year"], how="inner")
    if len(merged) < 30:
        return {"n_pairs": int(len(merged)), "pearson_r": None}
    return {"n_pairs": int(len(merged)), "pearson_r": float(merged[col].corr(merged[f"{col}_next"]))}


def build_panel() -> pd.DataFrame:
    paths = sorted(glob.glob(PF_GLOB))
    out = []
    for path in paths:
        norm_p = path.replace("\\", "/")
        year = int(norm_p.split("year=")[1].split("/")[0])
        print(f"  reading {year}...")
        cols = ["batter", "pitch_type", "is_in_play", "estimated_woba_using_speedangle"]
        d = ds.dataset(path).to_table(columns=cols).to_pandas()
        d = d.dropna(subset=["batter", "pitch_type"])
        d = d[d["is_in_play"] == True].copy()
        agg = (
            d.groupby(["batter", "pitch_type"], observed=True)
            .agg(bip=("estimated_woba_using_speedangle", "count"),
                 xwoba=("estimated_woba_using_speedangle", "mean"))
            .reset_index()
        )
        agg["year"] = year
        agg = agg[agg["bip"] >= 50]
        out.append(agg)
    big = pd.concat(out, ignore_index=True)

    # Per (batter, year): best, worst, spread
    summary = (
        big.groupby(["batter", "year"], as_index=False)
        .agg(best_pitch_xwoba=("xwoba", "max"),
             worst_pitch_xwoba=("xwoba", "min"),
             n_pitch_types=("xwoba", "count"))
    )
    summary = summary[summary["n_pitch_types"] >= 2].copy()
    summary["pitch_spread"] = summary["best_pitch_xwoba"] - summary["worst_pitch_xwoba"]
    summary["r_BestPitchXwoba"] = summary.groupby("year")["best_pitch_xwoba"].transform(rate_2080)
    summary["r_PitchSpread"] = summary.groupby("year")["pitch_spread"].transform(rate_2080)
    return summary


def main():
    panel = build_panel()
    print(f"Hitter pitch-type panel rows: {len(panel)}")

    yoy_best = yoy_stability(panel, "best_pitch_xwoba")
    yoy_spread = yoy_stability(panel, "pitch_spread")
    yoy_best_r = yoy_stability(panel, "r_BestPitchXwoba")
    print("YoY best_pitch_xwoba:", yoy_best)
    print("YoY pitch_spread:", yoy_spread)
    print("YoY r_BestPitchXwoba:", yoy_best_r)

    h = pd.read_csv(HITTER_MASTER)
    h = h.merge(panel, on=["batter", "year"], how="left")

    # T+1 join
    h_next = h[["batter", "year", "fp_per_pa"]].rename(columns={"year": "y_next", "fp_per_pa": "fp_per_pa_t1_actual"})
    h_next["year"] = h_next["y_next"] - 1
    h = h.merge(h_next[["batter", "year", "fp_per_pa_t1_actual"]], on=["batter", "year"], how="left")

    h_reg = h[(h["pa"].fillna(0) >= 200) & h["r_BestPitchXwoba"].notna()].copy()

    base_curr = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE"])
    test_best = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "r_BestPitchXwoba"])
    test_spread = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "r_PitchSpread"])
    test_both = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "r_BestPitchXwoba", "r_PitchSpread"])

    # Tougher baseline that already controls for overall xwoba_on_contact
    # — checks whether per-pitch info adds beyond knowing the player's overall contact quality.
    base_tough = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "xwoba_on_contact"])
    test_tough_best = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "xwoba_on_contact", "r_BestPitchXwoba"])
    test_tough_spread = run_reg(h_reg, "fp_per_pa", ["CONTACT", "POWER", "DISCIPLINE", "xwoba_on_contact", "r_PitchSpread"])

    print(f"\nCurrent-year baseline (CONTACT+POWER+DISC): R²={base_curr['r2']}, n={base_curr['n']}")
    print(f"+r_BestPitchXwoba: R²={test_best['r2']}")
    print(f"+r_PitchSpread: R²={test_spread['r2']}")
    print(f"+both: R²={test_both['r2']}")
    print(f"\nTough baseline (CPD+xwoba_on_contact): R²={base_tough['r2']}")
    print(f"Tough +r_BestPitchXwoba: R²={test_tough_best['r2']}")
    print(f"Tough +r_PitchSpread: R²={test_tough_spread['r2']}")

    base_t1 = run_reg(h_reg, "fp_per_pa_t1_actual", ["CONTACT", "POWER", "DISCIPLINE", "age", "fp_per_pa"])
    test_t1_best = run_reg(h_reg, "fp_per_pa_t1_actual", ["CONTACT", "POWER", "DISCIPLINE", "age", "fp_per_pa", "r_BestPitchXwoba"])
    test_t1_spread = run_reg(h_reg, "fp_per_pa_t1_actual", ["CONTACT", "POWER", "DISCIPLINE", "age", "fp_per_pa", "r_PitchSpread"])

    print(f"\nT+1 baseline (CONTACT+POWER+DISC+age+fp): R²={base_t1['r2']}, n={base_t1['n']}")
    print(f"T+1 +r_BestPitchXwoba: R²={test_t1_best['r2']}")
    print(f"T+1 +r_PitchSpread: R²={test_t1_spread['r2']}")

    results = {
        "n_panel_rows": int(len(panel)),
        "yoy": {
            "best_pitch_xwoba": yoy_best,
            "pitch_spread": yoy_spread,
            "r_BestPitchXwoba": yoy_best_r,
        },
        "current_year": {
            "baseline": base_curr,
            "test_best": test_best,
            "test_spread": test_spread,
            "test_both": test_both,
            "delta_r2_best": test_best["r2"] - base_curr["r2"] if test_best["r2"] else None,
            "delta_r2_spread": test_spread["r2"] - base_curr["r2"] if test_spread["r2"] else None,
            "tough_baseline_with_xwoba_on_contact": base_tough,
            "tough_test_best": test_tough_best,
            "tough_test_spread": test_tough_spread,
            "delta_r2_best_over_tough": test_tough_best["r2"] - base_tough["r2"] if test_tough_best["r2"] else None,
            "delta_r2_spread_over_tough": test_tough_spread["r2"] - base_tough["r2"] if test_tough_spread["r2"] else None,
        },
        "t1": {
            "baseline": base_t1,
            "test_best": test_t1_best,
            "test_spread": test_t1_spread,
            "delta_r2_best": test_t1_best["r2"] - base_t1["r2"] if test_t1_best["r2"] else None,
            "delta_r2_spread": test_t1_spread["r2"] - base_t1["r2"] if test_t1_spread["r2"] else None,
        },
    }
    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
