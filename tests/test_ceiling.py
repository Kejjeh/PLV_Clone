"""Behavioral tests for the model-accuracy-ceiling audit toolkit.

TDD: one cycle per test — write red, implement green, repeat. Each test uses
seeded RNG (`np.random.default_rng(seed=42)`) for determinism. No walltime
randomness, no `time` imports.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from plv_clone.models.xfp.ceiling import (
    FeatureCeiling,
    LinearCeiling,
    NonlinearCeiling,
    feature_ceiling,
    linear_ceiling,
    nonlinear_ceiling,
)


# ---------------------------------------------------------------------------
# Synthetic-data helpers
# ---------------------------------------------------------------------------
def _linear_df(seed: int = 42, n_per_year: int = 200, years=(2022, 2023, 2024, 2025)):
    """y = β·X + small gaussian noise. Ridge should be optimal; XGB/RF should
    NOT outperform meaningfully → verdict AT_CEILING."""
    rng = np.random.default_rng(seed)
    parts = []
    for y in years:
        x1 = rng.normal(0, 1, n_per_year)
        x2 = rng.normal(0, 1, n_per_year)
        x3 = rng.normal(0, 1, n_per_year)
        noise = rng.normal(0, 0.5, n_per_year)
        target = 0.6 * x1 + 0.4 * x2 - 0.3 * x3 + noise
        parts.append(pd.DataFrame({
            "year": y,
            "split_day": 60,
            "f1": x1, "f2": x2, "f3": x3,
            "y": target,
        }))
    return pd.concat(parts, ignore_index=True)


def _nonlinear_df(seed: int = 42, n_per_year: int = 400, years=(2022, 2023, 2024, 2025)):
    """y = sign(x1) * x2 + x1*x3 + noise. Ridge cannot capture the
    interaction/threshold; XGB should pick up extra r → SIGNIFICANT_NONLINEARITY."""
    rng = np.random.default_rng(seed)
    parts = []
    for y in years:
        x1 = rng.normal(0, 1, n_per_year)
        x2 = rng.normal(0, 1, n_per_year)
        x3 = rng.normal(0, 1, n_per_year)
        noise = rng.normal(0, 0.3, n_per_year)
        target = np.sign(x1) * x2 + x1 * x3 + 0.2 * x1 + noise
        parts.append(pd.DataFrame({
            "year": y,
            "split_day": 60,
            "f1": x1, "f2": x2, "f3": x3,
            "y": target,
        }))
    return pd.concat(parts, ignore_index=True)


# ---------------------------------------------------------------------------
# nonlinear_ceiling
# ---------------------------------------------------------------------------
def test_nonlinear_ceiling_returns_at_ceiling_for_linear_data():
    """Pure-linear y = β·X + noise: XGB and RF should not meaningfully beat
    Ridge. Both gaps should be < 0.003 -> AT_CEILING."""
    df = _linear_df()

    result = nonlinear_ceiling(
        df=df,
        feats=["f1", "f2", "f3"],
        target_col="y",
        train_years=[2022, 2023, 2024, 2025],
        min_train=100,
        min_test=30,
    )

    assert isinstance(result, NonlinearCeiling)
    assert result.ridge_r > 0.5  # sanity: model is at least learning
    # Linear data: tree models cannot meaningfully beat Ridge. Upside gap
    # (positive direction) should be < 0.003; verdict measures HEADROOM,
    # so negative gaps don't count.
    assert result.xgb_gap < 0.003, f"xgb_gap={result.xgb_gap:+.4f} should not exceed +0.003 upside"
    assert result.rf_gap < 0.003, f"rf_gap={result.rf_gap:+.4f} should not exceed +0.003 upside"
    assert result.verdict == "AT_CEILING"


def test_nonlinear_ceiling_detects_nonlinearity_on_interaction_data():
    """Sign-flip + multiplicative-interaction target: Ridge cannot capture this,
    but XGB tree splits can. xgb_gap should exceed the +0.003 threshold,
    pushing verdict out of AT_CEILING."""
    df = _nonlinear_df()

    result = nonlinear_ceiling(
        df=df,
        feats=["f1", "f2", "f3"],
        target_col="y",
        train_years=[2022, 2023, 2024, 2025],
        min_train=100,
        min_test=30,
    )

    # XGB should beat Ridge by a meaningful margin
    assert result.xgb_gap > 0.005, (
        f"xgb_gap={result.xgb_gap:+.4f} should be substantial on interaction data"
    )
    assert result.verdict in ("MILD_NONLINEARITY", "SIGNIFICANT_NONLINEARITY")


# ---------------------------------------------------------------------------
# linear_ceiling
# ---------------------------------------------------------------------------
def test_linear_ceiling_returns_stable_for_well_conditioned_features():
    """Independent gaussian features → held-out r essentially flat across
    a wide alpha grid (regularisation amount doesn't matter much when X^T X is
    well-conditioned). r_std < 0.005 → STABLE."""
    df = _linear_df()

    result = linear_ceiling(
        df=df,
        feats=["f1", "f2", "f3"],
        target_col="y",
        train_years=[2022, 2023, 2024, 2025],
        min_train=100,
        min_test=30,
    )

    assert isinstance(result, LinearCeiling)
    assert result.r_at_chosen > 0.5  # sanity
    assert len(result.alpha_range_tested) >= 5  # actually swept multiple alphas
    assert result.alpha_chosen in result.alpha_range_tested
    assert result.r_std_across_alphas < 0.005, (
        f"r_std={result.r_std_across_alphas:.5f} should be tight on well-conditioned data"
    )
    assert result.verdict == "STABLE"


def test_linear_ceiling_returns_alpha_sensitive_on_collinear_features():
    """Highly collinear features (f2 ≈ f1 + tiny noise) make the ridge regression
    ill-conditioned: small alpha differences flip large coefficients, so the
    held-out r becomes alpha-sensitive."""
    rng = np.random.default_rng(42)
    n_per_year = 50  # small n exacerbates ill-conditioning
    years = [2022, 2023, 2024, 2025]
    parts = []
    for y in years:
        x1 = rng.normal(0, 1, n_per_year)
        # Near-duplicate features: tiny perturbation -> near-singular X^T X
        x2 = x1 + rng.normal(0, 1e-4, n_per_year)
        x3 = x1 + rng.normal(0, 1e-4, n_per_year)
        x4 = x1 + rng.normal(0, 1e-4, n_per_year)
        # Target depends on x1 plus larger noise (so signal isn't trivial,
        # but the ridge alpha pick swings r across the reasonable zone).
        noise = rng.normal(0, 1.5, n_per_year)
        target = 1.0 * x1 + noise
        parts.append(pd.DataFrame({
            "year": y, "split_day": 60,
            "f1": x1, "f2": x2, "f3": x3, "f4": x4,
            "y": target,
        }))
    df = pd.concat(parts, ignore_index=True)

    result = linear_ceiling(
        df=df,
        feats=["f1", "f2", "f3", "f4"],
        target_col="y",
        train_years=years,
        min_train=100,
        min_test=30,
    )

    # On near-collinear features with small n and meaningful noise, the
    # local r_std around the chosen alpha exceeds the 0.005 stability gate.
    assert result.r_std_across_alphas >= 0.005, (
        f"r_std={result.r_std_across_alphas:.5f} should exceed 0.005 on collinear data"
    )
    assert result.verdict == "ALPHA_SENSITIVE"


# ---------------------------------------------------------------------------
# feature_ceiling
# ---------------------------------------------------------------------------
def test_feature_ceiling_returns_baseline_optimal_when_candidates_are_noise():
    """Baseline features = actual signal-carriers. Candidates = pure noise.
    LassoCV should zero out the candidates → delta_r ≈ 0,
    new_features_kept is empty → BASELINE_OPTIMAL."""
    rng = np.random.default_rng(42)
    n_per_year = 200
    years = [2022, 2023, 2024, 2025]
    parts = []
    for y in years:
        # Signal features
        x1 = rng.normal(0, 1, n_per_year)
        x2 = rng.normal(0, 1, n_per_year)
        # Pure-noise candidates
        n1 = rng.normal(0, 1, n_per_year)
        n2 = rng.normal(0, 1, n_per_year)
        n3 = rng.normal(0, 1, n_per_year)
        noise = rng.normal(0, 0.5, n_per_year)
        target = 0.6 * x1 + 0.4 * x2 + noise
        parts.append(pd.DataFrame({
            "year": y, "split_day": 60,
            "f1": x1, "f2": x2,
            "noise1": n1, "noise2": n2, "noise3": n3,
            "y": target,
        }))
    df = pd.concat(parts, ignore_index=True)

    result = feature_ceiling(
        df=df,
        baseline_feats=["f1", "f2"],
        candidate_feats=["noise1", "noise2", "noise3"],
        target_col="y",
        train_years=years,
        min_train=100,
        min_test=30,
    )

    assert isinstance(result, FeatureCeiling)
    assert result.baseline_r > 0.5  # sanity
    assert abs(result.delta_r) < 0.005, (
        f"delta_r={result.delta_r:+.4f} should be tiny when candidates are noise"
    )
    assert len(result.new_features_kept) == 0, (
        f"Lasso should zero all noise candidates, kept: {result.new_features_kept}"
    )
    assert result.verdict == "BASELINE_OPTIMAL"


def test_feature_ceiling_returns_add_candidates_when_real_signal_in_candidates():
    """Baseline features are real signal-carriers but explain only part of the
    target. A real signal feature hides among noise candidates. Lasso should
    keep the real signal candidate → delta_r > 0.005, verdict ADD_CANDIDATES."""
    rng = np.random.default_rng(42)
    n_per_year = 250
    years = [2022, 2023, 2024, 2025]
    parts = []
    for y in years:
        # Baseline features
        x1 = rng.normal(0, 1, n_per_year)
        x2 = rng.normal(0, 1, n_per_year)
        # Candidates: two are noise, one is a real signal (z1)
        z1 = rng.normal(0, 1, n_per_year)  # real signal
        n1 = rng.normal(0, 1, n_per_year)
        n2 = rng.normal(0, 1, n_per_year)
        noise = rng.normal(0, 0.4, n_per_year)
        # Target depends meaningfully on x1, x2, AND z1
        target = 0.4 * x1 + 0.4 * x2 + 0.6 * z1 + noise
        parts.append(pd.DataFrame({
            "year": y, "split_day": 60,
            "f1": x1, "f2": x2,
            "z1": z1, "noise1": n1, "noise2": n2,
            "y": target,
        }))
    df = pd.concat(parts, ignore_index=True)

    result = feature_ceiling(
        df=df,
        baseline_feats=["f1", "f2"],
        candidate_feats=["z1", "noise1", "noise2"],
        target_col="y",
        train_years=years,
        min_train=100,
        min_test=30,
    )

    assert result.extended_r > result.baseline_r
    assert result.delta_r >= 0.005, (
        f"delta_r={result.delta_r:+.4f} should exceed +0.005 when a real signal is added"
    )
    assert "z1" in result.new_features_kept, (
        f"Lasso should keep z1 (real signal), kept: {result.new_features_kept}"
    )
    # Baseline features should still survive (they're real signal too)
    assert "f1" in result.survived_features
    assert "f2" in result.survived_features
    assert result.verdict == "ADD_CANDIDATES"
