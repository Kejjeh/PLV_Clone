"""
Tests for export pipeline integrity (P0-A, P1-C, P1-D).

Covers:
  - Stale master_hitter fallback is no longer triggered (P0-A)
  - Unresolved numeric name threshold checks in validate_outputs (P1-C)
  - Empty fantasy_positions threshold checks in validate_outputs (P1-D)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure scripts/ is importable
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))


# ══════════════════════════════════════════════════════════════════════════════
# P0-A: Stale fallback removed
# ══════════════════════════════════════════════════════════════════════════════

class TestStaleFallbackRemoved:
    """When no hitters qualify at min_pa, the output must be empty — not loaded
    from a pre-existing artifact that could contain stale metrics.

    We mock build_master_hitter directly so the test is not coupled to model
    loading or parquet formats. The assertions verify the pipeline's behaviour
    *after* build_master_hitter returns empty, which is the exact code path
    affected by the P0-A change.
    """

    def _setup(self, tmp_path, monkeypatch):
        """Common setup: dirs, stale CSV, patched helpers."""
        import plv_clone.pipelines.build_exports as be
        from plv_clone.config import PipelineConfig

        pp_dir = tmp_path / "processed" / "process_plus_scores" / "year=2099"
        pp_dir.mkdir(parents=True)
        # Minimal parquet so the directory is detected as present
        pd.DataFrame({"batter": [1], "discipline_value": [0.0],
                      "game_date": ["2099-04-01"]}).to_parquet(
            pp_dir / "part-0.parquet", index=False
        )

        out_dir = tmp_path / "outputs"
        out_dir.mkdir()

        # Stale CSV with sentinel process_plus=999 that must NOT reappear
        pd.DataFrame({
            "batter": [1], "batter_name": ["Stale Player"],
            "process_plus": [999.0], "pa": [200],
        }).to_csv(out_dir / "master_hitter_2099.csv", index=False)

        cfg = PipelineConfig(
            processed_dir=tmp_path / "processed",
            outputs_dir=out_dir,
            models_dir=tmp_path / "models",
            raw_data_dir=tmp_path / "raw",
            min_pa_process=9999,
        )

        # Patch: build_master_hitter returns empty (simulates no qualifying hitters)
        monkeypatch.setattr(be, "build_master_hitter", lambda *a, **kw: pd.DataFrame())
        monkeypatch.setattr(be, "build_position_map", lambda *a, **kw: pd.DataFrame())
        monkeypatch.setattr(be, "_build_batter_name_map", lambda *a, **kw: {})
        # build_rolling_process_plus needs game_date; skip by patching read_parquet
        # to return a df that the rolling builder handles gracefully (no game_date col)
        monkeypatch.setattr(be, "build_rolling_process_plus",
                            lambda *a, **kw: pd.DataFrame())

        return be, cfg, out_dir

    def test_empty_master_hitter_is_written_not_stale_reload(
        self, tmp_path, monkeypatch
    ):
        be, cfg, out_dir = self._setup(tmp_path, monkeypatch)

        exports = be.run(year=2099, config=cfg)
        result = exports.get("master_hitter", pd.DataFrame())

        # Core assertion: stale process_plus=999 must NOT appear
        assert result.empty or 999.0 not in result.get("process_plus", pd.Series()).values, (
            "Stale metrics from a prior artifact must not appear in current export"
        )

        # Written CSV must be clean — either empty or without stale process_plus.
        # In production build_master_hitter returns a schema'd empty DataFrame
        # (header only); the mock returns a column-less frame (empty file).
        # Both are acceptable; neither should contain the old stale value.
        try:
            written = pd.read_csv(out_dir / "master_hitter_2099.csv")
        except pd.errors.EmptyDataError:
            written = pd.DataFrame()  # empty file = no stale data
        if not written.empty:
            assert 999.0 not in written.get("process_plus", pd.Series()).values, (
                "Written CSV must not contain stale process_plus=999"
            )

    def test_empty_master_hitter_does_not_raise(self, tmp_path, monkeypatch):
        """run() completes without error when no hitters qualify."""
        be, cfg, _ = self._setup(tmp_path, monkeypatch)
        be.run(year=2099, config=cfg)  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# P1-C: Unresolved numeric name threshold
# ══════════════════════════════════════════════════════════════════════════════

class TestNameResolutionCheck:
    """check_name_resolution returns correct pass/warning/fail depending on numeric fraction."""

    @pytest.fixture(autouse=True)
    def _patch_cfg(self, tmp_path, monkeypatch):
        """Point CFG.outputs_dir at tmp_path for all tests in this class."""
        import validate_outputs as vo
        from plv_clone.config import PipelineConfig

        # Use a fresh config pointing at tmp_path
        cfg_obj = PipelineConfig(
            processed_dir=tmp_path / "processed",
            outputs_dir=tmp_path / "outputs",
            models_dir=tmp_path / "models",
            raw_data_dir=tmp_path / "raw",
        )
        (tmp_path / "outputs").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(vo, "CFG", cfg_obj)
        self.out_dir = tmp_path / "outputs"
        self.vo = vo

    def _write_hitter(self, names: list[str]):
        pd.DataFrame({"batter_name": names}).to_csv(
            self.out_dir / "master_hitter_2026.csv", index=False
        )

    def _write_pitcher(self, names: list[str]):
        pd.DataFrame({"player_name": names}).to_csv(
            self.out_dir / "master_pitcher_2026.csv", index=False
        )

    def test_all_resolved_passes(self):
        self._write_hitter(["Aaron Judge", "Mookie Betts"])
        self._write_pitcher(["Zack Wheeler", "Spencer Strider"])
        checks = self.vo.check_name_resolution(2026)
        assert all(c.passed for c in checks)

    def test_zero_numeric_passes(self):
        self._write_hitter(["Juan Soto"] * 20)
        self._write_pitcher(["Gerrit Cole"] * 10)
        checks = self.vo.check_name_resolution(2026)
        assert all(c.passed for c in checks)

    def test_below_threshold_is_warning_not_failure(self):
        # 1 numeric out of 50 = 2% < 5% threshold
        names = ["Aaron Judge"] * 49 + ["12345678"]
        self._write_hitter(names)
        self._write_pitcher(["Zack Wheeler"] * 10)
        hitter_check = next(c for c in self.vo.check_name_resolution(2026) if "Hitter" in c.name)
        assert not hitter_check.passed
        assert hitter_check.is_warning, "Below threshold should be warning, not hard failure"

    def test_above_threshold_is_hard_failure(self):
        # 6 numeric out of 20 = 30% > 5% threshold
        names = ["Aaron Judge"] * 14 + ["12345678"] * 6
        self._write_hitter(names)
        self._write_pitcher(["Zack Wheeler"] * 10)
        hitter_check = next(c for c in self.vo.check_name_resolution(2026) if "Hitter" in c.name)
        assert not hitter_check.passed
        assert not hitter_check.is_warning, "Above threshold should be hard failure"

    def test_missing_file_is_failure(self):
        checks = self.vo.check_name_resolution(2026)
        assert any(not c.passed for c in checks)


# ══════════════════════════════════════════════════════════════════════════════
# P1-D: Empty fantasy_positions threshold
# ══════════════════════════════════════════════════════════════════════════════

class TestPositionQualityCheck:
    """check_position_quality returns correct pass/warning/fail based on empty fraction."""

    @pytest.fixture(autouse=True)
    def _patch_cfg(self, tmp_path, monkeypatch):
        import validate_outputs as vo
        from plv_clone.config import PipelineConfig

        cfg_obj = PipelineConfig(
            processed_dir=tmp_path / "processed",
            outputs_dir=tmp_path / "outputs",
            models_dir=tmp_path / "models",
            raw_data_dir=tmp_path / "raw",
        )
        (tmp_path / "outputs").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(vo, "CFG", cfg_obj)
        self.out_dir = tmp_path / "outputs"
        self.vo = vo

    def _write_hitter(self, fantasy_positions: list[str]):
        pd.DataFrame({
            "batter_name": [f"Player{i}" for i in range(len(fantasy_positions))],
            "fantasy_positions": fantasy_positions,
        }).to_csv(self.out_dir / "master_hitter_2026.csv", index=False)

    def test_all_populated_passes(self):
        self._write_hitter(["OF", "1B", "2B", "OF", "3B"] * 10)
        checks = self.vo.check_position_quality(2026)
        assert all(c.passed for c in checks)

    def test_exactly_at_threshold_passes(self):
        # 20% empty of 10 = 2 empty → exactly at threshold → passes
        positions = ["OF"] * 8 + ["", ""]
        self._write_hitter(positions)
        checks = self.vo.check_position_quality(2026)
        assert all(c.passed for c in checks)

    def test_above_threshold_fails(self):
        # 21% empty of 100 = 21 empty → above threshold → fail
        positions = ["OF"] * 79 + [""] * 21
        self._write_hitter(positions)
        checks = self.vo.check_position_quality(2026)
        quality_check = next(c for c in checks if "fantasy_positions" in c.name)
        assert not quality_check.passed

    def test_empty_master_hitter_passes_gracefully(self):
        """Early season with 0 rows should not fail the position check."""
        pd.DataFrame(columns=["batter_name", "fantasy_positions"]).to_csv(
            self.out_dir / "master_hitter_2026.csv", index=False
        )
        checks = self.vo.check_position_quality(2026)
        assert all(c.passed for c in checks)

    def test_missing_column_is_failure(self):
        pd.DataFrame({"batter_name": ["A", "B"]}).to_csv(
            self.out_dir / "master_hitter_2026.csv", index=False
        )
        checks = self.vo.check_position_quality(2026)
        assert any(not c.passed for c in checks)

    def test_missing_file_is_failure(self):
        checks = self.vo.check_position_quality(2026)
        assert any(not c.passed for c in checks)


# ══════════════════════════════════════════════════════════════════════════════
# Early-season empty leaderboard — check_process_plus graceful handling
# ══════════════════════════════════════════════════════════════════════════════

class TestProcessPlusEmptyLeaderboard:
    """check_process_plus returns a single warning (not hard failures) when the
    leaderboard has 0 rows — i.e., no hitter has reached min_pa yet."""

    @pytest.fixture(autouse=True)
    def _patch_cfg(self, tmp_path, monkeypatch):
        import validate_outputs as vo
        from plv_clone.config import PipelineConfig

        cfg_obj = PipelineConfig(
            processed_dir=tmp_path / "processed",
            outputs_dir=tmp_path / "outputs",
            models_dir=tmp_path / "models",
            raw_data_dir=tmp_path / "raw",
        )
        (tmp_path / "outputs").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(vo, "CFG", cfg_obj)
        self.out_dir = tmp_path / "outputs"
        self.vo = vo

    def _write_empty_leaderboard(self):
        pd.DataFrame(columns=["batter", "process_plus", "discipline_plus",
                               "contact_plus", "power_plus", "pa"]).to_csv(
            self.out_dir / "process_plus_leaderboard_2026.csv", index=False
        )

    def test_empty_leaderboard_returns_single_warning(self):
        self._write_empty_leaderboard()
        checks = self.vo.check_process_plus(2026)
        assert len(checks) == 1, f"Expected 1 check, got {len(checks)}"
        assert not checks[0].passed
        assert checks[0].is_warning, "Empty leaderboard should be a warning, not a hard failure"

    def test_empty_leaderboard_no_hard_failures(self):
        """--strict must not be triggered by an empty early-season leaderboard."""
        self._write_empty_leaderboard()
        checks = self.vo.check_process_plus(2026)
        hard_failures = [c for c in checks if not c.passed and not c.is_warning]
        assert hard_failures == [], f"Unexpected hard failures: {hard_failures}"
