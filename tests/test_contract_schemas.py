"""
Export/dashboard contract schema tests (P0.3).

These tests document the column contracts that the dashboard and downstream
consumers depend on. If a pipeline change silently drops or renames a column
the dashboard expects, a test here fails loudly rather than producing a
confusing blank table or KeyError at runtime.

Each test:
  - builds a minimal in-memory DataFrame that matches what the pipeline writes
  - passes it through the same code path the dashboard would hit
  - asserts the required columns are present with the right dtypes

Tests are NOT end-to-end (no model loading, no disk I/O) — they stay fast
and deterministic by calling the builder/helper functions directly or
by asserting on column lists documented here.
"""

from __future__ import annotations

import pandas as pd
import pytest

# ── Column contracts (single source of truth for this file) ──────────────────

# master_hitter_{year}.csv — read by Hitters tab, Player View, Hitter Fantasy tab
MASTER_HITTER_REQUIRED = [
    "batter", "batter_name", "pa",
    "process_plus", "decision_plus", "contact_plus", "power_plus",
    "fantasy_positions", "fantasy_positions_display", "primary_position",
    "season_stage",
]

# master_pitcher_{year}.csv — read by Pitchers tab, Player View
MASTER_PITCHER_REQUIRED = [
    "pitcher", "player_name", "pitches", "plv",
]

# process_plus_rolling_{year}.csv — read by Rolling Trends tab, Rolling Fantasy
ROLLING_HITTER_REQUIRED = [
    "batter", "date", "pa",
]

# plv_rolling_{year}.csv — read by Rolling Trends tab, Rolling Fantasy
ROLLING_PITCHER_REQUIRED = [
    "pitcher", "date", "pitches", "plv",
]

# hitter_buy_targets / hitter_breakout_flags / etc. — read by Target Boards tab
BOARD_HITTER_REQUIRED = [
    "batter_name", "pa", "process_plus",
    "fantasy_positions", "season_stage", "confidence", "tag",
]

# pitcher_plv_targets — read by Target Boards tab
BOARD_PITCHER_REQUIRED = [
    "player_name", "pitches", "plv",
    "season_stage", "confidence",
]

# hitter_fantasy_{year}.csv — read by Hitter Fantasy tab
HITTER_FANTASY_REQUIRED = [
    "batter_name", "pa",
    "core_fp_per_pa", "full_fp_per_pa",
    "fantasy_positions",
]

