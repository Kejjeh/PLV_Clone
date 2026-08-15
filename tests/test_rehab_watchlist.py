"""Tests for lib/rehab_watchlist — auto-discovered IL players + FA watchlist,
merged into one master rehab-check list (built TDD 2026-08-15).

WHY THIS EXISTS. The prior rehab-check routines hardcoded a name list at
creation time (Pivetta/Glasnow/Rodón, Cruz/Garcia/Martinez/Palencia) — stale
the moment anyone else on the roster lands on the IL. This module owns the
auto-discovery seam: who currently needs a rehab check, derived live from the
roster, not from a name list written once and never revisited.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

RW = pytest.importorskip("scripts.xfp.lib.rehab_watchlist")


def test_discover_il_players_finds_my_team_players_on_the_il():
    roster = [
        {"player_name": "Nick Pivetta", "team_name": "New York Ligers", "injury_status": "SIXTY_DAY_DL"},
        {"player_name": "Corbin Carroll", "team_name": "New York Ligers", "injury_status": "ACTIVE"},
    ]
    out = RW.discover_il_players(roster, my_team_name="New York Ligers")
    assert [p["player_name"] for p in out] == ["Nick Pivetta"]


def test_discover_il_players_excludes_day_to_day_and_other_teams():
    roster = [
        # day-to-day isn't a rehab case — gotcha #7, BE/day-to-day still plays
        {"player_name": "Vladimir Guerrero Jr.", "team_name": "New York Ligers", "injury_status": "DAY_TO_DAY"},
        # correct status, wrong team — not mine to track
        {"player_name": "Garrett Crochet", "team_name": "Team Solomon", "injury_status": "SIXTY_DAY_DL"},
    ]
    out = RW.discover_il_players(roster, my_team_name="New York Ligers")
    assert out == []


def test_build_rehab_master_list_tags_source_and_merges():
    il_players = [{"player_name": "Nick Pivetta", "team_name": "New York Ligers", "injury_status": "SIXTY_DAY_DL"}]
    fa_watchlist = [{"player_name": "Oneil Cruz", "note": "hand fracture"}]
    out = RW.build_rehab_master_list(il_players, fa_watchlist)
    assert {"player_name": "Nick Pivetta", "source": "mine"} in [
        {"player_name": p["player_name"], "source": p["source"]} for p in out]
    assert {"player_name": "Oneil Cruz", "source": "fa_watchlist"} in [
        {"player_name": p["player_name"], "source": p["source"]} for p in out]
    assert len(out) == 2


# ── once a watched player is reinstated, the checker pivots from rehab-stage
# tracking to real playing-time tracking (the Oneil Cruz fold-in) ──────────

def test_needs_playing_time_mode_true_once_activated():
    assert RW.needs_playing_time_mode("activated") is True


def test_needs_playing_time_mode_false_while_still_out():
    assert RW.needs_playing_time_mode("on_rehab") is False
    assert RW.needs_playing_time_mode("on_il") is False
