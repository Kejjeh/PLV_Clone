"""
Decision component of Process+.

Measures the value of the hitter's swing/take decision on each pitch:

    discipline_value = EV(actual_choice) - EV(counterfactual_choice)

Both EVs are computed from PLV sub-model predictions (not observed outcomes),
so this component captures decision *quality* independent of execution.

Positive discipline_value means the hitter chose correctly (actual EV > alternative).

Population units: same run-expectancy units as the count-value table (delta_run_exp).
Cross-pitch sign convention: higher is *better for the hitter*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from plv_clone.models.plv_model import PLVModel, _lookup_vec
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def compute_discipline_values(
    df: pd.DataFrame,
    plv_model: PLVModel,
) -> pd.Series:
    """Compute per-pitch decision values for all pitches.

    For each pitch:
      - EV_take  = p_cs * ev_cs + p_ball * ev_ball
      - EV_swing = p_whiff * ev_whiff + p_contact * (p_foul * ev_foul + p_in_play * e_xwoba)

    discipline_value:
      - If hitter swung:  EV_swing - EV_take  (positive = swing was the better choice)
      - If hitter took:   EV_take  - EV_swing  (positive = take was the better choice)

    Args:
        df:        Feature-engineered pitch DataFrame (requires is_swing, balls, strikes,
                   and all PLV feature columns).
        plv_model: Loaded and scored PLVModel.

    Returns:
        Series of per-pitch discipline_value, indexed as df.
    """
    # Pre-encode categoricals once (mirrors PLVModel._pre_encode)
    df = plv_model._pre_encode(df)

    balls   = df["balls"].fillna(0).astype(int)
    strikes = df["strikes"].fillna(0).astype(int)

    # ── Sub-model predictions ──────────────────────────────────────────────
    p_swing   = pd.Series(plv_model.swing_model.predict_proba(df), index=df.index)
    p_take    = 1.0 - p_swing

    p_cs      = pd.Series(plv_model.cs_model.predict_proba(df), index=df.index)
    p_ball    = 1.0 - p_cs

    p_contact = pd.Series(plv_model.contact_model.predict_proba(df), index=df.index)
    p_whiff   = 1.0 - p_contact

    p_foul    = pd.Series(plv_model.foul_model.predict_proba(df), index=df.index)
    p_in_play = 1.0 - p_foul

    e_xwoba   = pd.Series(plv_model.bbv_model.predict(df), index=df.index)

    # ── Count table lookups ────────────────────────────────────────────────
    ev_cs     = _lookup_vec(plv_model.count_table, balls, strikes, "ev_called_strike")
    ev_ball   = _lookup_vec(plv_model.count_table, balls, strikes, "ev_ball")
    ev_whiff  = _lookup_vec(plv_model.count_table, balls, strikes, "ev_whiff")
    ev_foul   = _lookup_vec(plv_model.count_table, balls, strikes, "ev_foul")

    # ── EV branches ───────────────────────────────────────────────────────
    ev_take_branch  = p_cs * ev_cs + p_ball * ev_ball
    ev_contact_part = p_foul * ev_foul + p_in_play * e_xwoba
    ev_swing_branch = p_whiff * ev_whiff + p_contact * ev_contact_part

    # ── Decision value ────────────────────────────────────────────────────
    is_swing = df["is_swing"].astype(float)
    discipline_value = (
        is_swing       * (ev_swing_branch - ev_take_branch) +
        (1.0 - is_swing) * (ev_take_branch  - ev_swing_branch)
    )

    return pd.Series(discipline_value.values, index=df.index, name="discipline_value")
