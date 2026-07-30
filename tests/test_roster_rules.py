"""Tests for lib/roster_rules — legality of a proposed roster change (C3).

The optimizer searches thousands of permutations and will find and exploit any
gap in these rules, so each one is pinned. The 4-RP floor in particular is a
STANDING OWNER RULE (2026-07-18), not a league constraint: violating it produces
advice Josh will not take, which is worse than producing none.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

RR = pytest.importorskip("scripts.xfp.lib.roster_rules")


def _p(name, bucket, pos, elig=None, on_il=False, mlbam=None):
    return {"name": name, "mlbam": mlbam, "bucket": bucket, "espn_pos": pos,
            "eligible": set(elig or [pos]), "on_il": on_il, "slot": None}


def _roster(n_h=13, n_sp=9, n_rp=4, with_catcher=True):
    r = []
    for i in range(n_h - (1 if with_catcher else 0)):
        r.append(_p(f"H{i}", "H", "OF", ["OF"], mlbam=1000 + i))
    if with_catcher:
        r.append(_p("Catch", "H", "C", ["C"], mlbam=1999))
    for i in range(n_sp):
        r.append(_p(f"SP{i}", "SP", "SP", ["SP"], mlbam=2000 + i))
    for i in range(n_rp):
        r.append(_p(f"RP{i}", "RP", "RP", ["RP"], mlbam=3000 + i))
    return r


# ── league constants ─────────────────────────────────────────────────────────

def test_roster_spec_matches_the_league():
    assert (RR.ACTIVE_HITTERS, RR.ACTIVE_PITCHERS, RR.BENCH, RR.IL_SLOTS) == (13, 9, 4, 3)
    assert RR.ROSTER_TOTAL == 29
    assert RR.RP_FLOOR == 4


# ── the 4-RP floor (standing owner rule) ─────────────────────────────────────

def test_cannot_drop_an_rp_below_the_floor():
    r = _roster(n_rp=4)
    probs = RR.check_swap(r, add=_p("FA SP", "SP", "SP"), drop=r[-1])
    assert any("floor" in p for p in probs)


def test_rp_for_rp_at_the_floor_is_legal():
    """The standing rule permits exactly one thing: an RP-for-RP upgrade."""
    r = _roster(n_rp=4)
    assert RR.check_swap(r, add=_p("FA RP", "RP", "RP"), drop=r[-1]) == []


def test_dropping_an_rp_above_the_floor_is_fine():
    r = _roster(n_rp=5)
    assert RR.check_swap(r, add=_p("FA SP", "SP", "SP"), drop=r[-1]) == []


def test_the_floor_message_names_the_rule_so_the_reason_is_actionable():
    r = _roster(n_rp=4)
    probs = RR.check_swap(r, add=_p("FA H", "H", "OF"), drop=r[-1])
    assert any("2026-07-18" in p for p in probs), probs


# ── positional coverage ──────────────────────────────────────────────────────

def test_cannot_drop_the_last_catcher():
    r = _roster()
    catcher = next(p for p in r if p["espn_pos"] == "C")
    probs = RR.check_swap(r, add=_p("FA OF", "H", "OF"), drop=catcher)
    assert any("nobody eligible at C" in p for p in probs)


def test_dropping_a_catcher_is_fine_when_a_second_one_exists():
    r = _roster()
    r.append(_p("Catch2", "H", "C", ["C"], mlbam=1998))
    catcher = next(p for p in r if p["name"] == "Catch")
    assert not any("eligible at C" in p
                   for p in RR.check_swap(r, add=_p("FA OF", "H", "OF"), drop=catcher))


def test_of_coverage_accepts_lf_cf_rf():
    r = [_p("Only OF", "H", "CF", ["CF"], mlbam=1)]
    assert RR._covers(r, "OF") == 1


# ── bucket sufficiency ───────────────────────────────────────────────────────

def test_cannot_fall_below_thirteen_hitters():
    r = _roster(n_h=13)
    probs = RR.check_swap(r, add=_p("FA SP", "SP", "SP"),
                          drop=next(p for p in r if p["bucket"] == "H"))
    assert any("13 active hitter slots" in p for p in probs)


def test_cannot_fall_below_nine_pitchers():
    r = _roster(n_sp=5, n_rp=4)          # exactly 9
    probs = RR.check_swap(r, add=_p("FA H", "H", "OF"),
                          drop=next(p for p in r if p["bucket"] == "SP"))
    assert any("9 active pitcher slots" in p for p in probs)


# ── SP cap precondition ──────────────────────────────────────────────────────

def test_sp_add_with_no_cap_remaining_is_pointless():
    r = _roster(n_sp=10)
    probs = RR.check_swap(r, add=_p("FA SP", "SP", "SP"),
                          drop=next(p for p in r if p["bucket"] == "SP"),
                          cap_remaining=0)
    assert any("cap" in p for p in probs)


def test_sp_add_with_cap_remaining_is_allowed():
    r = _roster(n_sp=10)
    probs = RR.check_swap(r, add=_p("FA SP", "SP", "SP"),
                          drop=next(p for p in r if p["bucket"] == "SP"),
                          cap_remaining=3)
    assert not any("cap" in p for p in probs)


# ── lineup capacity (guards a real engine limitation) ────────────────────────

def test_capacity_flags_an_add_whose_games_cannot_be_played():
    """13 slots x 4 days = 52. Thirteen 4-game hitters already want 52, so a
    14th cannot play at all — yet the MC engine would credit him fully."""
    why = RR.lineup_capacity_problem(n_hitters_after=14, hitter_games_after=56,
                                     days_remaining=4)
    assert why and "could not be played" in why


def test_capacity_allows_an_add_that_fits_real_headroom():
    """Off-days create genuine room: 48 games used of 52 leaves exactly 4."""
    assert RR.lineup_capacity_problem(n_hitters_after=14, hitter_games_after=52,
                                      days_remaining=4) is None


def test_capacity_is_skipped_when_days_remaining_is_unknown():
    assert RR.lineup_capacity_problem(n_hitters_after=99, hitter_games_after=999,
                                      days_remaining=0) is None


def test_check_swap_wires_the_capacity_check_for_hitter_adds():
    r = _roster(n_h=13)
    hg = {p["mlbam"]: 4 for p in r if p["bucket"] == "H"}
    hg["FA Bat"] = 4
    probs = RR.check_swap(
        r, add=_p("FA Bat", "H", "OF"),
        drop=next(p for p in r if p["bucket"] == "SP"),
        hitter_games=hg, days_remaining=4)
    assert any("lineup slots exist" in p for p in probs), probs


def test_capacity_does_not_fire_for_a_pitcher_add():
    r = _roster()
    hg = {p["mlbam"]: 4 for p in r if p["bucket"] == "H"}
    probs = RR.check_swap(r, add=_p("FA SP", "SP", "SP"),
                          drop=next(p for p in r if p["bucket"] == "SP"),
                          hitter_games=hg, days_remaining=4)
    assert not any("lineup slots" in p for p in probs)


# ── mechanics ────────────────────────────────────────────────────────────────

def test_apply_swap_is_pure():
    r = _roster()
    before = len(r)
    RR.apply_swap(r, add=_p("X", "H", "OF"), drop=r[0])
    assert len(r) == before


def test_apply_swap_preserves_roster_size_on_a_one_for_one():
    r = _roster()
    after = RR.apply_swap(r, add=_p("X", "H", "OF"), drop=r[0])
    assert len(after) == len(r)


def test_dropping_someone_not_on_the_roster_raises():
    with pytest.raises(RR.IllegalMove):
        RR.apply_swap(_roster(), drop=_p("Ghost", "H", "OF", mlbam=99999))


def test_check_swap_reports_a_nonexistent_drop_rather_than_raising():
    probs = RR.check_swap(_roster(), drop=_p("Ghost", "H", "OF", mlbam=99999))
    assert probs and "not on the roster" in probs[0]


def test_il_drop_is_flagged_as_not_freeing_an_active_slot():
    r = _roster()
    r.append(_p("Stashed", "SP", "SP", on_il=True, mlbam=4000))
    probs = RR.check_swap(r, drop=r[-1])
    assert any("frees an IL slot" in p for p in probs)


def test_il_players_do_not_count_toward_active_buckets():
    r = _roster(n_rp=4)
    r.append(_p("IL RP", "RP", "RP", on_il=True, mlbam=4001))
    # still at the floor of 4 ACTIVE rps, so an RP drop must still be blocked
    probs = RR.check_swap(r, add=_p("FA H", "H", "OF"),
                          drop=next(p for p in r if p["bucket"] == "RP" and not p["on_il"]))
    assert any("floor" in p for p in probs)


def test_no_move_is_trivially_legal():
    assert RR.check_swap(_roster()) == []


def test_is_legal_mirrors_check_swap():
    r = _roster()
    assert RR.is_legal(r, add=_p("FA OF", "H", "OF"), drop=r[0])
    assert not RR.is_legal(r, add=_p("FA SP", "SP", "SP"), drop=r[-1])
