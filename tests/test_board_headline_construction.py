"""The board's headline `ros_total` must be built the same way for both buckets.

AUDIT 2026-08-14. `build_period_xfp_board` shipped two different constructions
under one column name:

  * HITTERS: `ros_total = rate x model_pa_per_teamgame x team_games_remaining`
    — pace-forward off the validated volume companion. The availability overlay
    (IL return dates, when-active PA rate) went to `ros_overlay_diag`, because
    Study C (2026-08-12) FAILED the overlay's pre-registered auto-ship gate.
  * SPs: `ros_total = sum over periods of rate x starts`, where `starts` came
    from the IL-return lattice WITH the 0.6-start ramp discount applied — i.e.
    the availability overlay, in the headline, for the bucket where the gate
    failure was never even measured.

So the same column meant "gated construction" for hitters and "ungated
construction" for SPs, and an SP/hitter comparison on that column compared two
different quantities. The failed gate applies to the METHOD, not to one bucket.

The fix is one shared pace-forward primitive used by both buckets, with the
period/availability numbers preserved as `*_diag`. That keeps the diagnostic
work (it is genuinely informative, and the prospective ledger needs it) while
making the headline honest and cross-bucket comparable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.availability import pace_forward_ros_fp  # noqa: E402


def test_pace_forward_is_rate_times_volume_times_games():
    # 0.15 FP/PA x 4.2 PA per team game x 40 games = 25.2
    assert pace_forward_ros_fp(rate=0.15, per_teamgame=4.2,
                               team_games_remaining=40) == pytest.approx(25.2)


def test_same_primitive_serves_starters():
    """An SP's volume companion is GS/team-game — identical shape, so the same
    function must serve it. Two constructions is how the buckets diverged."""
    # 14.0 FP/start x 0.19 GS per team game x 40 games = 106.4
    assert pace_forward_ros_fp(rate=14.0, per_teamgame=0.19,
                               team_games_remaining=40) == pytest.approx(106.4)


def test_zero_games_remaining_is_zero_not_an_error():
    assert pace_forward_ros_fp(rate=14.0, per_teamgame=0.19,
                               team_games_remaining=0) == 0.0


def test_missing_volume_refuses_rather_than_defaulting():
    """A silent league-average fill is an invented projection wearing a real
    player's name. None in, None out."""
    assert pace_forward_ros_fp(rate=14.0, per_teamgame=None,
                               team_games_remaining=40) is None
    assert pace_forward_ros_fp(rate=None, per_teamgame=0.19,
                               team_games_remaining=40) is None


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        pace_forward_ros_fp(rate=14.0, per_teamgame=-0.1, team_games_remaining=40)
    with pytest.raises(ValueError):
        pace_forward_ros_fp(rate=14.0, per_teamgame=0.19, team_games_remaining=-1)


# ── the structural guard: the board must not re-derive either construction ────

_BOARD = (Path(__file__).resolve().parent.parent / "scripts" / "xfp"
          / "build_period_xfp_board.py")


def test_board_uses_the_shared_primitive_for_both_buckets():
    src = _BOARD.read_text(encoding="utf-8")
    assert "pace_forward_ros_fp" in src, (
        "the board must build its headline from the shared primitive")
    assert src.count("pace_forward_ros_fp(") >= 2, (
        "both the hitter and SP branches must go through it")


def test_board_headline_does_not_carry_the_ramp_discount():
    """The ramp discount is the availability overlay. It belongs in *_diag."""
    src = _BOARD.read_text(encoding="utf-8")
    for line in src.splitlines():
        if '"ros_total"' in line:
            assert "SP_RAMP_DISCOUNT" not in line and "per_period" not in line, (
                f"headline ros_total is still overlay-derived: {line.strip()}")
