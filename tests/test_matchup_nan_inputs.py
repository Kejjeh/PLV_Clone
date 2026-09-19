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
