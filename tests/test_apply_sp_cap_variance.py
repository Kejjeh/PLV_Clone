"""apply_sp_cap() must reduce sigma2 along with fp when it zeroes a capped
start — issue #14.

project_sp_starts() (src/plv_clone/matchup_projection.py) computes a
pitcher's sigma2 as `n_starts * sigma**2` — a uniform per-start variance
share. apply_sp_cap() zeroed a capped start's mean FP contribution but left
sigma2 untouched, so win_probability() was fed a team variance inflated
relative to its (correctly reduced) mean.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from build_matchup_dashboard import apply_sp_cap  # noqa: E402


def _two_start_pitcher(fp_good=15.0, fp_bad=2.0, sigma=9.4):
    """A pitcher with 2 starts this week — sigma2 = 2 * sigma**2, matching
    project_sp_starts()'s actual formula."""
    return {
        'fp': fp_good + fp_bad,
        'sigma2': 2 * sigma ** 2,
        'breakdown': [
            {'type': 'start', 'fp': fp_good},
            {'type': 'start', 'fp': fp_bad},
        ],
    }


def test_capping_one_of_two_starts_halves_sigma2():
    """Cap forces the weaker start to zero — sigma2 must drop to the
    single-surviving-start share (sigma2 / 2), not stay at the 2-start
    combined value."""
    sigma = 9.4
    proj = _two_start_pitcher(sigma=sigma)
    team_projections = {'Ace McPitcher': proj}

    capped_fp = apply_sp_cap(team_projections, cap=1)

    assert capped_fp == 2.0
    assert proj['fp'] == 15.0
    assert proj['sigma2'] == pytest.approx(sigma ** 2, rel=1e-6)


def test_capping_nothing_leaves_sigma2_untouched():
    proj = _two_start_pitcher()
    team_projections = {'Ace McPitcher': proj}
    original_sigma2 = proj['sigma2']

    capped_fp = apply_sp_cap(team_projections, cap=5)

    assert capped_fp == 0
    assert proj['sigma2'] == original_sigma2


def test_capping_both_starts_of_same_pitcher_zeroes_sigma2():
    """If both of a pitcher's starts get capped (a 2-start pitcher zeroed
    entirely because the rest of the team already fills the cap), sigma2
    must go to ~0 — subtracting a fraction of the ALREADY-reduced sigma2 on
    the second capped start would under-remove variance and leave a
    residual instead of zero."""
    sigma = 9.4
    proj = _two_start_pitcher(fp_good=15.0, fp_bad=2.0, sigma=sigma)
    team_projections = {
        'Ace McPitcher': proj,
        # 3 other single-start pitchers filling the cap ahead of Ace's 2.
        'B': {'fp': 20.0, 'sigma2': sigma ** 2, 'breakdown': [{'type': 'start', 'fp': 20.0}]},
        'C': {'fp': 19.0, 'sigma2': sigma ** 2, 'breakdown': [{'type': 'start', 'fp': 19.0}]},
        'D': {'fp': 18.0, 'sigma2': sigma ** 2, 'breakdown': [{'type': 'start', 'fp': 18.0}]},
    }

    apply_sp_cap(team_projections, cap=3)

    assert proj['fp'] == 0.0
    assert proj['sigma2'] == pytest.approx(0.0, abs=1e-9)
