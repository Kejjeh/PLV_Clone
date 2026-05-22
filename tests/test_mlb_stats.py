"""Behavioral tests for mlb_stats pure merge + prediction logic.

HTTP-fetching wrapper (`fetch_week_probables`) is tested separately; the
pure prediction unit is what bug B (no-rotation-gap-fallback undercount)
regresses against.
"""
from __future__ import annotations

from datetime import date

from plv_clone.mlb_stats import predict_rotation_starts


def test_predicts_next_start_at_gap_after_last_actual():
    """Last actual start + rotation gap lands on a team game in window -> one predicted start."""
    last_actual = date(2026, 5, 17)
    prior_start = date(2026, 5, 12)
    week_start = date(2026, 5, 22)
    week_end = date(2026, 5, 28)
    team_schedule = [
        (date(2026, 5, 22), "BAL"),
        (date(2026, 5, 23), "BAL"),
        (date(2026, 5, 24), "NYY"),
    ]

    result = predict_rotation_starts(
        gamelog_dates=[last_actual, prior_start],
        confirmed_dates=[],
        team_schedule=team_schedule,
        week_start=week_start,
        week_end=week_end,
    )

    assert result == [(date(2026, 5, 22), "BAL")]


def test_predicted_start_dedups_against_confirmed_date():
    """A predicted date that is already a confirmed start must not double-emit."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 17), date(2026, 5, 12)],
        confirmed_dates=[date(2026, 5, 22)],
        team_schedule=[(date(2026, 5, 22), "BAL")],
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
    )

    assert result == []


def test_gap_clamps_to_seven_when_prior_starts_far_apart():
    """A 10-day gap from extended rest must clamp to 7, not extrapolate the full gap."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 17), date(2026, 5, 7)],
        confirmed_dates=[],
        team_schedule=[
            (date(2026, 5, 24), "NYY"),
            (date(2026, 5, 27), "TBR"),
        ],
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
    )

    assert result == [(date(2026, 5, 24), "NYY")]


def test_gap_clamps_to_four_when_prior_starts_close():
    """A 3-day gap (rare back-to-back) must clamp to 4 minimum."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 20), date(2026, 5, 17)],
        confirmed_dates=[],
        team_schedule=[
            (date(2026, 5, 23), "NYY"),
            (date(2026, 5, 24), "NYY"),
        ],
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
    )

    assert result == [(date(2026, 5, 24), "NYY")]
