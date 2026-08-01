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

from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
CONTRACT_YEAR = 2026

# ── Column contracts (single source of truth for this file) ──────────────────

# master_hitter_{year}.csv — read by Hitters tab, Player View, Hitter Fantasy tab
#
# 2026-08-01 correction (audit item 36): this list used to name `discipline_plus`
# and `season_stage`. The export has carried NEITHER in any vintage (checked
# 2023/2024/2025/2026) — the pillar is written as `decision_plus`, and
# `discipline_plus` is synthesised DOWNSTREAM at
# src/plv_clone/pipelines/build_target_boards.py:102
# (`hitters["discipline_plus"] = hitters["decision_plus"]`), which is why the
# board exports below legitimately require it and this one does not.
# The old names were only ever checked against a hand-written fixture, so the
# four-season drift was invisible. Corrected here rather than in the export:
# adding columns to a shipped artifact that app/dashboard.py and the Player View
# read would be a behavior change dressed up as a test fix.
#
# NOTE (review 2026-08-01): app/dashboard.py still NAMES `discipline_plus` in
# its candidate display/sort lists, but every such reference is filtered
# through `if c in df.columns` (or the df_show re-filter at :673), so the
# absent column degrades to not-displayed rather than crashing — which is why
# the contract tracks the ARTIFACT's real columns, not the dashboard's
# wish-list. If discipline_plus's successor (`decision_plus`) is ever meant to
# surface there, that is a dashboard change, not a contract change.
MASTER_HITTER_REQUIRED = [
    "batter", "batter_name", "pa",
    "process_plus", "decision_plus", "k_avoidance_plus", "power_plus",
    "fantasy_positions", "fantasy_positions_display", "primary_position",
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
#
# 2026-08-01 correction (audit item 36): `season_stage` was declared here but the
# pitcher board has never written it (14 columns; the hitter boards DO carry it).
# Second violation the vacuous fixture tests were hiding.
BOARD_PITCHER_REQUIRED = [
    "player_name", "pitches", "plv",
    "confidence",
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


# ── The contract, checked against the file the pipeline ACTUALLY wrote ────────
#
# Audit 2026-08-01 item 36: eight `test_required_cols_present` methods used to
# check a hand-written in-memory fixture against the constant it had been
# transcribed from. Copy == copy, so they could not fail — and they were green
# for four seasons while master_hitter_*.csv did not carry two of the columns
# the constant claimed. These parametrized cases read the real export instead.
#
# Semantics are ADDITIVE (superset): a pipeline that adds a column must not fail
# here; only a DROPPED or RENAMED column does.

EXPORT_CONTRACTS = {
    "master_hitter": (f"master_hitter_{CONTRACT_YEAR}.csv", MASTER_HITTER_REQUIRED),
    "master_pitcher": (f"master_pitcher_{CONTRACT_YEAR}.csv", MASTER_PITCHER_REQUIRED),
    "process_plus_rolling": (f"process_plus_rolling_{CONTRACT_YEAR}.csv",
                             ROLLING_HITTER_REQUIRED),
    "plv_rolling": (f"plv_rolling_{CONTRACT_YEAR}.csv", ROLLING_PITCHER_REQUIRED),
    "hitter_board": (f"hitter_buy_targets_{CONTRACT_YEAR}.csv", BOARD_HITTER_REQUIRED),
    "pitcher_board": (f"pitcher_plv_targets_{CONTRACT_YEAR}.csv", BOARD_PITCHER_REQUIRED),
    "hitter_fantasy": (f"hitter_fantasy_{CONTRACT_YEAR}.csv", HITTER_FANTASY_REQUIRED),
    "pitcher_fantasy": (f"pitcher_fantasy_{CONTRACT_YEAR}.csv", PITCHER_FANTASY_REQUIRED),
}


@pytest.mark.parametrize("label", sorted(EXPORT_CONTRACTS))
def test_shipped_export_carries_its_declared_contract(label):
    """The export on disk must carry every column its consumers read by name.

    A missing column does not raise at runtime — app/dashboard.py filters its
    Sort-by list with `if c in hitters.columns`, so the option just silently
    disappears from the UI. This test is the only place that notices.
    """
    fname, required = EXPORT_CONTRACTS[label]
    path = REPO_ROOT / "data" / "outputs" / fname
    if not path.exists():
        pytest.skip(f"{path} not present in this checkout (pipeline not yet run)")
    cols = list(pd.read_csv(path, nrows=1).columns)
    missing = [c for c in required if c not in cols]
    assert not missing, (
        f"{fname} is missing declared contract columns {missing}.\n"
        f"Either the pipeline dropped/renamed them, or the constant is "
        f"aspirational — correct whichever is wrong, do NOT widen the export to "
        f"satisfy the test.\nColumns actually written ({len(cols)}): {cols}")


# ── dtypes and value domains, read off the shipped export ────────────────────
#
# These replace a set of per-class fixture assertions that checked the dtype of a
# literal the test itself had just written (`assert is_numeric_dtype(sample["pa"])`
# on a frame built from python ints). Same intent, but pointed at the artifact.

DTYPE_CONTRACTS = [
    ("master_hitter", "batter", "numeric"),
    ("master_hitter", "process_plus", "numeric"),
    ("master_hitter", "fantasy_positions", "string"),
    ("master_pitcher", "plv", "numeric"),
    ("hitter_fantasy", "core_fp_per_pa", "numeric"),
    ("hitter_fantasy", "full_fp_per_pa", "numeric"),
    ("pitcher_fantasy", "fp_per_ip", "numeric"),
]


@pytest.mark.parametrize("label,column,kind", DTYPE_CONTRACTS)
def test_shipped_export_column_dtype(label, column, kind):
    fname, _ = EXPORT_CONTRACTS[label]
    path = REPO_ROOT / "data" / "outputs" / fname
    if not path.exists():
        pytest.skip(f"{path} not present in this checkout (pipeline not yet run)")
    s = pd.read_csv(path, nrows=200)[column].dropna()
    if s.empty:
        pytest.skip(f"{fname}:{column} is all-null in the sampled rows")
    check = (pd.api.types.is_numeric_dtype if kind == "numeric"
             else pd.api.types.is_string_dtype)
    assert check(s), f"{fname}:{column} is {s.dtype}, expected {kind}"


def test_hitter_board_season_stage_is_a_known_stage():
    """`season_stage` drives the threshold set the board was built with, so an
    unrecognised value means a board scored against thresholds nobody declared."""
    fname, _ = EXPORT_CONTRACTS["hitter_board"]
    path = REPO_ROOT / "data" / "outputs" / fname
    if not path.exists():
        pytest.skip(f"{path} not present in this checkout (pipeline not yet run)")
    seen = set(pd.read_csv(path)["season_stage"].dropna().unique())
    assert seen, f"{fname} wrote no season_stage values at all"
    assert seen <= {"early", "mid", "mature"}, f"unknown season_stage values: {seen}"


# hitter_pre_breakout_{year}.csv — read by Target Boards tab
PRE_BREAKOUT_REQUIRED = [
    "batter_name", "pa", "blast_rate", "discipline_plus",
    "xwoba_on_contact", "tag", "season_stage",
]


# ── build_target_boards column constants ─────────────────────────────────────

class TestBoardBaseColsContract:
    """_BASE_HITTER_COLS must contain dashboard-critical fields (regression guard)."""

    def test_base_hitter_cols_has_required(self):
        from plv_clone.pipelines.build_target_boards import _BASE_HITTER_COLS
        for col in ("fantasy_positions", "fantasy_positions_display", "season_stage"):
            assert col in _BASE_HITTER_COLS, f"_BASE_HITTER_COLS missing: {col}"


# ── pre-breakout board ────────────────────────────────────────────────────────

class TestPreBreakoutContract:
    """Schema and no-data behavior for hitter_pre_breakout_{year}.csv."""

    def _base_hitters(self):
        return pd.DataFrame({
            "batter": [1, 2, 3],
            "batter_name": ["A", "B", "C"],
            "pa": [80, 60, 40],
            "confidence": ["Tier A", "Tier A", "Watch"],
            "primary_position": ["OF", "1B", "3B"],
            "fantasy_positions": ["OF", "1B", "3B"],
            "fantasy_positions_display": ["OF", "1B", "3B"],
            "process_plus": [112.0, 109.0, 105.0],
            "discipline_plus": [114.0, 110.0, 95.0],
            "k_avoidance_plus": [108.0, 103.0, 99.0],
            "power_plus": [110.0, 105.0, 100.0],
            "xwoba_on_contact": [0.360, 0.350, 0.380],
            "blast_rate": [0.12, 0.09, 0.07],
            "avg_swing_speed": [74.5, 72.1, 70.8],
            "swing_count": [200, 150, 120],
            "rolling_decision_30d": [0.068, 0.065, 0.060],
            "rolling_trend": ["hot", "warm", "flat"],
            "season_stage": ["mature", "mature", "mature"],
        })

    def test_populated_result_has_required_cols(self):
        from plv_clone.pipelines.build_target_boards import (
            _pre_breakout_board, get_thresholds,
        )
        t = get_thresholds("mature")
        result = _pre_breakout_board(self._base_hitters(), t)
        assert isinstance(result, pd.DataFrame)
        _assert_cols(result, PRE_BREAKOUT_REQUIRED, "hitter_pre_breakout")

    def test_no_blast_rate_col_returns_schemaful_empty(self):
        from plv_clone.pipelines.build_target_boards import (
            _pre_breakout_board, _PRE_BREAKOUT_EMPTY_COLS, get_thresholds,
        )
        h = self._base_hitters().drop(columns=["blast_rate"])
        t = get_thresholds("mature")
        result = _pre_breakout_board(h, t)
        assert len(result) == 0
        assert list(result.columns) == _PRE_BREAKOUT_EMPTY_COLS

    def test_all_null_blast_rate_returns_schemaful_empty(self):
        from plv_clone.pipelines.build_target_boards import (
            _pre_breakout_board, _PRE_BREAKOUT_EMPTY_COLS, get_thresholds,
        )
        h = self._base_hitters().copy()
        h["blast_rate"] = float("nan")
        t = get_thresholds("mature")
        result = _pre_breakout_board(h, t)
        assert len(result) == 0
        assert list(result.columns) == _PRE_BREAKOUT_EMPTY_COLS
