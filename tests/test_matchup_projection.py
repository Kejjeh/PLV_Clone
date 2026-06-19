"""Tests for plv_clone.matchup_projection — the deep matchup adjuster core.

These assert the adjuster math through the module's interface with literal
contexts (no I/O, no dashboard).  Expected values are computed by hand from the
combination rules documented in the module.
"""
import math
from datetime import date

import pytest

from plv_clone.matchup_projection import (
    MatchupConfig, ProjResult,
    SPStartCtx, HitterGameCtx,
    sp_opp_factor, hitter_opp_factor, platoon_factor,
    project_sp_starts, project_hitter_games, project_rp,
    il_availability_factor,
    win_prob_normal, win_prob_bootstrap, win_prob,
)

CFG = MatchupConfig()


# --- factor clamps -----------------------------------------------------------

def test_sp_opp_factor_clamped():
    assert sp_opp_factor(1.0) == 1.0
    assert sp_opp_factor(0.5) == 1.20          # 1/0.5 = 2.0 → clamp hi
    assert sp_opp_factor(2.0) == 0.80          # 1/2.0 = 0.5 → clamp lo
    assert sp_opp_factor(None) == 1.0
    assert sp_opp_factor(0) == 1.0


def test_hitter_opp_factor_prefers_sp():
    # opposing SP path: league_avg (11.5) / opp_per_start
    f, proj = hitter_opp_factor(opp_per_start=11.5, team_pit_index=2.0, cfg=CFG)
    assert f == pytest.approx(1.0)
    assert proj == 11.5
    # tough SP (high per_start) suppresses → clamp lo 0.70
    f, proj = hitter_opp_factor(opp_per_start=100.0, team_pit_index=None, cfg=CFG)
    assert f == 0.70
    # fallback to team index when no SP
    f, proj = hitter_opp_factor(opp_per_start=None, team_pit_index=1.10, cfg=CFG)
    assert f == pytest.approx(1.10)
    assert proj is None
    # neither → neutral
    assert hitter_opp_factor(None, None, CFG) == (1.0, None)


def test_platoon_factor():
    assert platoon_factor(0.310, CFG) == pytest.approx(1.0)
    assert platoon_factor(0.500, CFG) == 1.15     # clamp hi
    assert platoon_factor(None, CFG) == 1.0
    assert platoon_factor(0.0, CFG) == 1.0


# --- SP projection -----------------------------------------------------------

def test_project_sp_single_confirmed_start():
    starts = [SPStartCtx(date='2026-06-20', opp_team='NYY', opp_bat_index=1.0, confirmed=True)]
    r = project_sp_starts(10.0, starts, sigma=5.5, cfg=CFG)
    # 10 * 1.0(opp) * 1.0(recent) * 1.0(calib) * 1.0(confirmed) * 1.0(momentum)
    assert r.fp == pytest.approx(10.0)
    assert r.units == 1
    assert r.sigma2 == pytest.approx(1 * 5.5 ** 2)
    b = r.breakdown[0]
    assert b['type'] == 'start' and b['confirmed'] is True
    assert b['confidence'] == 1.0


def test_project_sp_unconfirmed_applies_confidence_discount():
    starts = [SPStartCtx('2026-06-20', 'NYY', 1.0, confirmed=False)]
    r = project_sp_starts(10.0, starts, recent_factor=1.1, calib=0.95,
                          momentum=1.05, sigma=5.5, cfg=CFG)
    expected = 10.0 * 1.0 * 1.1 * 0.95 * 0.80 * 1.05
    assert r.fp == pytest.approx(expected)
    assert r.breakdown[0]['confidence'] == 0.80


def test_project_sp_two_starts_variance_adds():
    starts = [SPStartCtx('2026-06-20', 'NYY', 1.0),
              SPStartCtx('2026-06-23', 'BOS', 2.0)]   # second is clamped to 0.80
    r = project_sp_starts(10.0, starts, sigma=4.0, cfg=CFG)
    assert r.fp == pytest.approx(10.0 + 8.0)
    assert r.sigma2 == pytest.approx(2 * 4.0 ** 2)


# --- hitter projection -------------------------------------------------------

def test_project_hitter_neutral_game_legacy_sigma():
    games = [HitterGameCtx('2026-06-20', 'NYY', opp_per_start=11.5)]
    r = project_hitter_games(3.0, games, legacy_sigma=True, cfg=CFG)
    assert r.fp == pytest.approx(3.0)            # all factors neutral
    assert r.sigma2 == pytest.approx(1 * 3.5 ** 2)
    assert r.breakdown[0]['opp_sp_proj'] == 11.5


