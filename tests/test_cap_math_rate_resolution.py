"""Regression tests for issue #61: an SP whose rate can't be resolved was
silently projected at 0.0 FP, which sorts him LAST in cap_excess_starts and so
makes him the first start benched — a wrong answer pointing in the worst
possible direction, with nothing to distinguish it from a real zero.

The fix does two things: accept an MLBAM-keyed rp3 (RosterPitcher carries the
id; the lookup used to ignore it — CLAUDE.md don't-do #10), and flag the filler
zero via SPStart.rate_resolved / unresolved_starts().
"""
from datetime import date

import pytest

from plv_clone.cap_math import (
    RosterPitcher,
    WeekProbables,
    unresolved_starts,
    weekly_sp_projection,
)

MON = date(2026, 4, 6)
SUN = date(2026, 4, 12)

REAL = RosterPitcher(name="Real Arm", mlbam_id=111, injury_status="ACTIVE", position="SP")
GHOST = RosterPitcher(name="Ghost", mlbam_id=222, injury_status="ACTIVE", position="SP")

PROBABLES = WeekProbables(
    starts={(111, date(2026, 4, 7)): "NYY", (222, date(2026, 4, 8)): "BOS"}
)


def _project(rp3):
    return weekly_sp_projection(
        roster=[REAL, GHOST],
        week_start=MON,
        week_end=SUN,
        rp3=rp3,
        probables=PROBABLES,
    )


@pytest.mark.parametrize(
    "rp3",
    [
        pytest.param({"Real Arm": 14.0}, id="name-keyed"),
        pytest.param({111: 14.0}, id="mlbam-keyed"),
    ],
)
def test_both_key_forms_resolve_and_an_unmatched_arm_is_flagged(rp3):
    """Name- and MLBAM-keyed rp3 dicts both work, and the miss is visible."""
    starts = _project(rp3)
    by_name = {s.pitcher_name: s for s in starts}

    assert by_name["Real Arm"].projected_fp == pytest.approx(14.0)
    assert by_name["Real Arm"].rate_resolved is True

    # The filler zero survives (callers depending on a float still get one)...
    assert by_name["Ghost"].projected_fp == 0.0
    # ...but is no longer indistinguishable from a genuine zero projection.
    assert by_name["Ghost"].rate_resolved is False
    assert [s.pitcher_name for s in unresolved_starts(starts)] == ["Ghost"]


def test_a_genuine_zero_is_not_reported_as_unresolved():
    """A pitcher actually projected at 0.0 is resolved — that IS his number."""
    starts = _project({"Real Arm": 14.0, "Ghost": 0.0})
    by_name = {s.pitcher_name: s for s in starts}

    assert by_name["Ghost"].projected_fp == 0.0
    assert by_name["Ghost"].rate_resolved is True
    assert unresolved_starts(starts) == []


def test_mlbam_wins_over_a_colliding_name():
    """Identity beats name when rp3 carries both (CLAUDE.md don't-do #10)."""
    starts = _project({111: 14.0, "Real Arm": 99.0, 222: 5.0})
    by_name = {s.pitcher_name: s for s in starts}
    assert by_name["Real Arm"].projected_fp == pytest.approx(14.0)
    assert by_name["Ghost"].projected_fp == pytest.approx(5.0)
    assert unresolved_starts(starts) == []
