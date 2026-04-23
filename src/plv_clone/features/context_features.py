"""
Within-game and within-season context features.

These features are valid for retrospective modelling (training and
historical scoring) but would require careful real-time management for
live predictions.  They are clearly labelled as context features.

Rolling velocity deltas and pitch-in-outing features require the
DataFrame to be sorted by (game_date, game_pk, at_bat_number, pitch_number).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_SORT_KEY = ["game_date", "game_pk", "at_bat_number", "pitch_number"]


def build_context_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add within-game and within-season context features.

    Requires the DataFrame to be sorted by pitch order.
    Returns a copy; the input is never modified.
    """
    df = df.copy()

    if not _is_sorted(df):
        logger.debug("Sorting DataFrame by pitch order for context features.")
        sort_cols = [c for c in _SORT_KEY if c in df.columns]
        df = df.sort_values(sort_cols).reset_index(drop=True)

    df = _add_pitch_in_ab(df)
    df = _add_velocity_delta(df)

    logger.debug("build_context_features: added context columns to %d rows.", len(df))
    return df


def _is_sorted(df: pd.DataFrame) -> bool:
    sort_cols = [c for c in _SORT_KEY if c in df.columns]
    if not sort_cols:
        return True
    sorted_df = df[sort_cols].sort_values(sort_cols)
    return (sorted_df.values == df[sort_cols].values).all()


def _add_pitch_in_ab(df: pd.DataFrame) -> pd.DataFrame:
    """Pitch sequence number within each plate appearance."""
    df = df.copy()
    if "at_bat_number" in df.columns and "game_pk" in df.columns:
        df["pitch_in_ab"] = df.groupby(["game_pk", "at_bat_number"]).cumcount() + 1
    else:
        df["pitch_in_ab"] = 1
    return df


def _add_velocity_delta(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling mean velocity delta for each (pitcher, pitch_type) combination.

    velocity_delta = release_speed - rolling mean of last 50 pitches of that type.
    Positive = pitcher throwing harder than their recent norm for that pitch.

    Uses expanding window within each (pitcher, pitch_type) group, shifted by 1
    to prevent data leakage (no look-ahead).
    """
    df = df.copy()

    if "release_speed" not in df.columns or "pitcher" not in df.columns:
        df["velocity_delta"] = np.nan
        return df

    key = ["pitcher", "pitch_type"]
    available_key = [c for c in key if c in df.columns]
    if not available_key:
        df["velocity_delta"] = np.nan
        return df

    # Compute rolling mean (window=50, min_periods=5) shifted by 1 pitch
    def _rolling_mean_shifted(s: pd.Series) -> pd.Series:
        return s.shift(1).rolling(window=50, min_periods=5).mean()

    rolling_mean = df.groupby(available_key)["release_speed"].transform(
        _rolling_mean_shifted
    )
    df["velocity_delta"] = df["release_speed"] - rolling_mean
    return df
