"""The publish gate — the guard that stops stale projections shipping.

WHY THIS FILE EXISTS (audit 2026-08-01, items 16/32/51)
-------------------------------------------------------
`refresh_dashboards.main()` refuses to publish when the model rebuild (step 2)
failed, because every dashboard below step 2 would then be rendered from
YESTERDAY's projections. That guard is the single most consequential branch in
the nightly pipeline and it had no test at all (item 32).

It also announced itself only by printing and returning, so the nightly
workflow saw exit 0, reported a green job, and committed the stale-projection
CSVs anyway (item 16). The driver's exit code is deliberately NOT changed here:
daily-refresh.yml's `Commit & push regenerated plv_clone data` step carries no
`if:`, so a non-zero exit would permanently drop a day of ESPN transaction and
roster archival that rolls off the API in 7-14 days. The gate announces itself
through a marker file the workflow reads instead.

Every test drives main() with `run` replaced by a recorder, so no subprocess is
ever launched. Assertions use subset semantics — main() has a Monday-only
branch, so the exact command list differs by weekday.
"""
from __future__ import annotations

import ast
import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

import refresh_dashboards as R  # noqa: E402


class Recorder:
    """Stands in for refresh_dashboards.run, recording every step issued."""

    def __init__(self, fail_labels: tuple[str, ...] = ()):
        self.fail_labels = fail_labels
        self.calls: list[tuple[str, str]] = []

    def __call__(self, label, cmd, cwd=None, timeout=900, env=None):
        self.calls.append((label, cmd))
        return not any(label.startswith(f) for f in self.fail_labels)

    @property
    def commands(self) -> str:
        return "\n".join(cmd for _, cmd in self.calls)


@pytest.fixture
def driver(monkeypatch, tmp_path):
    """main() wired to a recorder, with ROOT pointed at a scratch tree."""
    monkeypatch.setenv("PLV_ESPN_SNAPSHOT", "0")
    monkeypatch.setenv("PLV_ESPN_SNAPSHOT_TTL_MIN", "1")
    monkeypatch.setattr(R, "ROOT", tmp_path)
    (tmp_path / "data" / "outputs").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["refresh_dashboards.py"])

    def _drive(*fail_labels: str) -> Recorder:
        rec = Recorder(fail_labels)
        monkeypatch.setattr(R, "run", rec)
        R.main()
        return rec

    return _drive


MODEL_REBUILD = "2. Rebuild xFP models"


def test_a_gated_publish_announces_itself_to_the_caller(driver, tmp_path):
    """The nightly job must be able to SEE that the publish was withheld.

    Printing it into a 140-minute log the workflow never reads is not an
    announcement: the job reported green and committed the stale CSVs anyway.
    """
    rec = driver(MODEL_REBUILD)

    assert "git push" not in rec.commands, "a gated run must not publish"

    marker = R.publish_gated_marker()
    assert marker.exists(), (
        "a gated run left no caller-visible signal — the workflow cannot tell "
        "a gated run from a clean one")
    assert marker.read_text(encoding="utf-8").startswith(date.today().isoformat())


def test_a_failed_model_rebuild_publishes_nothing(driver):
    """Audit F2, finally under test: stale projections must not reach Pages."""
    rec = driver(MODEL_REBUILD)

    assert "git add" not in rec.commands
    assert "git commit" not in rec.commands
    assert "git push" not in rec.commands


def test_a_failed_model_rebuild_still_runs_the_fail_soft_builds(driver):
    """The gate withholds the PUBLISH, not the work.

    The local dashboards are still rebuilt so an operator can inspect exactly
    what would have shipped; only the git steps are withheld.
    """
    rec = driver(MODEL_REBUILD)

    assert "build_matchup_dashboard.py" in rec.commands
    assert "build_xfp_board_dashboard.py" in rec.commands


def test_a_failed_profiles_build_withholds_only_the_profiles_pages(driver):
    """One broken page must not withhold the other five dashboards."""
    rec = driver("4.35")

    adds = [c for c in rec.commands.splitlines() if c.startswith("git add")]
    if not adds:
        pytest.skip("publish block emitted no git add — the untracked "
                    "xfp-model/ sibling is absent on this checkout")
    add = adds[0]
    for page in R.PUBLISH_PAGES_CORE:
        assert page in add, f"{page} must still publish"
    for page in R.PUBLISH_PAGES_PROFILES:
        assert page not in add, (
            f"{page} came from a failed build and must be withheld")


def test_no_step_outcome_is_overwritten_by_a_later_step():
    """Every step's pass/fail flag must stay readable for the whole run.

    main() carries ~30 `ok_*` locals and the publish gate is one of them, so a
    name bound by two different steps is one edit away from a step gating on
    another step's outcome. `ok_bs` was bound by BOTH the boxscore bridge (1.5)
    and the bat-speed accumulator (1.65): harmless only because each was read
    before the next rebind. Structural, because the harm is latent by nature —
    it appears the moment someone adds a reader.
    """
    src = (Path(R.__file__)).read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "main")

    seen: dict[str, int] = {}
    clashes = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "run"):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in seen:
                clashes.append(f"{target.id} (lines {seen[target.id]} and {target.lineno})")
            seen[target.id] = target.lineno

    assert not clashes, (
        "a refresh step's outcome flag is rebound by a later step: "
        + "; ".join(clashes))


def test_a_clean_run_clears_the_gate_marker(driver, tmp_path):
    """A marker that outlives its run would alert on every later night."""
    marker = R.publish_gated_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("2026-01-01T00:00:00", encoding="utf-8")

    driver()  # nothing fails

    assert not marker.exists(), "yesterday's gate marker must not persist"
