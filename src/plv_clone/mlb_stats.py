"""Adapter for MLB Stats API + pure rotation-gap prediction.

See ADR-0002. The MLB Stats API fetch is the I/O wrapper around pure
functions that work on already-normalized data, so the bug-B
no-rotation-gap-fallback regression test can be written against
literals.
"""
from __future__ import annotations

from datetime import date, timedelta


def predict_rotation_starts(
    *,
    gamelog_dates: list[date],
    confirmed_dates: list[date],
    team_schedule: list[tuple[date, str]],
    week_start: date,
    week_end: date,
) -> list[tuple[date, str]]:
    if not gamelog_dates:
        return []
    last_actual = gamelog_dates[0]
    prior = gamelog_dates[1]
    gap = max(4, min(7, (last_actual - prior).days))
    next_date = last_actual + timedelta(days=gap)
    if next_date in confirmed_dates:
        return []
    sched = {d: opp for d, opp in team_schedule}
    if next_date in sched:
        return [(next_date, sched[next_date])]
    return []
