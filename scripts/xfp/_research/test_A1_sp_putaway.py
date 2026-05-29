"""
Test A1 — SP put-away pitch.

For each (pitcher, year): compute whiff% by pitch_type with >=30 swings,
take max → best_putaway_whiff. Rate within-year 20-80 → r_BestPutaway.

Tests:
 (1) YoY stability of r_BestPutaway.
 (2) Current-year regression: fp_per_start ~ STUFF + r_BestPutaway.
 (3) T+1 regression: fp_per_start_t1 ~ SWING_MISS + CALLED_STRIKE +
                       r_BestPutaway + age.

No production scripts/CSVs are written.
"""

from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from sklearn.linear_model import LinearRegression
from scipy.stats import norm, t as student_t

ROOT = "c:/Users/Joshua/plv_clone"
PF_GLOB = f"{ROOT}/data/processed/pitch_features/year=*/*.parquet"
SP_MASTER = f"{ROOT}/data/research/sp_ratings_master.csv"
OUT = f"{ROOT}/scripts/xfp/_research/test_A1_results.json"

SWING_DESCS = {
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip",
    "hit_into_play", "foul_bunt", "missed_bunt",
}
WHIFF_DESCS = {
    "swinging_strike", "swinging_strike_blocked", "foul_tip", "missed_bunt",
}


def rate_2080(s: pd.Series) -> pd.Series:
    """Convert series to 20-80 scale using rank-percentile → z → 50+10z, clipped."""
    s = s.astype(float)
    valid = s.notna()
    if valid.sum() < 5:
        return pd.Series(np.nan, index=s.index)
    # rank percentile
    pct = s.rank(pct=True)
    # avoid 0 and 1
    pct = pct.clip(1e-3, 1 - 1e-3)
    z = pd.Series(norm.ppf(pct), index=s.index)
    out = 50 + 10 * z
    out = out.clip(20, 80)
    out[~valid] = np.nan
    return out


def build_putaway_panel() -> pd.DataFrame:
    """Aggregate per (pitcher, year, pitch_type) → take best whiff per pitcher-year."""
    paths = sorted(glob.glob(PF_GLOB))
    paths = [p for p in paths if "2026.bak" not in p]
    print(f"Found {len(paths)} pitch_features files")

    out = []
    for path in paths:
        # Robust year extract from .../year=YYYY/file.parquet
        norm = path.replace("\\", "/")
        year_str = norm.split("year=")[1].split("/")[0]
        year = int(year_str)
        print(f"  reading {year}...")
        cols = ["pitcher", "pitch_type", "description"]
        d = ds.dataset(path).to_table(columns=cols).to_pandas()
        d = d.dropna(subset=["pitcher", "pitch_type"])
        d["is_swing"] = d["description"].isin(SWING_DESCS)
        d["is_whiff"] = d["description"].isin(WHIFF_DESCS)
        agg = (
            d.groupby(["pitcher", "pitch_type"], observed=True)
            .agg(swings=("is_swing", "sum"), whiffs=("is_whiff", "sum"))
            .reset_index()
        )
        agg["year"] = year
        agg = agg[agg["swings"] >= 30].copy()
        agg["whiff_pct"] = agg["whiffs"] / agg["swings"]
        out.append(agg)

    big = pd.concat(out, ignore_index=True)
    # best-putaway pitch per (pitcher, year)
    best = (
        big.sort_values("whiff_pct", ascending=False)
        .groupby(["pitcher", "year"], as_index=False)
        .first()
        .rename(columns={
            "pitch_type": "best_putaway_pitch",
            "whiff_pct": "best_putaway_whiff",
            "swings": "best_putaway_swings",
        })[["pitcher", "year", "best_putaway_pitch", "best_putaway_whiff", "best_putaway_swings"]]
    )
    # add within-year 20-80 rating
    best["r_BestPutaway"] = best.groupby("year")["best_putaway_whiff"].transform(rate_2080)
    return best


def yoy_stability(panel: pd.DataFrame, col: str) -> dict:
    """Compute correlation between year t and year t+1 for the column."""
    p = panel[["pitcher", "year", col]].dropna()
    p2 = p.copy()
    p2["year"] = p2["year"] - 1
    p2 = p2.rename(columns={col: f"{col}_next"})
    merged = p.merge(p2, on=["pitcher", "year"], how="inner")
    if len(merged) < 30:
        return {"n_pairs": int(len(merged)), "pearson_r": None}
    r = merged[col].corr(merged[f"{col}_next"])
    return {"n_pairs": int(len(merged)), "pearson_r": float(r)}


def run_reg(df: pd.DataFrame, y: str, x_cols: list[str]) -> dict:
    d = df[[y] + x_cols].dropna()
    if len(d) < 30:
        return {"n": int(len(d)), "r2": None, "coefs": {}, "pvals": {}}
    X = d[x_cols].values
    yv = d[y].values
    model = LinearRegression().fit(X, yv)
    yhat = model.predict(X)
    resid = yv - yhat
    n, k = X.shape
    sse = float((resid ** 2).sum())
    sst = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1 - sse / sst if sst > 0 else float("nan")
    r2_adj = 1 - (1 - r2) * (n - 1) / max(n - k - 1, 1)
    # std errors via (X'X)^-1 * sigma^2
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
    return {
        "n": int(n),
        "r2": float(r2),
        "r2_adj": float(r2_adj),
        "coefs": coef_dict,
        "pvals": pval_dict,
    }


