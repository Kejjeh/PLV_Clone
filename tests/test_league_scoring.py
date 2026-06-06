"""
Tests for LeagueScoring game-level scoring API (PR 5 sub-action 1).

Covers:
- _parse_ip module-level helper (10 parametrized cases for MLB gameLog
  inningsPitched parsing including fractional-inning notation '.1' / '.2').
- score_hitter_game using non-default LeagueScoring weights.
- score_pitcher_start delegating to _score_pitcher_base_game (and ignoring
  SV/HLD in the input stats dict).
- score_pitcher_relief layering self.sv * saves + self.hd * holds on top
  of the shared base-game scoring.
"""

from __future__ import annotations

import pytest

from plv_clone.fantasy.scoring import LeagueScoring, _parse_ip


# ── _parse_ip parametrize block (10 cases) ────────────────────────────────────
@pytest.mark.parametrize(
    "raw, expected",
    [
        ('0.0', 0.0),
        ('1.0', 1.0),
        ('5.1', 5 + 1 / 3),
        ('5.2', 5 + 2 / 3),
        (5.0, 5.0),
        (0, 0.0),
        (None, 0.0),
        ('', 0.0),
        ('5', 5.0),
    ],
)
def test_parse_ip_valid(raw, expected):
    """_parse_ip must convert MLB gameLog inningsPitched strings + numerics."""
    assert _parse_ip(raw) == pytest.approx(expected)


def test_parse_ip_invalid_partial_raises():
    """'5.3' is not a valid partial-inning notation (only .0/.1/.2 exist)."""
    with pytest.raises(ValueError):
        _parse_ip('5.3')


# ── Scoring method tests (3) ──────────────────────────────────────────────────
def test_score_hitter_game():
    """score_hitter_game reads dataclass fields correctly (use non-default values)."""
    scoring = LeagueScoring(
        r=2.0,
        tb=1.5,
        rbi=3.0,
        bb_bat=0.5,
        hbp_bat=0.25,
        sb=4.0,
        k_bat=-1.5,
    )
    stats = {
        'runs': 2,
        'totalBases': 4,
        'rbi': 1,
        'baseOnBalls': 1,
        'hitByPitch': 0,
        'stolenBases': 1,
        'strikeOuts': 2,
    }
    expected = (
        2.0 * 2          # r * runs
        + 1.5 * 4        # tb * totalBases
        + 3.0 * 1        # rbi * rbi
        + 0.5 * 1        # bb_bat * baseOnBalls
        + 0.25 * 0       # hbp_bat * hitByPitch
        + 4.0 * 1        # sb * stolenBases
        + (-1.5) * 2     # k_bat * strikeOuts
    )
    assert scoring.score_hitter_game(stats) == pytest.approx(expected)


def test_score_pitcher_start_uses_base_game():
    """score_pitcher_start delegates to _score_pitcher_base_game; SV/HLD ignored."""
    scoring = LeagueScoring(
        k_pit=1.5,
        ip=3.5,
        h_pit=-0.75,
        er=-2.5,
        bb_pit=-1.25,
        hb_pit=-1.25,
        sv=99.0,   # non-default, must NOT contribute for a start
        hd=99.0,   # non-default, must NOT contribute for a start
    )
    stats = {
        'inningsPitched': '6.0',
        'strikeOuts': 7,
        'hits': 4,
        'earnedRuns': 2,
        'baseOnBalls': 1,
        'hitByPitch': 0,
    }
    expected_base = (
        1.5 * 7              # k_pit * strikeOuts
        + 3.5 * 6.0          # ip * IP(6.0)
        + (-0.75) * 4        # h_pit * hits
        + (-2.5) * 2         # er * earnedRuns
        + (-1.25) * 1        # bb_pit * baseOnBalls
        + (-1.25) * 0        # hb_pit * hitByPitch
    )
    assert scoring.score_pitcher_start(stats) == pytest.approx(expected_base)

    # Sanity check: SV/HLD in stats dict must NOT change a start's FP.
    stats_with_sv_hld = dict(stats, saves=1, holds=1)
    assert scoring.score_pitcher_start(stats_with_sv_hld) == pytest.approx(expected_base)


def test_score_pitcher_relief_adds_sv_hld():
    """score_pitcher_relief adds self.sv * saves + self.hd * holds atop base."""
    scoring = LeagueScoring(
        k_pit=1.0,
        ip=3.3,
        h_pit=-1.0,
        er=-2.0,
        bb_pit=-1.0,
        hb_pit=-1.0,
        sv=5.0,
        hd=2.5,    # non-default to prove the field is read
    )
    # Case 1: 1 IP relief, 1 HLD, no SV.
    stats_hld = {
        'inningsPitched': '1.0',
        'strikeOuts': 2,
        'hits': 1,
        'earnedRuns': 0,
        'baseOnBalls': 0,
        'hitByPitch': 0,
        'saves': 0,
        'holds': 1,
    }
    base_game_fp = (
        1.0 * 2          # k_pit * strikeOuts
        + 3.3 * 1.0      # ip * IP(1.0)
        + (-1.0) * 1     # h_pit * hits
        + (-2.0) * 0     # er * earnedRuns
        + (-1.0) * 0     # bb_pit * baseOnBalls
        + (-1.0) * 0     # hb_pit * hitByPitch
    )
    assert scoring.score_pitcher_relief(stats_hld) == pytest.approx(base_game_fp + 2.5)

    # Case 2: same base game with 1 SV (and 0 HLD) adds sv=5.0 on top.
    stats_sv = dict(stats_hld, saves=1, holds=0)
    assert scoring.score_pitcher_relief(stats_sv) == pytest.approx(base_game_fp + 5.0)
