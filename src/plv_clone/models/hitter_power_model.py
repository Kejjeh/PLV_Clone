"""
Power component of Process+.

Measures batted-ball damage quality for in-play events:

    power_value = actual_xwoba - expected_xwoba

    actual_xwoba   = estimated_woba_using_speedangle (Statcast)
    expected_xwoba = BattedBallValueModel prediction for this pitch

Power+ is defined *only for fair balls in play* (is_in_play == True and
estimated_woba_using_speedangle is not NaN). All other pitches are NaN.

This component deliberately excludes contact/whiff and foul/in-play decisions
(handled by Contact+). It answers only: given a fair ball was hit, how much
xwOBA above or below expectation did the hitter produce?

Population units: xwOBA points. Higher is *better for the hitter*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from plv_clone.models.plv_model import PLVModel
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def compute_power_values(
    df: pd.DataFrame,
    plv_model: PLVModel,
) -> pd.Series:
    """Compute per-pitch power values for in-play pitches.

    Returns NaN for all non-in-play pitches and for in-play pitches where
    estimated_woba_using_speedangle is missing.

    Args:
        df:        Feature-engineered pitch DataFrame.
        plv_model: Loaded PLVModel (uses BattedBallValueModel).

    Returns:
        Series of per-pitch power_value (NaN for non-in-play), indexed as df.
    """
    df = plv_model._pre_encode(df)

    # BattedBallValueModel prediction for every pitch (pitch chars only)
    e_xwoba = pd.Series(plv_model.bbv_model.predict(df), index=df.index)

    # Actual xwOBA from Statcast
    actual_xwoba = df["estimated_woba_using_speedangle"].copy()

    # Power value = actual - expected (only for valid in-play pitches)
    power_value = actual_xwoba - e_xwoba

    # Mask: only in-play pitches with non-null actual xwOBA
    is_in_play = df["is_in_play"].astype(bool)
    has_xwoba  = actual_xwoba.notna()
    valid      = is_in_play & has_xwoba

    result = pd.Series(np.nan, index=df.index, name="power_value")
    result[valid] = power_value[valid]

    return result