def main():
    panel = build_putaway_panel()
    print(f"Putaway panel rows: {len(panel)}")
    panel.to_parquet(f"{ROOT}/scripts/xfp/_research/_putaway_panel.parquet", index=False)

    # YoY stability
    yoy_raw = yoy_stability(panel, "best_putaway_whiff")
    yoy_rate = yoy_stability(panel, "r_BestPutaway")
    print("YoY stability (raw whiff):", yoy_raw)
    print("YoY stability (r_BestPutaway 20-80):", yoy_rate)

    # Join with SP master
    sp = pd.read_csv(SP_MASTER)
    sp = sp[sp["data_tier"].astype(str).str.lower() != "rookie"].copy() if "data_tier" in sp.columns else sp
    sp = sp.merge(panel, on=["pitcher", "year"], how="left")

    # Construct T+1 fp_per_start by joining next-year row
    sp_next = sp[["pitcher", "year", "fp_per_start"]].rename(
        columns={"year": "y_next", "fp_per_start": "fp_per_start_t1_actual"}
    )
    sp_next["year"] = sp_next["y_next"] - 1
    sp = sp.merge(sp_next[["pitcher", "year", "fp_per_start_t1_actual"]], on=["pitcher", "year"], how="left")

    # Filter to rows with sufficient TBF (regulars) AND with putaway data,
    # so baseline & test compare on identical samples (apples-to-apples).
    sp_reg = sp[(sp["tbf"].fillna(0) >= 150) & sp["r_BestPutaway"].notna()].copy()

    # Current-year baseline & test
    base_curr = run_reg(sp_reg, "fp_per_start", ["STUFF"])
    test_curr = run_reg(sp_reg, "fp_per_start", ["STUFF", "r_BestPutaway"])
    print(f"\nCurrent-year baseline (STUFF only): R²={base_curr['r2']}, n={base_curr['n']}")
    print(f"Current-year +r_BestPutaway: R²={test_curr['r2']}, n={test_curr['n']}")

    # Compare baseline that includes more SP rating features (mimicking the paper baseline of 0.75)
    base_curr_full = run_reg(sp_reg, "fp_per_start", ["STUFF", "MOVEMENT", "CONTROL"])
    test_curr_full = run_reg(sp_reg, "fp_per_start", ["STUFF", "MOVEMENT", "CONTROL", "r_BestPutaway"])
    print(f"Full baseline (STUFF+MOVEMENT+CONTROL): R²={base_curr_full['r2']}")
    print(f"Full + r_BestPutaway: R²={test_curr_full['r2']}")

    # Tough baseline — already controls for overall SwStr%
    base_tough = run_reg(sp_reg, "fp_per_start", ["STUFF", "MOVEMENT", "CONTROL", "swstr_pct"])
    test_tough = run_reg(sp_reg, "fp_per_start", ["STUFF", "MOVEMENT", "CONTROL", "swstr_pct", "r_BestPutaway"])
    print(f"Tough baseline (+swstr_pct): R²={base_tough['r2']}")
    print(f"Tough + r_BestPutaway: R²={test_tough['r2']}")

    # T+1 prediction
    base_t1 = run_reg(sp_reg, "fp_per_start_t1_actual", ["SWING_MISS", "CALLED_STRIKE", "age"])
    test_t1 = run_reg(sp_reg, "fp_per_start_t1_actual", ["SWING_MISS", "CALLED_STRIKE", "age", "r_BestPutaway"])
    print(f"\nT+1 baseline (SWING_MISS+CALLED_STRIKE+age): R²={base_t1['r2']}, n={base_t1['n']}")
    print(f"T+1 + r_BestPutaway: R²={test_t1['r2']}, n={test_t1['n']}")

    # Also try richer T+1 baseline that matches production framing
    rich = ["STUFF", "MOVEMENT", "CONTROL", "age", "fp_per_start"]
    base_t1_rich = run_reg(sp_reg, "fp_per_start_t1_actual", rich)
    test_t1_rich = run_reg(sp_reg, "fp_per_start_t1_actual", rich + ["r_BestPutaway"])
    print(f"T+1 rich baseline (STUFF+MOV+CTRL+age+prior fp): R²={base_t1_rich['r2']}")
    print(f"T+1 rich + r_BestPutaway: R²={test_t1_rich['r2']}")

    import json
    results = {
        "yoy_stability_raw": yoy_raw,
        "yoy_stability_r_BestPutaway": yoy_rate,
        "current_year": {
            "baseline_STUFF": base_curr,
            "test_STUFF_putaway": test_curr,
            "baseline_full": base_curr_full,
            "test_full_putaway": test_curr_full,
            "delta_r2_simple": (test_curr["r2"] - base_curr["r2"]) if test_curr["r2"] else None,
            "delta_r2_full": (test_curr_full["r2"] - base_curr_full["r2"]) if test_curr_full["r2"] else None,
            "baseline_tough": base_tough,
            "test_tough_putaway": test_tough,
            "delta_r2_tough": (test_tough["r2"] - base_tough["r2"]) if test_tough["r2"] else None,
        },
        "t1": {
            "baseline_simple": base_t1,
            "test_simple_putaway": test_t1,
            "baseline_rich": base_t1_rich,
            "test_rich_putaway": test_t1_rich,
            "delta_r2_simple": (test_t1["r2"] - base_t1["r2"]) if test_t1["r2"] else None,
            "delta_r2_rich": (test_t1_rich["r2"] - base_t1_rich["r2"]) if test_t1_rich["r2"] else None,
        },
        "n_pitcher_years_with_putaway": int(panel.shape[0]),
    }
    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
