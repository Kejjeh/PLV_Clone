"""The Monday brief must not credit the refresh with artifacts nothing writes.

WHY THIS FILE EXISTS (audit 2026-08-01, item 20)
------------------------------------------------
monday-brief.yml's header called itself "a pure READ of artifacts the daily
refresh already wrote (model_scorecard, verdict_scorecard, dpwin_history,
weekly_optimizer, matchup_leverage, season_sim)". Two of those six do have
scheduled producers (refresh steps 4.97 / 4.97b, Mondays). The other four do
not: `grep -rn "run_matchup_leverage|run_weekly_optimizer|run_season_sim"
scripts/xfp/refresh_dashboards.py scripts/xfp/refresh_all.py .github/workflows/`
returns nothing. Three of those four are nonetheless held to a ONE-DAY
freshness bar in build_monday_brief.STALE_AFTER_DAYS, so the brief reports them
stale essentially every week and the reader learns to ignore the line.

This test is data-driven on purpose: it reads the claim out of the header and
the freshness bars out of the composer, so it fires either when a new artifact
is added to the claim without a producer, or when someone wires a producer and
forgets to move the artifact back into the refresh-produced list.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
BRIEF = ROOT / "scripts" / "xfp" / "build_monday_brief.py"


def _constant(name: str) -> dict:
    tree = ast.parse(BRIEF.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in build_monday_brief.py")


def _header_comment() -> str:
    lines = []
    for line in (WORKFLOWS / "monday-brief.yml").read_text(encoding="utf-8").splitlines():
        if line.startswith("on:"):
            break
        lines.append(re.sub(r"^#\s?", "", line))
    return "\n".join(lines)


def _scheduled_sources() -> str:
    """Everything the scheduled pipeline actually EXECUTES.

    Comments are excluded on both sides — a workflow header that names a
    script is a claim about the pipeline, not part of it, and counting it
    would let this whole file pass vacuously the moment someone documents the
    gap it exists to detect. Python comment lines are dropped; for workflows
    only the steps' `run:` blocks are read.
    """
    parts = []
    for py in ("refresh_dashboards.py", "refresh_all.py"):
        text = (ROOT / "scripts" / "xfp" / py).read_text(encoding="utf-8")
        parts += [ln for ln in text.splitlines() if not ln.strip().startswith("#")]
    for wf in WORKFLOWS.glob("*.yml"):
        import yaml as _yaml
        doc = _yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        for spec in (doc.get("jobs") or {}).values():
            for step in spec.get("steps", []):
                if step.get("run"):
                    parts.append(step["run"])
    return "\n".join(parts)


def _has_scheduled_producer(artifact: str) -> bool:
    regen = _constant("REGEN")[artifact]
    scripts = re.findall(r"[\w./]+\.py", regen)
    scheduled = _scheduled_sources()
    return any(s in scheduled for s in scripts)


def test_the_producer_probe_is_not_vacuous():
    """Anti-vacuity guard for every other test in this file.

    The whole file is meaningless if _has_scheduled_producer() answers True for
    everything. These two are the ground truth as of 2026-08-01: the scorecards
    ARE produced (refresh steps 4.97 / 4.97b) and the decision-layer engines are
    NOT invoked by any workflow or either refresh driver. If wiring the decision
    engines in is what broke this test, delete the assertion — that is the win.
    """
    assert _has_scheduled_producer("model_scorecard.csv")
    assert not _has_scheduled_producer("matchup_leverage.json")
    assert not _has_scheduled_producer("weekly_optimizer.json")
    assert not _has_scheduled_producer("season_sim.json")


def test_the_header_claims_only_artifacts_the_pipeline_actually_produces():
    """"the daily refresh already wrote (...)" must be true of every name."""
    header = _header_comment()
    m = re.search(r"daily refresh already\s+wrote \(([^)]*)\)", header, re.S)
    assert m, ("monday-brief.yml no longer states which artifacts the refresh "
               "writes — keep the claim, keep it checkable")

    claimed = [n.strip() for n in m.group(1).replace("\n", " ").split(",") if n.strip()]
    regen = _constant("REGEN")
    unproduced = []
    for name in claimed:
        keys = [k for k in regen if k.startswith(name)]
        assert keys, f"header names {name!r}, which is not an artifact the brief reads"
        if not any(_has_scheduled_producer(k) for k in keys):
            unproduced.append(name)

    assert not unproduced, (
        "the header credits the daily refresh with artifacts no scheduled job "
        f"produces: {unproduced} — correct the header or wire the producers")


def test_every_hand_run_artifact_is_named_as_such_in_the_header():
    """A reader must be told which artifacts only an interactive run refreshes."""
    header = _header_comment()
    regen = _constant("REGEN")
    for artifact in regen:
        if _has_scheduled_producer(artifact):
            continue
        stem = artifact.split(".")[0]
        assert stem in header, (
            f"{artifact} has no scheduled producer and is not mentioned in "
            "monday-brief.yml's header — its staleness will read as a pipeline "
            "failure rather than as a hand-run artifact")


def test_the_one_day_freshness_bars_are_documented_as_hand_run():
    """The bars that fire weekly are exactly the unscheduled decision layer."""
    stale = _constant("STALE_AFTER_DAYS")
    daily = {a for a, days in stale.items() if days <= 1}
    assert daily, "no artifact carries a one-day bar any more — update this spec"

    header = _header_comment()
    for artifact in sorted(daily):
        if _has_scheduled_producer(artifact):
            continue
        # Uppercase on purpose: the header already says "a hand-run would" in
        # passing, which must not be mistaken for the deliberate marker.
        assert "HAND-RUN" in header, (
            f"{artifact} is held to a one-day bar with no scheduled producer; "
            "the header must mark the decision-layer artifacts HAND-RUN")
