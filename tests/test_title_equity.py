"""Tests for lib/title_equity — period dpwin -> championship equity (C4).

The load-bearing property is honesty about staleness. season_sim.json is
regenerated on its own cadence, so it is routinely a period or two behind the
live matchup, and the failure mode to prevent is laundering an old leverage
weight as a current one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

TE = pytest.importorskip("scripts.xfp.lib.title_equity")


def _payload(period=15, rows=((15, 2.67), (16, 1.24), (17, 0.88), (18, 1.39)),
             plus2=0.56):
    return {
        "period": period,
        "josh": {
            "p_title": 0.1078,
            "value_of_win_curve": [
                {"period": p, "dtitle_pp": d, "dplayoffs_pp": 5.0,
                 "p_win_week": 0.43, "p_title_if_win": 0.11,
                 "p_title_if_lose": 0.10}
                for p, d in rows],
            "sensitivity": {"dtitle_mean_plus2_pp": plus2},
        },
    }


# ── the core conversion ──────────────────────────────────────────────────────

def test_exact_period_match_is_fresh():
    wv = TE.win_value(15, payload=_payload(period=15))
    assert wv["status"] == "fresh"
    assert wv["dtitle_pp"] == 2.67
    assert wv["periods_stale"] == 0


def test_equity_is_dpwin_times_the_weight():
    e = TE.equity(0.0875, 17, payload=_payload())
    assert e["dtitle_pp_per_win"] == 0.88
    assert e["dtitle_equity_pp"] == pytest.approx(0.0875 * 0.88, abs=1e-6)


def test_the_curve_is_not_flat_which_is_the_whole_point():
    """The same weekly edge is worth 3x more in a high-leverage week. If this
    ever collapses to a constant, the bridge stops earning its keep."""
    pay = _payload()
    hi = TE.equity(0.0875, 15, payload=pay)["dtitle_equity_pp"]
    lo = TE.equity(0.0875, 17, payload=pay)["dtitle_equity_pp"]
    assert hi > lo * 2.5


# ── staleness honesty ────────────────────────────────────────────────────────

def test_a_later_period_is_marked_stale_with_the_gap():
    wv = TE.win_value(17, payload=_payload(period=15))
    assert wv["status"] == "stale"
    assert wv["periods_stale"] == 2
    assert "generated at period 15" in wv["note"]
    assert "Re-run /season-sim" in wv["note"]


def test_a_stale_weight_is_still_returned_not_suppressed():
    """It is a DISPLAY conversion under Rule 13 — dpwin remains the sort key — so
    hiding it would lose real strategic information. It must be labelled, not
    dropped."""
    e = TE.equity(0.05, 17, payload=_payload(period=15))
    assert e["dtitle_equity_pp"] is not None
    assert e["status"] == "stale"


def test_hard_stale_is_escalated_in_the_note():
    wv = TE.win_value(18, payload=_payload(period=15))
    assert wv["periods_stale"] == 3
    assert "HARD-STALE" in wv["note"]


def test_source_period_is_always_reported_so_nothing_launders():
    for per in (15, 16, 17):
        wv = TE.win_value(per, payload=_payload())
        assert wv["source_period"] == per
        assert wv["payload_period"] == 15


# ── graceful degradation ─────────────────────────────────────────────────────

def test_missing_period_interpolates_from_neighbours():
    """josh_sensitivities skips periods whose conditioning sample is < 50 sims,
    so a hole in the curve is expected rather than exceptional."""
    pay = _payload(rows=((15, 2.0), (17, 1.0)))
    wv = TE.win_value(16, payload=pay)
    assert wv["status"] == "interpolated"
    assert wv["dtitle_pp"] == pytest.approx(1.5)
    assert set(wv["source_period"]) == {15, 17}
    assert "conditioning sample" in wv["note"]


def test_missing_payload_yields_None_not_zero():
    """A silent 0.0 would read as 'this move is worth nothing' rather than 'we
    cannot say' — the same class of error as a silent-zero feature fill."""
    e = TE.equity(0.05, 17, path=ROOT / "data" / "outputs" / "__does_not_exist__.json")
    assert e["dtitle_equity_pp"] is None
    assert e["dtitle_pp_per_win"] is None
    assert e["status"] == "unavailable"
    assert "season_sim.json missing" in e["note"]


def test_empty_curve_is_handled():
    pay = _payload()
    pay["josh"]["value_of_win_curve"] = []
    wv = TE.win_value(17, payload=pay)
    assert wv["dtitle_pp"] is None and wv["status"] == "unavailable"


def test_no_neighbours_to_interpolate_from():
    pay = _payload(rows=((15, 2.0),))
    wv = TE.win_value(99, payload=pay)
    # a single neighbour is still usable; the failure case is none at all
    assert wv["status"] == "interpolated"
    pay["josh"]["value_of_win_curve"] = [{"period": 15, "dtitle_pp": None}]
    wv2 = TE.win_value(99, payload=pay)
    assert wv2["dtitle_pp"] is None


def test_plus2_context_is_carried_but_separate():
    """+2 FP/wk of roster quality is context for persistent-value moves; it must
    not be folded into the per-move conversion."""
    wv = TE.win_value(17, payload=_payload(plus2=0.56))
    assert wv["plus2_pp"] == 0.56
    e = TE.equity(0.10, 17, payload=_payload(plus2=0.56))
    assert e["dtitle_equity_pp"] == pytest.approx(0.10 * 0.88, abs=1e-6)


# ── annotate + banner ────────────────────────────────────────────────────────

def test_annotate_fills_moves_in_place_without_resorting():
    moves = [{"dpwin": 0.02}, {"dpwin": 0.09}, {"dpwin": -0.01}]
    wv = TE.annotate(moves, 17, payload=_payload())
    assert [round(m["dtitle_equity_pp"], 4) for m in moves] == [
        pytest.approx(0.0176, abs=1e-4),
        pytest.approx(0.0792, abs=1e-4),
        pytest.approx(-0.0088, abs=1e-4)]
    # order preserved — the weight is a per-period constant and cannot reorder
    assert [m["dpwin"] for m in moves] == [0.02, 0.09, -0.01]
    assert wv["dtitle_pp"] == 0.88


def test_annotate_sets_None_when_unavailable():
    moves = [{"dpwin": 0.02}]
    TE.annotate(moves, 17, payload={"period": 17, "josh": {}})
    assert moves[0]["dtitle_equity_pp"] is None


def test_banner_states_the_status_and_the_note():
    b = TE.banner(TE.win_value(17, payload=_payload(period=15)))
    assert "STALE" in b and "0.88pp" in b and "Re-run /season-sim" in b


def test_banner_when_unavailable():
    b = TE.banner({"dtitle_pp": None, "note": "nothing here"})
    assert "UNAVAILABLE" in b


# ── real payload, if present ──────────────────────────────────────────────────

def test_against_the_real_payload_if_it_exists():
    pay = TE.load_payload()
    if not pay:
        pytest.skip("season_sim.json not present")
    curve = (pay.get("josh") or {}).get("value_of_win_curve") or []
    if not curve:
        pytest.skip("curve empty")
    per = int(curve[0]["period"])
    wv = TE.win_value(per, payload=pay)
    assert wv["dtitle_pp"] is not None
    assert wv["status"] in ("fresh", "stale", "interpolated")


def test_both_runners_wire_the_bridge():
    for f in ("run_weekly_optimizer.py", "run_matchup_leverage.py"):
        src = (ROOT / "scripts" / "xfp" / f).read_text(encoding="utf-8")
        assert "title_equity as TE" in src, f
        assert "TE.annotate(" in src, f
