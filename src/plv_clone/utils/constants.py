"""
Static constants for the PLV Clone pipeline.

This module is the single source of truth for:
  - Pitch type groupings
  - The outcome transition table (raw description → resolved outcome)
  - Count-state transition logic
  - Terminal PA xwOBA values
  - Zone classification buckets
"""

from __future__ import annotations

# ── Pitch type groupings ────────────────────────────────────────────────────
# Maps Statcast pitch_type codes to a coarse group label.
PITCH_TYPE_GROUP: dict[str, str] = {
    "FF": "Fastball",   # Four-seam fastball
    "SI": "Fastball",   # Sinker
    "FC": "Fastball",   # Cutter
    "SL": "Breaking",   # Slider
    "CU": "Breaking",   # Curveball
    "KC": "Breaking",   # Knuckle curve
    "SV": "Breaking",   # Sweeper
    "ST": "Breaking",   # Sweeping curve (newer code)
    "CS": "Breaking",   # Slow curve
    "CH": "Offspeed",   # Changeup
    "FS": "Offspeed",   # Splitter
    "FO": "Offspeed",   # Forkball
    "SC": "Offspeed",   # Screwball
    "KN": "Offspeed",   # Knuckleball
    "EP": "Offspeed",   # Eephus
}

VALID_PITCH_TYPES: list[str] = sorted(PITCH_TYPE_GROUP.keys())

# ── Terminal PA xwOBA constants ──────────────────────────────────────────────
# These are FIXED values, not computed from training data.
# Source: publicly available MLB xwOBA scale values.
TERMINAL_XWOBA: dict[str, float] = {
    "walk": 0.690,
    "hbp": 0.720,
    "strikeout": 0.000,
    "catcher_interf": 0.690,  # treat same as walk
}

# ── Outcome transition table ─────────────────────────────────────────────────
# Maps raw Statcast `description` strings to a canonical `resolved_outcome`.
# This is the single source of truth for all downstream outcome flag derivation.
#
# Vocabulary of resolved_outcome values:
#   ball            - non-swing, count advances to next ball state
#   called_strike   - non-swing, count advances to next strike state
#   whiff           - swing and miss, count advances to next strike state
#   foul            - swing with contact, foul ball (see bunt_foul_k for edge case)
#   foul_tip        - foul tip (treated as whiff for contact purposes if caught)
#   in_play         - swing with contact, ball put in play (PA may end)
#   hbp             - hit by pitch, PA ends
#   walk            - ball four, PA ends (rare: can appear as description)
#   strikeout       - third strike, PA ends (rare: can appear as description)
#   bunt_foul_k     - bunt foul with 2 strikes (PA ends as strikeout)
#   catcher_interf  - catcher interference, PA ends
#   unknown         - unrecognized description (excluded from modeling)
DESCRIPTION_TO_OUTCOME: dict[str, str] = {
    # Balls / non-swings
    "ball": "ball",
    "blocked_ball": "ball",
    "pitchout": "ball",
    "automatic_ball": "ball",
    # Called strikes
    "called_strike": "called_strike",
    "automatic_strike": "called_strike",
    # Swinging strikes / whiffs
    "swinging_strike": "whiff",
    "swinging_strike_blocked": "whiff",
    "missed_bunt": "whiff",
    # Foul tips (treated as whiff for contact model; advances strike count if < 2)
    "foul_tip": "foul_tip",
    # Foul balls
    "foul": "foul",
    "foul_bunt": "foul",  # NOTE: reclassified to bunt_foul_k when strikes == 2
    "foul_pitchout": "foul",
    # Balls in play
    "hit_into_play": "in_play",
    "hit_into_play_no_out": "in_play",
    "hit_into_play_score": "in_play",
    # Terminal events (rare as description values; usually in `events` column)
    "hit_by_pitch": "hbp",
    "pitchout_hit_into_play": "in_play",
    "pitchout_hit_into_play_score": "in_play",
    # Interference
    "catcher_interf": "catcher_interf",
}

# Resolved outcomes that constitute a swing
SWING_OUTCOMES: frozenset[str] = frozenset(
    ["whiff", "foul_tip", "foul", "bunt_foul_k", "in_play"]
)

# Resolved outcomes that constitute contact (swing but not a miss)
CONTACT_OUTCOMES: frozenset[str] = frozenset(["foul_tip", "foul", "bunt_foul_k", "in_play"])

# Resolved outcomes that are fair balls in play
IN_PLAY_OUTCOMES: frozenset[str] = frozenset(["in_play"])

# Resolved outcomes that are foul balls (for the foul model target)
FOUL_OUTCOMES: frozenset[str] = frozenset(["foul", "foul_tip", "bunt_foul_k"])

# Resolved outcomes that terminate the PA
TERMINAL_OUTCOMES: frozenset[str] = frozenset(
    ["hbp", "catcher_interf"]
    # walk and strikeout are captured via balls/strikes count exhaustion, not description
)

# ── Count-state transitions ───────────────────────────────────────────────────
# All valid (balls, strikes) states in a plate appearance.
COUNT_STATES: list[tuple[int, int]] = [
    (0, 0), (0, 1), (0, 2),
    (1, 0), (1, 1), (1, 2),
    (2, 0), (2, 1), (2, 2),
    (3, 0), (3, 1), (3, 2),
]


def next_count_after_ball(balls: int, strikes: int) -> tuple[int, int] | str:
    """Return next (balls, strikes) after a ball, or 'walk' if ball four."""
    if balls >= 3:
        return "walk"
    return (balls + 1, strikes)


def next_count_after_strike(balls: int, strikes: int) -> tuple[int, int] | str:
    """Return next (balls, strikes) after a strike, or 'strikeout' if third strike."""
    if strikes >= 2:
        return "strikeout"
    return (balls, strikes + 1)


def next_count_after_foul(balls: int, strikes: int) -> tuple[int, int]:
    """Return next (balls, strikes) after a foul ball. Count never advances past 2 strikes."""
    if strikes < 2:
        return (balls, strikes + 1)
    return (balls, strikes)  # stays at 2 strikes on foul


# ── Statcast zone classification ─────────────────────────────────────────────
# Statcast uses zones 1-9 (in-zone) and 11-14 (chase zones outside zone).
IN_ZONE: frozenset[int] = frozenset(range(1, 10))       # zones 1–9
CHASE_ZONE: frozenset[int] = frozenset(range(11, 15))   # zones 11–14
HEART_ZONE: frozenset[int] = frozenset([5])              # centre of zone


def classify_zone(zone: int | float | None) -> str:
    """Classify a Statcast zone integer into heart / in_zone / chase / waste."""
    if zone is None or (isinstance(zone, float) and zone != zone):
        return "unknown"
    z = int(zone)
    if z == 5:
        return "heart"
    if z in IN_ZONE:
        return "in_zone"
    if z in CHASE_ZONE:
        return "chase"
    return "waste"
