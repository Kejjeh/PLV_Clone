"""TEST F — T+2 and T+3 horizon projections.

Build T+1, T+2, T+3 panels by shifting fp_per_pa / fp_per_start.
Fit linear regressions on same feature set. Report R² + top 3 features by |beta|.

Holdout strategy: train (year <= 2022) test (year == 2023) for fair comparison
(since T+1 from 2023 needs 2024, T+2 from 2023 needs 2025, T+3 from 2023 needs 2026 — all present).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _common import (
    HIT_SUBS, SP_SUBS, build_horizon_panel,
    load_hitters, load_sps,
)
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)


def fit_horizon(df, feats, y_col, test_year=2023):
    df = df.dropna(subset=feats + [y_col]).copy()
    df = df[df["data_tier"] == "FULL"]
    train = df[df["year"] <= test_year - 1]
    test = df[df["year"] == test_year]
    if len(train) < 100 or len(test) < 20:
        return None
    # standardize features so |beta| is meaningful
    means = train[feats].mean()
    sds = train[feats].std().replace(0, 1)
    Xtr = (train[feats] - means) / sds
    Xte = (test[feats] - means) / sds
    m = LinearRegression().fit(Xtr, train[y_col])
    yp = m.predict(Xte)
    r2 = r2_score(test[y_col], yp)
    mae = mean_absolute_error(test[y_col], yp)
    coef = dict(zip(feats, m.coef_.tolist()))
    top3 = sorted(coef.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
    return {
        "r2": float(r2),
        "mae": float(mae),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "top_features_by_abs_beta": [(k, float(v)) for k, v in top3],
        "all_coefs_standardized": coef,
    }


def run_set(loader, id_col, y_col, feats, label):
    df = loader()
    df = build_horizon_panel(df, id_col=id_col, y_col=y_col, horizons=(1, 2, 3))
    out = {}
    for h in (1, 2, 3):
        r = fit_horizon(df, feats, f"fp_t{h}", test_year=2023)
        out[f"T+{h}"] = r
    return out


if __name__ == "__main__":
    out = {
        "hitters": run_set(load_hitters, "batter", "fp_per_pa", HIT_SUBS + ["age"], "hitters"),
        "sps":     run_set(load_sps,     "pitcher", "fp_per_start", SP_SUBS + ["velo_rating", "age"], "sps"),
    }
    with open(OUT / "test_F_results.json", "w") as f:
        json.dump(out, f, indent=2, default=float)
    # Print compact summary
    for grp, hd in out.items():
        print(f"\n== {grp} ==")
        for h, r in hd.items():
            if r is None:
                print(f"  {h}: insufficient data")
                continue
            top = ", ".join(f"{k}={v:+.4f}" for k, v in r["top_features_by_abs_beta"])
            print(f"  {h}  R²={r['r2']:.3f}  MAE={r['mae']:.4f}  n_tr={r['n_train']}  n_te={r['n_test']}  top: {top}")
