"""8 parametrize cases for the pure period-math helpers (PR 3a).

The pure layer is the unit-test target. The DataFrame adapter has a
single sanity test at the bottom.
"""
from datetime import date

import pandas as pd
import pytest

from scripts.xfp.lib.period_math import (
    adapter_period_closed_from_history_df,
    compute_period_window,
    is_period_closed,
    period_window_for_snapshots,
)


@pytest.mark.parametrize(
    "anchor,expected_start,expected_end",
    [
        # Monday snapshot — start equals anchor.
        (date(2026, 6, 1), date(2026, 6, 1), date(2026, 6, 7)),
        # Mid-week snapshot — start backs up to Monday.
        (date(2026, 6, 4), date(2026, 6, 1), date(2026, 6, 7)),
        # Sunday snapshot — start backs up six days to Monday.
        (date(2026, 6, 7), date(2026, 6, 1), date(2026, 6, 7)),
        # Year boundary: Dec 30 2024 is a Monday => window ends Jan 5 2025.
        (date(2024, 12, 30), date(2024, 12, 30), date(2025, 1, 5)),
        # Leap-year Feb 29: Feb 29 2024 is a Thursday => Mon Feb 26 - Sun Mar 3.
        (date(2024, 2, 29), date(2024, 2, 26), date(2024, 3, 3)),
    ],
    ids=["monday", "midweek", "sunday", "year_boundary", "leap_year"],
)
def test_compute_period_window(anchor: date, expected_start: date, expected_end: date) -> None:
    start, end = compute_period_window(anchor)
    assert start == expected_start
    assert end == expected_end
    # Invariant: window is always exactly 7 days inclusive.
    assert (end - start).days == 6


@pytest.mark.parametrize(
    "period_end,today,expected_closed",
    [
        # Today < end => open.
        (date(2026, 6, 7), date(2026, 6, 5), False),
        # Today == Sunday end => not yet closed (period CLOSES the day after).
        (date(2026, 6, 7), date(2026, 6, 7), False),
        # Today > end => closed.
        (date(2026, 6, 7), date(2026, 6, 8), True),
    ],
    ids=["before_end", "on_sunday", "after_sunday"],
)
def test_is_period_closed(period_end: date, today: date, expected_closed: bool) -> None:
    assert is_period_closed(period_end, today) is expected_closed


def test_period_window_for_snapshots_uses_earliest() -> None:
    """The window must anchor on the EARLIEST snapshot, not the latest
    (drift mid-period otherwise expands the apparent window)."""
    start, end = period_window_for_snapshots(
        [date(2026, 6, 3), date(2026, 6, 1), date(2026, 6, 5)]
    )
    assert start == date(2026, 6, 1)
    assert end == date(2026, 6, 7)


def test_period_window_for_snapshots_empty_raises() -> None:
    with pytest.raises(ValueError):
        period_window_for_snapshots([])


def test_adapter_period_closed_from_history_df() -> None:
    """Sanity check the I/O adapter routes through the pure layer."""
    df = pd.DataFrame(
        {
            "matchup_period": [9, 9, 10, 10],
            "snapshot_date": [
                pd.Timestamp("2026-05-25"),
                pd.Timestamp("2026-05-26"),
                pd.Timestamp("2026-06-01"),
                pd.Timestamp("2026-06-04"),
            ],
        }
    )
    # Period 9 (May 25 Mon - May 31 Sun) is closed as of June 5.
    # Period 10 (Jun 1 Mon - Jun 7 Sun) is still open.
    out = adapter_period_closed_from_history_df(df, today=date(2026, 6, 5))
    assert out == {9: True, 10: False}
