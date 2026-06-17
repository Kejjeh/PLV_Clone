"""Tests for plv_clone.projections.ProjectionStore — the single load seam for
the rh3 / rp3 / rprs2 projection artifacts."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from plv_clone.projections import ProjectionStore, PROJECTIONS


def test_typed_accessors_load_real_artifacts():
    rp3 = PROJECTIONS.rp3()
    assert not rp3.empty and "pitcher" in rp3.columns
    assert "batter" in PROJECTIONS.rh3().columns
    assert not PROJECTIONS.rprs2().empty


def test_memoized_returns_cached_frame():
    assert PROJECTIONS.rp3() is PROJECTIONS.rp3()


def test_missing_artifact_fail_soft_empty(tmp_path):
    store = ProjectionStore(outputs_dir=tmp_path)
    assert store.rp3().empty
    assert store.rh3().empty


def test_injected_fixture(tmp_path):
    (tmp_path / "xfp_rp3_projections.csv").write_text(
        "pitcher,xfp_rp3_per_start\n607074,11.84\n"
    )
    store = ProjectionStore(outputs_dir=tmp_path)
    df = store.rp3()
    assert list(df["pitcher"]) == [607074]
    assert df["xfp_rp3_per_start"].iloc[0] == 11.84


def test_clear_forces_reload(tmp_path):
    p = tmp_path / "xfp_rh3_projections.csv"
    p.write_text("batter,xfp_rh3_per_game\n1,5.0\n")
    store = ProjectionStore(outputs_dir=tmp_path)
    assert len(store.rh3()) == 1
    p.write_text("batter,xfp_rh3_per_game\n1,5.0\n2,6.0\n")
    assert len(store.rh3()) == 1  # still cached
    store.clear()
    assert len(store.rh3()) == 2  # re-read after clear
