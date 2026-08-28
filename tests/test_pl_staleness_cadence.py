"""PL-cache staleness has ONE owner, and it is cadence-aware.

CLAUDE.md gotcha #10: a PL cache is stale once its NEXT edition publishes, not
at a flat 7 days. `lib.pl_cache._cache_is_stale` implements that. The canonical
triangulate test carried a SECOND rule — `_PL_STALE_DAYS = {'H': 7, 'SP': 7,
'RP': 7}` — deciding the same question for the same four files with a flat
day-count. That is the don't-do #18 shape: a correct rule in one place and a
cruder copy in its sibling.

The copy was wrong in the DANGEROUS direction. The editions land on different
weekdays (SP Monday, closers Tuesday, hitters Wednesday, streamers rolling
~2d), so a flat 7 misjudges by up to two days depending on which weekday CI
runs — and it can report a cache FRESH while a newer edition is already out.
A false-fresh keeps the verdict lock engaged against data that has moved,
red-CIing on operational drift, which is the exact failure the relaxation
exists to prevent. `test_the_flat_rule_would_have_called_a_stale_cache_fresh`
below is a concrete instance.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone

import pytest

pl_cache = pytest.importorskip("scripts.xfp.lib.pl_cache")
tri_test = pytest.importorskip("tests.test_triangulate")

ET = timezone(timedelta(hours=-4))


def _flat_rule(fetched: date, now: date, window: int = 7) -> bool:
    """The rule that used to live in test_triangulate, for comparison only."""
    return (now - fetched).days > window


# ── one owner ────────────────────────────────────────────────────────────────

def test_the_triangulate_test_delegates_rather_than_re_deciding():
    """Checks for an actual ASSIGNMENT, not a mention.

    A substring match on the name would fire on the comment in that file which
    explains why the constant was removed — prose describing a rule is not the
    rule. (Same trap as the docstring guard in #64: the explanation of a fix
    reads exactly like the fix being reverted.)
    """
    import ast

    tree = ast.parse(inspect.getsource(tri_test))
    assigned = {
        t.id
        for n in ast.walk(tree) if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)
    }
    assert "_PL_STALE_DAYS" not in assigned, (
        "a second staleness rule is back in test_triangulate — delegate to "
        "lib.pl_cache._cache_is_stale (gotcha #10, don't-do #18)"
    )
    imported = {
        a.asname or a.name
        for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        for a in n.names
    }
    assert "_pl_cache_is_stale" in imported or "_cache_is_stale" in imported, (
        "the canonical rule is no longer imported"
    )


def test_the_canonical_rule_covers_every_pl_cache_file():
    """The flat copy knew only H/SP/RP and defaulted everything else to 7 days —
    so the streamer cache, which refreshes every ~2 days, was judged on a window
    3.5x too wide."""
    for fname in pl_cache.PL_CACHE_FILES.values():
        assert fname in pl_cache.PL_PUBLISH_CADENCE, (
            f"{fname} has no declared publish cadence, so staleness for it "
            f"falls back to a flat default — the thing gotcha #10 forbids"
        )
    assert pl_cache.PL_PUBLISH_CADENCE["pl_sp_streamers_latest.json"] == ("rolling", 2)


def test_the_cadences_really_do_differ_by_weekday():
    """If they were all the same weekday a flat rule would be harmless. They
    aren't: Monday / Tuesday / Wednesday."""
    weekly = {f: v for f, (m, v) in pl_cache.PL_PUBLISH_CADENCE.items() if m == "weekly"}
    assert len(set(weekly.values())) > 1, weekly


# ── the divergence that motivated the change ─────────────────────────────────

def test_the_flat_rule_would_have_called_a_stale_cache_fresh():
    """Hitters (Wednesday edition) stamped Thu 2026-08-20, checked Thu 08-27.

    Age is exactly 7 days, so the flat `> 7` test says FRESH. But the Wednesday
    2026-08-26 edition published the evening before, so the cache is a full
    edition behind. The flat rule keeps the lock engaged on stale data."""
    fetched = date(2026, 8, 20)
    now = datetime(2026, 8, 27, 10, 0, tzinfo=ET)

    assert _flat_rule(fetched, now.date()) is False, "precondition: flat says fresh"

    stale, why = pl_cache._cache_is_stale("pl_hitters_top150.json", fetched, now)
    assert stale is True, f"cadence rule should call this stale, got: {why}"
    assert "2026-08-26" in why


def test_a_cache_is_not_stale_merely_for_being_over_a_week_old():
    """The other direction, and the one gotcha #10 states outright: age alone
    does not make a cache stale. Stamped Mon 2026-08-24, checked Mon 08-31 at
    10am — 7 days old, and that morning's edition has not published (PL lands
    ~7pm ET), so the cached one is still the latest live edition."""
    stale, why = pl_cache._cache_is_stale(
        "pl_sps_top100.json", date(2026, 8, 24),
        datetime(2026, 8, 31, 10, 0, tzinfo=ET))
    assert stale is False, why
    assert "current" in why


def test_the_publish_hour_is_respected_not_just_the_date():
    """Same calendar day, before vs after the ~7pm ET drop."""
    fetched = date(2026, 8, 24)
    before = pl_cache._cache_is_stale(
        "pl_sps_top100.json", fetched, datetime(2026, 8, 31, 18, 0, tzinfo=ET))
    after = pl_cache._cache_is_stale(
        "pl_sps_top100.json", fetched, datetime(2026, 8, 31, 20, 0, tzinfo=ET))
    assert before[0] is False, before[1]
    assert after[0] is True, after[1]


# ── the helper the test actually calls ───────────────────────────────────────

def test_the_helper_returns_a_reason_not_just_a_boolean():
    """The xfail message quotes it, so a human reading CI sees WHICH edition is
    out rather than a bare day count."""
    # No presence guard: pl_hitters_top150.json is TRACKED, so a None here is a
    # real failure (a missing or unstamped cache), not an absent-substrate skip.
    got = tri_test._pl_cache_staleness("H")
    assert got is not None, "the tracked PL hitter cache is missing or unstamped"
    stale, why = got
    assert isinstance(stale, bool)
    assert isinstance(why, str) and why


def test_an_unreadable_cache_yields_none_so_the_lock_stays_engaged():
    """None must mean "don't relax", never "assume fresh" or "assume stale"."""
    assert tri_test._pl_cache_staleness("NOT_A_BUCKET") is None
