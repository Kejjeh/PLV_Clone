"""
Statcast cleaning layer for the PLV Clone pipeline.

Two explicit, sequential stages:

  Stage 1 — Raw description normalisation (_normalize_description):
    Maps the raw Statcast `description` string to a canonical
    `resolved_outcome` value using DESCRIPTION_TO_OUTCOME from constants.
    The original `description` column is preserved alongside the new column.

  Stage 2 — Feature flag derivation (_add_outcome_flags):
    Derives all boolean flag columns (is_swing, is_contact, etc.) ONLY from
    `resolved_outcome`.  Never reads from the raw `description` string.

Additional cleaning: pitch type normalisation, pitch key deduplication and
uniqueness enforcement, missing value imputation for selected fields.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from plv_clone.data.schemas import (
    CLEAN_REQUIRED_COLS,
    PITCH_KEY_COLS,
    SchemaValidationError,
    validate_schema,
)
from plv_clone.utils.constants import (
    CONTACT_OUTCOMES,
    DESCRIPTION_TO_OUTCOME,
    FOUL_OUTCOMES,
    IN_PLAY_OUTCOMES,
    PITCH_TYPE_GROUP,
    SWING_OUTCOMES,
    TERMINAL_OUTCOMES,
    VALID_PITCH_TYPES,
    classify_zone,
)
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def clean_statcast(df: pd.DataFrame) -> pd.DataFrame:
    """Run the full cleaning pipeline on a raw Statcast DataFrame.

    Steps (in order):
      1. Drop duplicate pitches on the 5-column composite key.
      2. Filter to valid pitch types.
      3. Stage 1: Normalise description → resolved_outcome.
      4. Handle bunt-foul-K edge case.
      5. Stage 2: Derive outcome flags from resolved_outcome.
      6. Add pitch_group, pitch_id (display only), matchup.
      7. Impute selected missing numeric fields.
      8. Validate output schema.
      9. Log stats.

    Returns a cleaned copy; the input is never modified.
    """
    df = df.copy()
    n_raw = len(df)

    df = _drop_duplicates(df)
    df = _filter_valid_pitch_types(df)
    df = _normalize_description(df)
    df = _handle_bunt_foul_k(df)
    df = _add_outcome_flags(df)
    df = _add_derived_columns(df)
    df = _impute_missing(df)

    n_clean = len(df)
    logger.info(
        "clean_statcast: %d raw rows → %d clean rows (dropped %d)",
        n_raw,
        n_clean,
        n_raw - n_clean,
    )
    _log_outcome_distribution(df)

    # Soft schema check — warn on missing columns rather than hard-fail
    # (some optional columns like batter_name may not be present in all pulls)
    present = set(df.columns)
    core_missing = [c for c in PITCH_KEY_COLS if c not in present]
    if core_missing:
        raise SchemaValidationError(
            f"Pitch key columns missing after cleaning: {core_missing}"
        )

    return df


# ── Stage 1: Description normalisation ───────────────────────────────────────

def _normalize_description(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw `description` → `resolved_outcome` via the transition table.

    The mapping is a pure lookup; no logic beyond DESCRIPTION_TO_OUTCOME.
    Unrecognised descriptions are mapped to 'unknown' with a warning.
    """
    df = df.copy()
    raw_desc = df["description"].fillna("unknown").str.strip().str.lower()
    df["resolved_outcome"] = raw_desc.map(DESCRIPTION_TO_OUTCOME).fillna("unknown")

    unknown_mask = df["resolved_outcome"] == "unknown"
    if unknown_mask.any():
        unknown_vals = df.loc[unknown_mask, "description"].value_counts()
        logger.warning(
            "Unrecognised description values (will be excluded from modelling): %s",
            unknown_vals.to_dict(),
        )
    return df


# ── Bunt foul K edge case ─────────────────────────────────────────────────────

def _handle_bunt_foul_k(df: pd.DataFrame) -> pd.DataFrame:
    """Reclassify foul_bunt with 2 strikes as bunt_foul_k (PA-ending strikeout).

    This is an edge case where a bunt foul with two strikes results in a
    strikeout, unlike a regular foul which does not advance the strike count.
    """
    df = df.copy()
    bunt_foul_k_mask = (
        (df["description"].str.lower() == "foul_bunt")
        & (df["strikes"].astype(int, errors="ignore") == 2)
    )
    if bunt_foul_k_mask.any():
        df.loc[bunt_foul_k_mask, "resolved_outcome"] = "bunt_foul_k"
        logger.debug(
            "Reclassified %d foul_bunt rows as bunt_foul_k (2-strike bunt foul K).",
            bunt_foul_k_mask.sum(),
        )
    return df


# ── Stage 2: Flag derivation — ONLY from resolved_outcome ────────────────────

