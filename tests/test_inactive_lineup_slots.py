"""A bench player scores in this league. Pin it.

WHY THIS EXISTS
CLAUDE.md gotcha #7 is unusually emphatic: "BE slot = active for Josh... Never
tell Josh a bench player 'won't score' — the slot doesn't matter, health does.
Canonical fix 2026-06-15."

That fix removed the bench slots from `INACTIVE_LINEUP_SLOTS`. Nothing tested
it. Meanwhile TWO of the three pieces of prose around it still described the
pre-fix behaviour:

  * the header comment above the constant, dated 2026-06-03, still read
    "Bench/IL/IR slots accrue ~0 actual FP ... including them inflates
    team-total projection by ~20 FP" — a direct argument for putting bench
    back in;
  * `_is_active_slot`'s own docstring still said "Active = anything NOT in
    {BE, IL*, IR}", contradicting the constant it reads.

An untested fix guarded by documentation that argues against it is a fix with
a short life expectancy. These tests are the guard. (Added 2026-08-27.)
"""
from __future__ import annotations

import pytest

bmd = pytest.importorskip("scripts.xfp.build_matchup_dashboard")


class _P:
    """Minimal stand-in for an espn_api player."""

    def __init__(self, slot, injury_status="ACTIVE"):
        self.lineup_slot = slot
        self.injuryStatus = injury_status


@pytest.mark.parametrize("slot", ["BE", "BENCH", "BN", "be", "Bench"])
def test_bench_is_an_active_scoring_slot(slot):
    """The canonical rule: health decides, not the slot."""
    assert bmd._is_active_slot(_P(slot)) is True, (
        f"lineup_slot={slot!r} must count as active — Josh activates every "
        f"healthy bench player before lock (gotcha #7)"
    )


def test_bench_slots_are_absent_from_the_inactive_set():
    """Guard the constant directly, so the reason survives a refactor."""
    inactive = {s.upper() for s in bmd.INACTIVE_LINEUP_SLOTS}
    leaked = inactive & {"BE", "BENCH", "BN"}
    assert not leaked, (
        f"{sorted(leaked)} is back in INACTIVE_LINEUP_SLOTS. A bench player "
        f"scores in BrownU (gotcha #7, canonical fix 2026-06-15) — zeroing him "
        f"by slot understates every team total that carries a healthy bench."
    )


@pytest.mark.parametrize("slot", ["IL", "IL10", "IL15", "IL60", "IR", "il60"])
def test_il_and_ir_slots_are_inactive(slot):
    """The half of the 2026-06-03 measurement that still stands."""
    assert bmd._is_active_slot(_P(slot)) is False, (
        f"lineup_slot={slot!r} must count as INACTIVE"
    )


@pytest.mark.parametrize("slot", ["SP", "RP", "C", "1B", "OF", "UTIL", "DH", "P"])
def test_real_lineup_slots_are_active(slot):
    assert bmd._is_active_slot(_P(slot)) is True


def test_an_injured_player_in_an_active_slot_is_still_slot_active():
    """Slot and health are separate axes — the Langford OF / Helsley BE case.

    `_is_active_slot` answers "does this slot score", NOT "is he healthy".
    Injury zeroing happens in project_player via injuryStatus. Conflating the
    two is don't-do #2.
    """
    assert bmd._is_active_slot(_P("OF", injury_status="TEN_DAY_IL")) is True
    assert bmd._is_active_slot(_P("BE", injury_status="DAY_TO_DAY")) is True


def test_missing_or_odd_slot_does_not_crash():
    assert bmd._is_active_slot(None) is False
    assert bmd._is_active_slot(_P(None)) is True   # unknown slot != inactive
    assert bmd._is_active_slot(_P("")) is True


def test_il_injury_states_is_the_canonical_set_not_a_hand_typed_copy():
    """Issue #28: ~14 modules hand-typing IL tuples is what lost SEVEN_DAY_DL."""
    from plv_clone.il_states import IL_STATES_WITH_DTD

    assert bmd.IL_INJURY_STATES is IL_STATES_WITH_DTD


def test_docstring_does_not_claim_bench_is_inactive():
    """The prose is part of the guard — it is what a future reader acts on."""
    doc = bmd._is_active_slot.__doc__ or ""
    assert "NOT in {BE," not in doc, (
        "_is_active_slot's docstring describes bench as inactive again"
    )
