"""A cache keyed on id() must keep its subject alive, or the key lies.

WHY THIS EXISTS
`LeagueState`'s per-process TTL cache keys frames as `(frame_name,
id(league))`, with a comment saying that is "so injected test doubles never
share". That reasoning holds only while both league objects are ALIVE.
CPython reuses an address the moment the previous occupant is collected, so a
league that went out of scope hands its id — and therefore its cached roster —
to an unrelated league created within the 300s TTL.

Measured before the fix, over 400 LeagueState round-trips on distinct fake
leagues: 44 ids reused and **202 of 400 calls returned another league's
roster**. That is not a leak or a slowdown; it is `my_roster()` confidently
returning somebody else's players, which is exactly what don't-do #11 exists
to prevent ("never label a player as yours without a live roster call").

The fix keeps the league referenced for the entry's lifetime, so the address
cannot be recycled while the key that names it is still in use.
(Added 2026-08-27.)
"""
from __future__ import annotations

import gc
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import plv_clone.league_state as ls_mod  # noqa: E402
from plv_clone.league_state import LeagueState, clear_ttl_cache  # noqa: E402
from test_league_state import _FakeLeague, _FakePlayer, _FakeTeam  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_ttl_cache()
    yield
    clear_ttl_cache()


def _roster_for(tag: str) -> tuple[list[str], int]:
    team = _FakeTeam(1, "New York Ligers", "josh", [_FakePlayer(name=tag)])
    league = _FakeLeague(teams=[team], free_agents=[])
    names = LeagueState(league=league).my_roster()["player_name"].tolist()
    return names, id(league)


def test_a_recycled_address_never_serves_another_leagues_roster():
    """The regression, at the scale that exposed it."""
    wrong = []
    for i in range(150):
        tag = f"P{i}"
        names, _ = _roster_for(tag)
        if names != [tag]:
            wrong.append((i, tag, names))
        gc.collect()
    assert not wrong, (
        f"{len(wrong)} of 150 calls returned another league's roster — the "
        f"id() cache key was recycled. First: {wrong[:3]}"
    )


def test_distinct_live_leagues_still_do_not_share():
    """The original intent of the id() key must survive the fix."""
    a_team = _FakeTeam(1, "New York Ligers", "josh", [_FakePlayer(name="A")])
    b_team = _FakeTeam(1, "New York Ligers", "josh", [_FakePlayer(name="B")])
    league_a = _FakeLeague(teams=[a_team], free_agents=[])
    league_b = _FakeLeague(teams=[b_team], free_agents=[])
    assert LeagueState(league=league_a).my_roster()["player_name"].tolist() == ["A"]
    assert LeagueState(league=league_b).my_roster()["player_name"].tolist() == ["B"]


def test_the_same_league_is_still_cached():
    """The fix must not defeat caching — that is the whole point of the key."""
    team = _FakeTeam(1, "New York Ligers", "josh", [_FakePlayer(name="Cached")])
    league = _FakeLeague(teams=[team], free_agents=[])
    state = LeagueState(league=league)
    first = state.my_roster()
    team.roster = [_FakePlayer(name="Changed Underneath")]
    second = state.my_roster()
    assert second["player_name"].tolist() == first["player_name"].tolist(), (
        "a second call within the TTL should be served from cache"
    )


def test_fresh_bypasses_the_cache():
    team = _FakeTeam(1, "New York Ligers", "josh", [_FakePlayer(name="Before")])
    league = _FakeLeague(teams=[team], free_agents=[])
    state = LeagueState(league=league)
    state.my_roster()
    team.roster = [_FakePlayer(name="After")]
    assert state.my_roster(fresh=True)["player_name"].tolist() == ["After"]


def test_expired_entries_are_swept_rather_than_accumulating():
    """Each entry now pins a League object, so dead ones must not pile up."""
    original = ls_mod.CACHE_TTL_SECONDS
    try:
        ls_mod.CACHE_TTL_SECONDS = 0.05

        class _Owner:
            pass

        for i in range(30):
            ls_mod._cache_put(("probe", i), pd.DataFrame([{"a": i}]), owner=_Owner())
        assert len(ls_mod._TTL_CACHE) == 30
        time.sleep(0.1)
        ls_mod._cache_put(("probe", 999), pd.DataFrame([{"a": 1}]), owner=_Owner())
        assert len(ls_mod._TTL_CACHE) == 1, (
            f"expired entries were not swept: {len(ls_mod._TTL_CACHE)} remain"
        )
    finally:
        ls_mod.CACHE_TTL_SECONDS = original
