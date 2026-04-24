"""
Tests for artifact provenance sidecar (P0.3 addition).

Verifies that write_build_meta() produces a valid JSON file with the
required keys and populated date/version fields.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plv_clone.utils.provenance import write_build_meta, read_build_meta


class TestWriteBuildMeta:
    def test_file_is_created(self, tmp_path):
        write_build_meta(tmp_path, year=2024, exports=["master_hitter"])
        assert (tmp_path / "build_meta_2024.json").exists()

    def test_required_keys_present(self, tmp_path):
        write_build_meta(tmp_path, year=2024, exports=["master_hitter", "master_pitcher"])
        meta = json.loads((tmp_path / "build_meta_2024.json").read_text())
        for key in ("built_at", "year", "exports"):
            assert key in meta, f"required key missing: {key}"

    def test_built_at_is_iso8601_utc(self, tmp_path):
        write_build_meta(tmp_path, year=2024)
        meta = json.loads((tmp_path / "build_meta_2024.json").read_text())
        built_at = meta["built_at"]
        assert built_at.endswith("Z"), "built_at must end with Z (UTC)"
        assert len(built_at) >= 20, "built_at must be a full ISO-8601 timestamp"
        # Parseable without error
        from datetime import datetime, timezone
        datetime.strptime(built_at, "%Y-%m-%dT%H:%M:%SZ")

    def test_year_field_matches_input(self, tmp_path):
        write_build_meta(tmp_path, year=2026)
        meta = json.loads((tmp_path / "build_meta_2026.json").read_text())
        assert meta["year"] == 2026

    def test_exports_list_populated(self, tmp_path):
        exports = ["master_hitter", "plv_rolling", "process_plus_rolling"]
        write_build_meta(tmp_path, year=2024, exports=exports)
        meta = json.loads((tmp_path / "build_meta_2024.json").read_text())
        assert meta["exports"] == exports

    def test_suffix_produces_distinct_file(self, tmp_path):
        write_build_meta(tmp_path, year=2024, suffix="_boards")
        assert (tmp_path / "build_meta_2024_boards.json").exists()
        assert not (tmp_path / "build_meta_2024.json").exists()

    def test_extra_fields_are_written(self, tmp_path):
        write_build_meta(tmp_path, year=2024, extra={"min_pa_process": 150, "rolling_days": 30})
        meta = json.loads((tmp_path / "build_meta_2024.json").read_text())
        assert meta["min_pa_process"] == 150
        assert meta["rolling_days"] == 30

    def test_model_version_read_from_version_info(self, tmp_path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "version_info.json").write_text(json.dumps({"version": "v1.2.3"}))
        write_build_meta(tmp_path / "outputs", year=2024, models_dir=models_dir)
        meta = json.loads((tmp_path / "outputs" / "build_meta_2024.json").read_text())
        assert meta.get("model_version") == "v1.2.3"

    def test_missing_version_info_does_not_raise(self, tmp_path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        # No version_info.json written
        write_build_meta(tmp_path, year=2024, models_dir=models_dir)
        meta = json.loads((tmp_path / "build_meta_2024.json").read_text())
        assert "model_version" not in meta or meta.get("model_version") is None


class TestReadBuildMeta:
    def test_returns_none_when_absent(self, tmp_path):
        assert read_build_meta(tmp_path, year=2099) is None

    def test_returns_dict_when_present(self, tmp_path):
        write_build_meta(tmp_path, year=2024, exports=["x"])
        result = read_build_meta(tmp_path, year=2024)
        assert isinstance(result, dict)
        assert result["year"] == 2024

    def test_suffix_roundtrip(self, tmp_path):
        write_build_meta(tmp_path, year=2024, suffix="_fantasy", exports=["hitter_fantasy"])
        result = read_build_meta(tmp_path, year=2024, suffix="_fantasy")
        assert result is not None
        assert "hitter_fantasy" in result["exports"]
