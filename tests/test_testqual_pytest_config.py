"""The suite's own invocation contract (audit 2026-08-01, items 37 + 53).

WHY THIS FILE EXISTS
--------------------
Two defects in one knob:

  item 37 — `[tool.coverage.run] source` listed MODULE names ("plv_clone",
    "lib", "app"), so anything outside those import roots could never be
    measured. Observed: `pytest tests/test_bat_speed_daily.py` printed
    "Module lib was never imported" / "No data was collected" and reported
    app/*.py at 0%, while the module under test — scripts/xfp/build_bat_speed_daily.py
    — contributed nothing. ~113k production lines under scripts/xfp outside
    lib/ were structurally unmeasurable.

  item 53 — `addopts` forced `--cov --cov-report=term-missing -v` onto EVERY
    invocation and never deselected `slow`, so the cheapest possible run paid
    full tracer + verbose overhead.

The fix is one change: coverage becomes an explicit CI choice, `addopts` keeps
only what every run wants. What every run wants is specifically `-r sxX` —
that is what makes the data-gated SKIP reasons (item 38) legible in
scripts/ci/run_summary.py's short-summary block.

THE INVOCATIONS
---------------
  default   : python scripts/ci/run_summary.py -- python -m pytest
  coverage  : python -m pytest --cov --cov-report=term-missing
  PRE-PUBLISH (must include the slow triangulate parallel-vs-batch equivalence
              test, which addopts now deselects):
              python -m pytest -m ""
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
CFG = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
ADDOPTS = CFG["tool"]["pytest"]["ini_options"]["addopts"]
COV_SOURCE = CFG["tool"]["coverage"]["run"]["source"]


# ── item 37: coverage must be able to SEE the production surface ─────────────

def test_coverage_source_entries_are_paths_that_exist():
    """Module-name entries silently measure nothing when the name is not an
    import root — that is exactly how scripts/xfp went unmeasured. Path entries
    bind regardless of import spelling (`lib.*` AND `scripts.xfp.lib.*` are both
    live in this suite)."""
    for entry in COV_SOURCE:
        assert (REPO_ROOT / entry).exists(), (
            f"coverage source {entry!r} is not a path in this repo — if it is a "
            "module name it measures nothing unless that module is imported")


def test_coverage_measures_the_scripts_xfp_engine_surface():
    """The engines the decision layer runs on live in scripts/xfp, not in the
    installed package. Reporting a coverage number that excludes them is the
    dishonest half of the defect."""
    covered = {Path(e).as_posix() for e in COV_SOURCE}
    assert "scripts/xfp" in covered, (
        f"scripts/xfp is not measured (source = {COV_SOURCE}) — ~113k production "
        "lines cannot appear in any coverage report")


def test_coverage_path_aliases_reconcile_both_lib_import_spellings():
    """`from lib.x import ...` and `pytest.importorskip('scripts.xfp.lib.x')` are
    BOTH used by the suite; without the alias they report as two files."""
    aliases = CFG["tool"]["coverage"]["paths"]
    flat = [Path(p).as_posix() for group in aliases.values() for p in group]
    assert any(p.endswith("scripts/xfp/lib") for p in flat), (
        f"no alias maps the scripts/xfp/lib import spellings together: {aliases}")


# ── item 53: the default invocation must be the cheap one ────────────────────

def test_default_addopts_does_not_force_coverage():
    """Coverage is a CI choice, not a tax on every `pytest tests/foo.py`.
    Measured A/B on the same 58 tests: 20.30s with the forced flags, 12.21s
    without (~40% faster)."""
    assert "--cov" not in ADDOPTS, (
        f"addopts still forces coverage on every invocation: {ADDOPTS!r}")


def test_default_addopts_does_not_force_verbose():
    """`-v` also forces the full per-test tree onto `--collect-only -q`."""
    assert " -v" not in f" {ADDOPTS}", f"addopts still forces -v: {ADDOPTS!r}"


def test_default_addopts_deselects_slow():
    """The slow triangulate subprocess tests must not be in the default loop."""
    assert "not slow" in ADDOPTS, (
        f"addopts does not deselect the slow marker: {ADDOPTS!r}")


def test_default_addopts_keeps_skip_reasons_visible():
    """`-r sxX` is load-bearing, not decoration: it is the ONLY thing that puts
    the data-gated skip reasons (item 38) into the short-summary block that
    scripts/ci/run_summary.py extracts."""
    assert "-r" in ADDOPTS and "s" in ADDOPTS.split("-r", 1)[1].split()[0], (
        f"addopts dropped the skip-reason report flag: {ADDOPTS!r} — data-gated "
        "skips become invisible in the summarised CI log")


def test_the_slow_marker_is_registered():
    markers = CFG["tool"]["pytest"]["ini_options"]["markers"]
    assert any(m.startswith("slow:") for m in markers), (
        "addopts deselects `slow` but the marker is unregistered — a typo in the "
        "marker name would silently deselect nothing")


@pytest.mark.parametrize("marked_file", ["tests/test_triangulate.py",
                                         "tests/test_triangulate_golden.py"])
def test_the_slow_marked_tests_still_exist(marked_file):
    """If these lose their marker, `-m ""` stops being a meaningful pre-publish
    invocation and the default run silently gets slower."""
    p = REPO_ROOT / marked_file
    if not p.exists():
        pytest.skip(f"{marked_file} not present")
    assert "pytest.mark.slow" in p.read_text(encoding="utf-8"), (
        f"{marked_file} no longer carries @pytest.mark.slow")
