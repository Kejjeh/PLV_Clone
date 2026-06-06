"""Eligibility-gated FA filtering test (PR 4)."""
import pandas as pd

from plv_clone.fa_eligibility import (
    NON_POSITIONAL_SLOTS,
    filter_eligible_fa,
    positional_slots,
)


def test_positional_slots_strips_util_be_il_dh() -> None:
    assert positional_slots(["1B", "3B", "UTIL", "BE", "DH", "IL"]) == {"1B", "3B"}
    assert positional_slots(["util", "be"]) == set()  # case-insensitive
    assert positional_slots([]) == set()


def test_filter_eligible_fa_keeps_only_positional_overlap() -> None:
    """A drop target eligible at 1B/3B/CI/UTIL/BE matches FAs at 1B or
    3B (or CI if it appears) but NOT pure OFs."""
    fa = pd.DataFrame({
        "player_name": ["Pete", "Manny", "Mookie", "Mike"],
        "eligible_slots": [
            ["1B", "UTIL", "BE"],   # eligible at 1B -> match
            ["3B", "UTIL", "BE"],   # 3B -> match
            ["OF", "UTIL", "BE"],   # OF only -> no match
            ["1B", "OF", "UTIL"],   # 1B + OF -> match (overlap on 1B)
        ],
        "primary_position": ["1B", "3B", "OF", "1B"],
    })
    target = ["1B", "3B", "CI", "UTIL", "BE"]
    out = filter_eligible_fa(fa, target)
    assert list(out["player_name"]) == ["Pete", "Manny", "Mike"]


def test_filter_eligible_fa_falls_back_to_primary_position() -> None:
    """When eligible_slots is missing, primary_position is the
    fallback gate."""
    fa = pd.DataFrame({
        "player_name": ["A", "B", "C"],
        "primary_position": ["1B", "OF", "3B"],
    })
    target = ["1B", "UTIL", "BE"]
    out = filter_eligible_fa(fa, target, fa_slot_col="not_a_col")
    assert list(out["player_name"]) == ["A"]


def test_filter_eligible_fa_bypasses_when_target_is_util_only() -> None:
    """A drop target with NO positional slots (UTIL/BE/IL only) means
    the caller wants a bucket-wide scan — return everything."""
    fa = pd.DataFrame({
        "player_name": ["A", "B", "C"],
        "primary_position": ["1B", "OF", "3B"],
    })
    out = filter_eligible_fa(fa, ["UTIL", "BE", "IL"])
    assert len(out) == 3


def test_non_positional_slots_is_lockable_set() -> None:
    """Lock the slot exclusion set so a future refactor that
    accidentally adds a positional slot (e.g. 'OF') to this set will
    fail loudly."""
    assert NON_POSITIONAL_SLOTS == frozenset({"BE", "IL", "IL_SLOT", "UTIL", "DH"})
