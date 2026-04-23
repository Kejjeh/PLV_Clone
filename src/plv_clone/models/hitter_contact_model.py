"""
Contact component of Process+.

Measures per-swing execution quality: how well did the hitter perform relative
to what was expected on a swing at this pitch?

    contact_value = actual_swing_ev - expected_swing_ev

*actual_swing_ev* uses count-table EVs for whiffs and fouls, and the
BattedBallValueModel's **model-predicted** xwOBA (not actual xwOBA) for
in-play balls. This isolates the contact/whiff and foul/in-play dimensions
while preventing double-counting with the Power+ component.

    actual_swing_ev =
        if whiff:   ev_whiff(balls, strikes)
        if foul:    ev_foul(balls, strikes)
        if in_play: e_xwoba_model(pitch)

    expected_swing_ev =
        p_whiff   * ev_whiff   +
        p_contact * (p_foul    * ev_foul + p_in_play * e_xwoba_model)

contact_value is defined for *all swings* (is_swing == True).
It is NaN for takes; do not include takes in hitter aggregation.

Population units: run-expectancy, same as the count-value table. Higher is
*better for the hitter*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from plv_clone.models.plv_model import PLVModel, _lookup_vec
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def compute_contact_values(
    df: pd.DataFrame,
    plv_model: PLVModel,
) -> pd.Series:
    """Compute per-pitch contact values for all pitches.

    Returns NaN for takes (is_swing == False); contact_value is only
    meaningful on pitches where the hitter swung.

    Args:
        df:        Feature-engineered pitch DataFrame.
        plv_model: Loaded PLVModel (all five sub-models).

    Returns:
        Series of per-pitch contact_value (NaN for takes), indexed as df.
    """
    df = plv_model._pre_encode(df)

    balls   = df["balls"].fillna(0).astype(int)
    strikes = df["strikes"].fillna(0).astype(int)

    # ── Sub-model predictions ──────────────────────────────────────────────
    p_contact = pd.Series(plv_model.contact_model.predict_proba(df), index=df.index)
    p_whiff   = 1.0 - p_contact

    p_foul    = pd.Series(plv_model.foul_model.predict_proba(df), index=df.index)
    p_in_play = 1.0 - p_foul

    # Model-predicted xwOBA (no launch angle info — pitch characteristics only)
    e_xwoba   = pd.Series(plv_model.bbv_model.predict(df), index=df.index)

    # ── Count table lookups ────────────────────────────────────────────────
    ev_whiff  = _lookup_vec(plv_model.count_table, balls, strikes, "ev_whiff")
    ev_foul   = _lookup_vec(plv_model.count_table, balls, strikes, "ev_foul")

    # ── Expected swing EV (model-based) ───────────────────────────────────
    ev_contact_part  = p_foul * ev_foul + p_in_play * e_xwoba
    expected_swing_ev = p_whiff * ev_whiff + p_contact * ev_contact_part

    # ── Actual swing EV ────────────────────────────────────────────────────
    # Use model e_xwoba for in-play — do NOT use actual xwOBA here.
    is_whiff   = df["is_whiff"].astype(float)
    is_foul    = df["is_foul"].astype(float)
    is_in_play = df["is_in_play"].astype(float)

    actual_swing_ev = (
        is_whiff   * ev_whiff +
        is_foul    * ev_foul  +
        is_in_play * e_xwoba
    )

    contact_value = actual_swing_ev - expected_swing_ev

    # ── Mask takes as NaN ──────────────────────────────────────────────────
    is_swing = df["is_swing"].astype(bool)
    result = pd.Series(contact_value.values, index=df.index, name="contact_value")
    result[~is_swing] = np.nan

    return result
