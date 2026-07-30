"""Structural tests for the self-hosted (Windows PowerShell) GitHub workflows.

WHY THIS FILE EXISTS
--------------------
A workflow defect cannot be caught by running the code — nothing here executes
until the runner picks the job up, and a PowerShell parse error there just emails
a red run at 07:00. One such defect was already found by hand while building the
Monday brief and is now locked down below:

  A NON-ASCII character inside a `shell: powershell` run block can break the
  parser. Windows PowerShell 5.1 decodes the script with the system ANSI
  codepage; an em-dash (U+2014, UTF-8 `E2 80 94`) read as cp1252 ends in 0x94 =
  U+201D RIGHT DOUBLE QUOTATION MARK, which PowerShell treats as a STRING
  DELIMITER. An em-dash inside a double-quoted string therefore terminates it
  early and the whole step fails to parse. Ubuntu/bash jobs are unaffected, so
  the rule is scoped to the PowerShell jobs.

These are cheap invariants, not a substitute for a real run — a GitHub schedule
cannot be triggered from a test.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"

# The jobs that run on Josh's PC in his real working tree.
SELF_HOSTED = ("daily-refresh.yml", "monday-brief.yml", "pl-cache.yml")


def _load(name: str) -> dict:
    path = WORKFLOW_DIR / name
    assert path.exists(), f"{name} is missing from .github/workflows"
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _jobs(doc: dict) -> dict:
    return doc["jobs"]


def _powershell_steps(doc: dict):
    """(job_name, step_name, run_script) for every powershell-shelled step."""
    out = []
    for job_name, spec in _jobs(doc).items():
        default_shell = (spec.get("defaults", {}).get("run", {}) or {}).get("shell")
        for step in spec.get("steps", []):
            run = step.get("run")
            if run is None:
                continue
            shell = step.get("shell", default_shell)
            if shell == "powershell":
                out.append((job_name, step.get("name", "<unnamed>"), run))
    return out


@pytest.mark.parametrize("name", SELF_HOSTED)
def test_workflow_parses(name):
    doc = _load(name)
    assert _jobs(doc), f"{name} declares no jobs"
    # `on:` parses to the boolean True in YAML 1.1 — accept either key.
    triggers = doc.get("on", doc.get(True))
    assert isinstance(triggers, dict), f"{name} has no usable `on:` block"
    assert "schedule" in triggers, f"{name} must be scheduled"
    assert "workflow_dispatch" in triggers, (
        f"{name} must keep workflow_dispatch so it can be tested by hand")


@pytest.mark.parametrize("name", SELF_HOSTED)
def test_powershell_run_blocks_are_ascii_only(name):
    """The em-dash-becomes-a-smart-quote defect. See the module docstring."""
    offenders = []
    for job, step, run in _powershell_steps(_load(name)):
        for i, line in enumerate(run.splitlines(), 1):
            if not line.isascii():
                bad = sorted({c for c in line if not c.isascii()})
                offenders.append(f"{name}[{job}/{step}] line {i}: {bad!r} in {line.strip()[:80]!r}")
    assert not offenders, (
        "non-ASCII in a PowerShell run block can terminate a string early "
        "(cp1252 decoding turns an em-dash's last byte into a smart quote):\n"
        + "\n".join(offenders))


@pytest.mark.parametrize("name", SELF_HOSTED)
def test_runs_on_self_hosted_windows_in_joshs_tree(name):
    for job, spec in _jobs(_load(name)).items():
        assert spec.get("runs-on") == ["self-hosted", "Windows"], (
            f"{name}[{job}] must target the self-hosted Windows runner")
        run_defaults = spec.get("defaults", {}).get("run", {})
        assert run_defaults.get("shell") == "powershell", f"{name}[{job}] shell"
        assert run_defaults.get("working-directory") == r"C:\Users\Joshua\plv_clone", (
            f"{name}[{job}] must run in Josh's real working tree, not a checkout")
        assert isinstance(spec.get("timeout-minutes"), int), (
            f"{name}[{job}] needs an explicit timeout-minutes")


def test_monday_brief_does_not_collide_with_the_daily_refresh():
    """The schedule rationale, asserted rather than left in a comment.

    daily-refresh starts at 11:00 UTC with a 180-minute timeout, so its HARD
    ceiling is 14:00 UTC. The brief reads the artifacts that refresh writes
    (model_scorecard at step 4.97, verdict_scorecard at 4.97b), so it must start
    after that ceiling or it can read a half-written file.
    """
    refresh = _load("daily-refresh.yml")
    brief = _load("monday-brief.yml")

    r_cron = (refresh.get("on", refresh.get(True)))["schedule"][0]["cron"]
    b_cron = (brief.get("on", brief.get(True)))["schedule"][0]["cron"]

    r_min, r_hour = int(r_cron.split()[0]), int(r_cron.split()[1])
    b_min, b_hour, b_dow = (int(b_cron.split()[0]), int(b_cron.split()[1]),
                            b_cron.split()[4])
    r_timeout = refresh["jobs"]["refresh"]["timeout-minutes"]

    refresh_start = r_hour * 60 + r_min
    refresh_ceiling = refresh_start + r_timeout
    brief_start = b_hour * 60 + b_min

    assert brief_start > refresh_ceiling, (
        f"the brief starts at {b_hour:02d}:{b_min:02d} UTC but the refresh's hard "
        f"ceiling is {refresh_ceiling // 60:02d}:{refresh_ceiling % 60:02d} UTC — "
        f"it could read a half-written scorecard")
    assert b_dow == "1", "the brief is a MONDAY job (cron day-of-week 1)"


def test_monday_brief_runs_the_composer_and_commits_the_output():
    steps = _load("monday-brief.yml")["jobs"]["monday-brief"]["steps"]
    scripts = "\n".join(s.get("run", "") for s in steps)
    assert "scripts/xfp/build_monday_brief.py" in scripts
    assert "git add data/outputs/monday_brief.md" in scripts
    # Branch-aware push (root-caused 2026-07-21): never push a stale `main` ref.
    assert "git branch --show-current" in scripts
    assert "git push origin HEAD" in scripts
    assert "git push origin main" not in scripts


def test_monday_brief_commits_even_when_an_artifact_is_malformed():
    """Exit 2 = brief written but an upstream artifact was truncated.

    The brief must still land (the reader needs the rest of it); the alert is
    re-raised as a red job in a LATER step.
    """
    steps = _load("monday-brief.yml")["jobs"]["monday-brief"]["steps"]
    names = [s.get("name", "") for s in steps]
    compose = next(s for s in steps if "Compose" in s.get("name", ""))
    assert "if ($rc -eq 2)" in compose["run"]
    assert "exit 0" in compose["run"], "exit 2 must not stop the commit step"

    commit_i = next(i for i, n in enumerate(names) if "Commit" in n)
    reraise_i = next(i for i, n in enumerate(names) if "Re-raise" in n)
    assert reraise_i > commit_i, "the alert must be re-raised AFTER the brief commits"


def test_daily_refresh_alert_step_never_gates_the_data_work():
    """The refresh must still commit a day of data even if the alert breaks."""
    steps = _load("daily-refresh.yml")["jobs"]["refresh"]["steps"]
    names = [s.get("name", "") for s in steps]
    alert = next(s for s in steps if "Surface scorecard" in s.get("name", ""))

    assert alert.get("if") == "always()", "the alert must run even after a failed refresh"
    assert alert["run"].rstrip().endswith("exit 0"), (
        "every path through the alert step must exit 0 — it must never be the "
        "reason a refresh loses a day of data")
    assert "try {" in alert["run"] and "catch {" in alert["run"], (
        "detection failure must be caught and reported, not thrown")

    # It has to run BEFORE the commit, since it feeds the commit message.
    alert_i = next(i for i, n in enumerate(names) if "Surface scorecard" in n)
    commit_i = next(i for i, n in enumerate(names) if "Commit" in n)
    assert alert_i < commit_i


def test_daily_refresh_alert_surfaces_the_three_drift_sentinels_by_name():
    alert = next(s for s in _load("daily-refresh.yml")["jobs"]["refresh"]["steps"]
                 if "Surface scorecard" in s.get("name", ""))
    for sentinel in ("collision_team_reachability", "collision_smoke",
                     "fa_join_coverage"):
        assert sentinel in alert["run"], f"{sentinel} not named in the alert step"
    assert "DRIFT SENTINEL FAIL" in alert["run"]
    assert "GITHUB_STEP_SUMMARY" in alert["run"], "must write a job summary"
    assert "SCORECARD_ALERT" in alert["run"], "must export the commit-message marker"
    # A missing scorecard must read as "could not check", not as a pass.
    assert "COULD NOT CHECK" in alert["run"]


@pytest.mark.parametrize("name", SELF_HOSTED)
def test_get_content_declares_utf8(name):
    """Windows PowerShell 5.1's Get-Content defaults to the ANSI codepage.

    Reading a UTF-8 artifact without `-Encoding UTF8` renders every em-dash as
    mojibake. Caught for real in the Monday brief's job summary, where the
    decision block arrived in the notification as 'a-hat-euro-trademark' noise.
    """
    offenders = []
    for job, step, run in _powershell_steps(_load(name)):
        for i, line in enumerate(run.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "Get-Content" not in stripped:
                continue
            # Must name UTF8 specifically. `-Encoding ASCII` satisfies a bare
            # "-Encoding" check and still mangles every em-dash in the brief,
            # which is exactly the defect this guard exists to catch.
            if "-encoding utf8" not in stripped.lower():
                offenders.append(f"{name}[{job}/{step}] line {i}: {stripped[:90]}")
    assert not offenders, (
        "Get-Content without -Encoding UTF8 mangles non-ASCII on PS 5.1:\n"
        + "\n".join(offenders))


@pytest.mark.parametrize("name", SELF_HOSTED)
def test_out_file_declares_utf8(name):
    """Same hazard on the write side: Out-File defaults to the ANSI codepage."""
    offenders = []
    for job, step, run in _powershell_steps(_load(name)):
        for i, line in enumerate(run.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "Out-File" not in stripped:
                continue
            if "-encoding utf8" not in stripped.lower():
                offenders.append(f"{name}[{job}/{step}] line {i}: {stripped[:90]}")
    assert not offenders, ("Out-File without -Encoding utf8:\n" + "\n".join(offenders))


def test_daily_refresh_commit_message_carries_the_alert_marker():
    commit = next(s for s in _load("daily-refresh.yml")["jobs"]["refresh"]["steps"]
                  if "Commit" in s.get("name", ""))
    assert "$alert = $env:SCORECARD_ALERT" in commit["run"]
    assert 'git commit -m "${alert}refresh: daily auto-refresh $stamp"' in commit["run"]
