"""T21 — a title-equity weight whose AGE cannot be determined is not 'fresh'.

The module's whole contract is that staleness is labelled, never laundered
("Every return carries ``status`` and ``source_period`` so the caller cannot
accidentally launder a stale number as fresh", module docstring). But a payload
carrying no ``period`` key fell into ``elif out['status'] != 'interpolated':
out['status'] = 'fresh'`` and came back byte-for-byte indistinguishable from a
genuinely current weight: status ``fresh``, ``periods_stale`` None, empty note,
banner reading ``[FRESH]``.

Not reachable from the repo's own producer today — ``run_season_sim.py`` always
writes ``period`` — so this closes a contract hole rather than fixing a number
Josh is currently being shown. The weight itself is unchanged and still
displayed (degrade rather than refuse); only the LABEL moves.

Rule 13: display-only. ``annotate`` still does not re-sort.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

TE = pytest.importorskip("scripts.xfp.lib.title_equity",
                         reason="title_equity import chain unavailable")

CURVE = [{"period": 16, "dtitle_pp": 1.10, "dplayoffs_pp": 2.0, "p_win_week": 0.50},
         {"period": 17, "dtitle_pp": 0.75, "dplayoffs_pp": 1.5, "p_win_week": 0.48}]


def _payload(**extra):
    pay = {"josh": {"value_of_win_curve": CURVE,
                    "sensitivity": {"dtitle_mean_plus2_pp": 0.68}}}
    pay.update(extra)
    return pay


def test_undatable_weight_is_not_labelled_fresh():
    """No ``period`` on the payload means the weight's age is unknowable — that
    must not be reported with the same word as a weight generated this period."""
    wv = TE.win_value(17, payload=_payload())

    assert wv["status"] != "fresh", (
        "an undatable weight is presented exactly like a current one "
        f"(status {wv['status']!r}, periods_stale {wv['periods_stale']!r}, "
        f"note {wv['note']!r})")
    assert wv["note"], "an undatable weight must carry a note saying so"

    banner = TE.banner(wv)
    assert "[FRESH]" not in banner, banner
    assert "unknown" in banner.lower(), banner


def test_undatable_weight_is_still_displayed():
    """Degrade rather than refuse: the number keeps flowing to the caller."""
    wv = TE.win_value(17, payload=_payload())
    assert wv["dtitle_pp"] == pytest.approx(0.75)
    assert wv["source_period"] == 17
    eq = TE.equity(0.05, 17, payload=_payload())
    assert eq["dtitle_equity_pp"] == pytest.approx(round(0.05 * 0.75, 4))


def test_an_explicitly_null_period_is_also_undatable():
    """``{'period': None}`` carries no more information than a missing key."""
    assert TE.win_value(17, payload=_payload(period=None))["status"] != "fresh"


def test_a_dated_current_payload_is_still_fresh():
    """The boundary the other way — the honest 'fresh' case must survive."""
    wv = TE.win_value(17, payload=_payload(period=17))
    assert wv["status"] == "fresh"
    assert wv["periods_stale"] == 0
    assert "[FRESH]" in TE.banner(wv)
