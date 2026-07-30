"""Regression tests for the hitter per-game outcome-sigma SCALE.

The bug these exist to prevent (found 2026-07-29, fixed same day):
``project_hitter_games`` computed per-game hitter variance as

    sigma2 = n * (0.517 * factor)**2 * pa_per_g          # WRONG

treating ``global_sigma_pa_fp = 0.517`` as a per-PA sigma.  It is actually the
pooled within-batter sigma of a per-GAME RATE (fp_proxy/PA) measured off a proxy
FP formula that omits R, RBI and SB.  The result was a 3.36x understatement of
per-game hitter sigma (11.3x in variance), which flowed straight into the
matchup win probability.  931 tests passed with that bug in place because the
only sigma assertion in the suite re-derived the buggy formula instead of
checking it against measured data.  These tests check the DATA.

Measurements (scripts/xfp/validate_hitter_sigma_scale.py, memo
data/research/validation_runs/hitter_sigma_scale_2026-07-29.md):
  * within-batter per-game SD of canonical BrownU hitter FP, 2026 started
    games, 377 batters / 26,199 games                    = 3.2502 FP
  * calibrated through-origin slope, sigma_game / pa_per_g = 0.784563
  * mean pa_per_g over those regulars                    = 4.0016
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from plv_clone.matchup_projection import (
    MatchupConfig, HitterGameCtx, project_hitter_games, hitter_sigma_per_game,
    _FP_PROXY_TO_FULL_FP_SIGMA, _LEAGUE_PA_PER_GAME_MEASURED,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = MatchupConfig()

# --- frozen empirical constants (see module docstring for provenance) ---------
EMPIRICAL_PER_GAME_SD = 3.2502      # canonical FP, within-batter, 2026 starts
EMPIRICAL_MEAN_PPG = 4.0016         # PA per started game, 2026 regulars
CALIBRATED_SLOPE = 0.784563         # sigma_game = SLOPE * pa_per_g


def _game(n: int = 1):
    return [HitterGameCtx(f'2026-06-{20 + i}', 'NYY', team_pit_index=1.0)
            for i in range(n)]


# =============================================================================
# 1. the scale is pinned to the empirical SD
# =============================================================================

def test_per_game_sigma_matches_empirical_sd():
    """A neutral-factor batter at league-mean PA/game must produce a per-game
    sigma within 10% of the MEASURED within-batter per-game FP SD.

    The buggy formula gave 1.0444 FP/g against a measured 3.2502 -- a 3.11x
    understatement -- so a 10% band is loose enough to survive a legitimate
    recalibration and tight enough that any repeat of a units error fails.
    """
    sigma = hitter_sigma_per_game(1.0, EMPIRICAL_MEAN_PPG, CFG)
    assert sigma == pytest.approx(CALIBRATED_SLOPE * EMPIRICAL_MEAN_PPG, rel=1e-6)
    rel_err = abs(sigma / EMPIRICAL_PER_GAME_SD - 1.0)
    assert rel_err < 0.10, (
        f"per-game hitter sigma {sigma:.4f} FP/g is {rel_err * 100:.1f}% off the "
        f"measured within-batter SD {EMPIRICAL_PER_GAME_SD:.4f} FP/g. If this is "
        f"an intentional recalibration, re-run "
        f"scripts/xfp/validate_hitter_sigma_scale.py and update the frozen "
        f"constants in this test WITH the new memo."
    )


def test_scale_constant_composition():
    """The shipped constant must be exactly proxy_sigma x conversion."""
    assert CFG.global_sigma_pa_fp * _FP_PROXY_TO_FULL_FP_SIGMA == pytest.approx(
        CALIBRATED_SLOPE, rel=1e-5)


def test_rejects_the_two_known_wrong_scales():
    """Guard the specific wrong answers, so a revert is caught by name."""
    sigma = hitter_sigma_per_game(1.0, EMPIRICAL_MEAN_PPG, CFG)
    buggy_sqrt_35 = 0.517 * math.sqrt(3.5)                   # 0.9672 -- shipped bug
    buggy_sqrt_real = 0.517 * math.sqrt(EMPIRICAL_MEAN_PPG)  # 1.0344
    exponent_only = 0.517 * EMPIRICAL_MEAN_PPG               # 2.0688 -- half a fix
    for wrong, name in ((buggy_sqrt_35, 'sqrt(3.5) per-PA reading'),
                        (buggy_sqrt_real, 'sqrt(ppg) per-PA reading'),
                        (exponent_only, 'exponent fix without the proxy rescale')):
        assert abs(sigma / wrong - 1.0) > 0.20, f"regressed to the {name}"


# =============================================================================
# 2. dimensional analysis -- PA/game must enter the VARIANCE quadratically
# =============================================================================

def test_variance_is_quadratic_in_pa_per_game():
    """Doubling PA/game must QUADRUPLE per-game variance, not double it.

    This is the dimensional identity the bug got wrong: per-game FP = rate x PA,
    so SD(per-game FP) = SD(rate) x PA, and variance goes as PA^2.
    """
    v1 = project_hitter_games(3.0, _game(1), sigma_factor=1.0,
                              pa_per_g=2.0, cfg=CFG).sigma2
    v2 = project_hitter_games(3.0, _game(1), sigma_factor=1.0,
                              pa_per_g=4.0, cfg=CFG).sigma2
    assert v2 / v1 == pytest.approx(4.0, rel=1e-9)
    # explicitly NOT the linear-in-ppg (per-PA) reading the bug implied
    assert v2 / v1 != pytest.approx(2.0, rel=0.05)


def test_sigma_is_linear_in_pa_per_game_and_in_factor():
    base = hitter_sigma_per_game(1.0, 4.0, CFG)
    assert hitter_sigma_per_game(1.0, 8.0, CFG) == pytest.approx(2 * base)
    assert hitter_sigma_per_game(2.0, 4.0, CFG) == pytest.approx(2 * base)


def test_variance_scales_linearly_in_games():
    """Games are independent draws: variance adds, sigma does not."""
    one = project_hitter_games(3.0, _game(1), sigma_factor=1.0,
                              pa_per_g=4.0, cfg=CFG).sigma2
    six = project_hitter_games(3.0, _game(6), sigma_factor=1.0,
                               pa_per_g=4.0, cfg=CFG).sigma2
    assert six == pytest.approx(6 * one)


def test_units_a_full_week_of_hitters_is_the_right_order_of_magnitude():
    """13 hitters x ~5.87 games at neutral factor should give a team hitter
    sigma near sqrt(13 * 5.87) * 3.14 ~= 27 FP, not ~9 FP (the bug)."""
    n_games = 6
    per_hitter = project_hitter_games(3.0, _game(n_games), sigma_factor=1.0,
                                      pa_per_g=EMPIRICAL_MEAN_PPG, cfg=CFG).sigma2
    team_sigma = math.sqrt(13 * per_hitter)
    assert 24.0 < team_sigma < 32.0, team_sigma


# =============================================================================
# 3. no silent defaults for bad input
# =============================================================================

def test_missing_pa_per_g_uses_the_measured_league_mean():
    assert CFG.league_pa_per_game == pytest.approx(_LEAGUE_PA_PER_GAME_MEASURED)
    assert hitter_sigma_per_game(1.0, None, CFG) == pytest.approx(
        CALIBRATED_SLOPE * _LEAGUE_PA_PER_GAME_MEASURED, rel=1e-6)
    assert hitter_sigma_per_game(1.0, float('nan'), CFG) == pytest.approx(
        CALIBRATED_SLOPE * _LEAGUE_PA_PER_GAME_MEASURED, rel=1e-6)


@pytest.mark.parametrize('bad', [0.0, -1.0, -0.001])
def test_nonpositive_pa_per_g_raises_instead_of_silently_defaulting(bad):
    """The pre-fix code did ``pa_per_g or cfg.league_pa_per_game``, so a 0.0
    PA/game silently became the league mean.  Broken input must be loud."""
    with pytest.raises(ValueError, match='pa_per_g'):
        hitter_sigma_per_game(1.0, bad, CFG)
    with pytest.raises(ValueError, match='pa_per_g'):
        project_hitter_games(3.0, _game(1), sigma_factor=1.0, pa_per_g=bad, cfg=CFG)


def test_missing_sigma_factor_raises_in_the_kernel_but_routes_to_legacy_above():
    with pytest.raises(ValueError, match='sigma_factor'):
        hitter_sigma_per_game(float('nan'), 4.0, CFG)
    # project_hitter_games still routes a missing factor to the legacy fixed σ
    r = project_hitter_games(3.0, _game(1), sigma_factor=float('nan'), cfg=CFG)
    assert r.sigma2 == pytest.approx(CFG.sigma_per_hitter_game ** 2)


def test_legacy_sigma_path_untouched():
    r = project_hitter_games(3.0, _game(2), sigma_factor=1.0, pa_per_g=4.0,
                             legacy_sigma=True, cfg=CFG)
    assert r.sigma2 == pytest.approx(2 * 3.5 ** 2)


# =============================================================================
# 4. the fp_proxy audit is pinned: the panel formula is NOT the scoring formula
# =============================================================================

def test_fp_proxy_is_not_the_canonical_brownu_formula():
    """If someone ever makes fp_proxy canonical, _FP_PROXY_TO_FULL_FP_SIGMA
    becomes a double-count.  Pin the source line so that change is caught."""
    src = (ROOT / 'scripts' / 'xfp' / 'analyze_hitter_boom_bust.py').read_text(
        encoding='utf-8')
    assert "g['fp_proxy'] = g['TB'] + g['BB'] + g['HBP'] - g['K']" in src, (
        "analyze_hitter_boom_bust.py no longer defines fp_proxy as TB+BB+HBP-K. "
        "The proxy->canonical conversion constant "
        "_FP_PROXY_TO_FULL_FP_SIGMA (1.5175) was measured against THAT formula "
        "and must be re-derived via scripts/xfp/validate_hitter_sigma_scale.py."
    )
    assert _FP_PROXY_TO_FULL_FP_SIGMA > 1.0


BOX_H = ROOT / 'data' / 'research' / 'xfp_cache' / 'boxscore_hitters.parquet'


@pytest.mark.skipif(not BOX_H.exists(),
                    reason='boxscore_hitters.parquet is gitignored; '
                           'run refresh_boxscores.py to enable this check')
def test_empirical_per_game_sd_is_still_what_the_constant_was_fit_to():
    """Re-measure the ground truth from the store and confirm the shipped scale
    still lands within 10% of it.  This is the test that would have caught the
    original bug: it goes to the DATA rather than re-deriving the formula.
    """
    import pandas as pd
    box = pd.read_parquet(BOX_H)
    recomputed = (box['r'] + box['tb'] + box['rbi'] + box['bb']
                  + box['hbp'] + box['sb'] - box['k']).astype(float)
    assert (recomputed - box['fp_h'].astype(float)).abs().max() < 1e-9, (
        'boxscore fp_h no longer equals the canonical BrownU hitter formula')

    lin = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitter_lineup_appearances_2026.parquet'
    if not lin.exists():
        pytest.skip('hitter_lineup_appearances_2026.parquet not present')
    la = pd.read_parquet(lin)
    j = box.merge(la[['game_pk', 'batter', 'started_game', 'pa_in_game']],
                  left_on=['game_pk', 'mlbam_id'], right_on=['game_pk', 'batter'],
                  how='inner')
    j = j[(j['started_game'] == True) & (j['pa_in_game'].astype(float) > 0)]  # noqa: E712
    cnt = j.groupby('mlbam_id')['fp_h'].transform('size')
    j = j[cnt >= 30]
    assert len(j) > 5000, f'too few started games to measure ({len(j)})'
    mean = j.groupby('mlbam_id')['fp_h'].transform('mean')
    measured_sd = float(((j['fp_h'].astype(float) - mean) ** 2).mean() ** 0.5)
    measured_ppg = float(j['pa_in_game'].astype(float).mean())
    model_sd = hitter_sigma_per_game(1.0, measured_ppg, CFG)
    assert abs(model_sd / measured_sd - 1.0) < 0.10, (
        f'shipped per-game hitter sigma {model_sd:.4f} vs freshly measured '
        f'within-batter SD {measured_sd:.4f} at PA/g {measured_ppg:.4f}. '
        f'Re-run scripts/xfp/validate_hitter_sigma_scale.py.')
