"""Tests for pitcher_role.detect_pitcher_role.

The load-bearing case: a dual-eligible pitcher (SP and RP both in
eligible_slots) whose ESPN .position tag is stale ('RP') but who is actually
starting (Detmers 2026). The module must own resolution and decide on real
gamesStarted WITHOUT the caller passing an id — i.e. detect_pitcher_role(player)
with no mlbam_id must NOT return the stale 'RP' tag.

The gamesStarted source and the name->id resolver are injected so the
dual-eligible path is exercised offline (no MLB Stats API, no CSV).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from scripts.xfp.lib.pitcher_role import detect_pitcher_role


class _Player:
    def __init__(self, name, position, eligibleSlots, proTeam=None):
        self.name = name
        self.position = position
        self.eligibleSlots = eligibleSlots
        self.proTeam = proTeam


def test_sp_only_eligible_short_circuits():
    assert detect_pitcher_role(_Player("Ace", "SP", ["SP"])) == "SP"


def test_rp_only_eligible_short_circuits():
    assert detect_pitcher_role(_Player("Closer", "RP", ["RP"])) == "RP"


def test_dual_eligible_resolves_to_sp_without_caller_passing_id():
    """The regression. ESPN says position='RP', but dual-eligible + 15 GS = SP.
    No mlbam_id passed — the module must resolve it itself, not use the tag."""
    detmers = _Player("Reid Detmers", "RP", ["SP", "RP"], proTeam="LAA")
    role = detect_pitcher_role(
        detmers,
        id_resolver=lambda name, team: 672282,      # offline: name -> id
        gs_lookup=lambda pid, season: "SP",         # offline: 15 GS -> SP
    )
    assert role == "SP"


def test_dual_eligible_with_explicit_id_still_works():
    detmers = _Player("Reid Detmers", "RP", ["SP", "RP"])
    role = detect_pitcher_role(
        detmers, mlbam_id=672282, gs_lookup=lambda pid, season: "SP"
    )
    assert role == "SP"


def test_dual_eligible_unresolvable_falls_back_to_position_tag():
    """When resolution is exhausted, the ESPN tag is the documented last resort."""
    nobody = _Player("Rookie Nobody", "RP", ["SP", "RP"])
    role = detect_pitcher_role(nobody, id_resolver=lambda name, team: None)
    assert role == "RP"


def test_df_row_input_dual_eligible():
    """Works on a dict/Series row, not just ESPN player objects."""
    row = {"player_name": "Reid Detmers", "position": "RP",
           "eligible_slots": ["SP", "RP"], "pro_team": "LAA"}
    role = detect_pitcher_role(
        row,
        id_resolver=lambda name, team: 672282,
        gs_lookup=lambda pid, season: "SP",
    )
    assert role == "SP"
