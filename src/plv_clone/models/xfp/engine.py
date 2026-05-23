"""Shared xFP toolkit — composed by per-model `fit_and_project` orchestrators.

Not a pipeline base class. Each per-model file (`rh3.py`, `rp3.py`, `rprs2.py`)
owns its own orchestration and reaches for these helpers at load-bearing
steps. See ADR-0001 for why.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_population_means(
    df: pd.DataFrame,
    train_years: list[int],
    spec: dict,
) -> dict:
    """Denom-weighted pooled mean per rate column over training years (2020 excluded)."""
    means: dict[str, float] = {}
    sub = df[df["year"].isin(train_years) & (df["year"] != 2020)]
    for rate_col, (denom_col, _k) in spec.items():
        if rate_col not in sub.columns or denom_col not in sub.columns:
            means[rate_col] = float(sub.get(rate_col, pd.Series([0])).mean(skipna=True) or 0.0)
            continue
        d = sub[[rate_col, denom_col]].dropna()
        d = d[d[denom_col] > 0]
        if d.empty:
            means[rate_col] = float(sub[rate_col].mean(skipna=True) or 0.0)
        else:
            means[rate_col] = float((d[rate_col] * d[denom_col]).sum() / d[denom_col].sum())
    return means


def apply_shrinkage(
    df: pd.DataFrame,
    pop_means: dict,
    spec: dict,
) -> pd.DataFrame:
    """For each (rate, (denom, k)): emit `rate_sh` = (n*obs + k*mu) / (n + k)."""
    out = df.copy()
    for rate_col, (denom_col, k) in spec.items():
        if rate_col not in out.columns or denom_col not in out.columns:
            mu = pop_means.get(rate_col, 0.0)
            out[rate_col + "_sh"] = mu
            continue
        n = out[denom_col].astype(float)
        obs = out[rate_col].astype(float)
        mean = pop_means.get(rate_col, float(np.nanmean(obs) or 0.0))
        obs_filled = obs.fillna(mean)
        n_eff = n.fillna(0.0)
        out[rate_col + "_sh"] = (n_eff * obs_filled + k * mean) / (n_eff + k)
    return out


def train_residual_table(
    *,
    df: pd.DataFrame,
    feats: list[str],
    target_col: str,
    train_years: list[int],
    min_train: int,
    min_test: int,
) -> pd.DataFrame:
    """Loop held-out years, fit Ridge on the rest, emit per-row (pred, actual, split_day, resid)."""
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    rows = []
    for held in train_years:
        train = df[df["year"] != held]
        test = df[df["year"] == held]
        if len(train) < min_train or len(test) < min_test:
            continue
        pipe = Pipeline([
            ("sc", StandardScaler()),
            ("r", RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5)),
        ])
        pipe.fit(train[feats].values, train[target_col].values)
        preds = pipe.predict(test[feats].values)
        rows.append(pd.DataFrame({
            "pred": preds,
            "actual": test[target_col].values,
            "split_day": test["split_day"].values,
        }))
    res = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["pred", "actual", "split_day"],
    )
    res["resid"] = res["actual"] - res["pred"]
    return res


def lookup_sigma(
    ci_table: dict,
    overall_sigma: float,
    split_day: int,
    pred: float,
    pred_buckets: dict[int, np.ndarray],
) -> float:
    """Map (split_day, pred) -> sigma using stored quartile cuts."""
    if split_day not in pred_buckets:
        return overall_sigma
    cuts = pred_buckets[split_day]
    q = int(np.searchsorted(cuts, pred))
    q = min(max(q, 0), len(cuts))
    return ci_table.get((split_day, q), overall_sigma)