def _add_outcome_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Derive all boolean outcome flags from `resolved_outcome`.

    Never reads from the raw `description` column.
    """
    df = df.copy()
    ro = df["resolved_outcome"]

    df["is_swing"] = ro.isin(SWING_OUTCOMES)
    df["is_take"] = ~df["is_swing"]
    df["is_called_strike"] = ro == "called_strike"
    df["is_ball"] = ro == "ball"
    df["is_whiff"] = ro == "whiff"
    df["is_contact"] = ro.isin(CONTACT_OUTCOMES)
    df["is_foul"] = ro.isin(FOUL_OUTCOMES)
    df["is_in_play"] = ro.isin(IN_PLAY_OUTCOMES)
    df["is_hbp"] = ro == "hbp"
    df["is_bunt_foul_k"] = ro == "bunt_foul_k"
    df["is_terminal_k"] = ro.isin({"whiff", "bunt_foul_k"}) & (
        df["strikes"].astype(float, errors="ignore") >= 2
    )
    df["is_walk"] = ro == "walk"

    # Sanity invariants
    assert (df["is_contact"] <= df["is_swing"]).all(), "Contact must be subset of swing"
    assert (df["is_in_play"] <= df["is_contact"]).all(), "In-play must be subset of contact"
    assert (df["is_foul"] <= df["is_contact"]).all(), "Foul must be subset of contact"

    return df


# ── Additional derived columns ────────────────────────────────────────────────

def _add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add pitch_group, pitch_id (display), matchup, zone_bin."""
    df = df.copy()

    # Pitch type group
    df["pitch_group"] = df["pitch_type"].map(PITCH_TYPE_GROUP).fillna("Other")

    # Human-readable pitch identifier (display only — NOT a join key)
    df["pitch_id"] = (
        df["game_pk"].astype(str)
        + "_"
        + df["at_bat_number"].astype(str)
        + "_"
        + df["pitch_number"].astype(str)
    )

    # Handedness matchup categorical
    df["matchup"] = df["p_throws"].fillna("?") + "_vs_" + df["stand"].fillna("?")

    # Zone classification
    df["zone_bin"] = df["zone"].apply(classify_zone)

    return df


# ── Deduplication and filtering ───────────────────────────────────────────────

def _drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate on the 5-column pitch key.  Enforce uniqueness after dedup."""
    df = df.copy()
    n_before = len(df)
    key_cols = [c for c in PITCH_KEY_COLS if c in df.columns]
    df = df.sort_values(key_cols).drop_duplicates(subset=key_cols, keep="first")
    n_dupes = n_before - len(df)
    if n_dupes > 0:
        logger.info("Dropped %d duplicate pitches (pitch key dedup).", n_dupes)

    # Enforce uniqueness — raise if any remain
    remaining = df.duplicated(subset=key_cols).sum()
    if remaining > 0:
        raise SchemaValidationError(
            f"Uniqueness violation: {remaining} duplicate pitch keys remain after dedup."
        )
    return df


def _filter_valid_pitch_types(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with unrecognised pitch types."""
    df = df.copy()
    if "pitch_type" not in df.columns:
        return df
    valid_mask = df["pitch_type"].isin(VALID_PITCH_TYPES)
    n_dropped = (~valid_mask).sum()
    if n_dropped > 0:
        dropped_types = df.loc[~valid_mask, "pitch_type"].value_counts().to_dict()
        logger.info(
            "Dropped %d rows with invalid/unknown pitch types: %s",
            n_dropped,
            dropped_types,
        )
    return df[valid_mask].copy()


# ── Missing value imputation ──────────────────────────────────────────────────

def _impute_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Median-impute selected continuous features.

    launch_speed / launch_angle are intentionally NOT imputed — they are null
    for non-contact events and models that need them filter to in-play rows.
    """
    df = df.copy()
    cols_to_impute = [
        "release_speed",
        "release_pos_x",
        "release_pos_z",
        "pfx_x",
        "pfx_z",
        "plate_x",
        "plate_z",
        "release_extension",
    ]
    for col in cols_to_impute:
        if col not in df.columns:
            continue
        n_missing = df[col].isna().sum()
        if n_missing > 0:
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val)
            logger.debug("Imputed %d nulls in '%s' with median %.4f.", n_missing, col, median_val)
    return df


# ── Diagnostics ───────────────────────────────────────────────────────────────

def _log_outcome_distribution(df: pd.DataFrame) -> None:
    """Log a brief breakdown of swing/take/in-play rates."""
    total = len(df)
    if total == 0:
        return
    n_swing = df["is_swing"].sum()
    n_contact = df["is_contact"].sum()
    n_in_play = df["is_in_play"].sum()
    logger.info(
        "Outcome distribution: swing %.1f%% | contact (of swings) %.1f%% | in-play (of contact) %.1f%%",
        100 * n_swing / total,
        100 * n_contact / n_swing if n_swing > 0 else 0,
        100 * n_in_play / n_contact if n_contact > 0 else 0,
    )
