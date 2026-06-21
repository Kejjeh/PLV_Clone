"""TDD: start-anchored SP archetype snapshots (Option A).

The deep module is `trailing_start_windows` — it re-anchors SP snapshots on the
actual cadence of EVENTS (starts) instead of the calendar week, with an
event-weighted trailing last-N-starts window. Display-only (Rule 13); fully
isolated from the shared rolling cache and the models.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.xfp.lib.sp_start_snapshots import (
    trailing_start_windows, rates_from_counts)


def _starts(n, **const):
    """n synthetic starts on consecutive-ish dates; const fields default to 1s."""
    out = []
    for i in range(n):
        s = {"date": f"2026-04-{i+1:02d}", "tbf": 20, "bb": 2, "k": 6, "pitches": 85}
        s.update(const)
        out.append(s)
    return out


def test_one_row_per_start_from_min_starts():
    rows = trailing_start_windows(_starts(4), window=10, min_starts=3)
    assert [r["start_no"] for r in rows] == [3, 4]
    assert [r["date"] for r in rows] == ["2026-04-03", "2026-04-04"]


def test_trailing_window_rolls_off_old_starts():
    # 5 starts with distinct tbf; window=3 sums only the last 3 starts.
    starts = [dict(date=f"2026-04-0{i+1}", tbf=t) for i, t in enumerate([10, 20, 30, 40, 50])]
    rows = trailing_start_windows(starts, window=3, min_starts=1)
    by_no = {r["start_no"]: r for r in rows}
    assert by_no[3]["tbf"] == 60    # 10+20+30
    assert by_no[4]["tbf"] == 90    # 20+30+40
    assert by_no[5]["tbf"] == 120   # 30+40+50 (start 1,2 rolled off)


def test_expanding_window_before_full():
    # window=10 but only 4 starts -> uses all available (expanding), reports n_starts.
    starts = [dict(date=f"2026-04-0{i+1}", tbf=t) for i, t in enumerate([10, 20, 30, 40])]
    rows = trailing_start_windows(starts, window=10, min_starts=3)
    by_no = {r["start_no"]: r for r in rows}
    assert by_no[3]["n_starts"] == 3 and by_no[3]["tbf"] == 60   # 10+20+30
    assert by_no[4]["n_starts"] == 4 and by_no[4]["tbf"] == 100  # 10+20+30+40


def test_rates_are_event_weighted_not_mean_of_rates():
    # Start A: 1 BB / 4 TBF (25%). Start B: 2 BB / 40 TBF (5%).
    # Event-weighted bb_pct = 3/44 = 6.8%, NOT (25%+5%)/2 = 15%.
    starts = [dict(date="2026-04-01", tbf=4, bb=1), dict(date="2026-04-06", tbf=40, bb=2)]
    row = trailing_start_windows(starts, window=10, min_starts=1)[-1]
    rates = rates_from_counts(row)
    assert abs(rates["bb_pct"] - 3 / 44) < 1e-9
    assert abs(rates["bb_pct"] - 0.15) > 0.05   # decisively not the naive mean


def test_min_starts_gate_suppresses_early_and_empty():
    assert trailing_start_windows(_starts(2), window=10, min_starts=3) == []
    assert trailing_start_windows([], window=10, min_starts=3) == []
