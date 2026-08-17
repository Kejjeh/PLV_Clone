"""Signal P — Short-Hold Churn Re-scan — issue #19.

CLAUDE.md gotcha #16 documents this as shipped and run by default, closing
the gap Signal D (prior-YEAR draft history only) doesn't cover: a player
added and dropped within 48h by any team, re-checked 3+ weeks later
against current rp3/rh3/rprs2 rank. It never actually existed in
run_fa_monitor.py — this implements and tests it for real.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import run_fa_monitor as m  # noqa: E402


class _Player:
    def __init__(self, name):
        self.name = name


class _Team:
    def __init__(self, name):
        self.team_name = name


class _Activity:
    def __init__(self, date_ms, actions):
        self.date = date_ms
        self.actions = actions  # list of (team, action_str, player)


class _FakeLeague:
    def __init__(self, activities):
        self._activities = activities

    def recent_activity(self, size=300):
        return self._activities


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _models_with(name, rank=4):
    """rp3/rh3/rprs2-shaped frames where `name` ranks well in rprs2 only
    (the Varland pattern: a reliever)."""
    empty_rp3 = pd.DataFrame({"player_name": ["Nobody"], "rank": [999]})
    empty_rh3 = pd.DataFrame({"player_name": ["Nobody"], "rank": [999]})
    rprs2 = pd.DataFrame({"name_api": [name], "rank": [rank]})
    return empty_rp3, empty_rh3, rprs2


def test_short_hold_add_then_drop_within_48h_surfaces_when_still_fa():
    """Canonical Varland pattern: added, dropped ~1 day later, still a FA
    3+ weeks on, now ranks well — must surface."""
    now = datetime.now(timezone.utc)
    add_time = now - timedelta(weeks=4)
    drop_time = add_time + timedelta(hours=20)
    team = _Team("Some Team")
    player = _Player("Louis Varland")
    activities = [
        _Activity(_ms(add_time), [(team, "WAIVER ADDED", player)]),
        _Activity(_ms(drop_time), [(team, "DROPPED", player)]),
    ]
    league = _FakeLeague(activities)
    rp3, rh3, rprs2 = _models_with("Louis Varland", rank=4)

    results = m.signal_p_short_hold_churn(
        league, rp3, rh3, rprs2, is_fa=lambda name: True)

    assert len(results) == 1
    assert results[0]["signal"] == "P"
    assert results[0]["player"] == "Louis Varland"
    assert results[0]["best_rank"] == 4


def test_churn_too_recent_does_not_surface_yet():
    """The 3-week wait matters — real signal hasn't had time to show."""
    now = datetime.now(timezone.utc)
    add_time = now - timedelta(days=2)
    drop_time = add_time + timedelta(hours=10)
    team = _Team("Some Team")
    player = _Player("Too Soon Guy")
    activities = [
        _Activity(_ms(add_time), [(team, "FA ADDED", player)]),
        _Activity(_ms(drop_time), [(team, "DROPPED", player)]),
    ]
    league = _FakeLeague(activities)
    rp3, rh3, rprs2 = _models_with("Too Soon Guy", rank=1)

    results = m.signal_p_short_hold_churn(
        league, rp3, rh3, rprs2, is_fa=lambda name: True)
    assert results == []


def test_currently_rostered_player_excluded_even_if_pattern_matches():
    """If someone re-added him since, he's not a pickup opportunity."""
    now = datetime.now(timezone.utc)
    add_time = now - timedelta(weeks=4)
    drop_time = add_time + timedelta(hours=5)
    team = _Team("Some Team")
    player = _Player("Now Rostered")
    activities = [
        _Activity(_ms(add_time), [(team, "FA ADDED", player)]),
        _Activity(_ms(drop_time), [(team, "DROPPED", player)]),
    ]
    league = _FakeLeague(activities)
    rp3, rh3, rprs2 = _models_with("Now Rostered", rank=1)

    results = m.signal_p_short_hold_churn(
        league, rp3, rh3, rprs2, is_fa=lambda name: False)
    assert results == []


def test_hold_longer_than_48h_is_not_short_hold_churn():
    """A normal multi-week roster stint isn't the churn pattern — only a
    genuine <=48h same-day/next-day scouting look counts."""
    now = datetime.now(timezone.utc)
    add_time = now - timedelta(weeks=5)
    drop_time = add_time + timedelta(days=10)
    team = _Team("Some Team")
    player = _Player("Normal Stint")
    activities = [
        _Activity(_ms(add_time), [(team, "FA ADDED", player)]),
        _Activity(_ms(drop_time), [(team, "DROPPED", player)]),
    ]
    league = _FakeLeague(activities)
    rp3, rh3, rprs2 = _models_with("Normal Stint", rank=1)

    results = m.signal_p_short_hold_churn(
        league, rp3, rh3, rprs2, is_fa=lambda name: True)
    assert results == []


def test_no_longer_ranking_well_does_not_surface():
    now = datetime.now(timezone.utc)
    add_time = now - timedelta(weeks=4)
    drop_time = add_time + timedelta(hours=5)
    team = _Team("Some Team")
    player = _Player("Replacement Level")
    activities = [
        _Activity(_ms(add_time), [(team, "FA ADDED", player)]),
        _Activity(_ms(drop_time), [(team, "DROPPED", player)]),
    ]
    league = _FakeLeague(activities)
    rp3, rh3, rprs2 = _models_with("Replacement Level", rank=500)

    results = m.signal_p_short_hold_churn(
        league, rp3, rh3, rprs2, is_fa=lambda name: True)
    assert results == []


def test_wired_into_sig_labels():
    """Regression guard for the actual documentation-vs-code gap: P must
    be a real, labeled signal, not just a function that exists."""
    assert "P" in m._SIG_LABELS


def test_wired_into_default_signals_dispatch():
    """P must be in main()'s default --signals list, or the CLAUDE.md
    claim ('run as part of the regular /fa-monitor sweep') stays false
    even with the function implemented."""
    import inspect
    src = inspect.getsource(m.main)
    default_line = next(l for l in src.splitlines() if "--signals" in l and "default" in l)
    assert "P" in default_line, f"Signal P missing from --signals default: {default_line!r}"
