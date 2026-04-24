"""
Tests for season stage inference — especially the new season_date parameter (P1-E).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from plv_clone.utils.season_stage import infer_stage


class TestInferStageByDate:
    def test_early_april(self):
        assert infer_stage(season_date=date(2026, 4, 15)) == "early"

    def test_early_may_before_cutoff(self):
        assert infer_stage(season_date=date(2026, 5, 15)) == "early"

    def test_mid_on_cutoff(self):
        assert infer_stage(season_date=date(2026, 5, 16)) == "mid"

    def test_mid_june(self):
        assert infer_stage(season_date=date(2026, 6, 15)) == "mid"

    def test_mid_july_before_cutoff(self):
        assert infer_stage(season_date=date(2026, 7, 25)) == "mid"

    def test_mature_on_cutoff(self):
        assert infer_stage(season_date=date(2026, 7, 26)) == "mature"

    def test_mature_august(self):
        assert infer_stage(season_date=date(2026, 8, 15)) == "mature"

    def test_mature_september(self):
        assert infer_stage(season_date=date(2026, 9, 30)) == "mature"

    def test_date_takes_precedence_over_pa_signal(self):
        """A mature calendar date beats low PA that would indicate early."""
        low_pa_hitters = pd.DataFrame({"pa": [20, 30, 25, 15]})
        # PA-based inference would say "early"; date says "mature"
        assert infer_stage(hitters=low_pa_hitters, season_date=date(2026, 8, 1)) == "mature"

    def test_date_early_overrides_high_pa(self):
        """An early calendar date beats high PA that would indicate mature."""
        high_pa_hitters = pd.DataFrame({"pa": [400, 450, 380, 420]})
        assert infer_stage(hitters=high_pa_hitters, season_date=date(2026, 4, 20)) == "early"


class TestInferStageByPA:
    """PA-based fallback still works when no season_date is given."""

    def test_early_by_pa(self):
        hitters = pd.DataFrame({"pa": [50, 80, 100, 120]})
        assert infer_stage(hitters=hitters) == "early"

    def test_mid_by_pa(self):
        hitters = pd.DataFrame({"pa": [150, 200, 250, 180]})
        assert infer_stage(hitters=hitters) == "mid"

    def test_mature_by_pa(self):
        hitters = pd.DataFrame({"pa": [400, 350, 420, 380]})
        assert infer_stage(hitters=hitters) == "mature"

    def test_fallback_to_mature_when_no_inputs(self):
        assert infer_stage() == "mature"

    def test_fallback_to_pitchers_when_no_hitters(self):
        pitchers = pd.DataFrame({"pitches": [80, 100, 90]})
        assert infer_stage(pitchers=pitchers) == "early"
