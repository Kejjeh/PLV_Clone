"""Tests for the name-resolution cache lookup helper."""
from __future__ import annotations

import pandas as pd
import pytest

from plv_clone.utils import name_match
from plv_clone.utils.name_match import (
    KNOWN_COLLISIONS,
    lookup_batter_id_cached,
    resolve_batter_id,
    _reset_cache_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_module_cache():
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


def _fake_cache() -> pd.DataFrame:
    """Hand-built cache covering a non-collision + the Max Muncy collision."""
    return pd.DataFrame([
        {
            "player_name": "Manny Machado", "team": "SD", "position": "3B",
            "batter_mlbam": 592518, "is_known_collision": False,
            "resolution_status": "resolved", "built_at": "2026-05-24T00:00:00",
        },
        {
            "player_name": "Max Muncy", "team": "LAD", "position": "3B",
            "batter_mlbam": 571970, "is_known_collision": True,
            "resolution_status": "resolved", "built_at": "2026-05-24T00:00:00",
        },
        {
            "player_name": "Max Muncy", "team": "ATH", "position": "SS",
            "batter_mlbam": 691777, "is_known_collision": True,
            "resolution_status": "resolved", "built_at": "2026-05-24T00:00:00",
        },
    ])


def test_lookup_non_colliding_matches_resolve_batter_id():
    """A non-collision name should return the same ID as the live resolver."""
    df = _fake_cache()
    cached = lookup_batter_id_cached("Manny Machado", team="SD", cache_df=df)
    assert cached == 592518


def test_lookup_max_muncy_disambiguates_by_team():
    """The canonical collision case: LAD → 571970, ATH → 691777."""
    df = _fake_cache()
    assert lookup_batter_id_cached("Max Muncy", team="LAD", cache_df=df) == 571970
    assert lookup_batter_id_cached("Max Muncy", team="ATH", cache_df=df) == 691777
    # The collision is curated:
    assert "Max Muncy" in KNOWN_COLLISIONS


def test_cache_miss_falls_back_cleanly(monkeypatch):
    """An unknown name shouldn't crash — falls through to resolve_batter_id.

    We monkeypatch the live resolver so the test doesn't depend on the
    multiyr CSV being readable.
    """
    df = _fake_cache()

    calls = []

    def _fake_resolve(name, *, team=None, position=None, **kw):
        calls.append((name, team, position))
        return None

    monkeypatch.setattr(name_match, "resolve_batter_id", _fake_resolve)
    result = lookup_batter_id_cached(
        "Nonexistent Player", team="XYZ", cache_df=df
    )
    assert result is None
    assert calls == [("Nonexistent Player", "XYZ", None)]
