"""Smoke test for the centralized pitcher-alias + classifier surface
introduced by PR 2.

Per plan v11, PR 2 adds 0 mandatory new tests (the surface is exercised
by downstream consumers). This file adds one small test purely to lock the
public API (import surface + canonical-spelling round-trip).
"""
from plv_clone.utils.name_match import (
    KNOWN_PITCHER_ALIASES,
    canonical_pitcher_spelling,
    classify_pitcher_bucket,
)


def test_known_pitcher_aliases_round_trip() -> None:
    """Each alias resolves to a non-empty canonical spelling that is itself
    a no-op when fed back into canonical_pitcher_spelling."""
    assert KNOWN_PITCHER_ALIASES, "alias map is empty — PR 2 lost the centralized dict"

    for alias, formal in KNOWN_PITCHER_ALIASES.items():
        assert canonical_pitcher_spelling(alias) == formal
        # canonical -> canonical (idempotent)
        assert canonical_pitcher_spelling(formal) == formal

    # Non-alias passes through unchanged.
    assert canonical_pitcher_spelling("Tarik Skubal") == "Tarik Skubal"


def test_classify_pitcher_bucket_handles_unknown_id() -> None:
    """An unknown mlbam_id returns None (caller decides fallback)."""
    # 1 is reserved and never a real mlbam_id.
    assert classify_pitcher_bucket(1) is None
