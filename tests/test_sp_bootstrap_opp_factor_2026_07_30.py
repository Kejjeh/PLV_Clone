"""I1 regression locks — the EMPIRICAL-BOOTSTRAP leg must respond to the matchup.

The defect these tests exist for: `sp_bench_mc.build_sp_sampler`'s empirical leg
(used at 100% under `--prior empirical`, and at w = n/(n+20) — 60% at the
production 30-start history — inside the CLI-DEFAULT `blend`) applied the
matchup as

    rng.choice(emp_arr, size=n, replace=True) * opp_factor

Multiplying by a positive scalar cannot change a sign, so

    P(modeled FP <= 0) was EXACTLY invariant to the opponent,

and a bootstrapped REAL disaster start got shrunk *toward zero* against the
TOUGHEST offenses (opp_factor < 1 means a harder matchup). The number a
bench/start call exists to price did not move with the matchup at all.

F2 (tests/test_sp_sampler_tail_2026_07_29.py) fixed the same sign defect on the
PARAMETRIC leg and explicitly declared this leg out of scope; 1210 tests passed
with it live because nothing asserted the empirical leg's response to
opp_factor. That missing assertion is the defect. It is these tests.

Study: data/research/validation_runs/sp_bootstrap_opp_factor_2026-07-30.md
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

# Will Warren's REAL trailing-30 started-game BrownU FP as of the I1 panel's
# last snapshot (2026-07-09), pulled from the MLB Stats API gameLog — the exact
# pool production would hand the sampler. mean 9.91, 6/30 = 20.0% at FP <= 0.
WARREN_POOL = [
    -4.8, 14.8, -2.8, 11.2, -0.8, 5.5, 15.8, 12.8, 6.5, 14.2,
    -1.8, 23.1, 13.8, 25.1, 11.6, 6.9, 15.2, 7.5, 8.5, 12.8,
    -4.5, 17.8, 11.5, 11.5, -4.8, 7.9, 20.5, 15.5, 14.8, 12.2,
]
POOL_MEAN = float(np.mean(WARREN_POOL))          # 9.8967 — derived, not retyped
assert abs(POOL_MEAN - 9.90) < 0.02              # fixture guard

# Panel constants from the pre-registered I1 run (n=929 scored starts, 170
# pitchers, after the declared MIN_POOL=10 filter on the F2 1037-start panel).
PANEL_MU = 10.054           # mean rp3 per-start (unchanged from F2)
PANEL_SIGMA = 8.642         # mean xfp_rp3_sigma (display band, x2.41)
REALIZED_NEG_RATE = 0.1639  # 170/1037 real starts at FP <= 0

# make_opp_factor's clip. < 1 = TOUGHER offense.
F_TOUGH, F_NEUTRAL, F_EASY = 0.83, 1.00, 1.20
FGRID = (0.83, 0.90, 1.00, 1.10, 1.20)

N_DRAWS = 200_000


def _sampler(prior, emp_fps=WARREN_POOL, mu=PANEL_MU, sigma=PANEL_SIGMA,
             k_prior=20):
    import sp_bench_mc
    return sp_bench_mc.build_sp_sampler(list(emp_fps), mu, sigma, prior,
                                        k_prior=k_prior, label='test-SP')


def _p0(fn, f, seed=41, n=N_DRAWS):
    return float((fn(np.random.default_rng(seed), n, f) <= 0).mean())


# ---------------------------------------------------------------------------
# THE test whose absence let this ship — mirrors F2's
# test_opp_factor_scales_location_not_the_finished_draw, for the BOOTSTRAP leg
# ---------------------------------------------------------------------------
def test_opp_factor_shifts_the_bootstrap_it_does_not_rescale_the_draw():
    """A tougher opponent must make a blow-up MORE likely, not merely smaller.

    The old code multiplied the bootstrapped real FP by opp_factor. That is
    scale-only: P(FP<=0) came out BIT-IDENTICAL at every opp_factor, because
    multiplying by a positive number preserves sign. Translating by
    m_emp*(f-1) moves probability mass across zero, which is the whole point.
    """
    fn, w = _sampler('empirical')
    assert w == 1.0
    rates = {f: _p0(fn, f) for f in FGRID}

    assert all(rates[a] >= rates[b] for a, b in zip(FGRID, FGRID[1:])), (
        f'P(FP<=0) is not non-increasing in opp_factor: {rates}')
    spread = rates[F_TOUGH] - rates[F_EASY]
    assert spread > 0.05, (
        f'opp_factor moves the empirical leg\'s downside by only '
        f'{spread*100:.2f}pp ({rates}) — it is almost certainly being applied '
        f'as a MULTIPLY on the finished draw again, which leaves P(FP<=0) '
        f'exactly invariant to the opponent.')

    p10s = {f: float(np.percentile(fn(np.random.default_rng(42), N_DRAWS, f), 10))
            for f in (F_TOUGH, F_NEUTRAL, F_EASY)}
    assert p10s[F_TOUGH] < p10s[F_NEUTRAL] < p10s[F_EASY], p10s


def test_a_real_blowup_gets_worse_against_a_tougher_offense():
    """The sign defect, stated directly.

    Under the old multiply, the worst bootstrapped start (-4.8 FP) became
    -3.98 against the TOUGHEST offense and -5.76 against the WEAKEST — exactly
    backwards. A translation moves it the right way.
    """
    fn, _ = _sampler('empirical')
    worst_tough = float(fn(np.random.default_rng(43), N_DRAWS, F_TOUGH).min())
    worst_easy = float(fn(np.random.default_rng(43), N_DRAWS, F_EASY).min())
    assert worst_tough < worst_easy, (
        f'worst modeled start is {worst_tough:.2f} vs a tough offense but '
        f'{worst_easy:.2f} vs a weak one — the matchup is making the disaster '
        f'LESS bad, which is the multiply defect.')
    assert worst_tough < min(WARREN_POOL), (
        f'the sampler cannot reach below the worst REAL start '
        f'({min(WARREN_POOL)}) even against the toughest offense')


def test_opp_factor_does_not_rescale_the_bootstrap_spread():
    """SD must be the pool's SD at every opp_factor.

    A multiply scales SD by f — inflating the modeled variance against weak
    offenses and deflating it against strong ones, on top of the sign error.
    """
    pool_sd = float(np.std(WARREN_POOL))
    fn, _ = _sampler('empirical')
    for f in (F_TOUGH, F_NEUTRAL, F_EASY):
        sd = float(fn(np.random.default_rng(44), N_DRAWS, f).std())
        assert abs(sd - pool_sd) < 0.15, (
            f'opp_factor={f}: SD {sd:.3f} != pool SD {pool_sd:.3f} — the leg '
            f'is rescaling spread (a multiply gives {pool_sd*f:.3f})')


def test_bootstrap_mean_still_scales_with_opp_factor():
    """INVARIANT, not a defect test: the change is shape-only.

    E[f*X] = f*m_emp = E[X + m_emp*(f-1)], so the fix must not move the mean
    the old code produced. This is what makes it safe to ship on a tie-break.
    """
    fn, _ = _sampler('empirical')
    for f in (F_TOUGH, F_NEUTRAL, F_EASY):
        m = float(fn(np.random.default_rng(45), N_DRAWS, f).mean())
        assert abs(m - POOL_MEAN * f) < 0.10, (
            f'opp_factor={f}: mean {m:.3f} != m_emp*f {POOL_MEAN*f:.3f}')


def test_blend_empirical_half_shifts_too():
    """`blend` is the CLI DEFAULT and routes w = n/(n+20) through this leg."""
    fn, w = _sampler('blend')
    assert math.isclose(w, 30 / 50)
    rates = {f: _p0(fn, f) for f in FGRID}
    assert all(rates[a] >= rates[b] for a, b in zip(FGRID, FGRID[1:])), rates
    assert rates[F_TOUGH] - rates[F_EASY] > 0.05, (
        f'blend downside barely responds to the matchup ({rates}) — with a '
        f'location-scaled parametric leg (F2) that can only mean the empirical '
        f'half is still multiplying.')


def test_bootstrap_is_still_a_bootstrap_of_real_starts():
    """The fix must preserve the empirical SHAPE — a shifted pool, not a new law."""
    fn, _ = _sampler('empirical')
    d = fn(np.random.default_rng(46), 20_000, F_TOUGH)
    delta = POOL_MEAN * (F_TOUGH - 1.0)
    expected = {round(v + delta, 6) for v in WARREN_POOL}
    assert {round(float(v), 6) for v in np.unique(d)}.issubset(expected), (
        'empirical leg is no longer a bootstrap of the real starts')
    # ...and specifically NOT the old rescaled pool
    rescaled = {round(v * F_TOUGH, 6) for v in WARREN_POOL}
    assert {round(float(v), 6) for v in np.unique(d)} != rescaled, (
        'empirical leg is still multiplying the finished draw by opp_factor')


def test_opp_factor_defaults_to_neutral():
    fn, _ = _sampler('empirical')
    a = fn(np.random.default_rng(47), 20_000)
    b = fn(np.random.default_rng(47), 20_000, 1.0)
    assert np.allclose(a, b)
    assert set(np.round(np.unique(a), 6)).issubset({round(v, 6)
                                                    for v in WARREN_POOL})


def test_realized_negative_rate_is_reachable_at_a_tough_matchup():
    """Sanity: the leg's blow-up rate should be in the neighbourhood of the
    16.39% realized on the F2/I1 panel, and must RISE toward it as the matchup
    gets harder rather than sitting frozen."""
    fn, _ = _sampler('empirical')
    assert _p0(fn, F_TOUGH) >= _p0(fn, F_NEUTRAL) >= REALIZED_NEG_RATE * 0.5


# ---------------------------------------------------------------------------
# no silent-zero / silent-default fallbacks (the 2026-07-28 ROOT-bug pattern)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf')])
def test_non_finite_pool_value_raises(bad):
    import sp_bench_mc
    with pytest.raises(ValueError, match='non-finite'):
        sp_bench_mc.build_sp_sampler([1.0, 2.0, bad], PANEL_MU, PANEL_SIGMA,
                                     'empirical', label='Nobody, Mr')


@pytest.mark.parametrize('bad_f', [float('nan'), float('inf')])
def test_non_finite_opp_factor_raises(bad_f):
    fn, _ = _sampler('empirical')
    with pytest.raises(ValueError, match='opp_factor'):
        fn(np.random.default_rng(48), 100, bad_f)


def test_empty_pool_raises_in_the_bootstrap_helper():
    import sp_bench_mc
    with pytest.raises(ValueError, match='empty empirical pool'):
        sp_bench_mc._bootstrap_draws(np.random.default_rng(49),
                                     np.array([]), 10, 1.0, 0.0)


# ---------------------------------------------------------------------------
# study anchors — these numbers came out of the pre-registered run and are
# recorded so a later change that moves them is visible
# ---------------------------------------------------------------------------
def test_study_anchor_multiply_is_provably_matchup_invariant():
    """Documents WHY the incumbent had to go, without needing the panel.

    This is the property the CRPS contrast could not see and the pre-declared
    responsiveness tie-break was written for: it holds for every pool, exactly.
    """
    pool = np.array(WARREN_POOL, dtype=float)
    rates = {f: float((pool * f <= 0).mean()) for f in FGRID}
    assert len(set(rates.values())) == 1, rates
    assert rates[F_TOUGH] == rates[F_EASY] == float((pool <= 0).mean())
