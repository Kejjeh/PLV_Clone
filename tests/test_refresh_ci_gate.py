"""A red test suite must stop the nightly publish; a broken runner must not.

WHY THIS FILE EXISTS (audit 2026-08-01, item 31)
------------------------------------------------
Nothing ran pytest anywhere: `grep -rn pytest .github/workflows/` was empty, so
a 1400-test suite gated neither the nightly publish nor a push to main. A
refresh could ship dashboards built by code whose own tests were failing.

The gate has to distinguish two outcomes that both look like "pytest returned
non-zero":

  exit 1      tests FAILED             -> gate, do not refresh
  exit 2      interrupted/collection   -> SUITE_RED (archive, no publish)
  exit 3-5    pytest could not RUN     -> SUITE_RED (archive, no publish)
              (corrected 2026-08-27 — exit 5 is "no tests collected", which
               is the gate not running, not a runner hiccup)
              (interrupted / internal error / usage error / no tests collected)

Conflating them would let one missing wheel on the runner wedge the whole
nightly and cost a day of ESPN transaction archival that rolls off in 7-14
days. So the tests below EXECUTE the step's PowerShell against a stubbed
`python` on PATH and assert its exit code per case, rather than reading it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "daily-refresh.yml"

pytestmark = pytest.mark.skipif(
    shutil.which("powershell") is None,
    reason="Windows PowerShell not on PATH (the self-hosted runner's shell)")


def _steps() -> list[dict]:
    with open(WORKFLOW, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["jobs"]["refresh"]["steps"]


def _gate_step() -> dict:
    hits = [s for s in _steps() if "pytest" in (s.get("run") or "")]
    assert hits, "no step in daily-refresh.yml runs pytest — the suite gates nothing"
    assert len(hits) == 1, "more than one pytest step: ambiguous"
    return hits[0]


def _exit_code_with_stub_pytest(stub_exit: int, tmp_path: Path) -> tuple[int, str, str]:
    """Run the gate step with `python` stubbed to a chosen exit code.

    Returns (exit_code, combined_output, github_env_contents) — the third
    element is what the step exported, which is the gate's REAL signal now:
    a red suite exits 0 (so the archival work still runs) and exports
    SUITE_RED=1 (so the refresh withholds the publish)."""
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python.bat").write_text(f"@echo off\r\nexit /b {stub_exit}\r\n",
                                     encoding="ascii")
    ps1 = tmp_path / "gate.ps1"
    ps1.write_text("$ErrorActionPreference = 'Stop'\n" + _gate_step()["run"],
                   encoding="utf-8")
    gh_env = tmp_path / "github_env.txt"
    gh_env.write_text("", encoding="utf-8")

    env = dict(os.environ)
    env["PATH"] = str(shim) + os.pathsep + env["PATH"]
    env["GITHUB_ENV"] = str(gh_env)
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-File", str(ps1)],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=180)
    return (proc.returncode, proc.stdout + proc.stderr,
            gh_env.read_text(encoding="utf-8-sig"))


@pytest.mark.parametrize("red", [1, 2])
def test_a_red_suite_withholds_the_publish_but_never_the_archival(red, tmp_path):
    """Review 2026-08-01, both halves. A red suite (exit 1) AND a collection
    error (exit 2 — a production import/syntax error lands here) export
    SUITE_RED=1 so the refresh runs --no-push: the day's ESPN archival is
    never sacrificed, and nothing built by red code reaches the public
    dashboards. The step itself exits 0 — the commit step has no `if:` and
    must still run."""
    code, out, gh = _exit_code_with_stub_pytest(red, tmp_path)
    assert code == 0, (
        "the gate must exit 0 on a red suite (archival must proceed)"
        + chr(10) + out)
    assert "SUITE_RED=1" in gh, (
        f"a red suite (pytest exit {red}) must export SUITE_RED=1 so the "
        "refresh withholds the publish" + chr(10) + out)


def test_a_passing_suite_lets_the_refresh_publish(tmp_path):
    code, out, gh = _exit_code_with_stub_pytest(0, tmp_path)
    assert code == 0, "a green suite must not block the refresh" + chr(10) + out
    assert "SUITE_RED" not in gh, "a green suite must not withhold the publish"


@pytest.mark.parametrize("unverifiable", [3, 4, 5])
def test_a_suite_that_could_not_run_withholds_the_publish(unverifiable, tmp_path):
    """"We could not verify the suite" gets the same handling as "it is red".

    CORRECTED 2026-08-27. This previously asserted that exits 3/4/5 must NOT
    withhold the publish, reasoning that gating on them "costs a day of
    unrecoverable archival data". That reasoning is about the wrong lever:

      * `exit 1` from this step WOULD cost the archival — the whole 2026-08-01
        review was about that, and it is why the step exits 0 on a red suite.
      * SUITE_RED costs NOTHING. The refresh step's own comment says
        "SUITE_RED withholds only the xfp-model publish; every archival and
        model step still runs and the data commit below still happens", the
        refresh runs `--no-push`, and the commit step carries no `if:`.

    So the two priorities are not in tension here, exactly as they were not
    for exits 1 and 2: archive everything, publish nothing.

    It matters most for **exit 5 = no tests were collected**. That is not a
    runner hiccup — it is the gate not running. A renamed marker, a pytest
    flag removed upstream, or a missing pytest-cov plugin each produce exit
    3/4/5, and each would otherwise publish dashboards having run ZERO tests
    — precisely what this step exists to prevent. Both are reachable: an
    empty marker selection exits 5, and `--no-cov` without pytest-cov exits 4.
    """
    code, out, gh = _exit_code_with_stub_pytest(unverifiable, tmp_path)
    assert code == 0, (
        f"pytest exit {unverifiable} must still exit the STEP 0 — the day's "
        "ESPN archival rolls off the API in 7-14 days and is unrecoverable"
        + chr(10) + out)
    assert "WARN" in out.upper(), (
        "an unverifiable suite must be reported distinctly from a red one")
    assert "SUITE_RED=1" in gh, (
        f"pytest exit {unverifiable} means the suite did not run — the publish "
        f"must be withheld until it can be verified, NOT waved through"
        + chr(10) + out)


def test_the_refresh_step_honors_suite_red_with_no_push():
    """The gate's export is only real if the refresh step consumes it."""
    steps = _steps()
    refresh = next(s for s in steps
                   if "refresh_dashboards.py" in (s.get("run") or ""))
    run = refresh["run"]
    assert "SUITE_RED" in run and "--no-push" in run, (
        "the refresh step must run --no-push when SUITE_RED=1 — without this "
        "the gate's export is decoration")


def test_the_gate_actually_invokes_the_test_suite():
    """The gate must RUN pytest, not merely mention it.

    `_gate_step()` locates the step by the substring "pytest", which also
    appears in its own "WARN: pytest could not run" log line. So a gate whose
    invocation was deleted while that message survived kept every other test in
    this file green: the exit-code branches were still exercised, because the
    stub replaces `python` regardless of its arguments. Assert the invocation
    itself.
    """
    run = _gate_step()["run"]
    invocations = [ln.strip() for ln in run.splitlines()
                   if "-m pytest" in ln and "Write-Host" not in ln]

    assert invocations, (
        "the gate step never invokes `python -m pytest` — it only mentions "
        f"pytest in its logging, so it gates on nothing:\n{run}")
    assert any("not slow" in ln for ln in invocations), (
        "the gate must deselect the slow marker, or it doubles the nightly's "
        f"pre-refresh wall time: {invocations}")


def test_the_gate_runs_before_the_refresh_step():
    names = [s.get("name", "") for s in _steps()]
    gate_i = names.index(_gate_step().get("name", ""))
    refresh_i = next(i for i, n in enumerate(names) if "Full refresh" in n)
    assert gate_i < refresh_i, "a gate that runs after the publish gates nothing"
