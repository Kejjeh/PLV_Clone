"""
Expanding-window hitter tendency features.

All rolling stats use ONLY past data (expanding window shifted by 1 pitch)
to prevent look-ahead leakage.  The DataFrame must be sorted by pitch order
before calling build_batter_features().

Features are regularised with a Laplace (additive) prior to stabilise
small-sample estimates for hitters seen for the first time in a season.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_SORT_KEY = ["game_date", "game_pk", "at_bat_number", "pitch_number"]
_PRIOR_N = 50  # pseudo-count for Laplace smoothing


def build_batter_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add expanding-window batter tendency features.

    Returns a copy; the input is never modified.
    """
    df = df.copy()

    sort_cols = [c for c in _SORT_KEY if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    df = _add_swing_rate(df)
    df = _add_contact_rate(df)
    df = _add_chase_rate(df)

    logger.debug("build_batter_features: added batter tendency columns to %d rows.", len(df))
    return df


def _expanding_rate(
    df: pd.DataFrame,
    group_cols: list[str],
    numerator_col: str,
    denominator_col: str | None,
    prior_mean: float,
    prior_n: int,
    output_col: str,
) -> pd.DataFrame:
    """Generic expanding-rate helper with Laplace prior.

    For each row, computes:
        rate = (cumsum(numerator, shifted) + prior_mean * prior_n)
               / (cumcount + prior_n)
    where cumsum and cumcount use only pitches BEFORE the current row.
    """
    df = df.copy()

    available_groups = [c for c in group_cols if c in df.columns]
    if not available_groups or numerator_col not in df.columns:
        df[output_col] = prior_mean
        return df

    denom_series = (
        df[denominator_col].astype(float)
        if denominator_col and denominator_col in df.columns
        else pd.Series(np.ones(len(df)), index=df.index, dtype=float)
    )
    num_series = df[numerator_col].astype(float) * denom_series

    def _laplace_rate(group_num: pd.Series, group_denom: pd.Series) -> pd.Series:
        cum_num = group_num.shift(1).expanding().sum().fillna(0)
        cum_den = group_denom.shift(1).expanding().sum().fillna(0)
        return (cum_num + prior_mean * prior_n) / (cum_den + prior_n)

    result = df.groupby(available_groups).apply(
        lambda g: _laplace_rate(
            num_series.loc[g.index],
            denom_series.loc[g.index],
        )
    )
    # Flatten multi-index from groupby
    if hasattr(result.index, "levels") and len(result.index.levels) > 1:
        result = result.droplevel(list(range(len(available_groups))))

    df[output_col] = result.reindex(df.index).fillna(prior_mean)
    return df


def _add_swing_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Batter season-to-date swing rate (all pitches)."""
    league_swing_rate = 0.47  # approximate MLB average
    return _expanding_rate(
        df,
        group_cols=["batter"],
        numerator_col="is_swing",
        denominator_col=None,
        prior_mean=league_swing_rate,
        prior_n=_PRIOR_N,
        output_col="batter_swing_rate",
    )


def _add_contact_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Batter season-to-date contact rate (contacts per swing)."""
    league_contact_rate = 0.78
    # Only count swings as denominator
    df = df.copy()
    df["_is_swing_float"] = df["is_swing"].astype(float) if "is_swing" in df.columns else 1.0
    df = _expanding_rate(
        df,
        group_cols=["batter"],
        numerator_col="is_contact",
        denominator_col="_is_swing_float",
        prior_mean=league_contact_rate,
        prior_n=_PRIOR_N,
        output_col="batter_contact_rate",
    )
    df = df.drop(columns=["_is_swing_float"])
    return df


def _add_chase_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Batter season-to-date chase rate (swings on pitches outside zone)."""
    league_chase_rate = 0.30
    df = df.copy()
    # Chase = swing on pitches in chase zone (zone 11-14)
    if "is_chase_zone" not in df.columns:
        df["batter_chase_rate"] = league_chase_rate
        return df
    df["_is_out_of_zone"] = df["is_chase_zone"].astype(float)
    df = _expanding_rate(
        df,
        group_cols=["batter"],
        numerator_col="is_swing",
        denominator_col="_is_out_of_zone",
        prior_mean=league_chase_rate,
        prior_n=_PRIOR_N,
        output_col="batter_chase_rate",
    )
    df = df.drop(columns=["_is_out_of_zone"])
    return df
