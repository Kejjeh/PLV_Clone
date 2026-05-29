"""TEST E — Specific interaction terms in linear T+1 model.

Add each interaction one at a time to the baseline (subs + age, or subs + velo + age),
fit on full FULL-tier T+1 panel using year-based holdout (test_year=2024 -> predicts 2025).
Report ΔR² and significance via OLS p-value on the interaction coef.
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
from sklearn.metrics import r2_score

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)

# Centered product to reduce collinearity
def centered_product(df, a, b):
    return (df[a] - df[a].mean()) * (df[b] - df[b].mean())


HIT_INTERACTIONS = [
    ("DAMAGE_PROD", "Z_CONTACT"),
    ("K_AVOIDANCE", "CONTACT_QUALITY"),
    ("RAW_POWER", "PATIENCE"),
    ("DAMAGE_PROD", "age"),
]

SP_INTERACTIONS = [
    ("SWING_MISS", "WALK_AVOID"),
    ("SWING_MISS", "age"),
]


def eval_with_interaction(df, feats, y_col, pair, test_year=2024):
    """Fit baseline + one interaction; return baseline R², new R², ΔR², coef stats."""
    a, b = pair
    df = df.dropna(subset=feats + [y_col]).copy()
    df = df[df["data_tier"] == "FULL"]
    inter_name = f"{a}_x_{b}"
    df[inter_name] = centered_product(df, a, b)

    train = df[df["year"] <= test_year - 1]
    test = df[df["year"] == test_year]

    if len(train) < 100 or len(test) < 20:
        return None

    # Baseline
    base = LinearRegression().fit(train[feats], train[y_col])
    yp_base = base.predict(test[feats])
    r2_base = r2_score(test[y_col], yp_base)

    # With interaction
    feats_aug = feats + [inter_name]
    aug = LinearRegression().fit(train[feats_aug], train[y_col])
    yp_aug = aug.predict(test[feats_aug])
    r2_aug = r2_score(test[y_col], yp_aug)

    # Significance: OLS p-value on the interaction coef on TRAIN, computed manually
    # Standard OLS: beta = (X'X)^-1 X'y; var(beta) = sigma^2 * (X'X)^-1; t = beta/se
    try:
        from scipy import stats
        X = train[feats_aug].to_numpy(dtype=float)
        X = np.column_stack([np.ones(len(X)), X])  # intercept
        y = train[y_col].to_numpy(dtype=float)
        XtX_inv = np.linalg.inv(X.T @ X)
        beta = XtX_inv @ X.T @ y
        resid = y - X @ beta
        n, k = X.shape
        sigma2 = (resid @ resid) / (n - k)
        se = np.sqrt(np.diag(sigma2 * XtX_inv))
        # interaction coef is the last one (after intercept + feats + inter)
        col_idx = 1 + feats_aug.index(inter_name)
        t_stat = beta[col_idx] / se[col_idx]
        p_inter = float(2 * (1 - stats.t.cdf(abs(t_stat), df=n - k)))
        beta_inter = float(beta[col_idx])
    except Exception as e:
        p_inter = None
        beta_inter = None

    return {
        "interaction": inter_name,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "r2_baseline": float(r2_base),
        "r2_with_interaction": float(r2_aug),
        "delta_r2": float(r2_aug - r2_base),
        "p_value_train": p_inter,
        "beta_train": beta_inter,
    }


def run_hitters():
    df = load_hitters()
    df = build_horizon_panel(df, id_col="batter", y_col="fp_per_pa", horizons=(1,))
    feats = HIT_SUBS + ["age"]
    results = []
    for pair in HIT_INTERACTIONS:
        r = eval_with_interaction(df, feats, "fp_t1", pair)
        if r is not None:
            results.append(r)
    return results


def run_sps():
    df = load_sps()
    df = build_horizon_panel(df, id_col="pitcher", y_col="fp_per_start", horizons=(1,))
    feats = SP_SUBS + ["velo_rating", "age"]
    results = []
    for pair in SP_INTERACTIONS:
        r = eval_with_interaction(df, feats, "fp_t1", pair)
        if r is not None:
            results.append(r)
    return results


if __name__ == "__main__":
    out = {"hitters": run_hitters(), "sps": run_sps()}
    with open(OUT / "test_E_results.json", "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(json.dumps(out, indent=2))
