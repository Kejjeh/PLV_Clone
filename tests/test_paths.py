"""Tests for plv_clone.paths — the repo-root + data-location seam."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_root_resolves_to_repo_with_data_dir():
    import plv_clone.paths as paths
    # __file__-relative default: ROOT is the repo and has the data/ tree.
    assert (paths.ROOT / "data").is_dir()
    assert paths.OUTPUTS == paths.ROOT / "data" / "outputs"
    assert paths.CACHE == paths.ROOT / "data" / "research" / "xfp_cache"


def test_plv_root_env_override(monkeypatch):
    monkeypatch.setenv("PLV_ROOT", "/tmp/whatever")
    import plv_clone.paths as paths
    importlib.reload(paths)
    try:
        assert paths.ROOT == Path("/tmp/whatever")
        assert paths.OUTPUTS == Path("/tmp/whatever") / "data" / "outputs"
    finally:
        monkeypatch.delenv("PLV_ROOT", raising=False)
        importlib.reload(paths)  # restore default for other tests


def test_xfp_docs_env_override(monkeypatch):
    monkeypatch.setenv("PLV_XFP_DOCS", "/tmp/docs")
    import plv_clone.paths as paths
    importlib.reload(paths)
    try:
        assert paths.XFP_DOCS == Path("/tmp/docs")
    finally:
        monkeypatch.delenv("PLV_XFP_DOCS", raising=False)
        importlib.reload(paths)
