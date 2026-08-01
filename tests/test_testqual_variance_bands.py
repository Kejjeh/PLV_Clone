"""Behavioral contract for scripts/xfp/lib/variance_bands.py (audit 2026-08-01, item 34).

WHY THIS FILE EXISTS
--------------------
`fallback_sigma` is the sigma source of last resort for all three Monte Carlo
engines — `lib/leverage_engine.py` (SP :363, RP :390/:392, H :405),
`run_matchup_leverage.py` and `run_season_sim.py`. Every ΔP(win) the decision
layer reports is denominated in it. It had no behavioral test, and every failure
mode — missing CSV, absent cell, non-positive sd — returns the CALLER's default
in total silence, so a P(win) computed from a degraded sigma is indistinguishable
from one computed from the measured table.

Rule 13: this is decision-layer only. The primary per-player bootstrap and the
rh3/rp3/rprs2 sigmas still win when present, so nothing here can move a
projection. The tests below therefore lock GRACEFUL DEGRADATION plus VISIBILITY,
never a number.

THE FIXTURE MATTERS: `_CACHE` is a module-level dict that `band_row` also uses
for per-cell memoisation, and `leverage_engine` imports `fallback_sigma` at
module scope. A test that repoints `BANDS_CSV` without clearing `_CACHE` poisons
every later test in the same session. The autouse fixture below is the guard.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

from lib import variance_bands as vb  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_module_cache():
    """Save/clear/restore the module-level cache around every test."""
    saved = dict(vb._CACHE)
    vb._CACHE.clear()
    yield
    vb._CACHE.clear()
    vb._CACHE.update(saved)


HEADER = "player_type,horizon,tier,era,sd_fp_total_per_horizon,shrink_k\n"


@pytest.fixture
def bands_csv(tmp_path, monkeypatch):
    """A minimal stand-in for the real subseason_variance_bands.csv."""
    p = tmp_path / "subseason_variance_bands.csv"
    p.write_text(
        HEADER
        + "H,game,T2,2021-25,3.5,600.0\n"
        + "SP,game,T2,2021-25,9.25,4.0\n"
        + "RP,game,T2,2021-25,4.0,25.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vb, "BANDS_CSV", p)
    return p


def test_a_missing_bands_table_announces_the_fallback_once(tmp_path, monkeypatch, capsys):
    """Silence is the defect. Every engine keeps running on the caller's default
    sigma — but the run must say which sigma it actually used."""
    monkeypatch.setattr(vb, "BANDS_CSV", tmp_path / "no_such_bands.csv")

    assert vb.fallback_sigma("H", default=3.0) == 3.0
    assert vb.fallback_sigma("SP", default=9.0) == 9.0

    err = capsys.readouterr().err
    assert "variance_bands" in err or "bands" in err.lower(), (
        "an absent bands table is silent — a P(win) built on caller defaults "
        f"looks exactly like one built on the measured table (stderr {err!r})")
    assert err.count("\n") == 1, (
        f"the notice must fire once per process, not per lookup (stderr {err!r})")


# ── the measured table wins when it is there ─────────────────────────────────

def test_sigma_comes_from_the_table_when_the_cell_exists(bands_csv):
    """The measured 2010-2025 value must beat the caller's guess."""
    assert vb.fallback_sigma("H", default=99.0) == pytest.approx(3.5)
    assert vb.fallback_sigma("SP", default=99.0) == pytest.approx(9.25)
    assert vb.fallback_sigma("RP", default=99.0) == pytest.approx(4.0)


def test_shrink_k_comes_from_the_table_when_the_cell_exists(bands_csv):
    assert vb.shrink_k("H", default=1.0) == pytest.approx(600.0)


def test_band_row_returns_the_whole_cell(bands_csv):
    row = vb.band_row("SP")
    assert row is not None
    assert row["sd_fp_total_per_horizon"] == pytest.approx(9.25)
    assert row["tier"] == "T2" and row["era"] == "2021-25"


def test_band_row_memoises_the_cell(bands_csv, monkeypatch):
    """Every simulated player hits this lookup; re-filtering the frame per call
    is the difference between a cheap draw assembly and a slow one."""
    vb.band_row("SP")
    calls = {"n": 0}
    real = vb.load_bands()

    class Counting:
        def __getitem__(self, k):
            calls["n"] += 1
            return real[k]

    monkeypatch.setitem(vb._CACHE, "df", Counting())
    vb.band_row("SP")
    assert calls["n"] == 0, "band_row re-filtered a cell it had already resolved"


# ── every degraded path returns the caller's default, never None, never a raise ─

def test_an_unknown_cell_returns_the_callers_default(bands_csv):
    assert vb.fallback_sigma("XX", default=7.5) == 7.5
    assert vb.fallback_sigma("H", horizon="decade", default=7.5) == 7.5
    assert vb.fallback_sigma("H", tier="T9", default=7.5) == 7.5
    assert vb.fallback_sigma("H", era="1899-1900", default=7.5) == 7.5
    assert vb.shrink_k("XX", default=12.0) == 12.0


def test_a_nonpositive_sd_is_treated_as_absent(tmp_path, monkeypatch):
    """A zero/negative sigma would collapse a player's draws to a point mass and
    hand the decision layer a fake certainty."""
    p = tmp_path / "bands.csv"
    p.write_text(HEADER + "H,game,T2,2021-25,0.0,600.0\nSP,game,T2,2021-25,-1.0,4.0\n",
                 encoding="utf-8")
    monkeypatch.setattr(vb, "BANDS_CSV", p)
    assert vb.fallback_sigma("H", default=3.0) == 3.0
    assert vb.fallback_sigma("SP", default=9.0) == 9.0


def test_a_nan_or_nonpositive_shrink_k_is_treated_as_absent(tmp_path, monkeypatch):
    p = tmp_path / "bands.csv"
    p.write_text(HEADER + "H,game,T2,2021-25,3.5,\nSP,game,T2,2021-25,9.0,0.0\n",
                 encoding="utf-8")
    monkeypatch.setattr(vb, "BANDS_CSV", p)
    assert vb.shrink_k("H", default=250.0) == 250.0
    assert vb.shrink_k("SP", default=250.0) == 250.0


def test_a_corrupt_table_degrades_instead_of_raising(tmp_path, monkeypatch):
    p = tmp_path / "bands.csv"
    p.write_bytes(b"\x00\x01\x02 not a csv \xff")
    monkeypatch.setattr(vb, "BANDS_CSV", p)
    assert vb.load_bands() is None
    assert vb.fallback_sigma("H", default=3.0) == 3.0


@pytest.mark.parametrize(
    "player_type,default",
    [("SP", 9.349), ("RP", 3.956), ("H", 3.0), ("H", 3.2)],
)
def test_every_engine_call_site_still_gets_a_float_with_the_table_absent(
    tmp_path, monkeypatch, player_type, default
):
    """These are the four live invocations (leverage_engine :363/:390/:392/:405,
    run_matchup_leverage :238, run_season_sim :107/:274/:307). run_season_sim
    does `float(fallback_sigma('H', default=3.2))` at MODULE SCOPE — a None here
    is an import-time TypeError that takes the whole season sim down."""
    monkeypatch.setattr(vb, "BANDS_CSV", tmp_path / "absent.csv")
    got = vb.fallback_sigma(player_type, default=default)
    assert isinstance(float(got), float) and got == default
