"""F2 regression locks — the SP bench/start sampler MUST be able to blow up.

The defect these tests exist for: sp_bench_mc.build_sp_sampler's 'rp3' and
'blend' modes ('blend' is the CLI DEFAULT) drew from a moment-matched LOGNORMAL,
whose support is (0, inf). BrownU SP FP = K + IP*3.3 - H - 2*ER - BB - HBP has no
floor, and 170 of 1037 real single starts in the validation panel finished at
FP <= 0 (16.39%, min -23.5). So P(modeled FP <= 0) was EXACTLY 0 for every
pitcher, every start — the single most decision-relevant outcome for a
bench/start call was modeled as impossible.

931 tests passed with that bug live, because nothing ever asserted the sampler's
left tail. That missing assertion is the defect. It is these tests.

Study: data/research/validation_runs/sp_sampler_tail_family_2026-07-29.md
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
for _p in (ROOT, os.path.join(ROOT, 'scripts', 'xfp')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Panel constants measured in the pre-registered F2 run (n=1037 starts,
# 202 pitchers, rp3 snapshots x boxscore_pitchers).
REALIZED_NEG_RATE = 0.1639          # 170/1037 real starts at FP <= 0
PANEL_MU = 10.054                   # mean rp3 per-start over the panel
PANEL_SIGMA = 8.642                 # mean xfp_rp3_sigma (display band, x2.41)
PANEL_MIN_FP = -23.5                # worst real start in the panel

N_DRAWS = 200_000


def _sampler(prior, emp_fps=(), mu=PANEL_MU, sigma=PANEL_SIGMA, k_prior=20):
    import sp_bench_mc
    fn, w = sp_bench_mc.build_sp_sampler(list(emp_fps), mu, sigma, prior,
                                         k_prior=k_prior, label='test-SP')
    return fn, w


# ---------------------------------------------------------------------------
# THE test whose absence let this ship
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('prior', ['rp3', 'blend'])
def test_parametric_sampler_can_produce_nonpositive_fp(prior):
    """P(FP <= 0) must not be identically zero for the parametric legs."""
    fn, _ = _sampler(prior, emp_fps=[])
    rng = np.random.default_rng(11)
    draws = fn(rng, N_DRAWS)
    n_bad = int((draws <= 0).sum())
    assert n_bad > 0, (
        f'prior={prior!r}: sampler produced ZERO draws at FP <= 0 out of '
        f'{N_DRAWS}. A distribution on (0, inf) cannot price a blow-up; '
        f'{REALIZED_NEG_RATE*100:.2f}% of real starts land there.')


@pytest.mark.parametrize('prior', ['rp3', 'blend'])
def test_parametric_sampler_neg_rate_near_empirical(prior):
    """P(FP <= 0) must land in the neighbourhood of the realized 16.39%.

    Validated Gaussian value at the panel mean (mu=10.054, sigma=8.642) is
    Phi(-mu/sigma) = 12.2%. The realized rate is 16.39%. The band below is
    deliberately generous on the LOW side only down to 8% — it is a
    structural-sanity lock, not a calibration gate (calibration is the study's
    job) — but it hard-fails both the old 0% and any accidental blow-out.
    """
    fn, _ = _sampler(prior, emp_fps=[])
    rng = np.random.default_rng(12)
    rate = float((fn(rng, N_DRAWS) <= 0).mean())
    assert 0.08 <= rate <= 0.28, (
        f'prior={prior!r}: modeled P(FP<=0)={rate:.4f} is not in the '
        f'neighbourhood of the realized {REALIZED_NEG_RATE:.4f}')
    # and it must be within 6pp of realized at the panel average inputs
    assert abs(rate - REALIZED_NEG_RATE) < 0.06, (
        f'prior={prior!r}: modeled P(FP<=0)={rate:.4f} vs realized '
        f'{REALIZED_NEG_RATE:.4f} — off by more than 6pp')


def test_parametric_sampler_reaches_the_worst_real_start():
    """The sampler must be able to reach a -23.5 FP start (the panel minimum)."""
    fn, _ = _sampler('rp3')
    rng = np.random.default_rng(13)
    draws = fn(rng, N_DRAWS)
    assert draws.min() <= PANEL_MIN_FP, (
        f'sampler minimum {draws.min():.2f} never reaches the worst real start '
        f'({PANEL_MIN_FP} FP) in {N_DRAWS} draws')


def test_p10_is_negative_at_panel_average_inputs():
    """The consumer-facing downside number must actually be a downside.

    Under the lognormal, mean p10 across the panel was +3.078 FP — i.e. the
    "10th percentile" of a start was a POSITIVE score. Gaussian gives -1.022.
    """
    fn, _ = _sampler('rp3')
    rng = np.random.default_rng(14)
    p10 = float(np.percentile(fn(rng, N_DRAWS), 10))
    assert p10 < 0, f'p10={p10:.3f} — modeled downside is still non-negative'


def test_moments_are_preserved():
    """Swapping the family must not move the mean/SD it is matched to."""
    fn, _ = _sampler('rp3')
    rng = np.random.default_rng(15)
    d = fn(rng, N_DRAWS)
    assert abs(d.mean() - PANEL_MU) < 0.10
    assert abs(d.std() - PANEL_SIGMA) < 0.10


def test_sampler_is_not_lognormal_anymore():
    """Direct guard against a revert: a lognormal is strictly positive."""
    import sp_bench_mc
    rng = np.random.default_rng(16)
    ln = sp_bench_mc._lognormal_draws(rng, PANEL_MU, PANEL_SIGMA, 50_000)
    assert (ln > 0).all(), 'sanity: _lognormal_draws is positive by construction'
    fn, _ = _sampler('rp3')
    assert not (fn(np.random.default_rng(16), 50_000) > 0).all(), (
        'the parametric SP leg is drawing strictly-positive values again — '
        'it has been reverted to a lognormal')


# ---------------------------------------------------------------------------
# empirical leg — declared OUT of F2's scope, must stay byte-identical
# ---------------------------------------------------------------------------
def test_empirical_leg_untouched():
    """'empirical' still bootstraps the real FPs, negatives and all."""
    emp = [-12.0, -3.4, 0.0, 5.5, 18.2, 22.0]
    fn, w = _sampler('empirical', emp_fps=emp)
    assert w == 1.0
    rng = np.random.default_rng(17)
    d = fn(rng, 20_000)
    assert set(np.unique(d)).issubset(set(emp)), 'empirical leg is not a bootstrap'
    assert (d < 0).mean() > 0.2


def test_empirical_leg_ignores_missing_rp3():
    """With real history, prior='empirical' must not need an rp3 mean at all."""
    fn, w = _sampler('empirical', emp_fps=[1.0, 2.0, -5.0], mu=None)
    rng = np.random.default_rng(18)
    assert len(fn(rng, 100)) == 100
    assert w == 1.0


def test_blend_weight_math_unchanged():
    """w = n_emp/(n_emp+k_prior) — the documented Rodon/Valdez anchors."""
    _, w2 = _sampler('blend', emp_fps=[1.0] * 2)
    _, w30 = _sampler('blend', emp_fps=[1.0] * 30)
    assert math.isclose(w2, 2 / 22)
    assert math.isclose(w30, 30 / 50)


def test_blend_mixes_both_legs():
    """Blend draws must contain BOTH bootstrapped atoms and continuous values."""
    emp = [7.0] * 30                      # degenerate atom, easy to detect
    fn, w = _sampler('blend', emp_fps=emp)
    rng = np.random.default_rng(19)
    d = fn(rng, 50_000)
    frac_atom = float((d == 7.0).mean())
    assert abs(frac_atom - w) < 0.02, (
        f'empirical leg share {frac_atom:.3f} != declared weight {w:.3f}')
    assert (d <= 0).any(), 'blend still cannot produce a blow-up'


# ---------------------------------------------------------------------------
# no silent-zero / silent-default fallbacks (the 2026-07-28 ROOT-bug pattern)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('bad_mu', [None, 0, 0.0, -1.0, float('nan'), float('inf')])
@pytest.mark.parametrize('prior', ['rp3', 'blend'])
def test_missing_rp3_mean_raises_not_defaults(prior, bad_mu):
    """A pitcher absent from rp3_map must RAISE, not become a 0-FP starter."""
    import sp_bench_mc
    with pytest.raises(ValueError, match='rp3 per-start mean'):
        sp_bench_mc.build_sp_sampler([1.0] * 10, bad_mu, PANEL_SIGMA, prior,
                                     label='Nobody, Mr')


def test_empty_history_with_missing_rp3_raises():
    """prior='empirical' falling back to rp3 with no rp3 either must raise."""
    import sp_bench_mc
    with pytest.raises(ValueError, match='rp3 per-start mean'):
        sp_bench_mc.build_sp_sampler([], None, PANEL_SIGMA, 'empirical',
                                     label='Nobody, Mr')


def test_error_message_names_the_pitcher():
    import sp_bench_mc
    with pytest.raises(ValueError) as ei:
        sp_bench_mc.build_sp_sampler([], None, PANEL_SIGMA, 'blend',
                                     label='Valdez, Framber')
    assert 'Valdez, Framber' in str(ei.value)


@pytest.mark.parametrize('bad_sigma', [0, -1.0, float('nan')])
def test_gaussian_draws_rejects_bad_sigma(bad_sigma):
    """No silent 1e-6 floor: a degenerate sigma must be loud."""
    import sp_bench_mc
    with pytest.raises(ValueError, match='sigma'):
        sp_bench_mc._gaussian_draws(np.random.default_rng(0), 10.0, bad_sigma, 5)


def test_gaussian_draws_rejects_nonfinite_mu():
    import sp_bench_mc
    with pytest.raises(ValueError, match='mu'):
        sp_bench_mc._gaussian_draws(np.random.default_rng(0), float('nan'), 5.0, 5)


def test_sigma_falls_back_to_module_constant_when_absent():
    """A missing rp3 SIGMA (unlike the mean) has a documented constant."""
    import sp_bench_mc
    fn, _ = sp_bench_mc.build_sp_sampler([], PANEL_MU, None, 'rp3', label='x')
    d = fn(np.random.default_rng(21), 40_000)
    assert abs(d.std() - sp_bench_mc.SIGMA_PER_SP_START) < 0.10


# ---------------------------------------------------------------------------
# opp_factor must move the downside in the RIGHT direction
# ---------------------------------------------------------------------------
def test_opp_factor_scales_location_not_the_finished_draw():
    """A tougher opponent must make a blow-up MORE likely, not merely smaller.

    The old code multiplied the finished draw by opp_factor, which is scale-only:
    P(FP<=0) came out identical at every opp_factor, and a negative draw got
    shrunk toward zero against the BEST offenses. Location scaling fixes both.
    """
    fn, _ = _sampler('rp3')
    rates, p10s = {}, {}
    for f in (0.83, 1.00, 1.20):
        d = fn(np.random.default_rng(31), N_DRAWS, f)
        rates[f] = float((d <= 0).mean())
        p10s[f] = float(np.percentile(d, 10))
    assert rates[0.83] > rates[1.00] > rates[1.20], (
        f'P(FP<=0) is not monotone decreasing in opp_factor: {rates}')
    assert rates[0.83] - rates[1.20] > 0.05, (
        f'opp_factor barely moves the downside ({rates}) — it is probably being '
        f'applied to the finished draw again (scale-only, P is invariant)')
    assert p10s[0.83] < p10s[1.00] < p10s[1.20]
    # and the mean must scale exactly
    for f in (0.83, 1.20):
        d = fn(np.random.default_rng(32), N_DRAWS, f)
        assert abs(d.mean() - PANEL_MU * f) < 0.10


def test_opp_factor_defaults_to_neutral():
    fn, _ = _sampler('rp3')
    a = fn(np.random.default_rng(33), 20_000)
    b = fn(np.random.default_rng(33), 20_000, 1.0)
    assert np.allclose(a, b)


def test_run_mc_does_not_double_apply_opp_factor():
    """run_mc must pass opp_factor INTO the sampler, not multiply afterwards."""
    import inspect
    import sp_bench_mc
    src = inspect.getsource(sp_bench_mc.run_mc)
    assert 'base * opp_factor' not in src, (
        'run_mc is multiplying the finished draw by opp_factor again')
    assert 'draw(rng, n_trials, opp_factor)' in src


# ---------------------------------------------------------------------------
# the study's own closed forms
# ---------------------------------------------------------------------------
def test_lognormal_crps_negative_branch_matches_energy_form():
    """The y<=0 CRPS branch (what the B3 side-cell had to drop) is correct."""
    from scripts.xfp.validate_sp_sampler_tail import (
        crps_lognormal_all_y, _draw_family, _crps_empirical,
    )
    rng = np.random.default_rng(41)
    for mu, sg, y in ((10.0, 8.6, -12.0), (6.0, 3.5, -1.0), (15.0, 9.5, 0.0)):
        cf = float(crps_lognormal_all_y(np.array([mu]), np.array([sg]),
                                        np.array([y]))[0])
        mc = _crps_empirical(_draw_family(rng, 'lognormal', mu, sg, 400_000), y)
        assert abs(mc - cf) / cf < 0.01, (mu, sg, y, cf, mc)


def test_shifted_lognormal_shift_must_cover_observations():
    """A shift that does not clear the observed minimum must RAISE."""
    from scripts.xfp.validate_sp_sampler_tail import crps_shifted_lognormal
    with pytest.raises(ValueError, match='shift'):
        crps_shifted_lognormal(np.array([10.0]), np.array([8.6]),
                               np.array([-40.0]))
