"""The FA pool is pulled whole and filtered locally — never per-position.

WHY THIS FILE EXISTS
`feedback_fa_pool_size_cap.md` / don't-do #6: a per-position
`league.free_agents(position_id=..., size=N)` call silently drops low-owned
high-FP candidates. `LeagueState.available_fa` gets this right and bakes
size=2000 with a manual post-filter.

`app/espn_connector.get_free_agents` did the opposite (issue #74):

  * it pushed `position_id` to ESPN, with the correct manual filter present
    only as a fallback for older espn-api versions, and
  * it defaulted to `size=200`, so any caller that omitted the argument got a
    200-deep pool.

Neither was live — no caller passed a position, and app/dashboard passed
size=2000 explicitly — which is exactly why it survived. (Fixed 2026-08-27.)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

ec = pytest.importorskip("espn_connector")


class _P:
    def __init__(self, name, position, owned=1.0):
        self.name = name
        self.position = position
        self.proTeam = "NYY"
        self.percent_owned = owned


class _League:
    """Records how free_agents was called."""

    def __init__(self, players):
        self._players = players
        self.calls: list[dict] = []

    def free_agents(self, **kwargs):
        self.calls.append(kwargs)
        return self._players


@pytest.fixture
def league(monkeypatch):
    lg = _League([
        _P("Ace Starter", "SP"),
        _P("Deep Cut", "SP", owned=0.4),
        _P("Some Bat", "OF"),
    ])
    monkeypatch.setattr(ec, "_get_league", lambda: lg)
    return lg


def test_position_is_never_pushed_to_espn(league):
    """position_id is the banned form — the filter must be local."""
    ec.get_free_agents(position="SP")
    assert league.calls, "free_agents was never called"
    for call in league.calls:
        assert "position_id" not in call, (
            f"position pushed to ESPN as {call} — this silently drops "
            f"low-owned high-FP candidates (don't-do #6)")
        assert "position" not in call


def test_the_filter_still_works_locally(league):
    df = ec.get_free_agents(position="SP")
    assert set(df["player_name"]) == {"Ace Starter", "Deep Cut"}


def test_no_position_returns_everyone(league):
    assert len(ec.get_free_agents()) == 3


def test_the_default_pool_is_the_full_pool(league):
    """A caller that omits `size` must not silently get a shallow pool."""
    ec.get_free_agents()
    assert league.calls[0]["size"] == ec.FA_POOL_SIZE
    assert ec.FA_POOL_SIZE >= 2000, (
        f"FA_POOL_SIZE is {ec.FA_POOL_SIZE}; a capped pool drops low-owned "
        f"high-FP candidates")


def test_an_explicit_size_is_still_honoured(league):
    ec.get_free_agents(size=50)
    assert league.calls[0]["size"] == 50
