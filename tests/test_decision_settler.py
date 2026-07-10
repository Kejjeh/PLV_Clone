"""Tests for plv_clone.decisions.settler — PR 5 sub-action 3.

The +2 settler round-trip tests are the HARD contract from plan v11.
Three additional pending-state tests pin down the window-end / min-events
gating behavior.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from plv_clone.decisions.logger import DecisionRecord
from plv_clone.decisions.settler import (
    SETTLEMENT_WINDOWS,
    settle_decision,
)


SNAP = "2026-05-10"  # 27d before today=2026-06-06 -> past 21d H window
TODAY = date(2026, 6, 6)


_UNITS = {"H": "fp_per_pa", "SP": "fp_per_start", "RP": "fp_per_g"}


def _make(
    verdict_top: str,
    *,
    proj_per: float = 0.72,
    bucket: str = "H",
    snapshot_date: str = SNAP,
    proj_units: str | None = "auto",
) -> DecisionRecord:
    # Schema-v2 records (2026-07-10 units fix) carry proj_units so the
    # settler settles natively. proj_units=None builds a LEGACY v1 record
    # (display-unit proj) for the conversion-path tests.
    inputs = {"proj_per": proj_per, "inputs_schema": 2}
    if proj_units == "auto":
        inputs["proj_units"] = _UNITS.get(bucket)  # None for unknown buckets
    elif proj_units is not None:
        inputs["proj_units"] = proj_units
    else:
        inputs = {"proj_per": proj_per}  # v1: no units, no schema field
    return DecisionRecord(
        decision_id=f"{snapshot_date}_test_{bucket}_001",
        snapshot_date=snapshot_date,
        player_name="Test Player",
        mlbam_id=999999,
        bucket=bucket,
        verdict_top=verdict_top,
        reason_tag=None,
        confidence=0.5,
        inputs=inputs,
    )


# ---------------------------------------------------------------------------
# The two mandatory settler round-trip tests
# ---------------------------------------------------------------------------


def test_settler_buy_hit_round_trip():
    """BUY decision + actual=0.80 vs proj=0.72 (residual +0.08, well above
    +0.02 H threshold) + n_events=45 + past 21d window -> BUY_HIT."""
    rec = _make("BUY", proj_per=0.72)
    settled = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=0.80, n_events=45
    )

    assert settled.settled_at == TODAY.isoformat()
    assert settled.settlement is not None
    assert settled.settlement["classification"] == "BUY_HIT"
    assert settled.settlement["residual"] == pytest.approx(0.08, abs=1e-9)
    assert settled.settlement["n_events"] == 45
    assert settled.settlement["event_unit"] == "PA"
    # original record unchanged (pure function)
    assert rec.settled_at is None
    assert rec.settlement is None


def test_settler_fade_miss_round_trip():
    """FADE decision + actual=0.74 vs proj=0.72 (residual +0.02, NOT below
    -0.02 threshold) + n_events=45 + past 21d window -> FADE_MISS.
    The hitter didn't tank like FADE predicted."""
    rec = _make("FADE", proj_per=0.72)
    settled = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=0.74, n_events=45
    )

    assert settled.settled_at == TODAY.isoformat()
    assert settled.settlement is not None
    assert settled.settlement["classification"] == "FADE_MISS"
    assert settled.settlement["residual"] == pytest.approx(0.02, abs=1e-9)


# ---------------------------------------------------------------------------
# Pending-state tests — settler should refuse to settle in these cases
# ---------------------------------------------------------------------------


def test_settler_pending_below_min_events():
    """Past window-end but n_events=10 (< 30 PA min for H) => unchanged."""
    rec = _make("BUY")
    out = settle_decision(rec, today=TODAY, actual_fp_per_unit=0.85, n_events=10)
    assert out.settled_at is None
    assert out.settlement is None


def test_settler_pending_before_window_end():
    """Only 7 days after snapshot (< 21d H window) => unchanged even with
    plenty of events."""
    rec = _make("BUY", snapshot_date="2026-05-30")
    out = settle_decision(rec, today=TODAY, actual_fp_per_unit=0.85, n_events=200)
    # 2026-05-30 + 21d = 2026-06-20, today=2026-06-06 is before window-end
    assert out.settled_at is None
    assert out.settlement is None


