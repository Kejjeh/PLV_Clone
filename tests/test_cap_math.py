"""Behavioral tests for cap_math.weekly_sp_projection.

Each test names a behavior at the public interface. The four /matchup-audit
bug patterns become tests here (except rotation-gap undercount, which belongs
in the mlb_stats slice — WeekProbables is the union of confirmed + predicted).
"""
from __future__ import annotations

from datetime import date, timedelta

from plv_clone.cap_math import (
    RosterPitcher,
    SPStart,
    WeekProbables,
    weekly_sp_projection,
)


def test_healthy_sp_with_one_probable_emits_one_spstart():
    roster = [
        RosterPitcher(
            name="Hunter Brown",
            mlbam_id=686613,
            injury_status="ACTIVE",
            position="SP",
        ),
    ]
    probables = WeekProbables(starts={(686613, date(2026, 5, 24)): "BAL"})
    rp3 = {"Hunter Brown": 16.5}

    result = weekly_sp_projection(
        roster=roster,
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
        rp3=rp3,
        probables=probables,
    )

    assert result == [
        SPStart(
            pitcher_name="Hunter Brown",
            mlbam_id=686613,
            start_date=date(2026, 5, 24),
            opponent_team="BAL",
            projected_fp=16.5,
            counts_toward_cap=True,
        )
    ]


def test_il_pitcher_with_probable_is_omitted():
    """Bug A: stale probables for an IL'd SP must not produce a projected start."""
    roster = [
        RosterPitcher(
            name="Spencer Strider",
            mlbam_id=675911,
            injury_status="SIXTY_DAY_DL",
            position="SP",
        ),
    ]
    probables = WeekProbables(starts={(675911, date(2026, 5, 24)): "BAL"})
    rp3 = {"Spencer Strider": 18.0}

    result = weekly_sp_projection(
        roster=roster,
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
        rp3=rp3,
        probables=probables,
    )

    assert result == []


def test_eleventh_chronological_start_does_not_count_toward_cap():
    """Only the first 10 chronological starts in a week count toward scoring."""
    week_start = date(2026, 5, 22)
    roster = [
        RosterPitcher(
            name=f"Pitcher{i}",
            mlbam_id=10000 + i,
            injury_status="ACTIVE",
            position="SP",
        )
        for i in range(11)
    ]
    probables = WeekProbables(
        starts={
            (10000 + i, week_start + timedelta(days=i)): "BAL" for i in range(11)
        },
    )
    rp3 = {f"Pitcher{i}": 10.0 for i in range(11)}

    result = weekly_sp_projection(
        roster=roster,
        week_start=week_start,
        week_end=week_start + timedelta(days=13),
        rp3=rp3,
        probables=probables,
    )

    chronological = sorted(result, key=lambda s: s.start_date)
    assert len(chronological) == 11
    assert all(s.counts_toward_cap for s in chronological[:10])
    assert chronological[10].counts_toward_cap is False


def test_probable_on_week_start_is_included():
    """Bug D: probables falling on week_start (today) must not be excluded by strict comparison."""
    today = date(2026, 5, 22)
    roster = [
        RosterPitcher(
            name="Hunter Brown",
            mlbam_id=686613,
            injury_status="ACTIVE",
            position="SP",
        ),
    ]
    probables = WeekProbables(starts={(686613, today): "BAL"})
    rp3 = {"Hunter Brown": 16.0}

    result = weekly_sp_projection(
        roster=roster,
        week_start=today,
        week_end=date(2026, 5, 28),
        rp3=rp3,
        probables=probables,
    )

    assert len(result) == 1
    assert result[0].start_date == today


def test_unresolved_mlbam_pitcher_is_omitted():
    """Bug C: a roster pitcher with mlbam_id=None must not phantom-match any probable."""
    roster = [
        RosterPitcher(
            name="Callup McNobody",
            mlbam_id=None,
            injury_status="ACTIVE",
            position="SP",
        ),
    ]
    probables = WeekProbables(starts={(999999, date(2026, 5, 24)): "BAL"})
    rp3 = {"Callup McNobody": 8.0}

    result = weekly_sp_projection(
        roster=roster,
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
        rp3=rp3,
        probables=probables,
    )

    assert result == []


# ── cap_excess_starts: the FP-rank planning cap (matchup/optimizer) ────────────

def test_cap_excess_starts_under_cap_is_empty():
    from plv_clone.cap_math import cap_excess_starts
    assert cap_excess_starts([10.0, 8.0, 5.0], cap=10) == set()
    assert cap_excess_starts([10.0] * 10, cap=10) == set()


def test_cap_excess_starts_zeros_lowest_fp_beyond_cap():
    from plv_clone.cap_math import cap_excess_starts
    # 12 starts, cap 10 -> the two LOWEST-FP indices (10:2.0, 11:1.0) are excess.
    fps = [float(x) for x in (5, 9, 3, 12, 7, 8, 6, 11, 4, 10, 2, 1)]
    assert cap_excess_starts(fps, cap=10) == {10, 11}


def test_cap_excess_starts_ties_keep_input_order():
    # All equal: keep first `cap` by input order; the rest are excess (stable),
    # matching the matchup's prior stable sort-by-fp behaviour.
    from plv_clone.cap_math import cap_excess_starts
    assert cap_excess_starts([5.0, 5.0, 5.0, 5.0], cap=2) == {2, 3}
