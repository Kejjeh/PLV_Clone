"""build_hitter_sigma_calibration.py

Fit the ridge predictor of per-batter sigma_emp on the boom-bust panel and
write a JSON calibration bundle the rh3 pipeline can load to apply a
heteroskedastic multiplicative sigma factor per batter.

Mirrors the fit in scripts/xfp/hitter_sigma_heteroskedastic_search.py — the
research script that validated SHIP_HETERO_FOR_HITTERS (CV r2=0.5744, pooled
coverage 25.10% -> 25.16%, per-batter spread 8.13pp -> 7.57pp).

Inputs:
  - data/research/validation_runs/hitter_boom_bust_panel.parquet
  - data/research/hitter_ratings_master.csv

Outputs:
  - data/research/validation_runs/hitter_sigma_calibration.json
      {
        "feat_cols": [...],
        "feat_mu":   [...],   # standardization mean per feature
        "feat_sd":   [...],   # standardization std per feature
        "coefs_standardized": {feat: coef, ...},
        "intercept": float,
        "global_sigma_per_pa": float,
        "factor_clip": [0.7, 1.5],
        "n_batters_fit": int,
        "cv_r2": float,
        "generated_at": "YYYY-MM-DD",
        "version": "hetero_v1"
      }
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "research" / "validation_runs" / "hitter_boom_bust_panel.parquet"
RATINGS = ROOT / "data" / "research" / "hitter_ratings_master.csv"
OUT = ROOT / "data" / "research" / "validation_runs" / "hitter_sigma_calibration.json"

MIN_GAMES_PER_BATTER = 100
FEAT_COLS = [
    "CONTACT", "POWER", "DISCIPLINE",
    "k_pct", "bb_pct", "iso", "hard_hit_pct", "barrel_pct", "sweet_spot_pct",
    "chase_pct", "contact_pct", "ev90", "sprint_speed",
    "xwoba_on_contact",
    "mean_lineup_spot",
]


def main() -> None:
    print("[1/4] loading panel + ratings...")
    df = pd.read_parquet(PANEL).dropna(subset=["fp_proxy", "PA"])
    df["fp_per_pa"] = df["fp_proxy"].astype(float) / df["PA"].astype(float)

    ratings = pd.read_csv(RATINGS, low_memory=False)

    print("[2/4] per-batter empirical sigma...")
    rows = []
    for bid, sub in df.groupby("batter"):
        if len(sub) < MIN_GAMES_PER_BATTER:
            continue
        w = sub["PA"].astype(float).values
        x = sub["fp_per_pa"].astype(float).values
        mean_w = float(np.average(x, weights=w))
        var_w = float(np.average((x - mean_w) ** 2, weights=w))
        rows.append({"batter": int(bid), "sigma_emp": float(np.sqrt(var_w))})
    pp = pd.DataFrame(rows)

    # global pooled per-PA sigma (PA-weighted residual variance vs each batter's mean)
    batter_mean = df.groupby("batter").apply(
        lambda s: np.average(s["fp_per_pa"], weights=s["PA"].astype(float)),
        include_groups=False,
    )
    df = df.merge(batter_mean.rename("batter_mean_fp_per_pa"), on="batter", how="left")
    resid = df["fp_per_pa"] - df["batter_mean_fp_per_pa"]
    global_sigma_per_pa = float(np.sqrt(np.average(resid ** 2, weights=df["PA"].astype(float).values)))
    print(f"  global_sigma_per_pa = {global_sigma_per_pa:.6f}  n_batters={len(pp)}")

    print("[3/4] join latest-year ratings + fit ridge...")
    feat_cols = [c for c in FEAT_COLS if c in ratings.columns]
    r = ratings[["batter", "year"] + feat_cols].copy()
    r["batter"] = pd.to_numeric(r["batter"], errors="coerce")
    r = r.dropna(subset=["batter"])
    r["batter"] = r["batter"].astype(int)
    r = r.sort_values(["batter", "year"]).groupby("batter").tail(1)
    merged = pp.merge(r, on="batter", how="left").dropna(subset=feat_cols + ["sigma_emp"])

    X = merged[feat_cols].values.astype(float)
    y = merged["sigma_emp"].values.astype(float)
    mu = X.mean(axis=0)
    sd = X.std(axis=0) + 1e-9
    Xz = (X - mu) / sd

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    preds = np.zeros_like(y)
    for tr, te in kf.split(Xz):
        m = Ridge(alpha=2.0).fit(Xz[tr], y[tr])
        preds[te] = m.predict(Xz[te])
    ss_res = float(((y - preds) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    cv_r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    m_full = Ridge(alpha=2.0).fit(Xz, y)
    coefs = {c: float(v) for c, v in zip(feat_cols, m_full.coef_.tolist())}
    intercept = float(m_full.intercept_)
    print(f"  n_fit={len(merged)}  CV r2={cv_r2:.4f}  intercept={intercept:.6f}")

    print("[4/4] writing calibration JSON...")
    bundle = {
        "version": "hetero_v1",
        "generated_at": str(date.today()),
        "feat_cols": feat_cols,
        "feat_mu": mu.tolist(),
        "feat_sd": sd.tolist(),
        "coefs_standardized": coefs,
        "intercept": intercept,
        "global_sigma_per_pa": global_sigma_per_pa,
        "factor_clip": [0.7, 1.5],
        "n_batters_fit": int(len(merged)),
        "cv_r2": float(cv_r2),
        "source_panel": str(PANEL.relative_to(ROOT)),
        "source_ratings": str(RATINGS.relative_to(ROOT)),
        "note": "Predicts per-batter sigma_emp from ratings_master features. "
                "Apply as factor = (pred_sigma / global) clamped to [0.7,1.5] "
                "then re-centered so mean(factor)=1 across active batters.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(f"  wrote {OUT}")


if __name__ == "__main__":
    main()
