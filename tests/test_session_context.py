"""Tests for SessionContext (PR 3b).

5 tests covering the cache mechanism:
  1. Smoke: each loader returns a DataFrame/dict for the production file path
     (or None if the file is absent in this checkout).
  2. Cache hit on second call (no re-read).
  3. Cache invalidation when file mtime changes.
  4. None on missing file.
  5. Targeted invalidate(name) clears only one loader.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from plv_clone.session_context import DEFAULT_PATHS, SessionContext


LOADERS_AND_KINDS = [
    ("rh3", "df"),
    ("rp3", "df"),
    ("rprs2", "df"),
    ("hitter_master", "df"),
    ("sp_master", "df"),
    ("rp_master", "df"),
    ("pl_top150", "dict"),
    ("pl_top100", "dict"),
    ("fa_snapshot_rp", "df"),
]


def test_session_context_has_nine_named_loaders() -> None:
    """The 9-loader contract is checked at the API surface."""
    ctx = SessionContext()
    for name, _kind in LOADERS_AND_KINDS:
        assert callable(getattr(ctx, name)), f"{name!r} loader missing"
    assert len(LOADERS_AND_KINDS) == 9


def test_session_context_smoke_returns_expected_kinds() -> None:
    """Each loader either returns the expected kind (DataFrame or dict)
    or None (when the file isn't present in this checkout). NEVER raises."""
    ctx = SessionContext()
    for name, kind in LOADERS_AND_KINDS:
        out = getattr(ctx, name)()
        if out is None:
            continue
        if kind == "df":
            assert isinstance(out, pd.DataFrame), f"{name!r}: expected DataFrame, got {type(out)}"
        elif kind == "dict":
            assert isinstance(out, dict), f"{name!r}: expected dict, got {type(out)}"


def test_session_context_caches_on_second_call(tmp_path: Path) -> None:
    """A second call with no mtime change reuses the cached object (identity check)."""
    csv_path = tmp_path / "rh3.csv"
    csv_path.write_text("rank,batter,player_name\n1,123,Test Player\n")
    ctx = SessionContext(paths={**DEFAULT_PATHS, "rh3": str(csv_path)})
    first = ctx.rh3()
    second = ctx.rh3()
    assert first is second, "expected cache hit (same DataFrame object)"


def test_session_context_invalidates_on_mtime_change(tmp_path: Path) -> None:
    """Touching the file (mtime advance) forces a re-read."""
    csv_path = tmp_path / "rh3.csv"
    csv_path.write_text("rank,batter,player_name\n1,1,A\n")
    ctx = SessionContext(paths={**DEFAULT_PATHS, "rh3": str(csv_path)})

    first = ctx.rh3()
    assert first is not None and len(first) == 1

    # Rewrite with a later mtime + different content.
    import os
    csv_path.write_text("rank,batter,player_name\n1,1,A\n2,2,B\n")
    later = os.path.getmtime(csv_path) + 1
    os.utime(csv_path, (later, later))

    second = ctx.rh3()
    assert second is not None
    assert len(second) == 2, "expected re-read after mtime change"
    assert first is not second


def test_session_context_returns_none_for_missing_file(tmp_path: Path) -> None:
    ctx = SessionContext(paths={**DEFAULT_PATHS, "rh3": str(tmp_path / "does_not_exist.csv")})
    assert ctx.rh3() is None


def test_session_context_targeted_invalidate(tmp_path: Path) -> None:
    """invalidate('rh3') clears only the rh3 cache, not other loaders."""
    rh3_path = tmp_path / "rh3.csv"
    rh3_path.write_text("rank,batter,player_name\n1,1,A\n")
    rp3_path = tmp_path / "rp3.csv"
    rp3_path.write_text("rank,pitcher,player_name\n1,1,A\n")
    ctx = SessionContext(paths={**DEFAULT_PATHS, "rh3": str(rh3_path), "rp3": str(rp3_path)})

    a = ctx.rh3()
    b = ctx.rp3()
    ctx.invalidate("rh3")
    assert "rh3" not in ctx._cache
    assert "rp3" in ctx._cache
    # rp3 still returns same cached object
    assert ctx.rp3() is b
