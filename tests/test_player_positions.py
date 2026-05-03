"""
Tests for player_positions.build_position_map() — specifically the fix that
unconditionally grants eligibility for a player's primary registered position
regardless of games-started threshold (mirrors ESPN behaviour).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from plv_clone.data.player_positions import PositionConfig, build_position_map


# ── helpers ───────────────────────────────────────────────────────────────────

def _fielding_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal fielding-stats DataFrame from a list of row dicts."""
    return pd.DataFrame(
        rows,
        columns=["player_id", "player_name", "position_raw", "games_played", "games_started"],
    )


# ── tests ─────────────────────────────────────────────────────────────────────

class TestPrimaryPositionAlwaysEligible:
    """Primary registered position must appear in fantasy_positions even when
    the player has zero games started there (e.g. catcher who only DHs)."""

    def test_catcher_primary_no_gs_at_c(self, monkeypatch, tmp_path):
        """
        Player 999 is registered as C (primary) but has 0 GS at C.
        He has 15 GS at DH only, which passes the threshold.
        After the fix, both "C" and "DH" must be in fantasy_positions.
        """
        import plv_clone.data.player_positions as pp_mod

        # Stub API calls so the test runs offline
        monkeypatch.setattr(pp_mod, "fetch_primary_positions", lambda year: {999: "C"})
        monkeypatch.setattr(
            pp_mod,
            "fetch_fielding_stats",
            lambda year: _fielding_df([
                # Player 999 has 15 GS at DH but 0 GS at C
                {"player_id": 999, "player_name": "Ivan Herrera",
                 "position_raw": "C",  "games_played": 5, "games_started": 0},
                {"player_id": 999, "player_name": "Ivan Herrera",
                 "position_raw": "DH", "games_played": 20, "games_started": 15},
            ]),
        )

        result = build_position_map(2026, config=PositionConfig(), cache_dir=None)

        assert len(result) == 1
        row = result.iloc[0]
        positions = set(row["fantasy_positions"].split("|")) if row["fantasy_positions"] else set()

        assert "C" in positions, (
            f"Expected 'C' in fantasy_positions but got: {row['fantasy_positions']!r}"
        )
        assert "DH" in positions, (
            f"Expected 'DH' in fantasy_positions but got: {row['fantasy_positions']!r}"
        )
        assert row["primary_position"] == "C"

    def test_gs_threshold_position_also_included(self, monkeypatch, tmp_path):
        """
        Player meets GS threshold at 2B. Primary is SS (below threshold).
        Both 2B and SS must appear in fantasy_positions.
        """
        import plv_clone.data.player_positions as pp_mod

        monkeypatch.setattr(pp_mod, "fetch_primary_positions", lambda year: {500: "SS"})
        monkeypatch.setattr(
            pp_mod,
            "fetch_fielding_stats",
            lambda year: _fielding_df([
                {"player_id": 500, "player_name": "Test Player",
                 "position_raw": "2B", "games_played": 20, "games_started": 15},
                {"player_id": 500, "player_name": "Test Player",
                 "position_raw": "SS", "games_played": 5,  "games_started": 3},
            ]),
        )

        result = build_position_map(2026, config=PositionConfig(), cache_dir=None)
        row = result.iloc[0]
        positions = set(row["fantasy_positions"].split("|")) if row["fantasy_positions"] else set()

        assert "2B" in positions
        assert "SS" in positions

    def test_pitcher_primary_excluded(self, monkeypatch, tmp_path):
        """
        With exclude_pitchers=True (default), a pitcher's primary position (P)
        must NOT be added to fantasy_positions.
        """
        import plv_clone.data.player_positions as pp_mod

        monkeypatch.setattr(pp_mod, "fetch_primary_positions", lambda year: {700: "P"})
        monkeypatch.setattr(
            pp_mod,
            "fetch_fielding_stats",
            lambda year: _fielding_df([
                {"player_id": 700, "player_name": "Pitcher McPitch",
                 "position_raw": "P", "games_played": 30, "games_started": 30},
            ]),
        )

        result = build_position_map(2026, config=PositionConfig(exclude_pitchers=True), cache_dir=None)
        row = result.iloc[0]
        positions = set(row["fantasy_positions"].split("|")) if row["fantasy_positions"] else set()

        assert "P" not in positions
        assert "SP" not in positions
        assert "RP" not in positions
