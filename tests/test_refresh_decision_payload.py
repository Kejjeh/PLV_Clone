"""index.html must be built AFTER the decision payload it embeds.

WHY THIS FILE EXISTS (audit 2026-08-01, item 13)
------------------------------------------------
The published index.html carried `window.XFP_DECISION = null` on 10 of its last
12 publishes (07-21 through 07-29 was nine consecutive nulls), so the Decision
tab was dead for over a week without a single error in the log.

The cause is an ORDERING inversion, not a broken builder.
build_index_dashboard.py embeds data/outputs/console_data.json only when its
`generated_at` date is TODAY (build_index_dashboard.py:5021-5034) — a good
check, and the only thing preventing a silently stale payload being shown as
current. But the index build is the LAST stage of refresh_all.py, i.e. inside
driver step 2, while console_data.json is written by the matchup build (step 4)
and the fallback writer (step 4.3), both later. The page was therefore always
written minutes BEFORE its own payload: on the 2026-07-31 run, index.html
landed 09:18 and console_data.json 09:22.

The spec below is about the ORDER of the commands the driver issues, asserted
from what it actually ran — not from source text.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

import refresh_dashboards as R  # noqa: E402


@pytest.fixture
def issued(monkeypatch, tmp_path):
    """Every command main() issues, in order, with nothing executed."""
    monkeypatch.setenv("PLV_ESPN_SNAPSHOT", "0")
    monkeypatch.setenv("PLV_ESPN_SNAPSHOT_TTL_MIN", "1")
    monkeypatch.setattr(R, "ROOT", tmp_path)
    (tmp_path / "data" / "outputs").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["refresh_dashboards.py", "--no-push"])

    commands: list[str] = []

    def recorder(label, cmd, cwd=None, timeout=900, env=None):
        commands.append(cmd)
        return True

    monkeypatch.setattr(R, "run", recorder)
    R.main()
    return commands


def _first_index(commands, needle) -> int:
    for i, cmd in enumerate(commands):
        if needle in cmd:
            return i
    raise AssertionError(f"the driver never issued a command containing {needle!r}")


def test_index_html_is_built_after_the_decision_payload_it_embeds(issued):
    """The Decision tab's payload must exist before the page that embeds it."""
    payload = _first_index(issued, "build_console_data.py")
    page = _first_index(issued, "build_index_dashboard.py")

    assert page > payload, (
        "index.html is emitted before console_data.json is written, so its "
        "same-day freshness check can never pass and the Decision tab ships "
        "as window.XFP_DECISION = null")


def test_the_decision_payload_is_written_after_the_matchup_build(issued):
    """Ordering the fix depends on: matchup is the authoritative writer."""
    assert _first_index(issued, "build_matchup_dashboard.py") < \
           _first_index(issued, "build_console_data.py")
