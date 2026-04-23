"""
BattedBallValueModel: E[xwOBA | in_play, pitch features].

Trained on IN-PLAY pitches only. Target: estimated_woba_using_speedangle.

Required features (per plan):
  count, pitch type, velocity, movement, location,
  pitcher handedness, batter stance, handedness matchup.

NO launch conditions (launch_speed / launch_angle) — the model predicts
expected batted-ball value from pitch characteristics alone, before any
contact information is observed.  Launch conditions are used only for
validation and diagnostics in notebooks.
"""

from __future__ import annotations

from plv_clone.data.schemas import FEATURE_COLS_BBV
from plv_clone.models._base_lgbm import BaseLGBMRegressor

_CATEGORICAL_COLS = ["pitch_type", "p_throws", "stand", "matchup"]


class BattedBallValueModel(BaseLGBMRegressor):
    """Regression model predicting expected xwOBA for in-play pitches."""

    model_name = "batted_ball_model"

    def __init__(
        self,
        feature_cols: list[str] | None = None,
        categorical_cols: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            feature_cols=feature_cols or FEATURE_COLS_BBV,
            categorical_cols=categorical_cols if categorical_cols is not None else _CATEGORICAL_COLS,
            **kwargs,
        )
