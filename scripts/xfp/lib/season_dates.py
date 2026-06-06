"""Canonical MLB Opening Day mapping.

Avoids hardcoded `3/1` season-start boundaries that would either pull in
spring-training leakage prior to Opening Day or miss the first week of the
season, depending on the year. Verified against statcast_<yr>.parquet
min(game_date) values for 2024/2025/2026.
"""
from __future__ import annotations
from datetime import date

# Verified against data/research/xfp_cache/statcast_{yr}.parquet:
#   2024 first game_date = 2024-03-28
#   2025 first game_date = 2025-03-27
#   2026 first game_date = 2026-03-26
_OPENING_DAY = {
    2024: date(2024, 3, 28),
    2025: date(2025, 3, 27),
    2026: date(2026, 3, 26),
}


def season_start(yr: int) -> date:
    """Return MLB Opening Day for the given year.

    Raises:
        ValueError: if no anchor is recorded for `yr`. Add the year to
            `_OPENING_DAY` rather than fall back to `3/1` or another guess.
    """
    if yr not in _OPENING_DAY:
        raise ValueError(
            f"season_start: no opening-day anchor recorded for {yr}; "
            f"add to scripts/xfp/lib/season_dates.py"
        )
    return _OPENING_DAY[yr]
