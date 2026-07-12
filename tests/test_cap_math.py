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


def test_cap_kwarg_counts_only_first_start():
    """cap= (decision-console seam) overrides the flat SP_CAP default."""
    week_start = date(2026, 5, 22)
    roster = [
        RosterPitcher(name=f"Pitcher{i}", mlbam_id=10000 + i,
                      injury_status="ACTIVE", position="SP")
        for i in range(3)
    ]
    probables = WeekProbables(
        starts={(10000 + i, week_start + timedelta(days=i)): "BAL" for i in range(3)},
    )
    rp3 = {f"Pitcher{i}": 10.0 for i in range(3)}

    result = weekly_sp_projection(
        roster=roster,
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        rp3=rp3,
        probables=probables,
        cap=1,
    )

    chronological = sorted(result, key=lambda s: s.start_date)
    assert [s.counts_toward_cap for s in chronological] == [True, False, False]


def test_rp3_absent_name_projects_zero_not_keyerror():
    """A probable for a pitcher missing from the rp3 map projects 0.0 FP
    (decision-console FA arms won't always carry a rate)."""
    roster = [
        RosterPitcher(name="Unrated Arm", mlbam_id=55555,
                      injury_status="ACTIVE", position="SP"),
    ]
    probables = WeekProbables(starts={(55555, date(2026, 5, 24)): "BAL"})

    result = weekly_sp_projection(
        roster=roster,
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
        rp3={},
        probables=probables,
    )

    assert len(result) == 1
    assert result[0].projected_fp == 0.0


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


def test_starts_per_sp_owner_constant():
    """The 1.19 rate now has ONE owner (was 8+ inline copies under 6 names)."""
    from plv_clone.cap_math import STARTS_PER_SP_PER_WEEK
    assert STARTS_PER_SP_PER_WEEK == 1.19


def test_projected_starts_and_gap_reproduce_session_cap_math():
    """Reproduces the 2026-07-03 forced-drop cascade numbers exactly."""
    from plv_clone.cap_math import projected_starts, gap_to_cap
    assert round(projected_starts(6), 2) == 7.14   # 6 healthy SPs
    assert round(gap_to_cap(6), 2) == 2.86         # under cap -> need streamers
    assert round(gap_to_cap(9), 2) == -0.71        # Fried return -> FORCED DROP
    assert gap_to_cap(8) > 0 > gap_to_cap(9)       # cap breaches between 8 and 9 SPs


# ── period-aware cap + window (2026-07-11 ASG block) ──────────────────────────

def test_default_period_uses_flat_sp_cap_10():
    """REGRESSION GUARD: a standard single-week period must stay cap 10 and have
    NO window override (caller then uses its own Mon–Sun week). This is the
    default-preserving contract — every non-listed period is byte-identical."""
    from plv_clone.cap_math import (
        sp_cap_for_period, period_window, is_period_covered, SP_CAP,
    )
    assert SP_CAP == 10
    for p in (1, 5, 10, 14, 16, 20):          # ordinary weekly periods
        assert sp_cap_for_period(p) == 10
        assert period_window(p) is None
        assert is_period_covered(p) is False
    # None (unknown period) also falls back to the default cap, no window.
    assert sp_cap_for_period(None) == 10
    assert period_window(None) is None
    assert is_period_covered(None) is False


def test_asg_period_15_uses_cap_16_and_two_week_window():
    """Period 15 (2026 All-Star block) → cap 16 over Jul 6–19."""
    from datetime import date
    from plv_clone.cap_math import (
        sp_cap_for_period, period_window, is_period_covered,
    )
    assert sp_cap_for_period(15) == 16
    assert period_window(15) == (date(2026, 7, 6), date(2026, 7, 19))
    assert is_period_covered(15) is True
    # the span really is longer than one scoring week (the whole point)
    start, end = period_window(15)
    assert (end - start).days + 1 > 7


def test_sp_cap_for_period_default_override_arg():
    """A caller can pass a non-10 default; overrides still win for listed periods."""
    from plv_clone.cap_math import sp_cap_for_period
    assert sp_cap_for_period(5, default=12) == 12    # uncovered -> caller default
    assert sp_cap_for_period(15, default=12) == 16   # covered -> override wins


def test_general_rule_10_times_weeks_playoff_two_week_round_is_20():
    """cap = 10 × weeks. A 2-week playoff round (periods 22/23) → 20; a 1-week
    round (period 21) → 10. No hardcoding needed — the week count drives it."""
    from plv_clone.cap_math import sp_cap_for_period
    assert sp_cap_for_period(21, weeks=1) == 10      # playoff round 1 (1 week)
    assert sp_cap_for_period(22, weeks=2) == 20      # playoff round 2 (2 weeks)
    assert sp_cap_for_period(23, weeks=2) == 20      # playoff round 3 (2 weeks)
    assert sp_cap_for_period(8, weeks=1) == 10       # regular week
    assert sp_cap_for_period(8) == 10                # weeks defaults to 1


def test_asg_override_beats_the_10_times_weeks_formula():
    """Period 15 = 16 even though weeks would say otherwise — override precedence.
    The ASG break removes game-days so 10×weeks (would be 10 or 20) is WRONG."""
    from plv_clone.cap_math import sp_cap_for_period
    assert sp_cap_for_period(15, weeks=1) == 16      # ESPN lists it as 1 week...
    assert sp_cap_for_period(15, weeks=2) == 16      # ...but override wins regardless


def test_weeks_in_period_reads_matchup_periods_mapping():
    """weeks = len(matchupPeriods[period]); playoff 22→[24,25]=2, regular=1."""
    from plv_clone.cap_math import weeks_in_period
    mp = {'21': [21], '22': [22, 23], '23': [24, 25], '15': [15], '8': [8]}
    assert weeks_in_period(mp, 21) == 1
    assert weeks_in_period(mp, 22) == 2
    assert weeks_in_period(mp, 23) == 2
    assert weeks_in_period(mp, 8) == 1
    assert weeks_in_period(mp, 15) == 1              # ASG lists as 1 (why it's an override)
    assert weeks_in_period(mp, 999) == 1             # unknown period -> 1
    assert weeks_in_period(None, 22) == 1            # no mapping -> 1
    assert weeks_in_period({}, 22) == 1


def test_playoff_cap_end_to_end_via_matchup_periods():
    """Integration: the real ESPN mapping shape drives 10×weeks correctly."""
    from plv_clone.cap_math import sp_cap_for_period, weeks_in_period
    mp = {'21': [21], '22': [22, 23], '23': [24, 25]}
    assert sp_cap_for_period(21, weeks=weeks_in_period(mp, 21)) == 10
    assert sp_cap_for_period(22, weeks=weeks_in_period(mp, 22)) == 20
    assert sp_cap_for_period(23, weeks=weeks_in_period(mp, 23)) == 20


def test_is_period_covered_requires_both_cap_and_window():
    """is_period_covered is True only when BOTH dicts have the period — a
    half-specified override must read as uncovered so the engine warns loudly."""
    from plv_clone.cap_math import (
        PERIOD_CAP_OVERRIDES, PERIOD_WINDOW_OVERRIDES, is_period_covered,
    )
    # every currently-listed period must be fully specified (both dicts)
    for p in PERIOD_CAP_OVERRIDES:
        assert p in PERIOD_WINDOW_OVERRIDES, f'period {p} cap without window'
        assert is_period_covered(p) is True
    for p in PERIOD_WINDOW_OVERRIDES:
        assert p in PERIOD_CAP_OVERRIDES, f'period {p} window without cap'
