"""Period-aware banked-count cross-check for the /matchup-leverage engine.

Locks the behavior that the ASG fix depends on: the authoritative per-team
SP-start count (statId 33) is read straight from ESPN's matchup endpoint
(cumulativeScore.statBySlot["22"].value) — the 3/16, 6/16 shown on the matchup
screen — rather than inferred from the boxscore store. Uses a fake league so
the test is offline and deterministic (no ESPN creds needed).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import run_matchup_leverage as ml  # noqa: E402


class _FakeRequest:
    """Mimics espn_api's EspnFantasyRequests.league_get(view=[...])."""

    def __init__(self, schedule, rate=1.4285714285714286):
        self._schedule = schedule
        self._rate = rate

    def league_get(self, params=None):
        view = (params or {}).get("view", [])
        if "mMatchupScore" in view:
            return {"schedule": self._schedule}
        if "mSettings" in view:
            return {"settings": {"rosterSettings": {
                "lineupSlotStatLimits": {"22": {"limitValue": self._rate,
                                                "statId": 33}}}}}
        return {}


class _FakeLeague:
    def __init__(self, schedule):
        self.espn_request = _FakeRequest(schedule)


def _gs_side(team_id, value, scoring_periods=(104, 105, 106, 107, 108)):
    return {
        "teamId": team_id,
        "cumulativeScore": {
            "statBySlot": {"22": {"statId": 33, "value": float(value),
                                  "limitExceeded": False}}},
        "pointsByScoringPeriod": {str(sp): 50.0 for sp in scoring_periods},
    }


def test_espn_period_meta_reads_authoritative_banked_counts():
    """Ligers (team 8) banked 3, Solomon (team 2) banked 6 — the real 3/16, 6/16."""
    schedule = [
        {"matchupPeriodId": 15,
         "home": _gs_side(8, 3),      # New York Ligers
         "away": _gs_side(2, 6)},     # Team Solomon
        {"matchupPeriodId": 15,       # an unrelated matchup, must be ignored
         "home": _gs_side(4, 5),
         "away": _gs_side(1, 4)},
        {"matchupPeriodId": 14,       # wrong period, must be ignored
         "home": _gs_side(8, 99),
         "away": _gs_side(2, 99)},
    ]
    meta = ml.espn_period_meta(_FakeLeague(schedule), 15,
                               my_team_id=8, opp_team_id=2)
    assert meta["my_banked"] == 3
    assert meta["opp_banked"] == 6
    # elapsed span (104..108) -> 4 day-delta, i.e. within a single week (no warn)
    assert meta["elapsed_span_days"] == 4
    # per-scoring-period cap rate is surfaced for the cross-check
    assert abs(meta["cap_rate_per_sp"] - 10 / 7) < 1e-9


def test_espn_period_meta_ignores_non_statid33_slot():
    """A statBySlot entry that is not the games-started counter yields None."""
    bad = {"teamId": 8,
           "cumulativeScore": {"statBySlot": {"22": {"statId": 99, "value": 7.0}}},
           "pointsByScoringPeriod": {"108": 1.0}}
    schedule = [{"matchupPeriodId": 15, "home": bad, "away": _gs_side(2, 6)}]
    meta = ml.espn_period_meta(_FakeLeague(schedule), 15, 8, 2)
    assert meta["my_banked"] is None       # guarded by statId==33
    assert meta["opp_banked"] == 6


def test_espn_period_meta_returns_empty_on_fetch_failure():
    """Any ESPN failure -> {} so the caller falls back to the boxscore count."""
    class _Boom:
        class espn_request:
            @staticmethod
            def league_get(params=None):
                raise RuntimeError("network down")
    meta = ml.espn_period_meta(_Boom(), 15, 8, 2)
    assert meta == {}


def test_multiweek_elapsed_span_flags_uncovered_period():
    """A period that has already scored across >1 week (span_days>6) is what the
    engine's LOUD warning keys on for an uncovered period."""
    schedule = [{"matchupPeriodId": 99,
                 "home": _gs_side(8, 8, scoring_periods=(104, 105, 111, 112)),
                 "away": _gs_side(2, 9, scoring_periods=(104, 112))}]
    meta = ml.espn_period_meta(_FakeLeague(schedule), 99, 8, 2)
    assert meta["elapsed_span_days"] == 8   # 112-104 -> >6 -> would warn
