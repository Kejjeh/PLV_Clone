"""win_value must INTERPOLATE holes but REFUSE to EXTRAPOLATE past the curve.

AUDIT 2026-08-14. `value_of_win_curve` is built by josh_sensitivities over the
periods the sim actually simulated — in the live payload, [19, 20]. The board
asks for periods 20-23. Periods 21/22/23 are PLAYOFF ROUNDS and carry no curve
row, so the "hole" branch fired and averaged the one neighbour it had (period
20, worth 0.30pp) into a playoff weight.

That is not the same kind of error as interpolating an interior hole:

  * An INTERIOR hole (curve has 19 and 21, asked for 20) is a missing sample of
    a quantity we bracketed on both sides. The mean of the neighbours is a
    defensible estimate and the docstring's stated rationale.
  * An EXTERIOR ask (curve stops at 20, asked for 22) is EXTRAPOLATION across a
    regime boundary. A regular-season week with P(playoffs) already 1.00 is
    worth almost nothing (0.30pp); winning a playoff round is worth a large
    fraction of the title. Laundering the former as the latter understates
    playoff leverage by roughly an order of magnitude, and does it while
    labelled `interpolated` — which reads as "estimated", not "invented".

The module's own contract is "we never multiply against the WRONG period's
weight while claiming it is the right one". Refusing (dtitle_pp=None) is the
only behaviour consistent with that, and callers already handle None.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.title_equity import equity, win_value  # noqa: E402

# Curve with an INTERIOR hole at 20, so both branches are exercisable.
CURVE = [{"period": 18, "dtitle_pp": 1.20, "p_win_week": 0.70},
         {"period": 19, "dtitle_pp": 1.57, "p_win_week": 0.77},
         {"period": 21, "dtitle_pp": 0.30, "p_win_week": 0.60}]
PAYLOAD = {"period": 19, "josh": {"value_of_win_curve": CURVE,
                                  "sensitivity": {"dtitle_mean_plus2_pp": 1.18}}}


def test_interior_hole_still_interpolates():
    """The documented behaviour is preserved: a bracketed hole is estimated."""
    out = win_value(20, payload=PAYLOAD)
    assert out["status"] == "interpolated"
    assert out["dtitle_pp"] == pytest.approx((1.57 + 0.30) / 2)
    assert out["source_period"] == [19, 21]


@pytest.mark.parametrize("period", [22, 23, 30])
def test_past_the_end_refuses_rather_than_extrapolating(period):
    """The live failure: curve ends at 21, board asks for playoff periods."""
    out = win_value(period, payload=PAYLOAD)
    assert out["dtitle_pp"] is None, (
        f"period {period} is outside the curve [18, 21]; returning a number "
        "here laundered a regular-season weight as a playoff-round weight")
    assert out["status"] == "out_of_range"
    assert "extrapolat" in out["note"].lower()
    # The note must say WHAT to do, not merely that it failed.
    assert "season-sim" in out["note"].lower()


def test_before_the_start_also_refuses():
    """Extrapolation is directionless — below the curve is equally invented."""
    out = win_value(10, payload=PAYLOAD)
    assert out["dtitle_pp"] is None and out["status"] == "out_of_range"


def test_equity_propagates_the_refusal_as_none_not_zero():
    """A silent 0.0 reads as 'this move is worth nothing'. It must stay None."""
    out = equity(0.08, 22, payload=PAYLOAD)
    assert out["dtitle_equity_pp"] is None
    assert out["dtitle_pp_per_win"] is None
    assert out["status"] == "out_of_range"


def test_curve_bounds_are_reported_so_the_caller_can_explain_the_gap():
    out = win_value(22, payload=PAYLOAD)
    assert out["curve_periods"] == (18, 21)
