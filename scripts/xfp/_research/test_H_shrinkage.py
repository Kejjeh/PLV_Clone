"""TEST H — Bayesian shrinkage on PARTIAL-tier hitters.

For each PARTIAL row, shrink each of the 12 sub-domain ratings toward the prior mean
(league mean = 50). FULL ratings stay as-is.

Shrinkage:
  prior_var  = 100 (within-year SD² = 10² for the 20-80 scale)
  sample_var = (within-year SD)² scaled by 1/effective_n
               where effective_n ≈ pa / pa_ref, pa_ref = 250 (FULL threshold)
  shrink_w   = sample_var / (sample_var + prior_var)
  posterior  = (1 - shrink_w) * raw + shrink_w * prior_mean

Then refit current-year and T+1 regressions on combined FULL+PARTIAL pool
with PARTIAL ratings replaced by posterior. Compare to (a) baseline using raw PARTIAL
and (b) FULL-only baseline.

Report whether shrinkage improves R² on the PARTIAL subset of the test year.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _common import (
    HIT_SUBS, build_horizon_panel, load_hitters,
)
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)


def shrink_partial(df: pd.DataFrame, subs=HIT_SUBS, pa_ref=250, prior_mean=50.0, prior_var=100.0) -> pd.DataFrame:
    """Return df with PARTIAL rows' sub-domain ratings shrunk toward prior_mean."""
    df = df.copy()
    is_partial = (df["data_tier"] == "PARTIAL") & df["pa"].notna()
    # effective_n bounded to [0.05, 1.0]
    eff_n = (df["pa"] / pa_ref).clip(lower=0.05, upper=1.0)
    # sample_var = prior_var / eff_n  (the smaller eff_n, the larger sample_var)
    sample_var = prior_var / eff_n
    shrink_w = sample_var / (sample_var + prior_var)
    # Only apply on partial rows
    for s in subs:
        if s not in df.columns:
            continue
        df[s] = df[s].astype(float)
        posterior = (1 - shrink_w) * df[s] + shrink_w * prior_mean
        df.loc[is_partial, s] = posterior[is_partial]
    return df


def fit_eval(df, feats, y_col, test_year, subset_filter=None):
    df = df.dropna(subset=feats + [y_col])
    train = df[df["year"] <= test_year - 1]
    test = df[df["year"] == test_year]
    if subset_filter is not None:
        test = test[subset_filter(test)]
    if len(train) < 50 or len(test) < 10:
        return None
    m = LinearRegression().fit(train[feats], train[y_col])
    yp = m.predict(test[feats])
    return {
        "r2": float(r2_score(test[y_col], yp)),
        "mae": float(mean_absolute_error(test[y_col], yp)),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
    }


def main():
    h = load_hitters()
    h = build_horizon_panel(h, id_col="batter", y_col="fp_per_pa", horizons=(1,))
    feats = HIT_SUBS + ["age"]

    h_shrunk = shrink_partial(h, subs=HIT_SUBS, pa_ref=250, prior_mean=50.0, prior_var=100.0)

    test_year_cy = 2024  # in-sample year
    test_year_t1 = 2024  # predicts 2025

    only_partial = lambda d: d["data_tier"] == "PARTIAL"
    only_full = lambda d: d["data_tier"] == "FULL"

    results = {}

    for label, y_col, ty in [
        ("current_year", "fp_per_pa", test_year_cy),
        ("t1",           "fp_t1",     test_year_t1),
    ]:
        # Baseline: train on FULL+PARTIAL with RAW ratings, evaluate on PARTIAL subset of test year
        raw_partial = fit_eval(h, feats, y_col, ty, subset_filter=only_partial)
        # Treatment: same pool but PARTIAL rows are shrunk
        shr_partial = fit_eval(h_shrunk, feats, y_col, ty, subset_filter=only_partial)
        # Reference: FULL-only model trained on FULL only, evaluated on FULL test
        full_only_train = h[h["data_tier"] == "FULL"]
        full_only = fit_eval(full_only_train, feats, y_col, ty, subset_filter=only_full)

        # Also: train on FULL-only, test on PARTIAL  (sanity)
        full_train_partial_test = fit_eval(
            pd.concat([h[h["data_tier"] == "FULL"], h[h["data_tier"] == "PARTIAL"]]),
            feats, y_col, ty, subset_filter=only_partial,
        )

        results[label] = {
            "test_year": ty,
            "partial_subset_baseline_raw": raw_partial,
            "partial_subset_shrunk":       shr_partial,
            "delta_r2_partial":            (shr_partial["r2"] - raw_partial["r2"]) if (raw_partial and shr_partial) else None,
            "full_only_reference":         full_only,
        }

    out = {
        "shrinkage_config": {"pa_ref": 250, "prior_mean": 50.0, "prior_var": 100.0},
        "n_partial": int((h["data_tier"] == "PARTIAL").sum()),
        "n_full": int((h["data_tier"] == "FULL").sum()),
        "results": results,
    }
    with open(OUT / "test_H_results.json", "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
