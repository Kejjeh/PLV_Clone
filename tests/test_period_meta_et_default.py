"""period_meta resolvers default `today` to the EASTERN date, not the process clock.

Defect (found 2026-09-18): the default was ``date.today()`` (UTC in the cloud
container and on hosted runners). Callers that omitted ``today=`` —
run_roster_audit, lineup_optimizer, build_period_xfp_board,
weekly_cap_check --period — resolved the week on the UTC calendar, so from
20:00 ET on a Sunday the window rolled to NEXT week. Fixed at the owner so
every caller is covered.
"""
from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from lib import period_meta as PM


def test_today_et_sunday_night_stays_sunday():
    # Monday 2026-09-21 01:30 UTC == Sunday 2026-09-20 21:30 ET
    assert PM.today_et(datetime(2026, 9, 21, 1, 30, tzinfo=UTC)) == date(2026, 9, 20)


def test_today_et_daytime_agrees_with_utc():
    assert PM.today_et(datetime(2026, 9, 21, 15, 0, tzinfo=UTC)) == date(2026, 9, 21)


def test_resolver_default_uses_the_et_clock(monkeypatch):
    monkeypatch.setattr(PM, "today_et", lambda now=None: date(2026, 9, 20))   # Sunday ET
    league = SimpleNamespace(currentMatchupPeriod=21,
                             settings=SimpleNamespace(matchup_periods={"21": [23]}))
    pm = PM.resolve_period_meta(league, 21)          # no today= — the defaulted path
    assert pm["week_start"] == date(2026, 9, 14) and pm["week_end"] == date(2026, 9, 20)
