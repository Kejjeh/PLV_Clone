"""The rotation lattice runs ~6% hot against the repo's own empirical rate.

AUDIT 2026-08-14. `sp_starts_in_window` places a start on every 5th team game
(`ROTATION_LEN = 5`). That lattice is the right STRUCTURE — a start lands on a
specific date, off-days shift it, and period assignment needs exactly that — but
as a RATE it is optimistic. A team plays ~6.3 games a week, so 1-in-5 implies
1.26 starts per SP per week. CLAUDE.md's validated empirical figure is **1.19**.

The ~6% gap is not noise, it is everything the clean lattice omits: skipped
turns on off-day-heavy weeks, six-man stretches, spot bullpen games, short IL
blips that never get recorded as a stint. Uncorrected it inflates every
period start count, and it does so in the direction that matters most here —
the cap analysis. Reading 10.6 projected starts against a cap of 10 as
"BINDING, spill 0.6" when the calibrated number is 10.0 turns a non-decision
into a phantom one.

So: keep the integer lattice for PLACEMENT, and carry an explicit, documented
efficiency factor for COUNTS. One named constant, derived from the two numbers
already in the repo, beats a silent 6% bias.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.playoff_calendar import (  # noqa: E402
    EMPIRICAL_STARTS_PER_WEEK, ROTATION_EFFICIENCY, ROTATION_LEN,
    TEAM_GAMES_PER_WEEK, expected_starts_in_window, sp_starts_in_window,
)


def test_the_uncorrected_lattice_is_hot_by_the_documented_margin():
    """Pin the defect itself so the constant can never drift silently."""
    lattice_rate = TEAM_GAMES_PER_WEEK / ROTATION_LEN
    assert lattice_rate == pytest.approx(1.26, abs=0.01)
    assert lattice_rate > EMPIRICAL_STARTS_PER_WEEK


def test_efficiency_reconciles_the_lattice_to_the_empirical_rate():
    corrected = (TEAM_GAMES_PER_WEEK / ROTATION_LEN) * ROTATION_EFFICIENCY
    assert corrected == pytest.approx(EMPIRICAL_STARTS_PER_WEEK, abs=1e-9)
    assert 0.90 < ROTATION_EFFICIENCY < 1.0, "a correction, not a rewrite"


def _dates(n: int, start: date = date(2026, 8, 17)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_expected_starts_scales_the_raw_lattice_count():
    days = _dates(28)
    last = date(2026, 8, 16)
    raw = sp_starts_in_window(team_dates=[last] + days, last_start_date=last,
                              window=(days[0], days[-1]))
    exp = expected_starts_in_window(team_dates=[last] + days,
                                    last_start_date=last,
                                    window=(days[0], days[-1]))
    assert exp == pytest.approx(raw * ROTATION_EFFICIENCY)
    assert exp < raw


def test_placement_is_unchanged_only_the_count_is_corrected():
    """The correction must not move which dates are starts — that would break
    period assignment, which is the whole reason the lattice exists."""
    days = _dates(20)
    last = date(2026, 8, 16)
    per_window = [
        sp_starts_in_window(team_dates=[last] + days, last_start_date=last,
                            window=(days[i], days[i]))
        for i in range(len(days))
    ]
    assert sum(per_window) == sp_starts_in_window(
        team_dates=[last] + days, last_start_date=last,
        window=(days[0], days[-1]))


def test_expected_starts_is_zero_when_the_lattice_is_empty():
    days = _dates(3)
    last = date(2026, 8, 16)
    assert expected_starts_in_window(team_dates=[last] + days,
                                     last_start_date=last,
                                     window=(days[0], days[-1])) == 0.0


def test_board_uses_the_calibrated_count_for_the_cap_analysis():
    src = (Path(__file__).resolve().parent.parent / "scripts" / "xfp"
           / "build_period_xfp_board.py").read_text(encoding="utf-8")
    assert "ROTATION_EFFICIENCY" in src or "expected_starts_in_window" in src, (
        "the cap analysis compares projected starts against a hard league cap; "
        "it must use the calibrated count, not the raw lattice")
