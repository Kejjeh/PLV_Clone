"""Split doubleheaders are TWO games on ONE date — count games, not dates.

Found live 2026-08-28 (period 21, an elimination round): `build_state` gave
Luis Garcia Jr. and Trent Grisham n_games=3 against an actual 4 (NYY split DH
on 8/29), and Corbin Carroll 2 against 3 (ARI likewise) — three uncounted
hitter-games in one matchup, all from a single line: the ESPN schedule dedup
keyed on (date, opp_team), which is not a game identity.

Two independent halves are pinned here because fixing either alone makes the
model WORSE:

  * DEMAND — the schedule must carry one entry per GAME, so every downstream
    consumer that counts entries (the hitter `rem` window in project_player,
    the RP `n_rem` in leverage_engine, decision_console's week game count)
    lands on 4 rather than 3.
  * CAPACITY — the lineup-slot guard sizes 13 slots x N. A hitter in ONE slot
    on a DH day is credited with TWO games, so counting DAYS understates
    capacity by exactly the amount the demand fix adds. Raising demand without
    raising capacity would make the guard reject legal adds.
"""
from __future__ import annotations

import inspect
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

# Deliberately a hard import, not importorskip: all three modules are tracked
# source, so a missing one is a real failure, and this regression must never be
# able to silently not run (test_testqual_data_gating's census bound is about
# exactly that). Nothing here touches a built data artifact.
import build_matchup_dashboard as BMD                       # noqa: E402
import lib.leverage_engine as LE                            # noqa: E402
import lib.roster_rules as RR                               # noqa: E402

NYY_MLB_ID = 147
WEEK = (date(2026, 8, 28), date(2026, 8, 30))

#: NYY (ESPN pro id 10) hosting BOS (2) — 8/28 single, 8/29 SPLIT DH, 8/30
#: single. Ids and epoch-ms stamps are the shape ESPN really returns; the two
#: 8/29 entries differ ONLY in `id` and first pitch, which is precisely why
#: (date, opp_team) could not tell them apart.
_NYY_GAMES = [
    {"id": 401816702, "date": 1787958900000, "homeProTeamId": 10,
     "awayProTeamId": 2, "scoringPeriodId": 157},
    {"id": 401874913, "date": 1788023100000, "homeProTeamId": 10,
     "awayProTeamId": 2, "scoringPeriodId": 158},   # DH game 1
    {"id": 401816717, "date": 1788045300000, "homeProTeamId": 10,
     "awayProTeamId": 2, "scoringPeriodId": 158},   # DH game 2
    {"id": 401816732, "date": 1788111300000, "homeProTeamId": 10,
     "awayProTeamId": 2, "scoringPeriodId": 159},
]


def _pro_schedule(by_period):
    return {"settings": {"proTeams": [
        {"id": 10, "abbrev": "NYY", "proGamesByScoringPeriod": by_period},
        {"id": 2, "abbrev": "BOS", "proGamesByScoringPeriod": {}},
    ]}}


class _FakeLeague:
    """Minimal stand-in for the espn_api League — only get_pro_schedule is read."""

    def __init__(self, by_period=None):
        payload = _pro_schedule(by_period or {
            "157": [_NYY_GAMES[0]],
            "158": _NYY_GAMES[1:3],
            "159": [_NYY_GAMES[3]],
        })
        self.espn_request = type("_Req", (), {
            "get_pro_schedule": staticmethod(lambda: payload)})()


def _nyy_schedule(league=None):
    sched = BMD.fetch_espn_week_schedule(league or _FakeLeague(), *WEEK)
    return sched.get(NYY_MLB_ID, [])


# ── demand: one entry per GAME ───────────────────────────────────────────────

def test_split_dh_yields_two_schedule_entries_on_one_date():
    """The regression itself: 4 games across 3 dates, not 3."""
    games = _nyy_schedule()
    assert len(games) == 4, f"split DH collapsed: {[g['date'] for g in games]}"
    assert [g["date"] for g in games] == ["2026-08-28", "2026-08-29",
                                          "2026-08-29", "2026-08-30"]


def test_hitter_n_games_counts_both_halves_of_the_dh():
    """What Garcia Jr./Grisham actually saw — the in-window count is 4, not 3,
    while the number of distinct dates is still 3."""
    lo, hi = WEEK[0].isoformat(), WEEK[1].isoformat()
    rem = [g for g in _nyy_schedule() if lo <= g["date"] <= hi]  # project_player
    assert len(rem) == 4
    assert len({g["date"] for g in rem}) == 3


