"""Offline tests for the SP Statcast context engine (stuff / command / contact).

Covers the firmed StuffFP composite and the collision-safe name resolution;
the parquet-backed aggregation is exercised at build time, not here."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from lib import sp_stuff_context as ctx  # noqa: E402


def test_stufffp_known_value():
    # -6.12 + .483*25 + 1.095*11 - .368*23 = 9.536 -> 9.5
    assert ctx.stufffp(25.0, 11.0, 23.0) == 9.5


def test_stufffp_none_inputs():
    assert ctx.stufffp(None, 11.0, 23.0) is None
    assert ctx.stufffp(25.0, None, 23.0) is None
    assert ctx.stufffp(25.0, 11.0, None) is None


def test_stufffp_weight_directions():
    """SwStr is the positive engine; Whiff enters negative (swing-rate
    suppressor) — the structure that makes the composite beat any single one."""
    base = ctx.stufffp(28.0, 12.0, 25.0)
    assert ctx.stufffp(28.0, 14.0, 25.0) > base   # more SwStr -> higher
    assert ctx.stufffp(28.0, 12.0, 30.0) < base   # more Whiff (fixed SwStr) -> lower
    assert ctx.stufffp(30.0, 12.0, 25.0) > base   # more CSW -> higher


def test_context_for_resolves_unique(monkeypatch):
    read = {"starts": 5, "low_conf": False,
            "s": {"stufffp": 12.0, "kbb": 18.0, "xwc": 0.300},
            "l3": {"stufffp": 13.5, "kbb": 20.0, "xwc": 0.280}}
    monkeypatch.setattr(ctx, "_name_map", lambda: {"john smith": {111}})
    monkeypatch.setattr(ctx, "_by_pitcher", lambda: {111: read})
    got = ctx.context_for("John Smith")
    assert got["s"]["stufffp"] == 12.0 and got["starts"] == 5


def test_context_for_ambiguous_returns_none(monkeypatch):
    """A shared full name must fail closed, never guess a wrong join."""
    monkeypatch.setattr(ctx, "_name_map", lambda: {"john smith": {111, 222}})
    monkeypatch.setattr(ctx, "_by_pitcher", lambda: {111: {}, 222: {}})
    assert ctx.context_for("John Smith") is None


def test_context_for_unknown_returns_none(monkeypatch):
    monkeypatch.setattr(ctx, "_name_map", lambda: {})
    monkeypatch.setattr(ctx, "_by_pitcher", lambda: {})
    assert ctx.context_for("Nobody Here") is None


def test_thin_threshold_constant():
    assert ctx.THIN_STARTS == 4 and ctx.MIN_START_PITCHES == 25
