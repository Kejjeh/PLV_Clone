"""matchup.html must cap the TODAY-FORWARD projection at cap − banked.

Defect (found 2026-09-18): main() passed the FULL period cap to
``apply_sp_cap`` although the projection holds only starts from today on
(banked starts are already in the live score). In a 2-week playoff round with
12 of 20 banked, the page let 20 MORE starts score while its own cap panel
said 12/20 — and P(win) was computed on the inflated total. leverage_engine
subtracts banked; the dashboard now shares that arithmetic.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_matchup_dashboard as BMD

SRC = ROOT / "scripts" / "xfp" / "build_matchup_dashboard.py"


def test_remaining_cap_arithmetic():
    assert BMD.remaining_cap(20, 12) == 8
    assert BMD.remaining_cap(10, 0) == 10
    assert BMD.remaining_cap(10, 11) == 0          # over-banked never negative
    assert BMD.remaining_cap(16, None) == 16       # ESPN fetch failed -> full cap, labelled elsewhere


def test_apply_sp_cap_zeroes_starts_beyond_remaining():
    proj = {"A": {"fp": 30.0, "units": 3, "sigma2": 90.0, "breakdown": [
        {"type": "start", "fp": 12.0}, {"type": "start", "fp": 10.0},
        {"type": "start", "fp": 8.0}]}}
    removed = BMD.apply_sp_cap(proj, cap=BMD.remaining_cap(20, 18))
    assert removed == 8.0
    assert proj["A"]["fp"] == 22.0


def test_main_never_caps_on_the_full_period_cap():
    """Every apply_sp_cap call in the builder must take a REMAINING-cap
    variable, never the raw period `sp_cap`."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "apply_sp_cap"]
    assert calls, "apply_sp_cap is no longer called — this test is stale"
    for c in calls:
        kw = {k.arg: k.value for k in c.keywords}
        assert "cap" in kw, f"line {c.lineno}: apply_sp_cap without cap="
        v = kw["cap"]
        assert not (isinstance(v, ast.Name) and v.id == "sp_cap"), (
            f"line {c.lineno}: apply_sp_cap(cap=sp_cap) applies the WHOLE "
            f"period cap to a today-forward projection; use remaining_cap()")
