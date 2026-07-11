"""Lock the ONE shared period-resolver (scripts/xfp/lib/period_meta.py).

All three cap consumers — run_matchup_leverage, run_roster_audit,
build_matchup_dashboard — resolve the current matchup period's cap + window +
banked count through this module, so these tests pin the contract that keeps
them consistent:

  • the ASG period (15) resolves to cap 16 over its real Jul 6–19 window;
  • a plain single-week period resolves to cap 10 + a Mon–Sun week (default-
    preserving);
  • a 2-week playoff round resolves to cap 20 over a 14-day span (10×weeks).

Offline: a fake league carries only the `settings.matchup_periods` mapping the
resolver reads, so no ESPN creds are needed.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from scripts.xfp.lib.period_meta import (  # noqa: E402
    resolve_period_meta, resolve_current_period_meta, espn_period_meta,
)


class _FakeSettings:
    def __init__(self, matchup_periods):
        self.matchup_periods = matchup_periods


class _FakeLeague:
    def __init__(self, matchup_periods, current_period=None):
        self.settings = _FakeSettings(matchup_periods)
        # ESPN exposes the live period as league.currentMatchupPeriod
        self.currentMatchupPeriod = current_period


# ESPN's real mapping shape: ASG lists as a single week-index despite its 2-week
# span (that's exactly why period 15 is an explicit override), playoff rounds
# span two scoring weeks.
_MP = {"8": [8], "15": [15], "21": [21], "22": [22, 23], "23": [24, 25]}


def test_current_asg_period_resolves_to_cap_16_and_two_week_window():
    """The live period this session (15) → cap 16 over Jul 6–19, marked covered."""
    league = _FakeLeague(_MP)
    meta = resolve_period_meta(league, 15, today=date(2026, 7, 11))
    assert meta["sp_cap"] == 16
    assert meta["covered"] is True
    assert meta["week_start"] == date(2026, 7, 6)
    assert meta["week_end"] == date(2026, 7, 19)
    # the override window really is longer than one scoring week
    assert (meta["week_end"] - meta["week_start"]).days + 1 > 7


def test_stubbed_single_week_period_resolves_to_cap_10_and_mon_sun_week():
    """A plain 1-week period → cap 10 + the Mon–Sun week of `today`, NOT covered.
    This is the default-preserving contract for every ordinary week."""
    league = _FakeLeague(_MP)
    # 2026-07-15 is a Wednesday → its Monday is 2026-07-13, Sunday 2026-07-19.
    meta = resolve_period_meta(league, 8, today=date(2026, 7, 15))
    assert meta["sp_cap"] == 10
    assert meta["weeks"] == 1
    assert meta["covered"] is False
    assert meta["week_start"] == date(2026, 7, 13)
    assert meta["week_end"] == date(2026, 7, 19)


def test_two_week_playoff_round_resolves_to_cap_20_over_14_day_span():
    """A 2-week playoff round (period 22 → [22,23]) → cap 20 via 10×weeks, with a
    14-day window anchored to the current Monday. 1-week round 21 stays 10."""
    league = _FakeLeague(_MP)
    meta = resolve_period_meta(league, 22, today=date(2026, 9, 14))  # a Monday
    assert meta["sp_cap"] == 20
    assert meta["weeks"] == 2
    assert meta["covered"] is False           # handled by 10×weeks, not an override
    assert meta["week_start"] == date(2026, 9, 14)
    assert (meta["week_end"] - meta["week_start"]).days + 1 == 14
    # the 1-week playoff round is unchanged at 10
    assert resolve_period_meta(league, 21, today=date(2026, 9, 14))["sp_cap"] == 10


def test_missing_matchup_periods_falls_back_to_single_week():
    """A league with no settings.matchup_periods → weeks 1, cap 10 (safe default)."""
    class _Bare:
        settings = None
    meta = resolve_period_meta(_Bare(), 8, today=date(2026, 7, 15))
    assert meta["sp_cap"] == 10 and meta["weeks"] == 1


# ── resolve_current_period_meta: reads league.currentMatchupPeriod itself ─────
# The seam the cap consumers call so none of them re-duplicate the
# getattr(currentMatchupPeriod) + resolve_period_meta dance.

def test_current_period_meta_reads_live_asg_period_as_16():
    """A league sitting on the ASG period (15) → cap 16, without the caller
    having to pass the period number."""
    league = _FakeLeague(_MP, current_period=15)
    meta = resolve_current_period_meta(league, today=date(2026, 7, 11))
    assert meta["sp_cap"] == 16
    assert meta["period"] == 15


def test_current_period_meta_missing_period_is_safe_10():
    """A league object with no currentMatchupPeriod attribute → single-week
    default (cap 10), never a crash — the fail-safe every caller relies on."""
    class _Bare:
        settings = None
    meta = resolve_current_period_meta(_Bare(), today=date(2026, 7, 15))
    assert meta["sp_cap"] == 10
    assert meta["weeks"] == 1


def test_current_period_meta_two_week_playoff_is_20():
    """The live-period seam preserves the 10×weeks rule: a league on a 2-week
    playoff round (22 → [22,23]) → cap 20."""
    league = _FakeLeague(_MP, current_period=22)
    meta = resolve_current_period_meta(league, today=date(2026, 9, 14))
    assert meta["sp_cap"] == 20
    assert meta["weeks"] == 2


# ── banked-count reader re-exported here shares one implementation ────────────

class _FakeRequest:
    def __init__(self, schedule):
        self._schedule = schedule

    def league_get(self, params=None):
        if "mMatchupScore" in (params or {}).get("view", []):
            return {"schedule": self._schedule}
        return {}


class _FakeLeagueWithReq:
    def __init__(self, schedule):
        self.espn_request = _FakeRequest(schedule)


def _gs_side(team_id, value):
    return {
        "teamId": team_id,
        "cumulativeScore": {
            "statBySlot": {"22": {"statId": 33, "value": float(value)}}},
        "pointsByScoringPeriod": {"104": 1.0, "108": 1.0},
    }


def test_espn_period_meta_opp_none_sets_only_my_banked():
    """roster-audit passes opp_team_id=None — only the user's banked count is set."""
    schedule = [{"matchupPeriodId": 15,
                 "home": _gs_side(8, 3), "away": _gs_side(2, 6)}]
    meta = espn_period_meta(_FakeLeagueWithReq(schedule), 15,
                            my_team_id=8, opp_team_id=None)
    assert meta["my_banked"] == 3
    assert "opp_banked" not in meta
