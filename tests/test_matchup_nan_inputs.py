"""A NaN matchup input must read as MISSING (neutral), never as the most
favourable multiplier.

Defect (found 2026-09-18): ``sp_opp_factor`` tested ``if not opp_bat_index``
and ``hitter_opp_factor`` tested ``is not None``. NaN passes both, ``1/NaN``
is NaN, and ``_clamp`` returns its UPPER bound for NaN (every comparison
against NaN is False). A missing team index or opposing-SP rate — routine when
a CSV cell is empty or a debutant has no rp3 row — therefore handed the player
a +20% (SP) / +30% (hitter) boost. ``platoon_factor`` was already NaN-safe,
which is the contract the other two now share.
"""
import math

from plv_clone.matchup_projection import (
    MatchupConfig,
    hitter_opp_factor,
    platoon_factor,
    sp_opp_factor,
)

CFG = MatchupConfig()
NAN = float("nan")


def test_sp_opp_factor_nan_is_neutral():
    assert sp_opp_factor(NAN) == 1.0
    assert sp_opp_factor(None) == 1.0
    assert sp_opp_factor(0.5) == 1.20          # a REAL value still clamps


def test_hitter_opp_factor_nan_sp_rate_falls_back_to_team_index():
    f, opp = hitter_opp_factor(NAN, 0.90, CFG)
    assert f == 0.90 and opp is None


def test_hitter_opp_factor_nan_everywhere_is_neutral():
    f, opp = hitter_opp_factor(NAN, NAN, CFG)
    assert f == 1.0 and opp is None
    f, opp = hitter_opp_factor(None, NAN, CFG)
    assert f == 1.0 and opp is None


def test_platoon_factor_nan_stays_neutral():
    assert platoon_factor(NAN, CFG) == 1.0


def test_no_factor_ever_returns_nan():
    for v in (NAN, None, 0.0, 1.0):
        assert not math.isnan(sp_opp_factor(v))
        assert not math.isnan(hitter_opp_factor(v, v, CFG)[0])


# ── review repair 2026-09-19: numeric missingness covers every non-finite scalar type ──

import numpy as np
import pytest


@pytest.mark.parametrize("bad", [np.float32("nan"), np.float64("nan"), float("inf"),
                                 float("-inf"), np.float32("inf"), np.float64("-inf")])
def test_non_finite_scalars_of_any_numeric_type_are_missing(bad):
    assert sp_opp_factor(bad) == 1.0
    assert hitter_opp_factor(bad, 0.90, CFG) == (0.90, None)     # falls to the team index
    assert hitter_opp_factor(bad, bad, CFG) == (1.0, None)


@pytest.mark.parametrize("good, expected", [(np.float32(0.5), 1.20), (np.float64(2.0), 0.80),
                                            (1.0, 1.0), (np.float32(1.0), 1.0)])
def test_valid_values_still_score_and_clamp_identically(good, expected):
    assert sp_opp_factor(good) == pytest.approx(expected)


def test_valid_hitter_rate_of_numpy_type_takes_the_sp_branch():
    f, opp = hitter_opp_factor(np.float64(14.0), 0.90, CFG)
    assert f == pytest.approx(11.5 / 14.0) and opp == pytest.approx(14.0)   # inside the 0.70-1.30 clamp
    f, opp = hitter_opp_factor(np.float64(23.0), 0.90, CFG)
    assert f == pytest.approx(0.70) and opp == pytest.approx(23.0)          # 11.5/23 = 0.5 -> clamp lo, unchanged