def test_true_duplicates_are_still_deduplicated():
    """Dedup is still required — proGamesByScoringPeriod can list ONE game under
    two scoring periods. Identity is the game id, so a repeat of 401816702
    collapses while the genuine DH pair survives."""
    league = _FakeLeague({
        "157": [_NYY_GAMES[0]],
        "158": _NYY_GAMES[1:3] + [dict(_NYY_GAMES[0], scoringPeriodId=158)],
        "159": [_NYY_GAMES[3]],
    })
    assert len(_nyy_schedule(league)) == 4


def test_schedule_entries_expose_no_internal_identity_keys():
    """The dedup scratch keys must not leak into the dicts every consumer
    iterates — the contract is the shape fetch_schedules_by_team returns."""
    for g in _nyy_schedule():
        assert not [k for k in g if k.startswith("_")], sorted(g)


# ── the SP side: a DH date must not drop or duplicate a start event ──────────

def test_dh_date_does_not_duplicate_or_drop_an_sp_start():
    """A pitcher starts ONE game of a doubleheader. build_sp_starts_by_pitcher
    keys probables by (pitcher, date) and reads only is_home/opp_team off the
    team-day record, so the second schedule entry must neither manufacture a
    phantom start nor change what the real one resolves to."""
    games = _nyy_schedule()
    by_date = {g["date"]: g for g in games}          # the SP-path lookup shape
    assert set(by_date) == {"2026-08-28", "2026-08-29", "2026-08-30"}
    dh = [g for g in games if g["date"] == "2026-08-29"]
    assert len(dh) == 2
    assert dh[0]["is_home"] == dh[1]["is_home"]
    assert dh[0]["opp_team"] == dh[1]["opp_team"]


# ── capacity: one lineup slot on a DH day yields TWO games ───────────────────

def test_games_per_day_marks_the_dh_date_as_two():
    gpd = LE._games_per_day({NYY_MLB_ID: _nyy_schedule()}, *WEEK)
    assert gpd == {"2026-08-28": 1, "2026-08-29": 2, "2026-08-30": 1}


def test_games_per_day_is_per_team_max_not_a_league_total():
    """Two teams playing the same day is still ONE game per slot-day — the
    constraint is one of Josh's slots, and it follows ONE team's schedule."""
    other = [dict(g, opp_team="X") for g in _nyy_schedule()
             if g["date"] != "2026-08-29"]
    gpd = LE._games_per_day({NYY_MLB_ID: _nyy_schedule(), 999: other}, *WEEK)
    assert gpd["2026-08-28"] == 1
    assert gpd["2026-08-29"] == 2


def test_slot_days_count_the_dh_date_twice():
    gpd = {"2026-08-28": 1, "2026-08-29": 2, "2026-08-30": 1}
    assert RR.lineup_slot_days(gpd, 3) == 4
    assert RR.lineup_slot_days(None, 3) == 3      # no schedule -> old behavior


def test_one_slot_on_a_dh_day_is_credited_with_two_games():
    """THE subtle interaction. 13 hitters over a 3-day window containing one
    split DH can play 13x4 = 52 games, not 13x3 = 39. Asking for exactly 52 is
    legal; day-counted capacity rejects it as 13 games oversubscribed."""
    gpd = {"2026-08-28": 1, "2026-08-29": 2, "2026-08-30": 1}
    assert RR.lineup_capacity_problem(
        n_hitters_after=13, hitter_games_after=52,
        days_remaining=3, games_per_day=gpd) is None
    assert RR.lineup_capacity_problem(
        n_hitters_after=13, hitter_games_after=52, days_remaining=3) is not None


def test_dh_capacity_still_rejects_a_genuine_oversubscription():
    """The guard must not go toothless: 53 games still exceeds 52 slots."""
    gpd = {"2026-08-28": 1, "2026-08-29": 2, "2026-08-30": 1}
    why = RR.lineup_capacity_problem(n_hitters_after=14, hitter_games_after=53,
                                     days_remaining=3, games_per_day=gpd)
    assert why and "could not be played" in why


def test_check_swap_threads_games_per_day_to_the_guard():
    """The kwarg must actually reach the guard through check_swap, or the
    optimizer keeps sizing capacity in days (don't-do #18)."""
    assert "games_per_day" in inspect.signature(RR.check_swap).parameters
