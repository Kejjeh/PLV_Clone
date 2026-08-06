# -*- coding: utf-8 -*-
"""Locks the volume rule the playoff board got wrong once.

The original board took max(projection, season-to-date, trailing-30d), which
silently reverts to the uncalibrated rate whenever raw pace is higher. These
tests pin the corrected precedence so it cannot come back.
"""
import datetime

import pytest

from scripts.xfp.build_playoff_board import availability, resolve_volume
from scripts.xfp.lib import late_season_volume as lsv


class TestResolveVolume:
    def test_uses_the_projection_as_is_even_when_pace_is_higher(self):
        # THE regression: season-to-date is higher, and must still lose
        assert resolve_volume(3.50, 4.60, 'H') == pytest.approx(3.50)

    def test_never_returns_the_max_of_its_inputs(self):
        for proj, to_date in ((3.5, 4.6), (0.14, 0.20), (2.9, 3.7)):
            side = 'SP' if proj < 1 else 'H'
            assert resolve_volume(proj, to_date, side) < max(proj, to_date)

    def test_falls_back_to_shrunk_season_to_date_without_a_projection(self):
        got = resolve_volume(None, 4.0, 'H')
        assert got == pytest.approx(4.0 * lsv.HITTER_RETENTION)
        assert got < 4.0

    def test_il_healthy_rate_wins_and_is_itself_shrunk(self):
        # Judge: projection and pace are both IL-suppressed, healthy is 4.24
        got = resolve_volume(2.29, 2.29, 'H', healthy=4.24)
        assert got == pytest.approx(4.24 * lsv.HITTER_RETENTION)
        assert got > 2.29

    def test_starter_volume_is_capped_at_a_rotation_slot(self):
        # a 30-day stretch without off-days can imply an impossible rate
        assert resolve_volume(0.30, 0.30, 'SP') == pytest.approx(0.21)
        assert resolve_volume(None, None, 'SP', healthy=0.40) == pytest.approx(0.21)

    def test_missing_everything_scores_zero_not_nan(self):
        assert resolve_volume(None, None, 'H') == 0.0


class TestAvailability:
    START = datetime.date(2026, 8, 24)
    END = datetime.date(2026, 9, 27)

    def test_healthy_player_is_fully_available(self):
        assert availability('', None, self.START, self.END) == 1.0

    def test_il_without_a_return_date_gets_no_credit(self):
        assert availability('SIXTY_DAY_DL', None, self.START, self.END) == 0.0

    def test_return_before_the_window_is_full_credit(self):
        assert availability('TEN_DAY_DL', datetime.date(2026, 8, 1),
                            self.START, self.END) == 1.0

    def test_return_after_the_window_is_worthless(self):
        assert availability('SIXTY_DAY_DL', datetime.date(2026, 10, 5),
                            self.START, self.END) == 0.0

    def test_mid_window_return_is_prorated(self):
        got = availability('TEN_DAY_DL', datetime.date(2026, 9, 10),
                           self.START, self.END)
        assert 0.0 < got < 1.0
        assert got == pytest.approx(17 / 34)
