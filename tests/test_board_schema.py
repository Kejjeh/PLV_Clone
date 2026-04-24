"""
Tests for target board column schema (P0-B).

Verifies that all hitter boards include fantasy_positions and season_stage,
which the dashboard needs for position filtering and stage display.
"""

from __future__ import annotations

import pandas as pd
import pytest

from plv_clone.pipelines.build_target_boards import (
    _BASE_HITTER_COLS,
    _hitter_display_cols,
    _buy_targets,
    _breakout_flags,
    _regression_flags,
    _discipline_targets,
    _power_targets,
)
from plv_clone.utils.season_stage import get_thresholds


@pytest.fixture
def minimal_hitters():
    """Minimal hitter DataFrame that satisfies all board filters."""
    return pd.DataFrame({
        "batter": [1, 2, 3, 4, 5],
        "batter_name": ["A", "B", "C", "D", "E"],
        "pa": [300, 400, 250, 350, 200],
        "process_plus": [115.0, 105.0, 90.0, 112.0, 108.0],
        "decision_plus": [115.0, 100.0, 95.0, 112.0, 109.0],
        "contact_plus": [108.0, 102.0, 96.0, 104.0, 107.0],
        "power_plus": [110.0, 98.0, 92.0, 108.0, 107.0],
        "xwoba_actual": [0.340, 0.420, 0.400, 0.320, 0.360],
        "swing_pct": [0.45, 0.50, 0.55, 0.42, 0.48],
        "chase_pct": [0.25, 0.30, 0.35, 0.22, 0.28],
        "rank_gap": [0.20, -0.20, -0.30, 0.25, 0.05],
        "pp_rank": [0.80, 0.55, 0.30, 0.75, 0.60],
        "xwoba_rank": [0.60, 0.75, 0.60, 0.50, 0.55],
        "confidence": ["Tier A", "Tier A", "Tier B", "Tier A", "Tier B"],
        "primary_position": ["OF", "1B", "3B", "2B", "C"],
        "fantasy_positions": ["OF", "1B", "3B", "2B", "C"],
        "fantasy_positions_display": ["OF", "1B", "3B", "2B", "C"],
        "season_stage": ["mature"] * 5,
        "tag": [""] * 5,
    })


class TestBaseCols:
    def test_fantasy_positions_in_base_cols(self):
        assert "fantasy_positions" in _BASE_HITTER_COLS

    def test_season_stage_in_base_cols(self):
        assert "season_stage" in _BASE_HITTER_COLS

    def test_fantasy_positions_display_in_base_cols(self):
        assert "fantasy_positions_display" in _BASE_HITTER_COLS


class TestHitterDisplayCols:
    def test_fantasy_positions_included_when_present(self, minimal_hitters):
        cols = _hitter_display_cols(minimal_hitters)
        assert "fantasy_positions" in cols

    def test_season_stage_included_when_present(self, minimal_hitters):
        cols = _hitter_display_cols(minimal_hitters)
        assert "season_stage" in cols

    def test_missing_cols_silently_dropped(self, minimal_hitters):
        df = minimal_hitters.drop(columns=["fantasy_positions"])
        cols = _hitter_display_cols(df)
        assert "fantasy_positions" not in cols


class TestBoardOutputSchema:
    """End-to-end: each board builder preserves fantasy_positions and season_stage."""

    def test_buy_targets_schema(self, minimal_hitters):
        t = get_thresholds("mature")
        df = _buy_targets(minimal_hitters, t)
        assert "fantasy_positions" in df.columns, "buy_targets missing fantasy_positions"
        assert "season_stage" in df.columns, "buy_targets missing season_stage"

    def test_breakout_flags_schema(self, minimal_hitters):
        t = get_thresholds("mature")
        df = _breakout_flags(minimal_hitters, t)
        assert "fantasy_positions" in df.columns
        assert "season_stage" in df.columns

    def test_regression_flags_schema(self, minimal_hitters):
        t = get_thresholds("mature")
        df = _regression_flags(minimal_hitters, t)
        assert "fantasy_positions" in df.columns
        assert "season_stage" in df.columns

    def test_discipline_targets_schema(self, minimal_hitters):
        t = get_thresholds("mature")
        df = _discipline_targets(minimal_hitters, t)
        assert "fantasy_positions" in df.columns
        assert "season_stage" in df.columns

    def test_power_targets_schema(self, minimal_hitters):
        t = get_thresholds("mature")
        df = _power_targets(minimal_hitters, t)
        assert "fantasy_positions" in df.columns
        assert "season_stage" in df.columns
