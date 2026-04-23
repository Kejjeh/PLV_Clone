"""
Probability calibration for PLV sub-model classifiers.

Wraps trained LightGBM boosters with isotonic regression calibration
fit on a held-out calibration set.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


class CalibratedBooster:
    """Trained LightGBM booster + isotonic calibration layer.

    Replaces CalibratedClassifierCV(cv='prefit') which was removed in sklearn 1.7+.
    """

    def __init__(
        self,
        booster,
        feature_cols: list[str],
        calibrator: IsotonicRegression,
        categorical_cols: list[str] | None = None,
    ) -> None:
        self.booster = booster
        self.feature_cols = feature_cols
        self.calibrator = calibrator
        self.categorical_cols = categorical_cols or []

    def _prepare_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """Select and encode features for LightGBM prediction.

        If all categorical columns are already pd.Categorical (pre-encoded by PLVModel),
        returns a view without copying. Otherwise encodes in-place on a copy.
        """
        needs_encode = False
        for col in self.categorical_cols:
            if col in X.columns:
                dtype = X[col].dtype
                if dtype == object or isinstance(dtype, pd.StringDtype) or str(dtype) in ("string", "str"):
                    needs_encode = True
                    break
        if needs_encode:
            out = X[self.feature_cols].copy()
            for col in self.categorical_cols:
                if col in out.columns:
                    dtype = out[col].dtype
                    if dtype == object or isinstance(dtype, pd.StringDtype) or str(dtype) in ("string", "str"):
                        out[col] = out[col].astype("category")
            return out
        return X[self.feature_cols]

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated positive-class probabilities."""
        X_feat = self._prepare_features(X) if isinstance(X, pd.DataFrame) else X
        raw = self.booster.predict(X_feat)
        return self.calibrator.predict(raw)


def calibrate_classifier(
    booster,
    feature_cols: list[str],
    X_cal: pd.DataFrame,
    y_cal: pd.Series,
    method: str = "isotonic",
    categorical_cols: list[str] | None = None,
) -> "CalibratedBooster":
    """Fit a calibration layer on top of a trained LightGBM booster.

    Args:
        booster:          Trained lgb.Booster.
        feature_cols:     Ordered list of feature column names.
        X_cal:            Calibration set features (DataFrame, already encoded).
        y_cal:            Calibration set labels (Series).
        method:           'isotonic' (only isotonic supported currently).
        categorical_cols: Column names that are categorical (for predict encoding).

    Returns:
        Fitted CalibratedBooster instance.
    """
    # X_cal is already encoded (pd.Categorical) — pass directly to booster
    raw_preds = booster.predict(X_cal[feature_cols])
    y_arr = np.asarray(y_cal, dtype=float)
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw_preds, y_arr)
    calibrated = CalibratedBooster(booster, feature_cols, iso, categorical_cols)
    logger.info(
        "Calibrated classifier using isotonic regression on %d samples.", len(y_cal)
    )
    return calibrated


def predict_proba_calibrated(
    calibrated_model: "CalibratedBooster",
    X: pd.DataFrame,
    feature_cols: list[str],
) -> np.ndarray:
    """Return calibrated positive-class probabilities for X.

    Args:
        calibrated_model: Fitted CalibratedBooster.
        X:                Feature DataFrame.
        feature_cols:     Ordered feature columns.

    Returns:
        1-D array of positive-class probabilities.
    """
    return calibrated_model.predict_proba(X)


def save_calibrated_model(model: "CalibratedBooster", path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model, f)
    logger.debug("Saved calibrated model -> %s", path)


def load_calibrated_model(path: Path) -> "CalibratedBooster":
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Calibrated model not found: {path}")
    with open(path, "rb") as f:
        return pickle.load(f)