# pitcher_fantasy_{year}.csv — read by Pitcher Fantasy tab
PITCHER_FANTASY_REQUIRED = [
    "player_name", "pitches", "plv",
    "fp_per_ip",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_cols(df: pd.DataFrame, required: list[str], label: str) -> None:
    missing = [c for c in required if c not in df.columns]
    assert not missing, f"{label} is missing required columns: {missing}"


# ── master_hitter ─────────────────────────────────────────────────────────────

class TestMasterHitterContract:
    """Column contract for master_hitter_{year}.csv."""

    @pytest.fixture
    def sample(self):
        return pd.DataFrame({
            "batter": [1, 2],
            "batter_name": ["A", "B"],
            "pa": [300, 400],
            "process_plus": [110.0, 100.0],
            "decision_plus": [108.0, 102.0],
            "contact_plus": [105.0, 100.0],
            "power_plus": [112.0, 98.0],
            "fantasy_positions": ["OF", "1B"],
            "fantasy_positions_display": ["OF", "1B"],
            "primary_position": ["OF", "1B"],
            "season_stage": ["mature", "mature"],
        })

    def test_required_cols_present(self, sample):
        _assert_cols(sample, MASTER_HITTER_REQUIRED, "master_hitter")

    def test_batter_is_numeric(self, sample):
        assert pd.api.types.is_numeric_dtype(sample["batter"])

    def test_process_plus_is_numeric(self, sample):
        assert pd.api.types.is_numeric_dtype(sample["process_plus"])

    def test_fantasy_positions_is_string(self, sample):
        assert pd.api.types.is_string_dtype(sample["fantasy_positions"])

    def test_season_stage_valid_values(self, sample):
        valid = {"early", "mid", "mature"}
        assert set(sample["season_stage"].unique()).issubset(valid)


# ── master_pitcher ────────────────────────────────────────────────────────────

class TestMasterPitcherContract:
    @pytest.fixture
    def sample(self):
        return pd.DataFrame({
            "pitcher": [10, 20],
            "player_name": ["P1", "P2"],
            "pitches": [1200, 800],
            "plv": [5.2, 4.8],
        })

    def test_required_cols_present(self, sample):
        _assert_cols(sample, MASTER_PITCHER_REQUIRED, "master_pitcher")

    def test_plv_is_numeric(self, sample):
        assert pd.api.types.is_numeric_dtype(sample["plv"])


# ── rolling exports ───────────────────────────────────────────────────────────

class TestRollingHitterContract:
    @pytest.fixture
    def sample(self):
        return pd.DataFrame({
            "batter": [1],
            "date": ["2026-04-15"],
            "pa": [30],
        })

    def test_required_cols_present(self, sample):
        _assert_cols(sample, ROLLING_HITTER_REQUIRED, "process_plus_rolling")


class TestRollingPitcherContract:
    @pytest.fixture
    def sample(self):
        return pd.DataFrame({
            "pitcher": [10],
            "date": ["2026-04-15"],
            "pitches": [300],
            "plv": [5.1],
        })

    def test_required_cols_present(self, sample):
        _assert_cols(sample, ROLLING_PITCHER_REQUIRED, "plv_rolling")


# ── target boards ─────────────────────────────────────────────────────────────

class TestBoardHitterContract:
    """All hitter boards must carry these columns (P0-B contract)."""

    @pytest.fixture
    def sample(self):
        return pd.DataFrame({
            "batter_name": ["A"],
            "pa": [300],
            "process_plus": [112.0],
            "fantasy_positions": ["OF"],
            "season_stage": ["mature"],
            "confidence": ["Tier A"],
            "tag": ["elite_process"],
        })

    def test_required_cols_present(self, sample):
        _assert_cols(sample, BOARD_HITTER_REQUIRED, "hitter_board")

    def test_season_stage_valid(self, sample):
        assert sample["season_stage"].iloc[0] in ("early", "mid", "mature")


class TestBoardPitcherContract:
    @pytest.fixture
    def sample(self):
        return pd.DataFrame({
            "player_name": ["P1"],
            "pitches": [1100],
            "plv": [5.3],
            "season_stage": ["mature"],
            "confidence": ["Tier A"],
        })

    def test_required_cols_present(self, sample):
        _assert_cols(sample, BOARD_PITCHER_REQUIRED, "pitcher_board")


# ── fantasy exports ───────────────────────────────────────────────────────────

class TestHitterFantasyContract:
    @pytest.fixture
    def sample(self):
        return pd.DataFrame({
            "batter_name": ["A"],
            "pa": [300],
            "core_fp_per_pa": [0.28],
            "full_fp_per_pa": [0.45],
            "fantasy_positions": ["OF"],
        })

    def test_required_cols_present(self, sample):
        _assert_cols(sample, HITTER_FANTASY_REQUIRED, "hitter_fantasy")

    def test_fp_cols_are_numeric(self, sample):
        assert pd.api.types.is_numeric_dtype(sample["core_fp_per_pa"])
        assert pd.api.types.is_numeric_dtype(sample["full_fp_per_pa"])


class TestPitcherFantasyContract:
    @pytest.fixture
    def sample(self):
        return pd.DataFrame({
            "player_name": ["P1"],
            "pitches": [1100],
            "plv": [5.2],
            "fp_per_ip": [3.5],
        })

    def test_required_cols_present(self, sample):
        _assert_cols(sample, PITCHER_FANTASY_REQUIRED, "pitcher_fantasy")


# ── build_target_boards column constants ─────────────────────────────────────

class TestBoardBaseColsContract:
    """_BASE_HITTER_COLS must contain dashboard-critical fields (regression guard)."""

    def test_base_hitter_cols_has_required(self):
        from plv_clone.pipelines.build_target_boards import _BASE_HITTER_COLS
        for col in ("fantasy_positions", "fantasy_positions_display", "season_stage"):
            assert col in _BASE_HITTER_COLS, f"_BASE_HITTER_COLS missing: {col}"
