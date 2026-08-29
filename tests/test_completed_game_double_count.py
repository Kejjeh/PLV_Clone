"""A game already FINAL must not be projected again.

`project_player` projects every game from TODAY through week_end, but the live
ESPN score ALREADY contains what today's finished games produced. Projecting
them again counts them twice — realized points land in the WTD score AND in the
"remaining" projection.

Found 2026-08-29 (period 21, elimination round): four of Josh's hitters had
completed Saturday games being re-projected on top of a live score that already
included them, inflating P(win). The split-doubleheader case is the sharp edge —
NYY game 1 was Final while game 2 had not started, so a (team, date) key cannot
tell them apart and the ORDINAL within the day is load-bearing.

Deliberately scoped to FINAL games only. An in-progress game stays projectable:
only part of it is in the live score, and the SP-cap arithmetic depends on an
in-flight start remaining in `my_sp_events` until ESPN's statId-33 absorbs it
on finalize (see the banked-staleness note in leverage_engine.build_state).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
XFP = ROOT / "scripts" / "xfp"

bmd = pytest.importorskip("scripts.xfp.build_matchup_dashboard")


def _games(*dates):
    return [{"date": d, "is_home": True, "opp_team": "X"} for d in dates]


def test_split_dh_drops_only_the_completed_half():
    """The canonical 2026-08-29 shape: NYY game 1 Final, game 2 not started."""
    games = _games("2026-08-29", "2026-08-29", "2026-08-30")
    completed = {(147, "2026-08-29", 0): True}       # ordinal 0 == game 1
    out = bmd.drop_completed(games, 147, completed)
    assert len(out) == 2, "only the finished half of the DH may be dropped"
    assert [g["date"] for g in out] == ["2026-08-29", "2026-08-30"]


def test_second_half_of_dh_can_be_the_completed_one():
    games = _games("2026-08-29", "2026-08-29", "2026-08-30")
    out = bmd.drop_completed(games, 147, {(147, "2026-08-29", 1): True})
    assert len(out) == 2


def test_no_completed_map_is_a_passthrough():
    """Omitting the map must preserve the old behavior exactly."""
    games = _games("2026-08-29", "2026-08-30")
    assert bmd.drop_completed(games, 147, None) == games
    assert bmd.drop_completed(games, 147, {}) == games


def test_other_teams_completions_do_not_leak():
    games = _games("2026-08-29", "2026-08-30")
    out = bmd.drop_completed(games, 147, {(119, "2026-08-29", 0): True})
    assert len(out) == 2, "another team's final game must not drop this team's"


def test_in_progress_is_not_completed():
    """Only terminal states count — an in-flight game stays projectable."""
    assert "In Progress" not in bmd.COMPLETED_GAME_STATES
    assert "Warmup" not in bmd.COMPLETED_GAME_STATES
    assert "Pre-Game" not in bmd.COMPLETED_GAME_STATES
    assert {"Final", "Game Over"} <= bmd.COMPLETED_GAME_STATES


def test_project_player_accepts_the_kwarg():
    import inspect
    sig = inspect.signature(bmd.project_player)
    assert "completed_games" in sig.parameters


# ── structural guard: DISCOVER call sites, don't enumerate them (don't-do #18)

#: Call sites that legitimately skip the filter, with the reason.
EXEMPT = {
    # Backtests replay a historical window; there is no live score to
    # double-count against, and every game in the window is "final".
    "scripts/xfp/backtest_adjusters.py",
}


def _call_sites():
    out = []
    for path in sorted(XFP.rglob("*.py")):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        src = path.read_text(encoding="utf-8")
        if "project_player(" not in src:
            continue
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            nm = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if nm != "project_player":
                continue
            kwargs = {k.arg for k in node.keywords}
            out.append((rel, node.lineno, "completed_games" in kwargs))
    return out


def test_every_project_player_call_passes_completed_games():
    """A fix applied to a SUBSET of call sites is this repo's dominant bug
    shape — it fails silently rather than crashing. Walk the package so a new
    consumer is covered the day it is written."""
    sites = _call_sites()
    assert sites, "no project_player call sites found — the walker broke"
    missing = [f"{f}:{ln}" for f, ln, ok in sites
               if not ok and f not in EXEMPT]
    assert not missing, (
        "these project_player calls omit completed_games and will re-project "
        f"games already final (double-count): {missing}"
    )
