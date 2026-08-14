"""BINDING vs slack must be decided on starts against the cap, not float noise.

AUDIT 2026-08-14. The board labelled a period BINDING whenever
`raw_fp > cap_absorbed_fp`. Once the rotation-efficiency correction landed,
period 20 came out at 9.4 projected starts against a cap of 10 — genuinely
UNDER the cap, with room for a streamer — and still printed BINDING, because
the greedy fill accumulates in a different order than the raw sum and the two
totals differed by ~1e-13.

The label is not decoration. BINDING means "your next start scores zero, do not
add an arm"; slack means "you have cap room to spend". Inverting it on floating
-point noise gives exactly backwards streaming advice for the week, and it does
so in the direction that costs points — telling you to sit on unused capacity.

The honest test is the one the league rule actually states: are projected starts
over the cap?
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.playoff_calendar import cap_absorbed_fp, cap_status  # noqa: E402


def test_under_the_cap_is_slack_with_the_room_reported():
    arms = [(14.0, 2.0), (13.0, 2.0), (12.0, 5.4)]      # 9.4 starts
    s = cap_status(arms, cap=10)
    assert s["binding"] is False
    assert s["starts"] == pytest.approx(9.4)
    assert s["room"] == pytest.approx(0.6)
    assert s["lost_fp"] == 0.0


def test_exactly_at_the_cap_is_not_binding():
    """Nothing spilled, so nothing was lost. 'At the cap' is not 'over' it."""
    s = cap_status([(14.0, 5.0), (12.0, 5.0)], cap=10)
    assert s["binding"] is False and s["room"] == pytest.approx(0.0)
    assert s["lost_fp"] == 0.0


def test_float_noise_at_the_cap_does_not_flip_the_label():
    """The live failure: greedy fill and raw sum differ in the last bit."""
    s = cap_status([(13.9, 3.0), (13.05, 3.0), (12.65, 3.4)], cap=10)
    assert s["binding"] is False, "9.4 starts against a cap of 10 is slack"


def test_over_the_cap_is_binding_and_prices_the_spill():
    arms = [(20.0, 6.0), (10.0, 6.0)]                    # 12 starts, cap 10
    s = cap_status(arms, cap=10)
    assert s["binding"] is True
    assert s["starts"] == pytest.approx(12.0)
    assert s["room"] == 0.0
    # cheapest starts spill: 2 x 10.0 FP
    assert s["lost_fp"] == pytest.approx(20.0)
    assert s["absorbed"] == pytest.approx(cap_absorbed_fp(arms, cap=10))


def test_empty_period_is_slack_not_binding():
    s = cap_status([], cap=10)
    assert s["binding"] is False and s["starts"] == 0.0 and s["room"] == 10.0


def test_board_uses_cap_status_rather_than_comparing_floats():
    src = (Path(__file__).resolve().parent.parent / "scripts" / "xfp"
           / "build_period_xfp_board.py").read_text(encoding="utf-8")
    assert "cap_status" in src
    assert "raw > absorbed" not in src, (
        "the float comparison that produced the inverted label")
