"""A refresh step that blows its timeout must leave no worker behind.

WHY THIS FILE EXISTS (audit 2026-08-01, item 17)
------------------------------------------------
`refresh_dashboards.run()` used `subprocess.run(..., shell=True, timeout=)`.
CPython's timeout path kills only the DIRECT child — which, under `shell=True`
on Windows, is `cmd.exe`. The python worker cmd.exe spawned is orphaned and
keeps running, keeps holding its file handles, and keeps WRITING into the same
data/outputs files the next pipeline step is about to read. The driver
meanwhile prints "continuing with next step" and moves on, so two writers race
over the same artifacts with nothing in the log to say so.

The spec below is deliberately about observable process state, not about which
API run() calls internally.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import pytest

psutil = pytest.importorskip("psutil")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

import refresh_dashboards as R  # noqa: E402


def _pids_carrying(marker: str) -> list[int]:
    """Every live process whose command line mentions `marker`.

    Excludes this test process itself — the marker travels through our own
    argv-free call, but a defensive filter keeps the probe honest if a future
    runner ever passes it on the command line.
    """
    hits = []
    me = psutil.Process().pid
    for proc in psutil.process_iter(["pid", "cmdline"]):
        if proc.info["pid"] == me:
            continue
        try:
            cmdline = " ".join(proc.info["cmdline"] or ())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if marker in cmdline:
            hits.append(proc.info["pid"])
    return hits


def _wait_until_gone(marker: str, seconds: float = 8.0) -> list[int]:
    deadline = time.time() + seconds
    while time.time() < deadline:
        alive = _pids_carrying(marker)
        if not alive:
            return []
        time.sleep(0.25)
    return _pids_carrying(marker)


def test_a_timed_out_step_leaves_no_worker_process_running(capsys):
    """The abandoned-worker spec.

    A step whose command outlives its timeout must be (a) reported as failed to
    the caller and (b) actually dead by the time run() returns, so the next step
    never shares its output files with a zombie writer.
    """
    marker = f"PLV_ORPHAN_PROBE_{uuid.uuid4().hex}"
    # A grandchild under the shell: `cmd.exe /c python -c "...sleep..."`.
    cmd = f'python -c "import time; time.sleep(45)" {marker}'

    assert not _pids_carrying(marker), "probe marker collided with a live process"

    ok = R.run("timeout probe", cmd, timeout=3)

    assert ok is False, "a timed-out step must report failure to the caller"
    survivors = _wait_until_gone(marker)
    assert not survivors, (
        f"worker process(es) {survivors} survived the timeout — they keep "
        "writing while the pipeline advances to the next step")

    out = capsys.readouterr().out
    assert "TIMED OUT" in out, "the timeout must still be announced in the log"


def test_a_normally_exiting_step_still_reports_its_outcome(capsys):
    """Guard rail: the kill path must not disturb the ordinary outcomes."""
    assert R.run("ok probe", 'python -c "raise SystemExit(0)"', timeout=60) is True
    assert R.run("fail probe", 'python -c "raise SystemExit(3)"', timeout=60) is False
    out = capsys.readouterr().out
    assert "exit code 3" in out
