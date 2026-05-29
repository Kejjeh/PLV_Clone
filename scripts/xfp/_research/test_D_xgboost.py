"""TEST D — XGBoost vs linear for T+1 prediction.

Hitters: 12 sub-domains + age -> fp_t1 (fp_per_pa shifted)
SPs:     6 sub-domains + velo_rating + age -> fp_t1 (fp_per_start shifted)

Train: years <= 2024, FULL tier, valid T+1
Holdout: year == 2024 with T+1 in 2025 (since 2025 is most recent complete y)
We use year-based holdout: train (year <= 2023), test (year == 2024) so T+1=2025 known.
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
    fit_linear_report, load_hitters, load_sps,
)

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)


def run_xgboost(X_train, y_train, X_test, y_test):
    import xgboost as xgb
    from sklearn.metrics import r2_score, mean_absolute_error
    m = xgb.XGBRegressor(
        n_estimators=500,
        learning_rate=0.03,
        max_depth=4,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=0,
        n_jobs=4,
        early_stopping_rounds=30,
    )
    # carve a small validation set out of train for early stopping
    n = len(X_train)
    rng = np.random.default_rng(0)
    idx = rng.permutation(n)
    cut = int(0.85 * n)
    tr_idx, va_idx = idx[:cut], idx[cut:]
    m.fit(
        X_train.iloc[tr_idx], y_train.iloc[tr_idx],
        eval_set=[(X_train.iloc[va_idx], y_train.iloc[va_idx])],
        verbose=False,
    )
    yp = m.predict(X_test)
    fi = dict(zip(X_train.columns, m.feature_importances_.tolist()))
    return {
        "r2": float(r2_score(y_test, yp)),
        "mae": float(mean_absolute_error(y_test, yp)),
        "feature_importance": fi,
    }


def split_train_test(df, feats, y_col, test_year=2024):
    df = df.dropna(subset=feats + [y_col])
    df = df[df["data_tier"] == "FULL"]
    train = df[df["year"] <= test_year - 1]
    test = df[df["year"] == test_year]
    return (
        train[feats], train[y_col],
        test[feats], test[y_col],
        len(train), len(test),
    )


def run_hitters():
    df = load_hitters()
    df = build_horizon_panel(df, id_col="batter", y_col="fp_per_pa", horizons=(1,))
    feats = HIT_SUBS + ["age"]
    Xtr, ytr, Xte, yte, ntr, nte = split_train_test(df, feats, "fp_t1", test_year=2024)
    lin = fit_linear_report(Xtr, ytr, Xte, yte)
    xgb = run_xgboost(Xtr, ytr, Xte, yte)
    return {
        "n_train": ntr, "n_test": nte, "test_year": 2024,
        "linear_r2": lin["r2"], "linear_mae": lin["mae"],
        "xgb_r2": xgb["r2"], "xgb_mae": xgb["mae"],
        "delta_r2": xgb["r2"] - lin["r2"],
        "linear_coef": lin["coef"],
        "xgb_feature_importance": xgb["feature_importance"],
    }


def run_sps():
    df = load_sps()
    df = build_horizon_panel(df, id_col="pitcher", y_col="fp_per_start", horizons=(1,))
    feats = SP_SUBS + ["velo_rating", "age"]
    Xtr, ytr, Xte, yte, ntr, nte = split_train_test(df, feats, "fp_t1", test_year=2024)
    lin = fit_linear_report(Xtr, ytr, Xte, yte)
    xgb = run_xgboost(Xtr, ytr, Xte, yte)
    return {
        "n_train": ntr, "n_test": nte, "test_year": 2024,
        "linear_r2": lin["r2"], "linear_mae": lin["mae"],
        "xgb_r2": xgb["r2"], "xgb_mae": xgb["mae"],
        "delta_r2": xgb["r2"] - lin["r2"],
        "linear_coef": lin["coef"],
        "xgb_feature_importance": xgb["feature_importance"],
    }


if __name__ == "__main__":
    out = {"hitters": run_hitters(), "sps": run_sps()}
    with open(OUT / "test_D_results.json", "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("linear_coef", "xgb_feature_importance")} for k, v in out.items()}, indent=2))
