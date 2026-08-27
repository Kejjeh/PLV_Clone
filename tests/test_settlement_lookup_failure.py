"""A failed gamelog fetch must not be graded as "he scored nothing".

WHY THIS EXISTS
`_fetch_gamelog` returned `[]` for BOTH a network/JSON failure and a player
with no games — its own docstring said so ("Network/JSON failure returns []").
`_totals_in_window` then returned `None` for both, and `settle_counterfactual`
coerced a `None` on the REJECTED side to 0.0.

The result: a decision whose alternative simply failed to resolve was credited
with the chosen player's ENTIRE total as `fp_gained` and classified
RIGHT_CALL. The bias points one way, and issue #54 established the rejected
side is usually an unrostered FA — i.e. exactly the side most likely to fail
to resolve.

`_totals_in_window`'s own docstring already said what should happen: "a player
who was hurt or benched should score 0, not be dropped as unsettleable." It
just could not tell that case apart from a failed fetch. Now it can — None is
reserved for a failed lookup, and a successful lookup with no games in the
window returns a real 0.0. `prediction.py` rule 3 has always drawn this line
correctly; the counterfactual book now agrees with it. (Added 2026-08-27.)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(ROOT / "src"))

sd = pytest.importorskip("settle_decisions")


def _game(day: str, **stat):
    """A box-score line with every field the BrownU hitter scorer reads."""
    base = {
        "date": day, "plateAppearances": 4, "gamesStarted": 0,
        "runs": 0, "totalBases": 0, "rbi": 0, "baseOnBalls": 0,
        "hitByPitch": 0, "stolenBases": 0, "strikeOuts": 0,
    }
    base.update(stat)
    return base


START, END = date(2026, 7, 1), date(2026, 7, 21)


def test_failed_fetch_returns_none(monkeypatch):
    """The signal that says 'we have no data', distinct from 'he scored 0'."""
    monkeypatch.setattr(sd, "_fetch_gamelog", lambda *a, **k: None)
    total, n = sd._totals_in_window(1, "H", START, END, {})
    assert total is None
    assert n == 0


def test_successful_fetch_with_no_games_returns_a_real_zero(monkeypatch):
    """The hurt/benched case _totals_in_window's docstring promises."""
    monkeypatch.setattr(sd, "_fetch_gamelog", lambda *a, **k: [])
    total, n = sd._totals_in_window(1, "H", START, END, {})
    assert total == 0.0, "a successful lookup with no games is a real zero"
    assert n == 0


def test_games_outside_the_window_are_a_real_zero_too(monkeypatch):
    """He played, just not in the window — still a zero, not missing data."""
    monkeypatch.setattr(sd, "_fetch_gamelog",
                        lambda *a, **k: [_game("2026-05-01")])
    total, n = sd._totals_in_window(1, "H", START, END, {})
    assert total == 0.0
    assert n == 0


def test_a_real_line_still_scores(monkeypatch):
    """The guard must not over-fire on the normal path."""
    monkeypatch.setattr(sd, "_fetch_gamelog", lambda *a, **k: [
        _game("2026-07-05", runs=2, rbi=1),
    ])
    total, n = sd._totals_in_window(1, "H", START, END, {})
    assert total is not None
    assert n == 4


def test_the_cache_is_consulted_once_per_key(monkeypatch):
    calls = []

    def _fake(mlbam, season, group):
        calls.append((mlbam, season, group))
        return []

    monkeypatch.setattr(sd, "_fetch_gamelog", _fake)
    cache: dict = {}
    sd._totals_in_window(1, "H", START, END, cache)
    sd._totals_in_window(1, "H", START, END, cache)
    assert len(calls) == 1, f"gamelog refetched: {calls}"


def test_a_cached_failure_is_still_a_failure(monkeypatch):
    """None must survive the cache — not decay into an empty list."""
    monkeypatch.setattr(sd, "_fetch_gamelog", lambda *a, **k: None)
    cache: dict = {}
    assert sd._totals_in_window(1, "H", START, END, cache)[0] is None
    assert sd._totals_in_window(1, "H", START, END, cache)[0] is None
