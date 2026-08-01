"""The nightly tripwire alert must know how old its evidence is.

WHY THIS FILE EXISTS (audit 2026-08-01, item 26)
------------------------------------------------
The scorecard is written by refresh step 4.97, which is gated on
`datetime.now().weekday() == 0` — Mondays only. The alert step read the CSV
every night, parsed `$asof` for DISPLAY, and set the commit-message marker
purely off the FAIL count, with no comparison against the run date. So one
Monday FAIL got re-reported as if current for up to six consecutive nights.

Observed: data/outputs/model_scorecard.csv carried one date (2026-07-30) with
one FAIL, and commit 0eb473a ("ALERT[1 tripwire FAIL] refresh: daily
auto-refresh 2026-07-31") re-reported it the next night.

Visibility-only: this changes what the step PRINTS and whether it exports the
marker, never any data. Suppressing the marker past the threshold must NOT read
as an all-clear -- a still-broken sentinel is still broken -- so the stale
branch emits the same emphatic COULD NOT CHECK line the absent-file branch uses.

The tests EXECUTE the step's PowerShell against synthetic scorecards.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "daily-refresh.yml"

pytestmark = pytest.mark.skipif(
    shutil.which("powershell") is None,
    reason="Windows PowerShell not on PATH (the self-hosted runner's shell)")

HEADER = "date,section,metric,segment,value,status,note\n"


def _alert_step() -> dict:
    with open(WORKFLOW, "r", encoding="utf-8") as fh:
        steps = yaml.safe_load(fh)["jobs"]["refresh"]["steps"]
    return next(s for s in steps if "Surface scorecard" in s.get("name", ""))


def _scorecard(tmp_path: Path, as_of: date, status: str = "FAIL") -> None:
    out = tmp_path / "data" / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / "model_scorecard.csv").write_text(
        HEADER
        + f"{as_of.isoformat()},data_health,fa_join_coverage,all,0.4,{status},synthetic\n",
        encoding="utf-8")


def _run_alert(tmp_path: Path) -> tuple[str, dict, str]:
    gh_env = tmp_path / "gh_env.txt"
    gh_sum = tmp_path / "gh_summary.md"
    gh_env.write_text("", encoding="utf-8")
    gh_sum.write_text("", encoding="utf-8")
    ps1 = tmp_path / "alert.ps1"
    ps1.write_text("$ErrorActionPreference = 'Stop'\n" + _alert_step()["run"],
                   encoding="utf-8")

    env = dict(os.environ)
    env["GITHUB_ENV"] = str(gh_env)
    env["GITHUB_STEP_SUMMARY"] = str(gh_sum)
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-File", str(ps1)],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"the alert step must never gate: {proc.stderr}"

    exported = {}
    for line in gh_env.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            exported[k.strip()] = v.strip()
    return proc.stdout, exported, gh_sum.read_text(encoding="utf-8-sig")


def test_a_days_old_scorecard_reports_could_not_check_not_an_alert(tmp_path):
    """Four days back: the evidence is too old to speak for tonight."""
    _scorecard(tmp_path, date.today() - timedelta(days=4))

    stdout, exported, summary = _run_alert(tmp_path)

    assert "COULD NOT CHECK" in (stdout + summary), (
        "a days-old scorecard must read as unverified, not as tonight's news")
    assert not exported.get("SCORECARD_ALERT", ""), (
        "an ALERT marker on a days-old FAIL puts a stale claim into `git log` "
        "forever")


def test_a_stale_scorecard_is_not_reported_as_an_all_clear(tmp_path):
    """Suppressing the marker must not silence a genuinely broken sentinel."""
    _scorecard(tmp_path, date.today() - timedelta(days=4))

    stdout, _exported, summary = _run_alert(tmp_path)
    both = (stdout + summary)

    assert "fa_join_coverage" in both, (
        "the FAIL detail must still be visible even when the marker is dropped")
    assert "Not an all-clear" in both or "NOT an all-clear" in both


def test_todays_scorecard_still_raises_its_alert(tmp_path):
    """Behaviour preservation: a current FAIL must still mark the commit."""
    _scorecard(tmp_path, date.today())

    _stdout, exported, _summary = _run_alert(tmp_path)

    assert exported.get("SCORECARD_ALERT", "").startswith("ALERT["), (
        "today's FAIL must still prefix the commit message")


def test_mondays_scorecard_read_on_tuesday_is_still_current(tmp_path):
    """The threshold must respect the Monday-only cadence of step 4.97."""
    _scorecard(tmp_path, date.today() - timedelta(days=1))

    _stdout, exported, _summary = _run_alert(tmp_path)

    assert exported.get("SCORECARD_ALERT", "").startswith("ALERT["), (
        "a one-day-old scorecard is the NORMAL case on a Tuesday - suppressing "
        "it would silence every real FAIL")
