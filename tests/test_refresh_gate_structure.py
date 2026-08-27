"""The nightly gate's exit-code contract, checked WITHOUT PowerShell.

WHY THIS FILE EXISTS
`tests/test_refresh_ci_gate.py` executes the gate step's real PowerShell
against a stubbed `python`, which is the strongest possible check — and it
skips entirely on any machine without PowerShell. All nine of its tests skip
on Linux, so in a Linux CI container the gate's contract is pinned by nothing
at all.

This file reads the same step out of the workflow YAML and asserts its branch
structure statically, so the contract holds everywhere. The two are
complementary: this one cannot prove the PowerShell *runs*, and that one
cannot run at all off Windows.

THE CONTRACT (corrected 2026-08-27)
  exit 0     suite green            -> publish
  exit 1     tests failed           -> SUITE_RED (archive, no publish)
  exit 2     interrupted/collection -> SUITE_RED (archive, no publish)
  exit 3,4,5 pytest could not run   -> SUITE_RED (archive, no publish)

Exits 3-5 used to wave the publish through as "a runner hiccup". Exit 5 means
NO TESTS WERE COLLECTED — the gate did not run — and the stated reason for not
gating ("costs a day of unrecoverable archival data") was about `exit 1` from
the step, not about SUITE_RED. SUITE_RED withholds only the publish: the
refresh still runs with --no-push and the data-commit step carries no `if:`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "daily-refresh.yml"


def _step(name_fragment: str) -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        for step in job.get("steps") or []:
            if name_fragment.lower() in (step.get("name") or "").lower():
                return step
    raise AssertionError(f"no step matching {name_fragment!r} in {WORKFLOW}")


def _gate_body() -> str:
    return _step("test gate")["run"]


def _code_lines(body: str) -> list[str]:
    """Executable lines only — comments must not satisfy an assertion."""
    return [ln for ln in body.splitlines() if not ln.strip().startswith("#")]


def test_the_gate_actually_runs_pytest():
    """Everything else here is vacuous if the command is not a test run."""
    body = " ".join(_code_lines(_gate_body()))
    assert "pytest" in body, "the gate step no longer invokes pytest"


def test_a_green_suite_is_the_only_path_that_skips_suite_red():
    body = _gate_body()
    code = _code_lines(body)
    green = [ln for ln in code if re.search(r"\$rc\s+-eq\s+0", ln)]
    assert green, "no explicit exit-0 branch found"
    assert any("exit 0" in ln for ln in green), (
        "the green branch must exit 0 without setting SUITE_RED")


@pytest.mark.parametrize("rc", [1, 2])
def test_a_red_suite_sets_suite_red(rc):
    code = " ".join(_code_lines(_gate_body()))
    assert re.search(rf"-eq\s+{rc}\b", code), (
        f"exit {rc} is no longer handled explicitly")
    assert "SUITE_RED=1" in code


def test_every_nonzero_exit_reaches_suite_red():
    """The correction: no non-zero exit may fall through to a bare publish.

    Structurally, the step must have exactly one terminal path that does NOT
    set SUITE_RED — the green one — and the fall-through (which catches exits
    3, 4 and 5) must set it.
    """
    code = _code_lines(_gate_body())
    text = "\n".join(code)

    assert text.count("SUITE_RED=1") >= 2, (
        "expected SUITE_RED to be set on BOTH the red branch and the "
        "could-not-run fall-through; found "
        f"{text.count('SUITE_RED=1')} occurrence(s).\n{text}")

    # The fall-through is whatever follows the last `-eq` guard. It must set
    # SUITE_RED before its exit.
    last_guard = max(
        (i for i, ln in enumerate(code) if re.search(r"\$rc\s+-eq", ln)),
        default=None)
    assert last_guard is not None, "no exit-code guards found at all"
    tail = "\n".join(code[last_guard + 1:])
    assert "SUITE_RED=1" in tail, (
        "the fall-through path (pytest exit 3/4/5 — including exit 5, "
        "'no tests collected') does not set SUITE_RED, so a suite that never "
        "ran would publish.\n" + tail)


def test_the_gate_step_still_exits_zero_on_every_path():
    """A non-zero STEP exit would cost the day's unrecoverable ESPN archival."""
    code = _code_lines(_gate_body())
    bad = [ln for ln in code if re.search(r"\bexit\s+[1-9]", ln)]
    assert not bad, (
        "the gate must exit 0 on every path — a non-zero exit skips the data "
        f"commit and loses that day's ESPN archival: {bad}")


def test_the_refresh_step_honors_suite_red():
    """SUITE_RED must reach --no-push, or withholding it means nothing."""
    body = _step("full refresh")["run"]
    assert "SUITE_RED" in body
    assert "--no-push" in body


def test_the_data_commit_is_unconditional():
    """The whole argument for exiting 0 rests on this step having no `if:`."""
    step = _step("commit & push regenerated")
    assert "if" not in step, (
        "the data-commit step gained an `if:` — the gate's exit-0-on-red "
        "design assumes archival is unconditional")
