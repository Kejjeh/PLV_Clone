"""The cached fast path must refuse to guess, exactly like the live resolver.

WHY THIS EXISTS
`resolve_batter_id` is careful: it gates on KNOWN_COLLISIONS, guards ambiguity
(`nunique() > 1 -> None`), and treats a team hint as authoritative — "a team
hint that matches no candidate resolves to None rather than falling back to
position". Its own comment says taking `.iloc[0]` "would be exactly the silent
wrong-player bug this module exists to prevent".

`lookup_batter_id_cached` — the MORE heavily used path, since it front-runs the
live resolver — did all four of those things wrong:

  1. It took `.iloc[0]` off a multi-row match with no uniqueness check, despite
     its own docstring promising "exact player_name match IF UNIQUE".
  2. A team hint matching no cached row was silently DISCARDED, and an
     arbitrary row returned — so a caller who supplied the disambiguator got a
     confidently wrong answer.
  3. It compared teams with a raw `.upper()` instead of `team_key`. ESPN spells
     the A's "Oak" while the canonical key is "ATH", so `lookup("Max Muncy",
     team="Oak")` matched nothing, fell into (2), and returned the LAD Muncy.
     That is the canonical don't-do #10 bug, live.
  4. The accent/suffix-normalizing fallback folds "Luis Garcia Jr." and
     "Luis Garcia" onto one key, so it could silently span two real players.

Anything the cache cannot answer unambiguously now defers to
`resolve_batter_id`, which owns the collision gate. (Added 2026-08-27.)
"""
from __future__ import annotations

import pandas as pd
import pytest

from plv_clone.utils.name_match import (
    KNOWN_COLLISIONS,
    lookup_batter_id_cached,
    team_key,
)

MUNCY_LAD = 571970
MUNCY_ATH = 691777


@pytest.fixture
def muncy_cache() -> pd.DataFrame:
    """A cache holding BOTH Max Muncys — the canonical collision."""
    return pd.DataFrame([
        {"player_name": "Max Muncy", "team": "LAD", "batter_mlbam": MUNCY_LAD},
        {"player_name": "Max Muncy", "team": "ATH", "batter_mlbam": MUNCY_ATH},
    ])


def test_muncy_is_still_a_known_collision():
    """Guard the premise — if this drops out, the tests below prove nothing."""
    assert "Max Muncy" in KNOWN_COLLISIONS
    assert {c[2] for c in KNOWN_COLLISIONS["Max Muncy"]} == {MUNCY_LAD, MUNCY_ATH}


def test_espn_spelling_of_the_as_resolves_to_the_right_muncy(muncy_cache):
    """The headline bug: ESPN says "Oak", the canonical key is "ATH"."""
    assert team_key("Oak") == "ATH", "premise: team_key canonicalizes Oak->ATH"
    assert lookup_batter_id_cached(
        "Max Muncy", team="Oak", cache_df=muncy_cache) == MUNCY_ATH


@pytest.mark.parametrize("team,expected", [
    ("ATH", MUNCY_ATH),
    ("Oak", MUNCY_ATH),
    ("LAD", MUNCY_LAD),
])
def test_team_hint_selects_the_right_player(muncy_cache, team, expected):
    assert lookup_batter_id_cached(
        "Max Muncy", team=team, cache_df=muncy_cache) == expected


def test_ambiguous_name_with_no_hint_refuses_to_guess(muncy_cache):
    assert lookup_batter_id_cached("Max Muncy", cache_df=muncy_cache) is None


def test_team_hint_matching_nothing_refuses_to_guess(muncy_cache):
    """A supplied disambiguator that matches nothing must not be discarded."""
    assert lookup_batter_id_cached(
        "Max Muncy", team="NYY", cache_df=muncy_cache) is None


def test_suffix_and_accent_folding_does_not_merge_two_players():
    """_normalize folds "Luis Garcia Jr." and "Luís García" onto one key."""
    cache = pd.DataFrame([
        {"player_name": "Luis Garcia Jr.", "team": "WSH", "batter_mlbam": 111111},
        {"player_name": "Luís García", "team": "HOU", "batter_mlbam": 222222},
    ])
    assert lookup_batter_id_cached("Luis Garcia", cache_df=cache) is None


def test_unambiguous_name_still_resolves_from_the_cache():
    """The guard must not over-fire — a unique name is still a cache hit."""
    cache = pd.DataFrame([
        {"player_name": "Luis Garcia Jr.", "team": "WSH", "batter_mlbam": 111111},
        {"player_name": "Luís García", "team": "HOU", "batter_mlbam": 222222},
    ])
    assert lookup_batter_id_cached("Luis Garcia Jr.", cache_df=cache) == 111111


def test_duplicate_rows_for_one_player_are_not_ambiguous():
    """Same id twice (multi-season rows) is ONE player — still resolvable."""
    cache = pd.DataFrame([
        {"player_name": "Aaron Judge", "team": "NYY", "batter_mlbam": 592450},
        {"player_name": "Aaron Judge", "team": "NYY", "batter_mlbam": 592450},
    ])
    assert lookup_batter_id_cached("Aaron Judge", cache_df=cache) == 592450


def test_accent_fallback_still_works_for_a_single_player():
    """The accent leg exists so ascii ESPN spellings find accented cache rows."""
    cache = pd.DataFrame([
        {"player_name": "José Ramírez", "team": "CLE", "batter_mlbam": 608070},
    ])
    assert lookup_batter_id_cached("Jose Ramirez", cache_df=cache) == 608070
