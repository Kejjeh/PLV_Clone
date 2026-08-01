"""What the nightly workflow does with the driver's gate marker.

WHY THIS FILE EXISTS (audit 2026-08-01, item 16)
------------------------------------------------
refresh_dashboards.main() returns instead of exiting non-zero when the publish
is gated, so daily-refresh.yml sees exit 0, reports a green job, and its
`git add data` step commits the stale-projection CSVs. The driver now drops a
PUBLISH_GATED marker (tests/test_refresh_publish_gate.py); this file asserts
the workflow actually READS it.

These tests EXECUTE the step's PowerShell rather than grepping it, because the
defect class here is behavioral (a marker written but never read looks fine in
a diff). GitHub's `shell: powershell` runs Windows PowerShell with
$ErrorActionPreference = 'Stop', which the harness reproduces.
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
        doc = yaml.safe_load(fh)
    return doc["jobs"]["refresh"]["steps"]


def _step_mentioning(token: str) -> dict:
    hits = [s for s in _steps() if token in (s.get("run") or "")]
    assert hits, f"no step in daily-refresh.yml mentions {token!r}"
    assert len(hits) == 1, f"{token!r} appears in {len(hits)} steps: ambiguous"
    return hits[0]


def _run_block(script: str, cwd: Path, tmp_path: Path) -> tuple[str, dict, str]:
    """Execute a workflow run block. Returns (stdout, GITHUB_ENV map, summary)."""
    gh_env = tmp_path / "gh_env.txt"
    gh_sum = tmp_path / "gh_summary.md"
    gh_env.write_text("", encoding="utf-8")
    gh_sum.write_text("", encoding="utf-8")
    ps1 = tmp_path / "step.ps1"
    ps1.write_text("$ErrorActionPreference = 'Stop'\n" + script, encoding="utf-8")

    env = dict(os.environ)
    env["GITHUB_ENV"] = str(gh_env)
    env["GITHUB_STEP_SUMMARY"] = str(gh_sum)
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-File", str(ps1)],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"the step must never fail the job: exit={proc.returncode}\n{proc.stderr}")

    exported = {}
    # PS 5.1's `Out-File -Encoding utf8` prepends a BOM when the target is
    # empty. The runner's env-file reader strips it (commit 0eb473a carries a
    # SCORECARD_ALERT marker produced by this exact idiom), so the harness
    # does too rather than pretending it is a defect.
    for line in gh_env.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            exported[k.strip()] = v.strip()
    return proc.stdout, exported, gh_sum.read_text(encoding="utf-8")


def test_the_nightly_job_reports_a_gated_publish(tmp_path):
    """A run whose model rebuild failed must not look like a normal night."""
    step = _step_mentioning("'.cache/PUBLISH_GATED'")
    cache = tmp_path / ".cache"
    cache.mkdir(parents=True)
    (cache / "PUBLISH_GATED").write_text("2026-08-01T02:55:10", encoding="utf-8")

    stdout, exported, summary = _run_block(step["run"], tmp_path, tmp_path)

    assert exported.get("PUBLISH_GATED") == "1", (
        "the gate must be exported so the commit step can mark the commit")
    assert "GATED" in summary.upper(), "the job summary must name the gate"
    assert "STALE" in (stdout + summary).upper()


def test_a_clean_night_exports_no_gate(tmp_path):
    """The alert must not fire when the model rebuild succeeded."""
    step = _step_mentioning("'.cache/PUBLISH_GATED'")
    (tmp_path / ".cache").mkdir(parents=True)

    stdout, exported, summary = _run_block(step["run"], tmp_path, tmp_path)

    assert "PUBLISH_GATED" not in exported, "no marker on disk means no alert"
    assert "GATED" not in summary.upper()


def test_the_data_commit_is_marked_when_the_publish_was_gated():
    """The stale-CSV commit must be legible as stale in `git log` forever."""
    commit = next(s for s in _steps() if "Commit" in s.get("name", ""))
    run = commit["run"]
    assert "$alert = $env:SCORECARD_ALERT" in run, "existing marker source intact"
    assert "PUBLISH_GATED" in run, (
        "the commit step must fold the publish gate into its message marker")
    assert 'git commit -m "${alert}refresh: daily auto-refresh $stamp"' in run
