"""Tests for the I4 reliever-band calibration study.

Pre-registration / result memo:
  data/research/validation_runs/rp_band_crps_2026-07-30.md

Two things are locked here.

1. The scoring rules are CORRECT. A calibration study that reports a
   CRPS-minimizing multiplier is only worth anything if the CRPS is right, so
   the closed-form Gaussian CRPS is checked against a high-precision Monte
   Carlo, and the O(m log m) sorted-identity ensemble CRPS is checked against
   the O(m^2) textbook definition it is an optimization of.

2. The band -> per-appearance sigma conversion FAILS LOUDLY on a degenerate
   band (House Rule 1). ``build_matchup_dashboard.py:568`` computes
   ``(p75 - p25) / 1.35`` with no guard, and ``xfp_rprs2_projections.csv``
   really does ship rows where ``p75 < p25`` (the ``clip(lower=0)`` at
   ``rprs2.py:409`` breaks the normal-IQR identity for negative projections).
   The unguarded expression therefore yields a NEGATIVE sigma, which
   ``leverage_engine._blend_draws`` then silently clamps to 1e-6 — a degenerate
   point mass presented as a predictive distribution. The tests below assert the
   old expression is negative on real production rows AND that the guarded
   helper refuses them, so the pair fails against the old behaviour by
   construction.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from validate_rp_band_crps import (  # noqa: E402
    RPRS2,
    SIGMA_PER_RP_GAME,
    crps_ensemble,
    crps_gaussian,
    implied_per_appearance_sigma,
    pinball,
)


# --------------------------------------------------------------------------- #
# 1. Closed-form Gaussian CRPS vs Monte Carlo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mu,sigma,y", [
    (0.0, 1.0, 0.0),
    (3.0, 2.5, 3.0),          # RP-scale, on the mean
    (3.0, 2.5, -8.0),         # a blow-up appearance: negatives are routine
    (2.26, 4.0, 12.0),        # the study's c* scale, upper tail
    (-1.5, 0.75, 4.0),
])
def test_crps_gaussian_matches_monte_carlo(mu, sigma, y):
    rng = np.random.default_rng(11)
    n = 400_000
    x1 = rng.normal(mu, sigma, n)
    x2 = rng.normal(mu, sigma, n)
    # CRPS = E|X - y| - 0.5 * E|X - X'|
    mc = np.abs(x1 - y).mean() - 0.5 * np.abs(x1 - x2).mean()
    closed = float(crps_gaussian(mu, sigma, y))
    assert closed == pytest.approx(mc, abs=0.02), (closed, mc)


def test_crps_gaussian_zero_at_perfect_point_forecast_limit():
    """As sigma -> 0 with y == mu, CRPS -> 0; and CRPS is scale-linear."""
    assert float(crps_gaussian(5.0, 1e-9, 5.0)) == pytest.approx(0.0, abs=1e-8)
    # CRPS(mu, s, mu) = s * (2*phi(0) - 1/sqrt(pi)) = s * (1/sqrt(pi))... check
    # linearity in s directly rather than restating the constant.
    a = float(crps_gaussian(0.0, 1.0, 0.0))
    b = float(crps_gaussian(0.0, 3.0, 0.0))
    assert b == pytest.approx(3.0 * a, rel=1e-12)


def test_crps_gaussian_drops_bad_sigma_instead_of_flooring():
    """sigma <= 0 or non-finite -> NaN, so callers DROP and count the row.

    A silent floor here is exactly the failure mode House Rule 1 forbids: it
    would turn a broken band into a confident, very sharp forecast.
    """
    out = crps_gaussian([0.0, 0.0, 0.0, 0.0],
                        [1.0, 0.0, -2.0, np.nan],
                        [1.0, 1.0, 1.0, 1.0])
    assert np.isfinite(out[0])
    assert np.isnan(out[1:]).all()


# --------------------------------------------------------------------------- #
# 2. Ensemble CRPS: sorted identity vs the O(m^2) definition
# --------------------------------------------------------------------------- #
def _crps_ensemble_bruteforce(samples, y):
    """Textbook O(m^2) fair estimator — the definition the fast path optimizes."""
    x = np.asarray(samples, float)
    y = np.asarray(y, float)
    out = np.empty(x.shape[0])
    for i in range(x.shape[0]):
        xi = x[i]
        m = len(xi)
        t1 = np.abs(xi - y[i]).mean()
        t2 = np.abs(xi[:, None] - xi[None, :]).sum() / (2.0 * m * m)
        out[i] = t1 - t2
    return out


def test_crps_ensemble_matches_bruteforce_definition():
    rng = np.random.default_rng(7)
    x = rng.normal(2.0, 3.0, size=(25, 120))
    y = rng.normal(2.0, 3.0, size=25)
    fast = crps_ensemble(x, y)
    slow = _crps_ensemble_bruteforce(x, y)
    assert np.allclose(fast, slow, rtol=1e-12, atol=1e-12)


def test_crps_ensemble_handles_unsorted_and_duplicated_samples():
    x = np.array([[3.0, -1.0, 3.0, 0.0, 3.0]])
    y = np.array([1.0])
    assert crps_ensemble(x, y) == pytest.approx(_crps_ensemble_bruteforce(x, y))


def test_crps_ensemble_agrees_with_closed_form_on_a_gaussian_sample():
    """Cross-validates the two independent estimators against each other."""
    rng = np.random.default_rng(123)
    mu, sigma, y = 3.0, 2.5, -4.0
    x = rng.normal(mu, sigma, size=(1, 200_000))
    assert float(crps_ensemble(x, np.array([y]))[0]) == pytest.approx(
        float(crps_gaussian(mu, sigma, y)), rel=0.01)


def test_crps_ensemble_rejects_bad_input():
    with pytest.raises(ValueError):
        crps_ensemble(np.zeros(10), np.zeros(10))              # 1-D samples
    with pytest.raises(ValueError):
        crps_ensemble(np.zeros((3, 5)), np.zeros(4))           # row mismatch
    bad = np.zeros((2, 5))
    bad[1, 2] = np.nan
    with pytest.raises(ValueError):
        crps_ensemble(bad, np.zeros(2))                        # non-finite


# --------------------------------------------------------------------------- #
# 3. Pinball
# --------------------------------------------------------------------------- #
def test_pinball_is_asymmetric_in_the_declared_direction():
    # q=0.25: under-prediction (y > qhat) is penalised at weight q
    assert pinball(10.0, 6.0, 0.25) == pytest.approx(0.25 * 4.0)
    # over-prediction (y < qhat) at weight (1-q)
    assert pinball(2.0, 6.0, 0.25) == pytest.approx(0.75 * 4.0)
    assert pinball(5.0, 5.0, 0.75) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# 4. The band -> per-appearance conversion fails loudly (House Rule 1)
# --------------------------------------------------------------------------- #
def test_implied_sigma_normal_case():
    # normal-IQR identity: width/1.35 is the total sigma, /sqrt(n) per unit
    s = implied_per_appearance_sigma(100.0, 157.4, 25.0)
    assert s == pytest.approx((57.4 / 1.35) / 5.0, rel=1e-12)


@pytest.mark.parametrize("p25,p75", [
    (31.6, -77.2),     # Tyler Tolbert, shipped 2026-07-30
    (0.0, -21.6),      # Ben Williamson
    (7.0, 6.6),        # Joey Lucchesi — inverted by only 0.4
    (5.0, 5.0),        # exactly degenerate
])
def test_implied_sigma_raises_on_non_positive_band_width(p25, p75):
    naive = (p75 - p25) / 1.35          # the unguarded production expression
    assert naive <= 0, "fixture must actually be degenerate"
    with pytest.raises(ValueError, match="non-positive rprs2 band width"):
        implied_per_appearance_sigma(p25, p75, 25.0)


def test_implied_sigma_raises_on_non_positive_expected_appearances():
    with pytest.raises(ValueError, match="must be > 0"):
        implied_per_appearance_sigma(100.0, 157.4, 0.0)
    with pytest.raises(ValueError, match="must be > 0"):
        implied_per_appearance_sigma(100.0, 157.4, float("nan"))


@pytest.mark.skipif(not RPRS2.exists(), reason="rprs2 projections not built")
def test_production_rprs2_really_ships_inverted_bands_and_they_are_rejected():
    """Exercise the guard on REAL production rows.

    This is the test that fails against the old behaviour: the unguarded
    dashboard expression returns a finite NEGATIVE sigma for these rows, which
    then reaches ``_blend_draws`` and is clamped to 1e-6.
    """
    import pandas as pd
    df = pd.read_csv(RPRS2)
    width = df["xfp_ros_p75"] - df["xfp_ros_p25"]
    bad = df[width <= 0]
    assert len(bad) > 0, (
        "expected at least one inverted band in the shipped rprs2 CSV; if this "
        "now passes, rprs2.py's clip(lower=0) was fixed — update the memo")
    for _, r in bad.iterrows():
        naive = (r["xfp_ros_p75"] - r["xfp_ros_p25"]) / 1.35
        assert np.isfinite(naive) and naive <= 0     # old behaviour: silent
        with pytest.raises(ValueError):              # new behaviour: loud
            implied_per_appearance_sigma(r["xfp_ros_p25"], r["xfp_ros_p75"], 25.0)


# --------------------------------------------------------------------------- #
# 5. The measured result the memo reports, pinned to the production constant
# --------------------------------------------------------------------------- #
def test_production_rp_sigma_constant_is_the_one_the_study_scored():
    """If SIGMA_PER_RP_GAME moves, the memo's c* is no longer about production."""
    from build_matchup_dashboard import SIGMA_PER_RP_GAME as prod
    assert SIGMA_PER_RP_GAME == prod == 2.5


def test_wider_band_is_better_when_the_narrow_one_is_too_sharp():
    """Directional sanity for the c* search: at the measured per-appearance
    dispersion (~4 FP within-pitcher SD), a 2.5 FP Gaussian is over-sharp, so a
    4.0 FP band must score better in expectation. This is the mechanism behind
    the memo's c* = 1.60 and it must not silently invert.
    """
    rng = np.random.default_rng(2026)
    y = rng.normal(3.0, 4.0, 200_000)          # truth: sigma 4.0
    narrow = np.nanmean(crps_gaussian(np.full_like(y, 3.0),
                                      np.full_like(y, 2.5), y))
    wide = np.nanmean(crps_gaussian(np.full_like(y, 3.0),
                                    np.full_like(y, 4.0), y))
    assert wide < narrow
    # and the optimum is at the truth, not merely "wider is always better"
    too_wide = np.nanmean(crps_gaussian(np.full_like(y, 3.0),
                                        np.full_like(y, 10.0), y))
    assert wide < too_wide
    assert norm.cdf(1.0) > 0.8   # guards the scipy import used above
