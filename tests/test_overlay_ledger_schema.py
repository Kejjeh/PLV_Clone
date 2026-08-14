"""The prospective-overlay ledger must key its cohort on an unambiguous column.

AUDIT 2026-08-14. `prereg_overlay_prospective_2026-08-12.md` defines the scored
cohort as "players whose snapshot-day source was `il_return_overlay`", and the
board wrote that string into a column named `qual`. For hitters `qual` held
`ros_volume()['source']` — exactly the intended meaning. For SP rows `qual` held
the rp3 `data_quality_tag` (`marcel_il`, `data_driven_full`): a MODEL-quality
label, not a VOLUME-construction label, in the same column of the same file.

Nothing breaks loudly. The settle script filters `qual == 'il_return_overlay'`,
finds only hitters, and reports a clean result — while `marcel_il` sits one row
below, close enough to the cohort string to be mis-read by a human and close
enough in kind to be mis-joined by the next script someone writes. A
pre-registered ledger that cannot be filtered unambiguously is the failure mode
the prereg's own schema check exists to prevent.

Fix: an explicit `vol_source` column carrying the VOLUME construction for every
row, whatever the bucket. `qual` keeps its per-bucket model meaning; the cohort
keys on `vol_source`, which means one thing everywhere.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_BOARD = _ROOT / "scripts" / "xfp" / "build_period_xfp_board.py"
_LEDGER_DIR = _ROOT / "data" / "research" / "validation_runs" / "overlay_prospective"
_PREREG = (_ROOT / "data" / "research" / "validation_runs"
           / "prereg_overlay_prospective_2026-08-12.md")

# The volume constructions a row may declare. Closed set on purpose: a new one
# has to be added here, which is the moment to ask whether the cohort changed.
VOL_SOURCES = {"il_return_overlay", "model_passthrough",
               "pace_forward_sp_volume", "no_sp_volume"}


def test_board_emits_vol_source_and_requires_it_in_the_ledger():
    src = _BOARD.read_text(encoding="utf-8")
    assert '"vol_source"' in src
    assert src.count('"vol_source"') >= 3, (
        "both bucket branches must set it, and the schema check must require it")


def test_prereg_cohort_keys_on_vol_source_not_qual():
    txt = _PREREG.read_text(encoding="utf-8")
    assert "vol_source" in txt, (
        "the pre-registration must name the column the cohort is actually "
        "filtered on")


@pytest.mark.skipif(not _LEDGER_DIR.exists(), reason="no ledger snapshots yet")
def test_every_ledger_row_declares_a_known_volume_construction():
    snaps = sorted(_LEDGER_DIR.glob("predictions_*.csv"))
    if not snaps:
        pytest.skip("no ledger snapshots yet")
    for snap in snaps:
        with snap.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert rows, f"{snap.name} is empty"
        assert "vol_source" in rows[0], (
            f"{snap.name} predates the vol_source column; it cannot be "
            "unambiguously filtered and must not be settled as-is")
        for r in rows:
            assert r["vol_source"] in VOL_SOURCES, (
                f"{snap.name}: unknown vol_source {r['vol_source']!r} for "
                f"{r['player']}")


@pytest.mark.skipif(not _LEDGER_DIR.exists(), reason="no ledger snapshots yet")
def test_the_cohort_filter_selects_only_hitters_on_an_il_return():
    """The registered cohort is IL returnees with an ESPN date — SP rows share
    the file but must never fall into it."""
    snaps = sorted(_LEDGER_DIR.glob("predictions_*.csv"))
    if not snaps:
        pytest.skip("no ledger snapshots yet")
    with snaps[-1].open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if "vol_source" not in rows[0]:
        pytest.skip("pre-vol_source snapshot")
    cohort = [r for r in rows if r["vol_source"] == "il_return_overlay"]
    for r in cohort:
        assert r["bucket"] == "H"
        assert r["return_date_used"], (
            f"{r['player']} is in the cohort without the return date that "
            "defines it — unsettleable")
