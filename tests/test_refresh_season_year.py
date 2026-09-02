"""The nightly ingestion steps must follow the calendar, not a literal.

WHY THIS FILE EXISTS (audit 2026-08-01, item 42)
------------------------------------------------
Three ingestion steps in the driver pinned the season to `2026`. On
2027-01-01 the statcast pull would keep growing statcast_2026.parquet and
`plv update` would rebuild 2026's boards, both reporting success — a silent
data hole at exactly the moment nobody is watching the pipeline.

Two of the three underlying scripts already default to the current calendar
year (refresh_xfp_statcast.py:84, plv_clone.cli.update), so the literal is
redundant today and wrong in January: dropping it is a no-op NOW, which is the
argument for shipping it now rather than in the off-season.

The third does NOT: build_batter_sb_gamelog.py's `--years` default is None
meaning EVERY year in the batter-years table (2018..current), so a bare removal
would trigger a ~9-season re-pull that blows the step's 900s timeout. That one
needs a COMPUTED current year, which is what season_year() supplies.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

import refresh_dashboards as R  # noqa: E402

# Non-capturing: findall must report the offending YEAR ("2026"), not the
# group ("20"), or the failure message names nothing useful.
SEASON_LITERAL = re.compile(r"\b(?:19|20)\d{2}\b")


@pytest.fixture
def issued(monkeypatch, tmp_path):
    def _drive() -> list[str]:
        monkeypatch.setenv("PLV_ESPN_SNAPSHOT", "0")
        monkeypatch.setenv("PLV_ESPN_SNAPSHOT_TTL_MIN", "1")
        monkeypatch.setattr(R, "ROOT", tmp_path)
        (tmp_path / "data" / "outputs").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sys, "argv", ["refresh_dashboards.py", "--no-push"])
        commands: list[str] = []
        monkeypatch.setattr(
            R, "run",
            lambda label, cmd, cwd=None, timeout=900, env=None: (
                commands.append(cmd), True)[1])
        R.main()
        return commands

    return _drive


def _only(commands, needle) -> str:
    hits = [c for c in commands if needle in c]
    assert hits, f"the driver issued no command containing {needle!r}"
    return hits[0]


def test_the_statcast_pull_names_no_season_literal(issued):
    cmd = _only(issued(), "refresh_xfp_statcast.py")
    found = SEASON_LITERAL.findall(cmd)
    assert not found, (
        f"the statcast ingestion command pins a season: {cmd!r} — on the first "
        "run of a new season it would keep growing the OLD season's parquet")


def test_the_plv_board_rebuild_is_retired(issued):
    """Step 1.98 (weekly `plv update`) was retired 2026-09-01 — positions come
    from the live map (ADR-0009 addendum). The nightly must not quietly
    re-grow a dependency on the dormant chain; a re-added step would also
    need this file's season-literal check back."""
    hits = [c for c in issued() if "plv_clone.cli update" in c]
    assert not hits, f"the nightly issues plv update again: {hits!r}"


def test_the_sb_gamelog_pull_targets_the_current_season(issued):
    """This one must be COMPUTED, not deleted: its default is all-years."""
    cmd = _only(issued(), "build_batter_sb_gamelog.py")
    assert f"--years {datetime.now().year}" in cmd, (
        "the SB gamelog pull must name exactly the current season — dropping "
        "the flag re-pulls ~9 immutable seasons and blows the 900s timeout")


def test_the_ingestion_steps_follow_a_season_roll(issued, monkeypatch):
    """The whole point: next January the pipeline moves on by itself."""
    monkeypatch.setenv("PLV_SEASON_YEAR", "2031")
    cmd = _only(issued(), "build_batter_sb_gamelog.py")
    assert "--years 2031" in cmd
