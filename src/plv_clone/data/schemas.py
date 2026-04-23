"""
Column schemas and validation for the PLV Clone pipeline.

Defines:
  - PITCH_KEY_COLS       — the canonical 5-column composite primary key
  - STATCAST_RAW_COLS    — minimum columns to retain from pybaseball pulls
  - CLEAN_REQUIRED_COLS  — columns expected in the cleaned pitch table
  - FEATURE_COLS_PLV     — model input columns shared across PLV sub-models
  - FEATURE_COLS_BBV     — required columns for the BattedBallValueModel
  - validate_schema()    — raises SchemaValidationError on missing columns
"""

from __future__ import annotations

import pandas as pd


class SchemaValidationError(ValueError):
    """Raised when a DataFrame is missing expected columns."""


# ── Primary key ───────────────────────────────────────────────────────────────
# The 5-column composite key is the canonical join and uniqueness key everywhere.
# A human-readable pitch_id string is for display only and must never be used
# as a join key.
PITCH_KEY_COLS: list[str] = [
    "game_pk",
    "at_bat_number",
    "pitch_number",
    "pitcher",
    "batter",
]

# ── Raw Statcast columns to retain on ingest ──────────────────────────────────
STATCAST_RAW_COLS: list[str] = [
    # Identifiers
    "game_date",
    "game_pk",
    "at_bat_number",
    "pitch_number",
    "pitcher",
    "batter",
    # Pitch type and characteristics
    "pitch_type",
    "release_speed",
    "release_pos_x",
    "release_pos_z",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "release_extension",
    # Count and context
    "balls",
    "strikes",
    "outs_when_up",
    "inning",
    "p_throws",
    "stand",
    "zone",
    # Outcome descriptors
    "description",
    "events",
    # Launch / contact metrics
    "launch_speed",
    "launch_angle",
    "estimated_woba_using_speedangle",
    # Run expectancy
    "delta_run_exp",
    # wOBA fields
    "woba_value",
    "woba_denom",
    # Base state (on_1b, on_2b, on_3b store runner IDs — cast to bool)
    "on_1b",
    "on_2b",
    "on_3b",
    # Player names for display
    "player_name",
    "batter_name",
]

# ── Cleaned pitch table columns ───────────────────────────────────────────────
CLEAN_REQUIRED_COLS: list[str] = PITCH_KEY_COLS + [
    "game_date",
    "pitch_type",
    "pitch_group",          # added by cleaning layer
    "release_speed",
    "release_pos_x",
    "release_pos_z",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "release_extension",
    "balls",
    "strikes",
    "p_throws",
    "stand",
    "zone",
    "description",          # raw Statcast description — preserved
    "resolved_outcome",     # normalised outcome from DESCRIPTION_TO_OUTCOME
    "events",
    # Outcome flags (all derived strictly from resolved_outcome)
    "is_swing",
    "is_take",
    "is_called_strike",
    "is_ball",
    "is_whiff",
    "is_contact",
    "is_foul",
    "is_in_play",
    "is_hbp",
    "is_bunt_foul_k",
    "is_terminal_k",
    "is_walk",
    # Optional launch fields (null for non-contact)
    "launch_speed",
    "launch_angle",
    "estimated_woba_using_speedangle",
    "delta_run_exp",
]

# ── PLV sub-model shared feature columns ──────────────────────────────────────
# These columns must be present in the feature-engineered dataset before any
# PLV sub-model is trained or scored.
FEATURE_COLS_PLV: list[str] = [
    # Physical pitch characteristics
    "release_speed",
    "release_pos_x",
    "release_pos_z",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "release_extension",
    # Derived movement / location
    "movement_magnitude",
    "plate_x_abs",
    "induced_vertical_break",
    # Count state
    "balls",
    "strikes",
    # Categorical identifiers (passed as LightGBM categoricals)
    "pitch_type",
    "pitch_group",
    "p_throws",
    "stand",
    "matchup",          # p_throws + "_vs_" + stand
    "zone_bin",         # heart / in_zone / chase / waste
]

# ── BattedBallValueModel required features ────────────────────────────────────
# Explicitly specified per plan: count, pitch type, velocity, movement,
# location, pitcher handedness, batter stance, and handedness matchup.
# No launch conditions (launch_speed / launch_angle) allowed here.
FEATURE_COLS_BBV: list[str] = [
    "balls",
    "strikes",
    "pitch_type",
    "release_speed",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "p_throws",
    "stand",
    "matchup",
]


def validate_schema(df: pd.DataFrame, expected_cols: list[str], label: str = "") -> None:
    """Assert that *df* contains all *expected_cols*.

    Raises SchemaValidationError listing missing columns.
    """
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        prefix = f"[{label}] " if label else ""
        raise SchemaValidationError(
            f"{prefix}DataFrame is missing {len(missing)} expected column(s): {missing}"
        )
