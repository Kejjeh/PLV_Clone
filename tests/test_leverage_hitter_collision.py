"""resolve_player_mlbam must disambiguate a same-name HITTER by team.

Defect (found 2026-09-18): the engine's resolver gated only pitchers through
the collision table; hitters went to the first-loaded-wins name cache, so
both Max Muncys resolved to whichever row the cache met first. That id keys
the MC draws AND the boxscore game-log join, so the wrong man's history drove
the other's simulated week.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import scripts.xfp.lib.leverage_engine as E  # tracked source: a hard import, never a guard


class _P:
    def __init__(self, name, pos, team):
        self.name, self.position, self.proTeam = name, pos, team


def test_both_muncys_resolve_to_their_own_ids(monkeypatch):
    # the name caches must NOT be consulted for a listed collision
    monkeypatch.setattr(E, "player_mlbam_lookup", lambda name: 571970)
    monkeypatch.setattr(E, "_resolve_mlbam_via_api", lambda name: None)
    assert E.resolve_player_mlbam(_P("Max Muncy", "3B", "ATH")) == 691777
    assert E.resolve_player_mlbam(_P("Max Muncy", "3B", "LAD")) == 571970


def test_non_collision_hitter_uses_the_cache(monkeypatch):
    monkeypatch.setattr(E, "player_mlbam_lookup", lambda name: 424242)
    assert E.resolve_player_mlbam(_P("Ordinary Bat", "OF", "NYY")) == 424242


# ── review repair 2026-09-19: a listed collision that cannot be settled STAYS unresolved ──

def _forbid(monkeypatch):
    """Any fall-through to the name cache / API is a contract violation."""
    def boom(name, *a, **k):
        raise AssertionError(f"forbidden fallback lookup for {name!r}")
    monkeypatch.setattr(E, "player_mlbam_lookup", boom)
    monkeypatch.setattr(E, "_resolve_mlbam_via_api", boom)


@pytest.mark.parametrize("team", [None, "", "ZZZ"])
def test_collision_with_missing_or_unknown_team_is_none_not_a_guess(monkeypatch, team):
    _forbid(monkeypatch)
    assert E.resolve_player_mlbam(_P("Max Muncy", "3B", team)) is None


def test_both_muncys_still_resolve_with_fallbacks_forbidden(monkeypatch):
    _forbid(monkeypatch)
    assert E.resolve_player_mlbam(_P("Max Muncy", "3B", "ATH")) == 691777
    assert E.resolve_player_mlbam(_P("Max Muncy", "3B", "LAD")) == 571970
