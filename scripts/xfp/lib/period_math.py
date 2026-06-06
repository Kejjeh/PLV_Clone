"""Pure period-math helpers extracted from
fetch_closed_matchup_actuals.py and other matchup-aware scripts.

Pure functions take (date | Timestamp, date | Timestamp) -> ... so they
can be unit-tested with no I/O. The adapter layer (`adapter_*` below) is
the thin wrapper that pulls dates from a DataFrame and routes them
through the pure functions; it is the only code with I/O dependencies.

Plan v11 PR 3a calls out this split explicitly so the pure logic is
exhaustively parametrized.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Tuple

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────
# Pure functions (no I/O)
# ─────────────────────────────────────────────────────────────────────────

def compute_period_window(period_first_snapshot_date: date) -> Tuple[date, date]:
    """Return the (Monday start, Sunday end) of the matchup-period ISO week
    that contains ``period_first_snapshot_date``.

    BrownU matchup periods run Mon-Sun. The first roster snapshot in a
    period typically lands on Monday but can drift (e.g. delayed
    snapshot after a weekend). The function anchors on the ISO week.

    Examples:
        >>> compute_period_window(date(2026, 6, 1))   # Monday
        (datetime.date(2026, 6, 1), datetime.date(2026, 6, 7))
        >>> compute_period_window(date(2026, 6, 4))   # Thursday
        (datetime.date(2026, 6, 1), datetime.date(2026, 6, 7))
    """
    start = period_first_snapshot_date - timedelta(days=period_first_snapshot_date.weekday())
    end = start + timedelta(days=6)
    return start, end


def is_period_closed(period_end: date, today: date) -> bool:
    """A period closes the day AFTER its Sunday end. ``today`` strictly
    later than ``period_end`` means the period's box-score finals are
    now available.

    Args:
        period_end: The Sunday end-of-period date (from
            ``compute_period_window`` or equivalent).
        today: Reference "now" date. Pure-function input so tests can
            simulate any clock.

    Returns:
        True if today is strictly past the period's Sunday end.

    Examples:
        >>> is_period_closed(date(2026, 6, 7), date(2026, 6, 8))
        True
        >>> is_period_closed(date(2026, 6, 7), date(2026, 6, 7))   # Sunday itself
        False
    """
    return today > period_end


def period_window_for_snapshots(snapshot_dates: Iterable[date]) -> Tuple[date, date]:
    """Compute the period window covering ``min(snapshot_dates)``.

    Convenience for callers that have a list of snapshot dates and want
    the ISO-week window containing the EARLIEST snapshot (which is
    typically the period's first snapshot).
    """
    snaps = sorted(snapshot_dates)
    if not snaps:
        raise ValueError("period_window_for_snapshots: empty snapshot list")
    return compute_period_window(snaps[0])


# ─────────────────────────────────────────────────────────────────────────
# Adapter (I/O-bearing wrapper around the pure layer)
# ─────────────────────────────────────────────────────────────────────────

def adapter_period_closed_from_history_df(
    history_df: pd.DataFrame,
    *,
    period_col: str = "matchup_period",
    date_col: str = "snapshot_date",
    today: date | None = None,
) -> dict[int, bool]:
    """Given a roster-history DataFrame with one row per (matchup_period,
    snapshot_date), return ``{period: is_closed}`` using the pure
    ``is_period_closed`` underneath.

    This is the I/O-bearing adapter. Production code (e.g.
    fetch_closed_matchup_actuals.py) should call THIS function, not
    the raw pure helpers, so that:
      1. DataFrame column conventions live in ONE place.
      2. Pure helpers stay test-isolated.

    Args:
        history_df: Roster-history DataFrame.
        period_col: Column with the matchup-period int.
        date_col: Column with the snapshot date (date or parseable string).
        today: Reference date (default: pd.Timestamp.today().date()).

    Returns:
        Mapping of matchup_period int -> bool (True if closed).
    """
    if today is None:
        today = pd.Timestamp.today().date()

    out: dict[int, bool] = {}
    if history_df.empty:
        return out

    # Normalize the date column to date objects for the pure layer.
    dates = pd.to_datetime(history_df[date_col]).dt.date
    for period, group_idx in history_df.groupby(period_col).groups.items():
        snaps = [dates.loc[i] for i in group_idx]
        _, end = period_window_for_snapshots(snaps)
        out[int(period)] = is_period_closed(end, today)
    return out
