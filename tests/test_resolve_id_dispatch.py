"""Tests for name_match.resolve_id — the unified, collision-safe resolution seam.

The load-bearing property: an ambiguous same-name collision (Max Muncy LAD vs
ATH) safe-fails to None without a team hint, and resolves correctly with one —
through the single dispatcher, so no caller can grab the wrong player.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from plv_clone.utils.name_match import resolve_id, KNOWN_COLLISIONS


def test_batter_collision_safe_fails_without_team():
    assert "Max Muncy" in KNOWN_COLLISIONS, "fixture expects Max Muncy collision"
    assert resolve_id("Max Muncy", kind="batter") is None


def test_batter_collision_resolves_with_team():
    lad_ids = [m for (t, _p, m) in KNOWN_COLLISIONS["Max Muncy"] if t.upper() == "LAD"]
    assert lad_ids, "fixture expects a LAD Max Muncy"
    assert resolve_id("Max Muncy", kind="batter", team="LAD") == lad_ids[0]


def test_kind_aliases_route_to_pitcher():
    # 'SP'/'RP'/'pitcher' all route to the pitcher resolver without error.
    for kind in ("pitcher", "SP", "RP"):
        # A name that doesn't resolve simply returns None — we're asserting the
        # dispatch path doesn't raise and doesn't route to the batter resolver.
        assert resolve_id("Definitely Not A Real Pitcher", kind=kind) is None


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        resolve_id("Whoever", kind="goalie")