def test_project_hitter_hetero_sigma():
    games = [HitterGameCtx('2026-06-20', 'NYY', team_pit_index=1.0)]
    r = project_hitter_games(3.0, games, sigma_factor=1.0, pa_per_g=4.0, cfg=CFG)
    # sigma_pa = 0.517 * 1.0 ; var = 1 game * sigma_pa^2 * 4.0
    assert r.sigma2 == pytest.approx((0.517 ** 2) * 4.0)


def test_project_hitter_nan_sigma_factor_falls_back_to_legacy():
    games = [HitterGameCtx('2026-06-20', 'NYY', team_pit_index=1.0)]
    r = project_hitter_games(3.0, games, sigma_factor=float('nan'), cfg=CFG)
    assert r.sigma2 == pytest.approx(1 * 3.5 ** 2)


def test_project_hitter_full_factor_chain():
    games = [HitterGameCtx('2026-06-20', 'NYY', opp_per_start=11.5, platoon_xwoba=0.310)]
    r = project_hitter_games(3.0, games, recent_factor=1.1, lineup_factor=1.05,
                             il_factor=0.5, calib=0.97, momentum=1.02,
                             legacy_sigma=True, cfg=CFG)
    expected = 3.0 * 1.0 * 1.1 * 1.05 * 1.0 * 1.0 * 0.5 * 0.97 * 1.02
    assert r.fp == pytest.approx(expected)


# --- RP projection -----------------------------------------------------------

def test_project_rp_basic():
    # xfp_ros=180 over 180 days → 1.0/team-game ; per_app = 1/0.35 ; 7 games * 0.55
    r = project_rp(180.0, 7, role='closer', app_rate=0.55,
                   days_remaining_season=180, cfg=CFG)
    per_app = (180.0 / 180) / 0.35
    exp_apps = 7 * 0.55
    assert r.fp == pytest.approx(per_app * exp_apps)
    assert r.units == pytest.approx(round(exp_apps, 1))
    assert r.sigma2 == pytest.approx(exp_apps * 2.5 ** 2)
    assert r.breakdown[0]['role'] == 'closer'


def test_project_rp_zero_when_no_ros_or_no_games():
    assert project_rp(0.0, 7, role='middle', app_rate=0.3, days_remaining_season=100).fp == 0.0
    assert project_rp(100.0, 0, role='middle', app_rate=0.3, days_remaining_season=100).fp == 0.0


# --- IL window ---------------------------------------------------------------

def test_il_availability_factor():
    today = date(2026, 6, 19)
    week_end = date(2026, 6, 22)        # 4-day window (19,20,21,22)
    # returns mid-week (21st) → days 21,22 available = 2/4
    assert il_availability_factor(date(2026, 6, 21), today, week_end) == pytest.approx(2 / 4)
    # already back (return <= today) → full
    assert il_availability_factor(date(2026, 6, 10), today, week_end) == pytest.approx(1.0)
    # returns after week → None (zero out)
    assert il_availability_factor(date(2026, 6, 30), today, week_end) is None


# --- win probability ---------------------------------------------------------

def test_win_prob_normal_symmetry():
    assert win_prob_normal(100, 100, 50, 50) == pytest.approx(0.5)
    assert win_prob_normal(110, 100, 50, 50) > 0.5
    # zero variance → deterministic
    assert win_prob_normal(110, 100, 0, 0) == 1.0
    assert win_prob_normal(90, 100, 0, 0) == 0.0


def test_win_prob_bootstrap_deterministic_and_sane():
    my = [(20.0, 25.0), (15.0, 16.0)]
    opp = [(18.0, 25.0), (14.0, 16.0)]
    p1 = win_prob_bootstrap(my, opp, my_wtd=10, opp_wtd=10, n_trials=2000, seed=42)
    p2 = win_prob_bootstrap(my, opp, my_wtd=10, opp_wtd=10, n_trials=2000, seed=42)
    assert p1 == p2                     # deterministic given seed
    assert 0.5 < p1 < 1.0               # I'm favored (higher means, same wtd)


def test_win_prob_dispatch():
    assert win_prob(110, 100, 50, 50, method='normal') == win_prob_normal(110, 100, 50, 50)
    with pytest.raises(ValueError):
        win_prob(0, 0, 0, 0, method='bootstrap')
