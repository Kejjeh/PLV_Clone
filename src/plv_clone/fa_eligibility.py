"""Eligibility-gated FA filtering (PR 4).

Replaces "compare your dropped 1B against every FA hitter" with
"compare only against FAs eligible at the slots your drop target opens
up." Used by the fa-replacement-pool skill.

Per plan v11 Decision 6, the following slot strings are EXCLUDED from
positional gating because they're either bench/IL OR utility-filler
slots that any hitter or pitcher can fill:
  - BE, IL, IL_SLOT (bench / injured-list slots)
  - UTIL, DH       (any hitter)
"""
from __future__ import annotations

from typing import Iterable, Sequence

import pandas as pd


# Slots that are NOT positional gates. A drop target whose ONLY eligible
# slot is UTIL gates on the BUCKET, not a specific position — meaning
# any hitter qualifies; this helper would return the full hitter pool
# unchanged.
NON_POSITIONAL_SLOTS = frozenset({"BE", "IL", "IL_SLOT", "UTIL", "DH"})


def positional_slots(eligible_slots: Iterable[str]) -> set[str]:
    """Strip NON_POSITIONAL_SLOTS, normalize casing.

    >>> positional_slots(["1B", "3B", "UTIL", "BE", "DH"])
    {'1B', '3B'}
    """
    return {s.upper() for s in eligible_slots if s and s.upper() not in NON_POSITIONAL_SLOTS}


def filter_eligible_fa(
    fa_df: pd.DataFrame,
    drop_target_eligible_slots: Sequence[str],
    *,
    fa_slot_col: str = "eligible_slots",
    fa_position_col: str = "primary_position",
) -> pd.DataFrame:
    """Return FA rows whose eligible-slot set overlaps with the
    POSITIONAL portion of the drop target's eligible_slots.

    Behavior:
      - If the drop target has NO positional slots (e.g., UTIL/BE/IL
        only), return the full ``fa_df`` unchanged — caller wanted a
        bucket-wide scan.
      - For each FA row, prefer ``fa_slot_col`` (list-typed); fall back
        to ``fa_position_col`` (string) when slots are missing.
      - Comparison is case-insensitive.

    Args:
        fa_df: FA pool DataFrame.
        drop_target_eligible_slots: ESPN ``eligible_slots`` list for the
            player being dropped (e.g. ``['1B','3B','CI','UTIL','BE']``).
        fa_slot_col: Column with the FA's eligible-slot list, if present.
        fa_position_col: Fallback column with the FA's primary position.

    Returns:
        DataFrame subset of ``fa_df`` keeping only positionally-eligible
        rows. Same column order; pandas index preserved.
    """
    target = positional_slots(drop_target_eligible_slots)
    if not target:
        # Drop target has no positional gate — return everything.
        return fa_df.copy()

    def _row_eligible(row: pd.Series) -> bool:
        slots = row.get(fa_slot_col)
        if isinstance(slots, (list, tuple, set)):
            fa_positional = positional_slots(slots)
        else:
            pos = row.get(fa_position_col)
            if not isinstance(pos, str) or not pos.strip():
                return False
            fa_positional = positional_slots([pos])
        return bool(target & fa_positional)

    mask = fa_df.apply(_row_eligible, axis=1)
    return fa_df.loc[mask].copy()


__all__ = ["NON_POSITIONAL_SLOTS", "positional_slots", "filter_eligible_fa"]
