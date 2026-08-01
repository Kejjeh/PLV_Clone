"""Refresh step registration and ordering, asserted from what main() ACTUALLY issues.

WHY THIS FILE EXISTS (audit 2026-08-01, items 39 + 40)
------------------------------------------------------
Two refresh guards were pinned to the SOURCE TEXT of refresh_dashboards.py and
could not fail on the regression they existed to catch:

  item 39 — tests/test_bat_speed_daily.py asserted `"1.65" in src`. The module
    docstring (line 12) contains the band label "1.65-1.98 feature/rolling
    caches...", so deleting the entire step at line 285 left that assertion
    green. Only the `"build_bat_speed_daily.py" in src` half was load-bearing,
    and neither half said anything about the NON-GATING claim in the test's own
    name.

  item 40 — tests/test_audit_regressions_0704.py compared `src.index(marker)`
    byte offsets. Commenting the live_blend producer OUT entirely left all three
    ordering assertions True, because the commented line still contains the
    marker string.

Both are replaced here by driving `main()` with a recorder in place of `run`, so
the assertions are made against the real emitted (label, command) sequence. No
subprocess is ever launched and no file outside tmp_path is touched.

There is deliberately ONE recorder in this file rather than a copy per concern;
when refresh_dashboards.main() eventually grows the declarative step list the
audit proposed, these assertions move onto that structure and the recorder goes
away. Assertions use subset/ordering semantics — main() has a Monday-only branch,
so the exact command list differs by weekday.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

import refresh_dashboards as R  # noqa: E402


class StepRecorder:
    """Stands in for refresh_dashboards.run, recording every step issued."""

    def __init__(self, fail_substrings: tuple[str, ...] = ()):
        self.fail_substrings = fail_substrings
        self.calls: list[tuple[str, str]] = []

    def __call__(self, label, cmd, cwd=None, timeout=900, env=None):
        self.calls.append((label, cmd))
        return not any(s in cmd or s in label for s in self.fail_substrings)

    # -- queries -------------------------------------------------------------
    @property
    def commands(self) -> list[str]:
        return [cmd for _, cmd in self.calls]

    @property
    def labels(self) -> list[str]:
        return [label for label, _ in self.calls]

    def issued(self, needle: str) -> bool:
        return any(needle in cmd for cmd in self.commands)

    def first_index(self, needle: str) -> int:
        """Position of the first step whose COMMAND (not comment) contains needle."""
        for i, cmd in enumerate(self.commands):
            if needle in cmd:
                return i
        raise AssertionError(
            f"no refresh step issues {needle!r}. Emitted commands:\n"
            + "\n".join(f"  {i:3d}  {c}" for i, c in enumerate(self.commands)))

    def first_label_index(self, needle: str) -> int:
        for i, label in enumerate(self.labels):
            if needle in label:
                return i
        raise AssertionError(
            f"no refresh step carries label {needle!r}. Emitted labels:\n"
            + "\n".join(f"  {i:3d}  {lb}" for i, lb in enumerate(self.labels)))


@pytest.fixture
def drive(monkeypatch, tmp_path):
    """main() wired to a StepRecorder, with ROOT pointed at a scratch tree."""
    monkeypatch.setenv("PLV_ESPN_SNAPSHOT", "0")
    monkeypatch.setenv("PLV_ESPN_SNAPSHOT_TTL_MIN", "1")
    monkeypatch.setattr(R, "ROOT", tmp_path)
    (tmp_path / "data" / "outputs").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["refresh_dashboards.py"])

    def _drive(*fail_substrings: str) -> StepRecorder:
        rec = StepRecorder(fail_substrings)
        monkeypatch.setattr(R, "run", rec)
        R.main()
        return rec

    return _drive


# ── item 39: the bat-speed accumulator is registered, and is non-gating ──────

def test_the_refresh_issues_the_bat_speed_daily_accumulator(drive):
    """The store is the substrate for the in-season bat-speed study — the one
    declared re-open condition for the closed in-season-delta family. If the step
    stops running, the store silently stops growing."""
    rec = drive()
    assert rec.issued("build_bat_speed_daily.py"), (
        "the bat-speed daily accumulator is not in the refresh chain")


def test_a_failed_bat_speed_step_does_not_gate_the_publish(drive):
    """The claim the old test's NAME made and its body never checked.

    The store is idempotent on (batter, game_date), so a failed day backfills on
    the next run — it must never be allowed to withhold the dashboards.
    """
    clean = drive()
    if not any("git push" in c for c in clean.commands):
        pytest.skip("clean run emitted no git push — the untracked xfp-model/ "
                    "sibling is absent on this checkout, so the publish leg "
                    "cannot be exercised here")

    rec = drive("build_bat_speed_daily.py")
    assert any("git push" in c for c in rec.commands), (
        "a failed bat-speed accumulator withheld the publish — it is declared "
        "non-gating (only the step-2 model rebuild gates)")
    later = rec.commands[rec.first_index("build_bat_speed_daily.py") + 1:]
    assert any("build_matchup_dashboard" in c for c in later), (
        "the pipeline stopped after the bat-speed failure instead of continuing")


# ── item 40: producers run before their consumers ───────────────────────────

def test_live_blend_is_built_before_matchup_consumes_it(drive):
    """Reversed for weeks (fixed 2026-07-04, a8ce49c): matchup.html rendered
    yesterday's blend every night."""
    rec = drive()
    assert rec.first_index("build_live_blend_xfp.py") < \
        rec.first_label_index("4. Build matchup.html"), \
        f"live_blend must build before matchup consumes it:\n{rec.labels}"


@pytest.mark.parametrize("producer", ["stream_the_stack.py",
                                      "build_hitter_boom_stack_daily.py"])
def test_boom_stack_producers_run_before_triangulate(drive, producer):
    rec = drive()
    assert rec.first_index(producer) < rec.first_index("build_triangulate_dashboard"), \
        f"{producer} (boom producer) must run before triangulate consumes it"
