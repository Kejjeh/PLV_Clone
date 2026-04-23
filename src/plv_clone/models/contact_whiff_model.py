"""
ContactModel: P(contact | swing, pitch features).

Trained on SWINGS ONLY. Target: is_contact.
P(whiff | swing) = 1 - P(contact | swing).
"""

from __future__ import annotations

from plv_clone.data.schemas import FEATURE_COLS_PLV
from plv_clone.models._base_lgbm import BaseLGBMClassifier

_CATEGORICAL_COLS = ["pitch_type", "pitch_group", "p_throws", "stand", "matchup", "zone_bin"]


class ContactModel(BaseLGBMClassifier):
    """Binary classifier predicting P(contact | swing)."""

    model_name = "contact_model"

    def __init__(
        self,
        feature_cols: list[str] | None = None,
        categorical_cols: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            feature_cols=feature_cols or FEATURE_COLS_PLV,
            categorical_cols=categorical_cols if categorical_cols is not None else _CATEGORICAL_COLS,
            **kwargs,
        )
