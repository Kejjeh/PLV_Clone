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


def _make(
    verdict_top: str,
    *,
    proj_per: float = 0.72,
    bucket: str = "H",
    snapshot_date: str = SNAP,
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=f"{snapshot_date}_test_{bucket}_001",
        snapshot_date=snapshot_date,
        player_name="Test Player",
        mlbam_id=999999,
        bucket=bucket,
        verdict_top=verdict_top,
        reason_tag=None,
        confidence=0.5,
        inputs={"proj_per": proj_per},
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
