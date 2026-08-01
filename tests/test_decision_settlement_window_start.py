"""T22 — the paired settlement window must begin after the move takes effect.

``counterfactual.window_for`` truncated ``executed_at`` to its date (``[:10]``)
and started the window there. ``settle_decisions._games_in_window`` filters
``start <= game_date <= end`` INCLUSIVE, so an evening move credited BOTH the
chosen and the rejected player with a full day-0 game the move could not
possibly have affected — pure noise added to ``fp_gained``, against a wash band
of only 10 FP for a hitter pair.

Both legs read this one window (``settle_decisions`` lines 334/352), so moving
the start moves them together and keeps the comparison symmetric. Window LENGTH
must not change: the end offset stays relative to the new start.

No production ledger data is touched — records are built through the public
``build_executed_record`` and the game frames are synthetic dicts in the shape
``_games_in_window`` consumes.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from plv_clone.decisions import counterfactual as CF  # noqa: E402
from plv_clone.decisions.logger import build_executed_record  # noqa: E402

SD = pytest.importorskip("settle_decisions",
                         reason="settle_decisions needs the dashboard import chain")

EXEC_DAY = "2026-07-15"


def _rec(executed, bucket="H"):
    return build_executed_record(
        snapshot_date=EXEC_DAY, player_name="Chosen", mlbam_id=1,
        bucket=bucket, action="swap", executed_at=executed,
        rejected={"name": "Passed", "mlbam": 2, "bucket": bucket},
        dpwin_chosen=0.05, dpwin_rejected=0.03)


def _games(*days):
    return [{"date": d} for d in days]


def test_evening_move_does_not_grade_the_day_it_could_not_affect():
    """A swap executed at 19:30 cannot change that night's lineups, so neither
    side's day-of-execution game may enter the settled totals."""
    start, end = CF.window_for(_rec(f"{EXEC_DAY}T19:30:00"))

    assert start > date.fromisoformat(EXEC_DAY), (
        f"window starts on the execution day itself ({start}) — both players "
        f"are credited a game the 19:30 move could not affect")

    # and the real consumer must agree, for both legs of the pair
    played = _games(EXEC_DAY, "2026-07-16")
    assert [g["date"] for g in SD._games_in_window(played, start, end)] == ["2026-07-16"]


def test_morning_move_still_grades_the_day_it_takes_effect():
    """The boundary the other way: a move made before first pitch DOES reach
    that day's slate, so day 0 must stay in the window."""
    start, _ = CF.window_for(_rec(f"{EXEC_DAY}T09:00:00"))
    assert start == date.fromisoformat(EXEC_DAY)


def test_window_length_is_unchanged_by_the_shift():
    """Moving the start must not silently shorten the graded interval."""
    for stamp in (f"{EXEC_DAY}T09:00:00", f"{EXEC_DAY}T19:30:00", EXEC_DAY):
        for bucket, days in (("H", 21), ("SP", 35), ("RP", 35)):
            s, e = CF.window_for(_rec(stamp, bucket))
            assert (e - s).days == days, f"{stamp} / {bucket}"


def test_date_only_stamp_keeps_the_execution_day():
    """A stamp with no time carries no evidence of lateness — do not invent it."""
    start, _ = CF.window_for(_rec(EXEC_DAY))
    assert start == date.fromisoformat(EXEC_DAY)
