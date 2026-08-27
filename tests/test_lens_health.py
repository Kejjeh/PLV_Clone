"""A degraded lens stack must be visible to the CALLER, not only on stderr.

WHY THIS EXISTS
The fail-soft lens handlers print a stderr breadcrumb and carry on (the
2026-07-04 fix for silent excepts hiding dead lenses for weeks). But
`triangulate_player` returned a verdict with nothing on the result dict to say
two lenses had been suppressed, so the same player synthesized to a DIFFERENT
verdict depending on whether `statcast_2026.parquet` happened to be present —
CAUTION with it, MIXED without — and the result looked entirely healthy.

That is CLAUDE.md don't-do #12: a verdict may change only on new data or a
corrected error, never silently. `result['degraded_lenses']` is what lets a
caller tell the difference. (Added 2026-08-27.)

Finding this also surfaced a second, quieter bug: `lib/extra_lenses.py` and
friends imported siblings as `from lib.trend_signal import ...` — an ABSOLUTE
import that only resolves when `scripts/xfp` is on sys.path. Imported by the
package path the lens raised ModuleNotFoundError and was silently dead. The
last test here pins the relative form.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "scripts" / "xfp" / "lib"

lens_health = pytest.importorskip("scripts.xfp.lib.lens_health")


@pytest.fixture(autouse=True)
def _clean_registry():
    lens_health.reset()
    yield
    lens_health.reset()


def test_records_a_suppression():
    lens_health.record("extra_lenses.trend_lens", FileNotFoundError("statcast_2026.parquet"))
    snap = lens_health.snapshot()
    assert len(snap) == 1
    assert "extra_lenses.trend_lens" in snap[0]
    assert "FileNotFoundError" in snap[0]
    assert "statcast_2026.parquet" in snap[0]


def test_healthy_build_records_nothing():
    assert lens_health.snapshot() == ()


def test_duplicate_suppressions_collapse():
    """A lens retried in a loop must not flood the registry."""
    for _ in range(5):
        lens_health.record("a.b", FileNotFoundError("x"))
    assert len(lens_health.snapshot()) == 1


def test_distinct_suppressions_all_kept_in_order():
    lens_health.record("a.b", FileNotFoundError("x"))
    lens_health.record("c.d", ValueError("y"))
    snap = lens_health.snapshot()
    assert len(snap) == 2
    assert snap[0].startswith("a.b")
    assert snap[1].startswith("c.d")


def test_reset_clears():
    lens_health.record("a.b", ValueError("x"))
    lens_health.reset()
    assert lens_health.snapshot() == ()


def test_record_never_raises():
    """A degradation recorder that can itself fail is worse than none."""
    class Nasty(Exception):
        def __str__(self):
            raise RuntimeError("boom")

    lens_health.record("a.b", Nasty())  # must not propagate


def test_triangulate_result_exposes_degraded_lenses():
    """The field must exist on every result, healthy or not."""
    tri = pytest.importorskip("scripts.xfp.lib.triangulate_core")
    result = tri.triangulate_player("Aaron Judge")
    if result is None:
        pytest.skip("Aaron Judge did not resolve in this checkout")
    assert "degraded_lenses" in result, (
        "triangulate_player must always report its lens health — a caller "
        "cannot otherwise tell a healthy verdict from a degraded one."
    )
    assert isinstance(result["degraded_lenses"], list)


def test_lib_modules_import_siblings_relatively():
    """`from lib.x import y` inside lib/ only works when scripts/xfp is on
    sys.path; by the package path it raises ModuleNotFoundError and, inside a
    fail-soft handler, silently kills the lens."""
    offenders = []
    for path in sorted(LIB.glob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("from lib.", "import lib.")):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {stripped}")

    assert not offenders, (
        "absolute sibling import(s) inside scripts/xfp/lib — use a relative "
        "import (`from .trend_signal import ...`) so the module works by the "
        "package path too:\n  " + "\n  ".join(offenders)
    )
