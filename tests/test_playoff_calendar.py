"""Behavioral tests for lib.playoff_calendar — period-conditional xFP.

Playoff xFP is not RoS-per-game smeared over a blob: periods 21/22/23 are
specific calendar windows with their own team-game counts, rotation timing,
and SP caps (10/20/20). Windows themselves come from resolve_period_meta at
integration time; these tests pass explicit dates.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.playoff_calendar import hitter_period_xfp  # noqa: E402


def test_hitter_period_xfp_counts_only_games_from_return_date():
    """A hitter returning mid-window produces FP only in games on/after his
    return: rate x PA/teamgame x available games in the window."""
    window_dates = [date(2026, 9, d) for d in (14, 15, 16, 18, 19, 20, 22)]
    xfp = hitter_period_xfp(
        rate_fp_per_pa=0.708,
        pa_per_teamgame=4.0,
        team_dates_in_window=window_dates,
        return_date=date(2026, 9, 18),   # misses the first 3 of 7 games
    )
    assert xfp == pytest.approx(0.708 * 4.0 * 4)


def test_sp_starts_fall_on_every_fifth_team_game_after_last_start():
    """Rotation cycle: an SP starts every 5th TEAM game after his last start;
    a window captures exactly the start dates that land inside it.

    The schedule must STRADDLE last_start_date — that is what carries rotation
    phase. (The original version of this test started the schedule two days
    AFTER the last start, so the phase filter removed nothing and the test
    passed for any last_start_date at all, including 2026-01-01.)"""
    from lib.playoff_calendar import sp_starts_in_window

    team_dates = [date(2026, 8, 10 + i) for i in range(19)]  # Aug 10..28 daily
    # last start Aug 13 -> next starts on the 5th/10th/15th game after = 8/18, 8/23, 8/28
    assert sp_starts_in_window(
        team_dates=team_dates, last_start_date=date(2026, 8, 13),
        window=(date(2026, 8, 24), date(2026, 8, 30)),
    ) == 1
    assert sp_starts_in_window(
        team_dates=team_dates, last_start_date=date(2026, 8, 13),
        window=(date(2026, 8, 14), date(2026, 8, 23)),
    ) == 2


def test_rotation_phase_actually_depends_on_last_start_date():
    """Two SPs on the SAME team with last starts a rotation turn apart must NOT
    receive identical start counts. Regression for the 2026-08-14 phase
    collapse: the board pulled its schedule starting at TODAY, so every date
    was already past every pitcher's last start, the phase filter became a
    no-op, and all 8 active SPs were handed an identical 7.0-start allocation
    — the period calendar added zero cross-sectional information."""
    from lib.playoff_calendar import sp_starts_in_window

    team_dates = [date(2026, 8, 10 + i) for i in range(19)]
    window = (date(2026, 8, 17), date(2026, 8, 23))
    counts = {ls: sp_starts_in_window(team_dates=team_dates,
                                      last_start_date=date(2026, 8, ls),
                                      window=window)
              for ls in (11, 12, 13, 14, 15)}
    assert len(set(counts.values())) > 1, (
        f"rotation phase is being ignored — every last-start date gives the "
        f"same count: {counts}")


def test_sp_starts_refuses_a_schedule_that_cannot_carry_phase():
    """If the schedule begins after the last start, phase is UNDEFINED — the
    function must say so rather than silently anchoring on the first date."""
    from lib.playoff_calendar import sp_starts_in_window

    with pytest.raises(ValueError, match="straddle"):
        sp_starts_in_window(
            team_dates=[date(2026, 8, 20 + i) for i in range(10)],
            last_start_date=date(2026, 8, 12),
            window=(date(2026, 8, 20), date(2026, 8, 29)),
        )


def test_cap_absorbs_weakest_overflow_starts():
    """League rule: starts past the period cap score ZERO. Roster period FP =
    the cap's worth of best starts; overflow comes out of the weakest arm."""
    from lib.playoff_calendar import cap_absorbed_fp

    arms = [(15.0, 4.0), (12.0, 4.0), (10.0, 4.0)]   # (fp_per_start, exp_starts)
    # cap 10 of 12 projected: 4x15 + 4x12 + only 2x10
    assert cap_absorbed_fp(arms, cap=10) == pytest.approx(4 * 15 + 4 * 12 + 2 * 10)
    # no overflow -> nothing absorbed
    assert cap_absorbed_fp(arms, cap=20) == pytest.approx(4 * 15 + 4 * 12 + 4 * 10)
