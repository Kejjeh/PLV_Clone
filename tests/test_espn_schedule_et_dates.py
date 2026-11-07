"""ESPN first-pitch epoch stamps must bucket to the EASTERN calendar date.

Defect (found 2026-09-18): ``fetch_espn_week_schedule`` used
``date.fromtimestamp(ms/1000)`` — the PROCESS-LOCAL zone. The live-matchup
runner is UTC, so every first pitch at/after 20:00 ET landed on tomorrow: the
period's last-night games fell past ``week_end`` and vanished, and the
(team, date, ordinal) key stopped lining up with ``fetch_completed_games``
(ET block dates), silently disabling the double-count guard for night games.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_matchup_dashboard as BMD

ET = ZoneInfo("America/New_York")


def _ms(y, m, d, hh, mm):
    return int(datetime(y, m, d, hh, mm, tzinfo=ET).timestamp() * 1000)


@pytest.fixture
def utc_process_clock(monkeypatch):
    """Force the process-local zone to UTC (the live-matchup runner) so the
    old `date.fromtimestamp` path is provably wrong here, not just on CI.
    Where tzset is unavailable (Windows) the fixture is a no-op: the ET
    conversion under test is zone-independent by construction."""
    if hasattr(time, "tzset"):
        monkeypatch.setenv("TZ", "UTC")
        time.tzset()
    yield
    if hasattr(time, "tzset"):
        os.environ.pop("TZ", None)
        time.tzset()


def test_late_et_first_pitch_stays_on_its_et_date(utc_process_clock):
    stamp = _ms(2026, 8, 30, 22, 10)               # Sun 10:10pm ET = Mon 02:10 UTC
    if hasattr(time, "tzset"):                      # the old bug, demonstrated on purpose
        assert date.fromtimestamp(stamp / 1000) == date(2026, 8, 31)   # noqa: DTZ012
    assert BMD.espn_game_date(stamp) == date(2026, 8, 30)


def test_last_night_of_the_window_is_not_dropped(utc_process_clock):
    week = (date(2026, 8, 24), date(2026, 8, 30))
    payload = {"settings": {"proTeams": [
        {"id": 10, "abbrev": "NYY", "proGamesByScoringPeriod": {"159": [
            {"id": 1, "date": _ms(2026, 8, 30, 13, 35), "homeProTeamId": 10, "awayProTeamId": 2},
            {"id": 2, "date": _ms(2026, 8, 30, 22, 10), "homeProTeamId": 10, "awayProTeamId": 2},
        ]}},
        {"id": 2, "abbrev": "BOS", "proGamesByScoringPeriod": {}},
    ]}}
    league = type("L", (), {"espn_request": type("R", (), {
        "get_pro_schedule": staticmethod(lambda: payload)})()})()
    games = BMD.fetch_espn_week_schedule(league, *week).get(147, [])
    assert [g["date"] for g in games] == ["2026-08-30", "2026-08-30"], games
