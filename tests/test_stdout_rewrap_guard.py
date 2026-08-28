"""No script may rebind sys.stdout at import time under pytest.

Windows scripts rewrap sys.stdout in a UTF-8 TextIOWrapper (the cp1252
console fix, CLAUDE.md gotcha #2). Done unguarded at MODULE level, the rewrap
fires when a TEST imports the script: under pytest, sys.stdout is the capture
object, and wrapping its .buffer then discarding the old wrapper closes
pytest's capture tempfile — every subsequent test errors with "I/O operation
on closed file" (2026-08-28: test_degraded_lens_surfacing importing
run_triangulate on Windows took down 4,097 setups/teardowns; the Linux
container never saw it because every rewrap sits behind sys.platform).

The contract: a stdout rewrap must also require ``sys.stdout is
sys.__stdout__`` — true when running as a script, false under pytest capture.

DISCOVERY over enumeration (don't-do #18): scan every script for the rewrap
pattern rather than naming the seven files that carried it on the day the
guard was written.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REWRAP = re.compile(r"TextIOWrapper\(\s*sys\.stdout\.buffer")
GUARD = re.compile(r"sys\.stdout\s+is\s+sys\.__stdout__")


def _rewrap_sites():
    for path in (ROOT / "scripts").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in REWRAP.finditer(text):
            yield path, text, m


def test_every_stdout_rewrap_is_guarded_against_pytest_capture():
    offenders = []
    for path, text, m in _rewrap_sites():
        # The guard must appear shortly before the rewrap (same if-block).
        window = text[max(0, m.start() - 400): m.start()]
        if not GUARD.search(window):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "sys.stdout rewrap without a `sys.stdout is sys.__stdout__` guard — "
        f"importing these under pytest closes the capture stream: {offenders}"
    )


def test_importing_run_triangulate_leaves_pytest_stdout_alone():
    """The concrete 2026-08-28 incident, pinned end-to-end."""
    before = sys.stdout
    sys.path.insert(0, str(ROOT))
    try:
        import importlib

        importlib.import_module("scripts.xfp.run_triangulate")
    finally:
        sys.path.remove(str(ROOT))
    assert sys.stdout is before, "importing run_triangulate rebound sys.stdout"
