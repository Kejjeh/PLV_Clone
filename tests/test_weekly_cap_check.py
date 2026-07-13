"""Offline tests for the pure logic in weekly_cap_check — the start projection
(esp. break/off-day sliding, which was a real bug) and the value blend."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import weekly_cap_check as w  # noqa: E402


def test_ip_float():
    assert w._ip_float("5.2") == 5 + 2 / 3
    assert w._ip_float("6.0") == 6.0
    assert w._ip_float(None) == 0.0


def test_proj_val_blend():
    # median-of-two = average; blends season proj with recent form
    assert w._proj_val(11.45, 2.88) == 7.16      # cold arm dragged down
    assert w._proj_val(10.26, 14.2) == 12.23     # opener-stale rp3 lifted by form
    assert w._proj_val(12.0, None) == 12.0       # only rp3
    assert w._proj_val(None, 9.0) == 9.0         # only form
    assert w._proj_val(None, None) == 0.0


def test_project_confirmed_wins():
    conf = {1: [date(2026, 7, 12), date(2026, 7, 18)]}
    out = w._project_starts(1, date(2026, 7, 7), 5, conf, set(),
                            date(2026, 7, 12), date(2026, 7, 19))
    assert out == [date(2026, 7, 12), date(2026, 7, 18)]


def test_project_cadence_slides_off_break():
    # last start 7/9, cadence 6 -> lands 7/15 (ASG break, no games) -> must slide
    # to the next game day (7/16), NOT skip the start entirely.
    game_days = {date(2026, 7, 16), date(2026, 7, 17), date(2026, 7, 18), date(2026, 7, 19)}
    out = w._project_starts(1, date(2026, 7, 9), 6, {}, game_days,
                            date(2026, 7, 16), date(2026, 7, 19))
    assert out == [date(2026, 7, 16)]            # slid off the break, not dropped


def test_project_counts_two_starts_in_window():
    game_days = {date(2026, 7, d) for d in range(16, 27)}
    out = w._project_starts(1, date(2026, 7, 15), 5, {}, game_days,
                            date(2026, 7, 16), date(2026, 7, 26))
    assert out == [date(2026, 7, 20), date(2026, 7, 25)]


def test_project_no_last_start():
    assert w._project_starts(1, None, 5, {}, set(),
                             date(2026, 7, 16), date(2026, 7, 19)) == []
