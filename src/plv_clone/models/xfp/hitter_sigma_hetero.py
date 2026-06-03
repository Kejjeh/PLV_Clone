"""hitter_sigma_hetero — per-batter sigma multiplicative factor for rh3.

Loads the calibration JSON written by
`scripts/xfp/build_hitter_sigma_calibration.py` (CV r2 = 0.5744 on 639
batters with >= 100 games; validation report at
`data/research/validation_runs/hitter_sigma_heteroskedastic_search.md`)
and produces a per-batter multiplicative factor in [0.7, 1.5], re-centered
to mean 1.0 across active batters so global pooled coverage is preserved.

Usage from rh3 pipeline:

    from plv_clone.models.xfp.hitter_sigma_hetero import (
        load_calibration, compute_batter_sigma_factors,
    )
    calib = load_calibration()
    factors = compute_batter_sigma_factors(ratings_df, calib)
    # factors is dict[batter_id -> float], mean ~= 1.0
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
CALIB_JSON = ROOT / "data" / "research" / "validation_runs" / "hitter_sigma_calibration.json"


def load_calibration(path: Path | None = None) -> dict:
    p = Path(path) if path is not None else CALIB_JSON
    if not p.exists():
        raise FileNotFoundError(
            f"hetero sigma calibration missing at {p}. "
            "Run scripts/xfp/build_hitter_sigma_calibration.py first."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def compute_batter_sigma_factors(
    ratings: pd.DataFrame,
    calib: dict,
    *,
    batter_subset: set[int] | None = None,
) -> dict[int, float]:
    """Return {batter_id -> sigma multiplicative factor}.

    Steps (per the validation recipe):
      1. Pick the latest-year ratings row per batter.
      2. Predict sigma_emp via the ridge: intercept + (X - mu)/sd @ coefs.
      3. factor_raw = pred_sigma / global_sigma_per_pa.
      4. Re-center so mean(factor_raw) == 1.0 across batters with complete
         features (computed BEFORE clipping for honest global preservation).
      5. Clamp to [factor_clip_lo, factor_clip_hi]. Missing-feature batters
         get factor=1.0.

    `batter_subset`, if supplied, limits the re-centering pool to active
    rh3 batters so the global ~50% calibration is preserved against the
    batters we actually publish projections for.
    """
    feat_cols: list[str] = calib["feat_cols"]
    mu = np.array(calib["feat_mu"], dtype=float)
    sd = np.array(calib["feat_sd"], dtype=float)
    coefs = np.array([calib["coefs_standardized"][c] for c in feat_cols], dtype=float)
    intercept = float(calib["intercept"])
    global_sigma = float(calib["global_sigma_per_pa"])
    clip_lo, clip_hi = calib.get("factor_clip", [0.7, 1.5])

    missing = [c for c in feat_cols if c not in ratings.columns]
    if missing:
        # Fallback: drop missing features from the model. Project intercept
        # only on remaining (best-effort) and don't blow up.
        keep_idx = [i for i, c in enumerate(feat_cols) if c in ratings.columns]
        feat_cols = [feat_cols[i] for i in keep_idx]
        mu = mu[keep_idx]
        sd = sd[keep_idx]
        coefs = coefs[keep_idx]

    r = ratings[["batter", "year"] + feat_cols].copy()
    r["batter"] = pd.to_numeric(r["batter"], errors="coerce")
    r = r.dropna(subset=["batter"])
    r["batter"] = r["batter"].astype(int)
    r = r.sort_values(["batter", "year"]).groupby("batter").tail(1).reset_index(drop=True)

    X = r[feat_cols].values.astype(float)
    ok = ~np.isnan(X).any(axis=1)
    pred_sigma = np.full(len(r), np.nan)
    if ok.any():
        Xz = (X[ok] - mu) / sd
        pred_sigma[ok] = intercept + Xz @ coefs

    factor_raw = pred_sigma / global_sigma  # NaN where features missing

    # Mean for re-centering: limit to the active subset if provided.
    if batter_subset is not None:
        mask = r["batter"].isin(batter_subset).values & ok
    else:
        mask = ok
    if mask.sum() > 0:
        mean_factor = float(np.nanmean(factor_raw[mask]))
    else:
        mean_factor = 1.0
    if not np.isfinite(mean_factor) or mean_factor <= 0:
        mean_factor = 1.0

    factor = factor_raw / mean_factor
    factor = np.clip(factor, clip_lo, clip_hi)
    # missing-feature batters -> neutral factor
    factor = np.where(np.isnan(factor), 1.0, factor)

    return dict(zip(r["batter"].astype(int).values, factor.astype(float)))


__all__ = ["load_calibration", "compute_batter_sigma_factors", "CALIB_JSON"]
