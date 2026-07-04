"""Tests for lib/rating_arc.compute_arcs — the in-season rating-arc owner.

Pure-function tests (injected snapshot rows, no statcast/network). Locks:
riser/faller tagging on the validated key pillar (SP STUFF / hitter CONTACT),
the lookback anchor selection, and the min-gap guard.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

from lib.rating_arc import compute_arcs, ARC_RISE, KEY_PILLAR


def _snap(pid, date, stuff, overall=55, mov=50, ctrl=50, name="Arm Guy"):
    return {"pitcher": pid, "player_name": name, "date": date,
            "OVERALL": overall, "STUFF": stuff, "MOVEMENT": mov, "CONTROL": ctrl}


def test_sp_riser_on_stuff_delta():
    snaps = [_snap(1, "2026-06-01", 52), _snap(1, "2026-06-15", 55),
             _snap(1, "2026-07-01", 59)]
    arcs = compute_arcs(snaps, "sp", lookback_days=28)
    assert len(arcs) == 1
    a = arcs[0]
    assert a["key_pillar"] == "STUFF" == KEY_PILLAR["sp"]
    assert a["date_then"] == "2026-06-01"       # closest to latest-28d
    assert a["key_delta"] == 7 >= ARC_RISE
    assert a["arc"] == "RISER"


def test_faller_and_flat():
    snaps = [_snap(2, "2026-06-01", 60), _snap(2, "2026-07-01", 53),
             _snap(3, "2026-06-01", 50), _snap(3, "2026-07-01", 52)]
    arcs = {a["pitcher"]: a for a in compute_arcs(snaps, "sp")}
    assert arcs[2]["arc"] == "FALLER"
    assert arcs[3]["arc"] == "FLAT"


def test_min_gap_guard_skips_new_players():
    """A player whose only earlier snapshot is <14d old has no meaningful arc."""
    snaps = [_snap(4, "2026-06-25", 50), _snap(4, "2026-07-01", 62)]
    assert compute_arcs(snaps, "sp", lookback_days=28, min_gap_days=14) == []


def test_hitter_key_pillar_is_contact():
    snaps = [{"batter": 9, "player_name": "Bat Guy", "date": "2026-06-01",
              "OVERALL": 50, "CONTACT": 48, "POWER": 55, "DISCIPLINE": 50, "SB": 50},
             {"batter": 9, "player_name": "Bat Guy", "date": "2026-07-01",
              "OVERALL": 55, "CONTACT": 56, "POWER": 55, "DISCIPLINE": 50, "SB": 50}]
    arcs = compute_arcs(snaps, "hitter")
    assert arcs[0]["key_pillar"] == "CONTACT"
    assert arcs[0]["key_delta"] == 8
    assert arcs[0]["arc"] == "RISER"


def test_sorted_by_key_delta_desc():
    snaps = [_snap(1, "2026-06-01", 50), _snap(1, "2026-07-01", 52),
             _snap(2, "2026-06-01", 50), _snap(2, "2026-07-01", 60)]
    arcs = compute_arcs(snaps, "sp")
    assert [a["pitcher"] for a in arcs] == [2, 1]
