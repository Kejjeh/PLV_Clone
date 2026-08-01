"""Behavioral contract for scripts/xfp/lib/disk_cache.py (audit 2026-08-01, item 33).

WHY THIS FILE EXISTS
--------------------
`year_cached_frame` is what the three rolling builders
(`build_rolling_hitters/pitchers/relievers.py`) put between the statcast cache
and the rows that train rh3 / rp3 / rprs2. It had ZERO tests, and both its read
path and its write path swallow every exception. A wrong cache KEY here does not
crash — it serves a stale training frame, silently, forever.

The invariants locked below are the ones that decide which bytes reach the
models:

  * a COMPLETED season is byte-identical cold vs warm (pickle, not parquet,
    precisely so no dtype round-trip can move a value);
  * the IN-PROGRESS season is never served from disk;
  * a declared dependency changing (mtime/size) invalidates;
  * a `version` bump invalidates and prunes the superseded entry;
  * a truncated/corrupt entry degrades to a rebuild, not to a wrong value;
  * an unwritable cache dir degrades to a rebuild AND SAYS SO (the write path
    used to fail in total silence, so a permanently unwritable cache dir was
    indistinguishable from a working one except by a ~345s nightly).

`_CACHE_DIR` and `_current_season` are module-level, so monkeypatching them is
the whole fixture story — nothing here touches the live `.build_cache`.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

from lib import disk_cache as dc  # noqa: E402


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Point the module's cache dir at a scratch tree."""
    d = tmp_path / "build_cache"
    monkeypatch.setattr(dc, "_CACHE_DIR", d)
    return d


@pytest.fixture
def dep(tmp_path):
    """One declared dependency file, as the rolling builders pass statcast."""
    p = tmp_path / "statcast_dep.parquet"
    p.write_bytes(b"v1")
    return p


class Builder:
    """Records how many times the expensive build actually ran."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


def test_an_unwritable_cache_dir_still_returns_the_built_value_and_says_so(
    tmp_path, monkeypatch, dep, capsys
):
    """A cache that can never be written must not fail the build — but it must
    stop being invisible. Silence here means every nightly pays the full ~345s
    rebuild while the log claims the cache is healthy."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("this is a file, so mkdir() underneath it cannot succeed")
    monkeypatch.setattr(dc, "_CACHE_DIR", blocker / "build_cache")

    b = Builder({"rows": 3})
    got = dc.disk_cached("rolling_hitters_2019", b, [str(dep)], version=1)

    assert got == {"rows": 3}, "an unwritable cache must never change the value"
    assert b.calls == 1

    err = capsys.readouterr().err
    assert "rolling_hitters_2019" in err and "cache" in err.lower(), (
        "an unwritable cache dir is silent — a permanently broken cache is "
        f"indistinguishable from a healthy one (stderr was {err!r})")


# ── the cache key: what decides whether a stale frame reaches rh3/rp3/rprs2 ────

def test_a_completed_season_returns_the_same_frame_cold_and_warm(cache_dir, dep):
    """The whole point of the cache: 2018-2025 rows must reproduce exactly.

    They feed rh3/rp3/rprs2 training, so cold and warm must be the SAME object
    value — this is why the entry is a pickle and not a parquet round-trip.
    """
    import pandas as pd

    frame = pd.DataFrame({"year": [2019, 2019], "batter": [1, 2], "x": [0.1, 0.2]})
    b = Builder(frame)

    cold = dc.year_cached_frame("rolling_hitters", 2019, b, [str(dep)], version=3)
    warm = dc.year_cached_frame("rolling_hitters", 2019, b, [str(dep)], version=3)

    assert b.calls == 1, "a completed season was rebuilt on the warm run"
    pd.testing.assert_frame_equal(cold, warm, check_dtype=True)
    assert list(cache_dir.glob("rolling_hitters_2019_*.pkl")), "no cache entry written"


def test_the_in_progress_season_is_rebuilt_from_source_every_run(
    cache_dir, dep, monkeypatch
):
    """Today's rows change all day. Serving them from disk would freeze the
    current season at whatever the first run of the day saw."""
    monkeypatch.setattr(dc, "_current_season", lambda: 2026)
    b = Builder("in-progress rows")

    for _ in range(3):
        assert dc.year_cached_frame("rolling_hitters", 2026, b, [str(dep)], version=3) \
            == "in-progress rows"

    assert b.calls == 3, "the in-progress season was served from disk"
    assert not list(cache_dir.glob("*.pkl")), (
        "the in-progress season wrote a cache entry — a later run could read it")


