"""
Base class for LightGBM sub-models used in the PLV pipeline.

Provides:
  - Consistent fit / predict / save / load interface
  - Metadata persistence (feature columns, training date, eval metrics)
  - Calibrated probability output via CalibratedClassifierCV
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from plv_clone.models.calibration import (
    calibrate_classifier,
    load_calibrated_model,
    predict_proba_calibrated,
    save_calibrated_model,
)
from plv_clone.utils.io import write_json, read_json
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


class BaseLGBMClassifier:
    """Base binary classifier backed by LightGBM with isotonic calibration."""

    model_name: str = "base_classifier"

    def __init__(
        self,
        feature_cols: list[str],
        categorical_cols: list[str] | None = None,
        lgbm_params: dict[str, Any] | None = None,
        early_stopping_rounds: int = 50,
        random_seed: int = 42,
    ) -> None:
        self.feature_cols = list(feature_cols)
        self.categorical_cols = categorical_cols or []
        self.early_stopping_rounds = early_stopping_rounds
        self.random_seed = random_seed
        self._default_params = {
            "objective": "binary",
            "metric": ["binary_logloss", "auc"],
            "n_estimators": 800,
            "learning_rate": 0.05,
            "num_leaves": 63,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 50,
            "n_jobs": -1,
            "random_state": random_seed,
            "verbose": -1,
        }
        if lgbm_params:
            self._default_params.update(lgbm_params)

        self._booster: lgb.Booster | None = None
        self._calibrated = None
        self._meta: dict[str, Any] = {}

    # ── Training ──────────────────────────────────────────────────────────

    def _encode_categoricals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert string categorical columns to pd.Categorical dtype for LightGBM.

        Skips the copy if all columns are already categorical (pre-encoded by PLVModel).
        """
        if not self.categorical_cols:
            return df[self.feature_cols]
        needs_encode = False
        for col in self.categorical_cols:
            if col in df.columns:
                dtype = df[col].dtype
                if dtype == object or isinstance(dtype, pd.StringDtype) or str(dtype) in ("string", "str"):
                    needs_encode = True
                    break
        if needs_encode:
            out = df[self.feature_cols].copy()
            for col in self.categorical_cols:
                if col in out.columns:
                    dtype = out[col].dtype
                    if dtype == object or isinstance(dtype, pd.StringDtype) or str(dtype) in ("string", "str"):
                        out[col] = out[col].astype("category")
            return out
        return df[self.feature_cols]

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
    ) -> "BaseLGBMClassifier":
        """Train the LightGBM model with early stopping on the validation set."""
        X_tr = self._encode_categoricals(X_train)
        X_v = self._encode_categoricals(X_val)
        clf = lgb.LGBMClassifier(**self._default_params)
        clf.fit(
            X_tr,
            y_train,
            eval_set=[(X_v, y_val)],
            callbacks=[
                lgb.early_stopping(self.early_stopping_rounds, verbose=False),
                lgb.log_evaluation(period=-1),
            ],
            categorical_feature=self.categorical_cols or "auto",
        )
        self._booster = clf.booster_
        best_iter = clf.best_iteration_
        logger.info(
            "[%s] Trained — best iter: %d | val log_loss: %.4f",
            self.model_name,
            best_iter,
            clf.best_score_["valid_0"].get("binary_logloss", float("nan")),
        )

        # Calibrate on the validation set (X_v already encoded as pd.Categorical)
        self._calibrated = calibrate_classifier(
            self._booster,
            self.feature_cols,
            X_v,
            y_val,
            categorical_cols=self.categorical_cols,
        )
        self._meta = {
            "model_name": self.model_name,
            "feature_cols": self.feature_cols,
            "categorical_cols": self.categorical_cols,
            "best_iteration": best_iter,
            "train_size": len(X_train),
            "val_size": len(X_val),
            "trained_at": datetime.utcnow().isoformat(),
        }
        return self

    # ── Prediction ────────────────────────────────────────────────────────

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated positive-class probabilities."""
        if self._calibrated is None:
            raise RuntimeError(f"{self.model_name}: model not fitted or loaded.")
        return predict_proba_calibrated(self._calibrated, X, self.feature_cols)

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self, models_dir: Path) -> None:
        """Save the calibrated model and metadata."""
        models_dir = Path(models_dir)
        models_dir.mkdir(parents=True, exist_ok=True)
        save_calibrated_model(
            self._calibrated, models_dir / f"{self.model_name}_calibrated.pkl"
        )
        write_json(self._meta, models_dir / f"{self.model_name}_meta.json")
        logger.info("[%s] Saved to %s", self.model_name, models_dir)

    @classmethod
    def load(cls, models_dir: Path, **kwargs) -> "BaseLGBMClassifier":
        """Load a saved calibrated model."""
        models_dir = Path(models_dir)
        meta = read_json(models_dir / f"{cls.model_name}_meta.json")
        instance = cls(
            feature_cols=meta["feature_cols"],
            categorical_cols=meta.get("categorical_cols"),
            **kwargs,
        )
        instance._calibrated = load_calibrated_model(
            models_dir / f"{cls.model_name}_calibrated.pkl"
        )
        instance._meta = meta
        logger.info("[%s] Loaded from %s", cls.model_name, models_dir)
        return instance


class BaseLGBMRegressor:
    """Base regression model backed by LightGBM."""

    model_name: str = "base_regressor"

    def __init__(
        self,
        feature_cols: list[str],
        categorical_cols: list[str] | None = None,
        lgbm_params: dict[str, Any] | None = None,
        early_stopping_rounds: int = 50,
        random_seed: int = 42,
    ) -> None:
        self.feature_cols = list(feature_cols)
        self.categorical_cols = categorical_cols or []
        self.early_stopping_rounds = early_stopping_rounds
        self.random_seed = random_seed
        self._default_params = {
            "objective": "regression",
            "metric": ["rmse", "mae"],
            "n_estimators": 800,
            "learning_rate": 0.05,
            "num_leaves": 63,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 50,
            "n_jobs": -1,
            "random_state": random_seed,
            "verbose": -1,
        }
        if lgbm_params:
            self._default_params.update(lgbm_params)

        self._model: lgb.LGBMRegressor | None = None
        self._meta: dict[str, Any] = {}

    def _encode_categoricals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert string categorical columns to pd.Categorical dtype for LightGBM.

        Skips the copy if all columns are already categorical (pre-encoded by PLVModel).
        """
        if not self.categorical_cols:
            return df[self.feature_cols]
        needs_encode = False
        for col in self.categorical_cols:
            if col in df.columns:
                dtype = df[col].dtype
                if dtype == object or isinstance(dtype, pd.StringDtype) or str(dtype) in ("string", "str"):
                    needs_encode = True
                    break
        if needs_encode:
            out = df[self.feature_cols].copy()
            for col in self.categorical_cols:
                if col in out.columns:
                    dtype = out[col].dtype
                    if dtype == object or isinstance(dtype, pd.StringDtype) or str(dtype) in ("string", "str"):
                        out[col] = out[col].astype("category")
            return out
        return df[self.feature_cols]

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
    ) -> "BaseLGBMRegressor":
        X_tr = self._encode_categoricals(X_train)
        X_v = self._encode_categoricals(X_val)
        reg = lgb.LGBMRegressor(**self._default_params)
        reg.fit(
            X_tr,
            y_train,
            eval_set=[(X_v, y_val)],
            callbacks=[
                lgb.early_stopping(self.early_stopping_rounds, verbose=False),
                lgb.log_evaluation(period=-1),
            ],
            categorical_feature=self.categorical_cols or "auto",
        )
        self._model = reg
        best_iter = reg.best_iteration_
        logger.info(
            "[%s] Trained — best iter: %d | val RMSE: %.4f",
            self.model_name,
            best_iter,
            reg.best_score_["valid_0"].get("rmse", float("nan")),
        )
        self._meta = {
            "model_name": self.model_name,
            "feature_cols": self.feature_cols,
            "categorical_cols": self.categorical_cols,
            "best_iteration": best_iter,
            "train_size": len(X_train),
            "val_size": len(X_val),
            "trained_at": datetime.utcnow().isoformat(),
        }
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError(f"{self.model_name}: model not fitted or loaded.")
        return np.clip(
            self._model.predict(self._encode_categoricals(X)),
            0.0, 1.0,
        )

    def save(self, models_dir: Path) -> None:
        import pickle
        models_dir = Path(models_dir)
        models_dir.mkdir(parents=True, exist_ok=True)
        with open(models_dir / f"{self.model_name}_model.pkl", "wb") as f:
            pickle.dump(self._model, f)
        write_json(self._meta, models_dir / f"{self.model_name}_meta.json")
        logger.info("[%s] Saved to %s", self.model_name, models_dir)

    @classmethod
    def load(cls, models_dir: Path, **kwargs) -> "BaseLGBMRegressor":
        import pickle
        models_dir = Path(models_dir)
        meta = read_json(models_dir / f"{cls.model_name}_meta.json")
        instance = cls(
            feature_cols=meta["feature_cols"],
            categorical_cols=meta.get("categorical_cols"),
            **kwargs,
        )
        with open(models_dir / f"{cls.model_name}_model.pkl", "rb") as f:
            instance._model = pickle.load(f)
        instance._meta = meta
        logger.info("[%s] Loaded from %s", cls.model_name, models_dir)
        return instance
