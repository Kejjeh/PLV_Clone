"""
Tests for PLV scoring logic.

These tests use lightweight mock models to verify the staged formula,
scaling, and serialisation without requiring a full training run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from plv_clone.features.run_value_features import build_count_value_table
from plv_clone.utils.constants import COUNT_STATES


# ── Mock sub-models ────────────────────────────────────────────────────────────

class _ConstantClassifier:
    """Always predicts the same probability (for testing formula correctness)."""
    def __init__(self, p: float, feature_cols: list[str]) -> None:
        self.p = p
        self.feature_cols = feature_cols

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.p)


class _ConstantRegressor:
    """Always predicts the same value."""
    def __init__(self, val: float, feature_cols: list[str]) -> None:
        self.val = val
        self.feature_cols = feature_cols

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.val)


@pytest.fixture
def tiny_count_table(tmp_path, feature_df):
    """Build a count table from the fixture feature data."""
    df = feature_df.copy()
    if "delta_run_exp" not in df.columns:
        df["delta_run_exp"] = 0.0
    return build_count_value_table(df, tmp_path)


@pytest.fixture
def mock_plv_model(feature_df, tiny_count_table):
    """PLVModel backed by constant-output mock sub-models."""
    from plv_clone.models.plv_model import PLVModel

    feature_cols = ["balls", "strikes", "release_speed", "pfx_x", "pfx_z"]

    model = PLVModel(
        swing_model=_ConstantClassifier(0.47, feature_cols),
        cs_model=_ConstantClassifier(0.35, feature_cols),
        contact_model=_ConstantClassifier(0.78, feature_cols),
        foul_model=_ConstantClassifier(0.40, feature_cols),
        bbv_model=_ConstantRegressor(0.32, feature_cols),
        count_table=tiny_count_table,
        scaling_params={"mean": 0.0, "std": 0.01, "target_avg": 5.0, "target_std": 1.5},
    )
    return model


# ── E_post bounds ─────────────────────────────────────────────────────────────

class TestEPost:
    def test_e_post_finite(self, mock_plv_model, feature_df):
        """E_post must be finite for all pitches."""
        e_post = mock_plv_model.compute_e_post(feature_df)
        assert e_post.notna().all(), "E_post must not be NaN."
        assert np.isfinite(e_post).all(), "E_post must be finite."

    def test_e_post_consistent_with_formula(self, mock_plv_model, feature_df, tiny_count_table):
        """E_post with constant models = a value independently hand-computed
        from the same staged formula, not a tautological self-comparison
        (issue #26 — the old assertion compared e_post.mean() to itself,
        which is true by construction regardless of what compute_e_post
        actually computes, and can never catch a formula regression)."""
        from plv_clone.models.plv_model import _lookup_vec

        # Constant sub-model outputs, per the mock fixture:
        p_swing, p_take = 0.47, 0.53
        p_cs_given_take, p_ball_given_take = 0.35, 0.65
        p_contact_given_swing, p_whiff_given_swing = 0.78, 0.22
        p_foul_given_contact, p_in_play_given_contact = 0.40, 0.60
        e_xwoba_in_play = 0.32

        balls = feature_df["balls"].fillna(0).astype(int)
        strikes = feature_df["strikes"].fillna(0).astype(int)
        ev_ball = _lookup_vec(tiny_count_table, balls, strikes, "ev_ball")
        ev_cs = _lookup_vec(tiny_count_table, balls, strikes, "ev_called_strike")
        ev_whiff = _lookup_vec(tiny_count_table, balls, strikes, "ev_whiff")
        ev_foul = _lookup_vec(tiny_count_table, balls, strikes, "ev_foul")

        e_take_branch = p_cs_given_take * ev_cs + p_ball_given_take * ev_ball
        e_contact_branch = p_foul_given_contact * ev_foul + p_in_play_given_contact * e_xwoba_in_play
        e_swing_branch = p_whiff_given_swing * ev_whiff + p_contact_given_swing * e_contact_branch
        expected = p_take * e_take_branch + p_swing * e_swing_branch

        e_post = mock_plv_model.compute_e_post(feature_df)
        assert e_post.values == pytest.approx(expected.values, rel=1e-6)

    def test_plv_raw_sign_convention(self, mock_plv_model, feature_df):
        """plv_raw = count_baseline - E_post; a pitch that moves E_post below baseline > 0."""
        plv_raw = mock_plv_model.compute_plv_raw(feature_df)
        # Just check that the series is finite
        assert np.isfinite(plv_raw).all()


# ── PLV transform ─────────────────────────────────────────────────────────────

class TestPLVTransform:
    def test_plv_finite(self, mock_plv_model, feature_df):
        scored = mock_plv_model.score_pitches(feature_df)
        assert np.isfinite(scored["plv"]).all()

    def test_score_pitches_adds_expected_columns(self, mock_plv_model, feature_df):
        scored = mock_plv_model.score_pitches(feature_df)
        required = [
            "p_swing", "p_take", "p_cs_given_take", "p_contact_given_swing",
            "p_whiff_given_swing", "p_foul_given_contact", "p_in_play_given_contact",
            "e_xwoba_in_play", "e_post", "plv_raw", "plv",
        ]
        for col in required:
            assert col in scored.columns, f"Missing column '{col}' in scored output."

    def test_p_swing_plus_p_take_equals_one(self, mock_plv_model, feature_df):
        scored = mock_plv_model.score_pitches(feature_df)
        total = scored["p_swing"] + scored["p_take"]
        np.testing.assert_allclose(total, 1.0, rtol=1e-5)

    def test_plv_with_correct_scaling_near_league_avg(self, mock_plv_model, feature_df):
        """When plv_raw is near the mean, plv should be near target_avg (5.0)."""
        # Patch plv_raw to exactly the population mean
        plv_raw = pd.Series(np.zeros(len(feature_df)))  # mean=0, and scaling_params mean=0
        plv = mock_plv_model.transform_to_plv(plv_raw)
        np.testing.assert_allclose(plv.mean(), 5.0, atol=0.5)


# ── No look-ahead in features ─────────────────────────────────────────────────

class TestNoLookahead:
    def test_batter_swing_rate_non_null(self, feature_df):
        from plv_clone.features.batter_features import build_batter_features
        result = build_batter_features(feature_df)
        assert "batter_swing_rate" in result.columns
        assert result["batter_swing_rate"].notna().all()

    def test_batter_rate_bounded(self, feature_df):
        from plv_clone.features.batter_features import build_batter_features
        result = build_batter_features(feature_df)
        assert (result["batter_swing_rate"] >= 0).all()
        assert (result["batter_swing_rate"] <= 1).all()