def test_touching_a_declared_dependency_invalidates_the_entry(cache_dir, dep):
    """A daily statcast refresh changes the dep's mtime/size; the cached year
    must not survive it."""
    first = Builder("built from v1")
    dc.year_cached_frame("rolling_pitchers", 2019, first, [str(dep)], version=1)
    assert first.calls == 1

    dep.write_bytes(b"v2-longer-content")  # size changes -> signature changes

    second = Builder("built from v2")
    got = dc.year_cached_frame("rolling_pitchers", 2019, second, [str(dep)], version=1)

    assert second.calls == 1, "a changed dependency was ignored — STALE rows served"
    assert got == "built from v2"


def test_an_undeclared_dependency_cannot_invalidate(cache_dir, tmp_path, dep):
    """The failure mode the swallowed exceptions cannot catch: a builder that
    reads a file it did not declare keeps serving the pre-change frame.

    This test does not demand a code change — it pins the semantics so a caller
    author can see that `dep_paths` must list EVERY file `build_year` opens.
    """
    undeclared = tmp_path / "undeclared_input.csv"
    undeclared.write_text("a")

    b = Builder("built while undeclared == 'a'")
    dc.year_cached_frame("rolling_relievers", 2019, b, [str(dep)], version=1)

    undeclared.write_text("b-changed")
    stale = dc.year_cached_frame("rolling_relievers", 2019, Builder("rebuilt"),
                                 [str(dep)], version=1)

    assert stale == "built while undeclared == 'a'", (
        "semantics changed: dep_paths is no longer the whole cache key")


def test_a_version_bump_rebuilds_and_prunes_the_superseded_entry(cache_dir, dep):
    """BUILDER_VERSION is the only lever a logic change has. It must both
    invalidate and clean up, or the cache dir grows a stale entry per bump."""
    dc.year_cached_frame("rolling_hitters", 2019, Builder("v1 logic"),
                         [str(dep)], version=1)
    assert len(list(cache_dir.glob("rolling_hitters_2019_*.pkl"))) == 1

    b2 = Builder("v2 logic")
    got = dc.year_cached_frame("rolling_hitters", 2019, b2, [str(dep)], version=2)

    assert b2.calls == 1 and got == "v2 logic", "a version bump did not invalidate"
    entries = list(cache_dir.glob("rolling_hitters_2019_*.pkl"))
    assert len(entries) == 1, f"superseded entry not pruned: {[p.name for p in entries]}"


def test_a_truncated_cache_entry_rebuilds_instead_of_returning_junk(cache_dir, dep):
    """A half-written pickle (killed job, full disk) must degrade to a rebuild."""
    dc.year_cached_frame("rolling_hitters", 2019, Builder("good rows"),
                         [str(dep)], version=1)
    entry = next(cache_dir.glob("rolling_hitters_2019_*.pkl"))
    entry.write_bytes(entry.read_bytes()[:5])  # truncate

    b = Builder("rebuilt rows")
    got = dc.year_cached_frame("rolling_hitters", 2019, b, [str(dep)], version=1)

    assert b.calls == 1 and got == "rebuilt rows"
    assert pickle.loads(entry.read_bytes()) == "rebuilt rows", "entry not repaired"


def test_a_missing_dependency_file_is_a_distinct_cache_key(cache_dir, tmp_path, dep):
    """`_dep_sig` records a missing dep as ':missing' rather than raising, so a
    run with the dep absent must not collide with a run that had it."""
    absent = tmp_path / "never_written.parquet"
    dc.year_cached_frame("rolling_hitters", 2019, Builder("with dep"),
                         [str(dep)], version=1)

    b = Builder("without dep")
    got = dc.year_cached_frame("rolling_hitters", 2019, b, [str(absent)], version=1)

    assert b.calls == 1 and got == "without dep", (
        "a present and an absent dependency produced the same cache key")


def test_two_cache_names_do_not_share_an_entry(cache_dir, dep):
    """hitters/pitchers/relievers all cache the same years side by side."""
    dc.year_cached_frame("rolling_hitters", 2019, Builder("H rows"), [str(dep)], version=1)
    b = Builder("SP rows")
    got = dc.year_cached_frame("rolling_pitchers", 2019, b, [str(dep)], version=1)
    assert b.calls == 1 and got == "SP rows"
