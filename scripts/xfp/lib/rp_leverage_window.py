"""RP leverage-window diagnostic (PR 7, Gate 0c).

Given an RP's recent role-usage stats, classify the trailing window as:

  - SAVE_PROMOTION_WINDOW    : closer-transition signal. Save-event count
                                in the trailing window is above the
                                promotion threshold AND prior-window save
                                count was zero or near-zero.
  - SETUP_CONSOLIDATION_WINDOW: setup role solidifying. Hold count above
                                the consolidation threshold AND save
                                count below promotion threshold.
  - None                      : neither signal present.

The two windows are DELIBERATELY DISTINCT (plan v11 Decision 7). Some
prior code treated "high HLD" as a SAVE proxy when the SV count was
thin -- that conflates two role transitions that have different fantasy
implications:

  - SAVE_PROMOTION moves a player from rprs2 ~2.0 FP/g HLD-rate territory
    to ~5.0 FP/g SV-rate territory. Major value swing.
  - SETUP_CONSOLIDATION holds the player IN the HLD territory but with
    higher floor. Modest value increase.

Callers (e.g. fa-monitor RP signal, save_handcuffs) want to know WHICH.
"""
from __future__ import annotations

from typing import Optional


# Thresholds derived from BrownU scoring + historical promotion-window
# patterns. The SAVE threshold is small because save EVENTS are
# infrequent; even 2 saves in a 14-day window signals role tilt.
SAVE_PROMOTION_MIN_SV_RECENT: int = 2
SAVE_PROMOTION_MAX_SV_PRIOR: int = 0

SETUP_CONSOLIDATION_MIN_HLD_RECENT: int = 4
SETUP_CONSOLIDATION_MAX_SV_RECENT: int = 1


def classify_rp_leverage_window(
    *,
    sv_recent: int,
    hld_recent: int,
    sv_prior: int = 0,
    hld_prior: int = 0,
) -> Optional[str]:
    """Classify the trailing-window leverage signal.

    Args:
        sv_recent: Saves in the trailing window (typically last 14 days).
        hld_recent: Holds in the trailing window.
        sv_prior: Saves in the immediately-prior window of the same
            length (default 0 = "no prior data"; fail-safe).
        hld_prior: Holds in the immediately-prior window (currently
            unused; reserved for SETUP-degradation future use).

    Returns:
        ``"SAVE_PROMOTION_WINDOW"``,
        ``"SETUP_CONSOLIDATION_WINDOW"``, or
        ``None`` when no window applies.

    Priority: SAVE_PROMOTION wins ties (a player with recent saves AND
    holds is best framed as a closer-transition, not a setup
    consolidation). This matches the fantasy-decision lens -- SV is the
    more lucrative signal.
    """
    # SAVE_PROMOTION_WINDOW
    if sv_recent >= SAVE_PROMOTION_MIN_SV_RECENT and sv_prior <= SAVE_PROMOTION_MAX_SV_PRIOR:
        return "SAVE_PROMOTION_WINDOW"

    # SETUP_CONSOLIDATION_WINDOW
    if (
        hld_recent >= SETUP_CONSOLIDATION_MIN_HLD_RECENT
        and sv_recent <= SETUP_CONSOLIDATION_MAX_SV_RECENT
    ):
        return "SETUP_CONSOLIDATION_WINDOW"

    return None


__all__ = [
    "classify_rp_leverage_window",
    "SAVE_PROMOTION_MIN_SV_RECENT",
    "SAVE_PROMOTION_MAX_SV_PRIOR",
    "SETUP_CONSOLIDATION_MIN_HLD_RECENT",
    "SETUP_CONSOLIDATION_MAX_SV_RECENT",
]