def test_settler_hold_classification_is_neutral():
    """HOLD verdict with residual +0.05 should classify HOLD_NEUTRAL — no
    HIT/MISS directional claim."""
    rec = _make("HOLD", proj_per=0.72)
    settled = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=0.77, n_events=45
    )
    assert settled.settled_at == TODAY.isoformat()
    assert settled.settlement["classification"] == "HOLD_NEUTRAL"


# ---------------------------------------------------------------------------
# Sanity coverage
# ---------------------------------------------------------------------------


def test_settler_no_actual_returns_unchanged():
    rec = _make("BUY")
    out = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=None, n_events=45
    )
    assert out.settled_at is None


def test_settler_unknown_bucket_returns_unchanged():
    rec = _make("BUY", bucket="UNKNOWN")
    out = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=0.85, n_events=45
    )
    assert out.settled_at is None


def test_settlement_windows_contract():
    """Pin the per-bucket contract so accidental changes break tests."""
    assert SETTLEMENT_WINDOWS["H"]["days"] == 21
    assert SETTLEMENT_WINDOWS["SP"]["days"] == 35
    assert SETTLEMENT_WINDOWS["RP"]["days"] == 35
    assert SETTLEMENT_WINDOWS["H"]["min_events"] == 30
    assert SETTLEMENT_WINDOWS["SP"]["min_events"] == 5
    assert SETTLEMENT_WINDOWS["RP"]["min_events"] == 10


# ---------------------------------------------------------------------------
# Legacy schema-v1 unit conversion (units bug fixed 2026-07-10)
# ---------------------------------------------------------------------------


def test_settler_v1_hitter_per_game_converted():
    """Legacy v1 H records logged rh3 FP/GAME as proj_per. The settler
    converts /3.5 (rh3 flat display convention): 2.52 FP/game -> 0.72
    FP/PA, actual 0.80 -> residual +0.08 -> BUY_HIT."""
    rec = _make("BUY", proj_per=2.52, proj_units=None)  # v1: no units field
    settled = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=0.80, n_events=45
    )
    assert settled.settlement is not None
    assert settled.settlement["proj_per"] == pytest.approx(0.72, abs=1e-9)
    assert settled.settlement["residual"] == pytest.approx(0.08, abs=1e-9)
    assert settled.settlement["classification"] == "BUY_HIT"
    assert settled.settlement["proj_units_note"] == "v1_h_per_game_converted"


def test_settler_v1_rp_total_unsettleable():
    """Legacy v1 RP records logged the rprs2 RoS TOTAL as proj_per — not
    convertible to FP/appearance after the fact. They settle (stop
    pending) with the realized value recorded but NO residual or
    directional classification."""
    rec = _make(
        "BUY", proj_per=135.0, bucket="RP",
        snapshot_date="2026-04-20",  # >35d before TODAY (RP window)
        proj_units=None,
    )
    settled = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=4.2, n_events=15
    )
    assert settled.settled_at == TODAY.isoformat()
    assert settled.settlement["classification"] == "UNSETTLEABLE_V1_UNITS"
    assert settled.settlement["residual"] is None
    assert settled.settlement["proj_per"] is None
    assert settled.settlement["actual_fp_per_unit"] == pytest.approx(4.2)


def test_settler_v2_rp_native_units():
    """Schema-v2 RP records carry fp_per_g proj — settle natively."""
    rec = _make(
        "BUY", proj_per=4.0, bucket="RP",
        snapshot_date="2026-04-20", proj_units="fp_per_g",
    )
    settled = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=4.8, n_events=15
    )
    assert settled.settlement["classification"] == "BUY_HIT"
    assert settled.settlement["residual"] == pytest.approx(0.8, abs=1e-9)
    assert settled.settlement["proj_units_note"] == "native"


def test_settler_unknown_units_left_unsettled():
    """An unrecognized proj_units string must never be guessed at —
    the record stays pending."""
    rec = _make("BUY", proj_per=0.72, proj_units="fp_per_fortnight")
    settled = settle_decision(
        rec, today=TODAY, actual_fp_per_unit=0.80, n_events=45
    )
    assert settled.settled_at is None
    assert settled.settlement is None
