"""ΔP(title) linearization for roster moves (v1 — sensitivity-based).

With P(playoffs) locked at 1.0 (sim @ period 19), a move's title impact is
its change to WEEKLY roster quality times the sim's own sensitivity
(dtitle_mean_plus2_pp per +2 FP/wk). Joint bracket MC is the registered
offseason upgrade; this v1 is the honest linear read off season_sim.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.title_equity import dtitle_for_ros_delta  # noqa: E402

PAYLOAD = {"period": 19,
           "josh": {"p_playoffs": 1.0,
                    "sensitivity": {"dtitle_mean_plus2_pp": 1.18},
                    "value_of_win_curve": [{"period": 19, "dtitle_pp": 1.57,
                                            "p_win_week": 0.77}]}}


def test_ros_fp_delta_converts_via_sim_sensitivity():
    """+30 RoS FP over 6 remaining weeks = +5 FP/wk -> (5/2)*1.18 pp."""
    out = dtitle_for_ros_delta(30.0, remaining_weeks=6, payload=PAYLOAD)
    assert out["dtitle_pp"] == pytest.approx((30.0 / 6 / 2) * 1.18)
    assert out["status"] == "linearized_v1"


def test_missing_sensitivity_returns_none_never_zero():
    """No sim sensitivity -> None + note (staleness is labelled, not laundered)."""
    out = dtitle_for_ros_delta(30.0, remaining_weeks=6,
                               payload={"period": 19, "josh": {}})
    assert out["dtitle_pp"] is None
    assert "sensitivity" in out["note"]
