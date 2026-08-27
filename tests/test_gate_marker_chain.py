"""The PUBLISH_GATED marker chain, checked WITHOUT PowerShell.

WHY THIS FILE EXISTS
`test_refresh_workflow_gate.py` asserts that the nightly workflow READS the
gate marker the driver writes. Its reasoning is right — "a marker written but
never read looks fine in a diff", so it executes the step's real PowerShell
rather than grepping it.

And it skips all three of its tests without PowerShell. On Linux those three
invariants are pinned by nothing, which is how PR #80's exit-5 bug shipped
past its own dedicated test file (issue #81).

This file checks the same chain statically, across the three files it spans:

    refresh_dashboards.publish_gated_marker()   writes ROOT/.cache/PUBLISH_GATED
      -> daily-refresh.yml "Surface a GATED publish"  reads that same relative
         path and exports PUBLISH_GATED=1
      -> daily-refresh.yml "Commit & push"      reads $env:PUBLISH_GATED and
         marks the commit message

A break anywhere in that chain silently produces a green nightly that commits
stale-projection CSVs with nothing saying so — the exact defect (audit
2026-08-01 item 16) the marker was introduced to fix.

Static checks cannot prove the PowerShell RUNS; the sibling file does that
where it can. These two are complementary, not redundant. (Added 2026-08-27.)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "daily-refresh.yml"
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(ROOT / "src"))


def _job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["refresh"]


def _step(fragment: str) -> dict:
    hits = [s for s in _job()["steps"]
            if fragment.lower() in (s.get("name") or "").lower()]
    assert hits, f"no step named like {fragment!r} in daily-refresh.yml"
    assert len(hits) == 1, f"{fragment!r} matched {len(hits)} steps"
    return hits[0]


def _code(step: dict) -> str:
    """Executable lines only — a comment must never satisfy an assertion."""
    return "\n".join(ln for ln in (step.get("run") or "").splitlines()
                     if not ln.strip().startswith("#"))


def _marker_relpath() -> str:
    rd = pytest.importorskip("refresh_dashboards")
    return rd.publish_gated_marker().relative_to(rd.ROOT).as_posix()


# ── link 1: the driver writes where the workflow looks ───────────────────────

def test_the_workflow_reads_the_path_the_driver_writes():
    """The 'written but never read' defect, as a cross-file assertion."""
    rel = _marker_relpath()
    body = _code(_step("surface a gated publish"))
    assert rel in body.replace("\\", "/"), (
        f"the driver writes {rel!r} but the gate step does not mention it. "
        f"A marker written to one path and read from another looks correct in "
        f"both files and reports every gated night as clean.\n{body}")


def test_the_marker_lives_under_a_gitignored_directory():
    """.cache must stay ignored, or `git add data` would commit the marker."""
    rel = _marker_relpath()
    assert rel.startswith(".cache/"), (
        f"the gate marker moved to {rel!r}; if it is no longer under .cache it "
        f"can be committed, and it would then alert on a later clean night")
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^\.?/?\.cache/?", ignored, re.M), (
        ".cache is not in .gitignore")


# ── link 2: the gate step exports the flag ───────────────────────────────────

def test_the_gate_step_exports_publish_gated():
    body = _code(_step("surface a gated publish"))
    assert "PUBLISH_GATED=1" in body
    assert "GITHUB_ENV" in body, (
        "PUBLISH_GATED must go to $GITHUB_ENV or later steps cannot see it")


def test_the_gate_step_runs_even_when_the_refresh_failed():
    """Without `if: always()` the alert dies with the thing it reports on."""
    step = _step("surface a gated publish")
    assert str(step.get("if", "")).strip() == "always()", (
        f"gate-surfacing step has if={step.get('if')!r}; it must be always()")


# ── link 3: the commit step consumes it ──────────────────────────────────────

def test_the_commit_step_marks_a_gated_commit():
    body = _code(_step("commit & push regenerated"))
    assert "PUBLISH_GATED" in body, (
        "the data-commit step does not read PUBLISH_GATED, so a stale-CSV "
        "commit is indistinguishable from a clean one in `git log` — which is "
        "the only place it stays legible weeks later")
    assert "GATED" in body


def test_the_gate_step_precedes_the_commit_step():
    """$GITHUB_ENV only reaches LATER steps — order is the whole mechanism."""
    names = [(s.get("name") or "").lower() for s in _job()["steps"]]
    gate = next(i for i, n in enumerate(names) if "surface a gated publish" in n)
    commit = next(i for i, n in enumerate(names) if "commit & push regenerated" in n)
    assert gate < commit, (
        f"the gate step (index {gate}) must run BEFORE the commit step "
        f"(index {commit}) — $GITHUB_ENV is only visible to subsequent steps")
