"""Behavioral spec for the ROS/playoff horizon on the positional board.

Audit item T44 (backlog group "lenses", 2026-08-01).

`run_positional_board.py` scaled every rp3 per-start projection by a constant
`WEEKS_REMAINING = 15.5` — the weeks left on **2026-06-15**, the day the board
was written. Its hitter and RP ROS columns come from rh3/rprs2, both of which
shrink with the calendar, so the SP column drifted further out of step every
week: on 2026-08-01 it claimed 18.4 remaining starts against a real 8.5.

The PLYO column was worse and in the other direction: a frozen `PLAYOFF_SHARE
= 6/20` is applied to hitters, RPs and both FA snapshots, so once the playoff
window opens the board under-reports playoff value for every bucket.

The horizon math is owned by `build_xfp_boards.py`'s date-parameterized block;
this file pins that the board tracks the same calendar rather than a literal.
"""
from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

# The board rebinds sys.stdout to a UTF-8 TextIOWrapper at import (Windows
# console fix). Left in place it detonates pytest's capture teardown, so the
# wrapper is detached — releasing the buffer WITHOUT closing it — and the
# original stream restored.
_saved_stdout = sys.stdout
try:
    rpb = importlib.import_module("run_positional_board")
finally:
    _wrapper = sys.stdout
    sys.stdout = _saved_stdout
    if _wrapper is not _saved_stdout:
        try:
            _wrapper.detach()
        except Exception:  # pragma: no cover - best effort
            pass

from plv_clone.cap_math import STARTS_PER_SP_PER_WEEK as SPW  # noqa: E402

# The season window the rest of the repo already uses (build_xfp_boards.py,
# run_consensus_diff.py). Restated here so the spec owns its own calendar.
SEASON_END = date(2026, 9, 20)
PLAYOFF_START = date(2026, 8, 17)
_RATE = SPW / 7.0


def _days_left(today: date) -> int:
    return max(0, (SEASON_END - today).days)


def _playoff_days(today: date) -> int:
    return max(0, (SEASON_END - max(today, PLAYOFF_START)).days)


def test_the_board_horizon_tracks_the_calendar_not_a_frozen_june_date():
    """Every horizon the board scales by must be derived from today's date.

    Two claims, both of which the frozen literals broke:
      1. the SP rest-of-season start count equals the starts actually left;
      2. the playoff share equals the playoff days' share of the days left.
    Plus the property that makes it a horizon at all — it shrinks as the season
    ends approaches, so a July build and a September build differ.
    """
    today = date.today()

    assert rpb.SP_STARTS_REMAINING == pytest.approx(
        round(_days_left(today) * _RATE, 1), abs=0.05), (
        "SP RoS starts must come from the calendar, not a June-15 freeze")
    assert rpb.PLAYOFF_SP_STARTS == pytest.approx(
        round(_playoff_days(today) * _RATE, 1), abs=0.05)
    assert rpb.PLAYOFF_SHARE == pytest.approx(
        _playoff_days(today) / max(1, _days_left(today)), abs=0.01), (
        "PLYO scales hitters and RPs too — a frozen 6/20 mis-states all three buckets")

    july, sept = date(2026, 7, 1), date(2026, 9, 1)
    assert rpb.sp_starts_remaining(july) > rpb.sp_starts_remaining(sept) > 0, (
        "the same per-start projection must not report the same RoS total in "
        "July and in September")
    assert rpb.sp_starts_remaining(SEASON_END + __import__("datetime").timedelta(days=5)) == 0


def test_the_playoff_share_is_whole_once_the_playoff_window_opens():
    """Inside the playoff window every remaining day is a playoff day."""
    inside = PLAYOFF_START + __import__("datetime").timedelta(days=3)
    assert rpb.playoff_share(inside) == pytest.approx(1.0)
    assert rpb.playoff_share(PLAYOFF_START) == pytest.approx(1.0)

    before = date(2026, 7, 1)
    assert 0.0 < rpb.playoff_share(before) < 1.0
