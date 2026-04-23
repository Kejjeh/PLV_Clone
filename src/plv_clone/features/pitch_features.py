"""
Physical pitch feature engineering for PLV sub-models.

Adds derived columns to the cleaned pitch table that capture pitch
movement, location, count leverage, and handedness interactions.

All features are computed from Statcast fields that are publicly available
at the time the pitch is thrown (no launch conditions, no post-contact data).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from plv_clone.utils.constants import classify_zone
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

# Approximate gravity correction constant for induced vertical break
# pfx_z includes gravity; induced_vb removes the gravity component
_GRAVITY_CONSTANT = 32.174   # ft/s^2
_FEET_PER_INCH = 1.0 / 12.0


def build_pitch_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add engineered pitch features to a cleaned Statcast DataFrame.

    Returns a copy with additional columns.  The input is never modified.
    """
    df = df.copy()

    df = _add_movement_features(df)
    df = _add_location_features(df)
    df = _add_count_features(df)
    df = _add_handedness_features(df)
    df = _add_zone_features(df)

    logger.debug("build_pitch_features: added derived columns to %d rows.", len(df))
    return df


def _add_movement_features(df: pd.DataFrame) -> pd.DataFrame:
    """Movement magnitude, induced vertical break, horizontal break symmetry."""
    df = df.copy()

    # Movement magnitude (Euclidean distance of horizontal + vertical break)
    if "pfx_x" in df.columns and "pfx_z" in df.columns:
        df["movement_magnitude"] = np.sqrt(df["pfx_x"] ** 2 + df["pfx_z"] ** 2)
    else:
        df["movement_magnitude"] = np.nan

    # Induced vertical break: pfx_z already measures movement relative to a
    # spin-free trajectory, so it IS the induced vertical break (in feet).
    # We rename for clarity.
    if "pfx_z" in df.columns:
        df["induced_vertical_break"] = df["pfx_z"]
    else:
        df["induced_vertical_break"] = np.nan

    # Arm-side horizontal break: flip sign for LHP so positive = arm-side
    # for both handedness groups (improves model feature interpretability).
    if "pfx_x" in df.columns and "p_throws" in df.columns:
        df["arm_side_break"] = np.where(
            df["p_throws"] == "L",
            -df["pfx_x"],   # flip for lefties: arm side is positive
            df["pfx_x"],
        )
    else:
        df["arm_side_break"] = np.nan

    return df


def _add_location_features(df: pd.DataFrame) -> pd.DataFrame:
    """Location-based features: distance from centre, glove/arm-side bins."""
    df = df.copy()

    if "plate_x" in df.columns:
        df["plate_x_abs"] = df["plate_x"].abs()
    else:
        df["plate_x_abs"] = np.nan

    if "plate_z" in df.columns:
        # Normalise vertical location to [0, 1] using standard zone height
        # (approximate; actual sz_top/sz_bot vary per batter)
        SZ_BOT = 1.5   # feet above ground (approximate league average)
        SZ_TOP = 3.5
        df["plate_z_norm"] = (df["plate_z"] - SZ_BOT) / (SZ_TOP - SZ_BOT)
    else:
        df["plate_z_norm"] = np.nan

    # Distance from centre of plate (0, midpoint of zone)
    if "plate_x" in df.columns and "plate_z" in df.columns:
        SZ_MID = 2.5
        df["dist_from_centre"] = np.sqrt(
            df["plate_x"] ** 2 + (df["plate_z"] - SZ_MID) ** 2
        )
    else:
        df["dist_from_centre"] = np.nan

    return df


def _add_count_features(df: pd.DataFrame) -> pd.DataFrame:
    """Encode count state as numeric leverage and categorical."""
    df = df.copy()

    if "balls" in df.columns and "strikes" in df.columns:
        # Simple count leverage index: hitter-favourable counts are positive,
        # pitcher-favourable are negative (approximation)
        _COUNT_LEVERAGE: dict[tuple[int, int], float] = {
            (0, 0): 0.0,
            (1, 0): 0.5,  (0, 1): -0.5,
            (2, 0): 1.0,  (1, 1): 0.0,   (0, 2): -1.0,
            (3, 0): 1.5,  (2, 1): 0.5,   (1, 2): -0.5,
                          (3, 1): 1.0,   (2, 2): 0.0,
                                          (3, 2): 0.5,
        }
        df["count_leverage"] = [
            _COUNT_LEVERAGE.get((int(b), int(s)), 0.0)
            for b, s in zip(df["balls"].fillna(0), df["strikes"].fillna(0))
        ]
        df["count_str"] = (
            df["balls"].fillna(0).astype(int).astype(str)
            + "-"
            + df["strikes"].fillna(0).astype(int).astype(str)
        )
    else:
        df["count_leverage"] = np.nan
        df["count_str"] = "0-0"

    return df


def _add_handedness_features(df: pd.DataFrame) -> pd.DataFrame:
    """Handedness matchup categorical feature."""
    df = df.copy()

    if "p_throws" in df.columns and "stand" in df.columns:
        if "matchup" not in df.columns:
            df["matchup"] = df["p_throws"].fillna("?") + "_vs_" + df["stand"].fillna("?")
        # Same-side / opposite-side flag (1 = platoon advantage for pitcher)
        df["is_same_hand"] = (df["p_throws"] == df["stand"]).astype(int)
    else:
        df.setdefault("matchup", "?_vs_?")
        df["is_same_hand"] = 0

    return df


def _add_zone_features(df: pd.DataFrame) -> pd.DataFrame:
    """Zone bin and zone-based shadow flags."""
    df = df.copy()

    if "zone" in df.columns:
        if "zone_bin" not in df.columns:
            df["zone_bin"] = df["zone"].apply(classify_zone)
        df["is_in_zone"] = df["zone_bin"].isin(["heart", "in_zone"]).astype(int)
        df["is_chase_zone"] = (df["zone_bin"] == "chase").astype(int)
    else:
        df.setdefault("zone_bin", "unknown")
        df["is_in_zone"] = 0
        df["is_chase_zone"] = 0

    return df
