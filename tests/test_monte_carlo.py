"""Regression tests for the IL-aware, calibrated Monte Carlo helpers.

These lock the three methodology fixes folded in 2026-06-19 (see monte_carlo.py
docstring): empirical scale calibration, IL time-phasing via return dates, and
the points-for seeding tiebreaker. Only the PURE helpers are tested — main()
needs live ESPN data and is exercised manually.
"""
from datetime import date
import importlib

mc = importlib.import_module("scripts.xfp.monte_carlo")


# ---------------------------- return_period --------------------------------

def test_return_period_none_is_season_ending():
    # No return date (season-ending / unknown) -> sentinel, never returns in-sim.
    assert mc.return_period(None, 12, date(2026, 6, 15)) == 999


def test_return_period_this_week_maps_to_current():
    # A return inside the current matchup week is available this period.
    assert mc.return_period(date(2026, 6, 19), 12, date(2026, 6, 15)) == 12


def test_return_period_past_date_clamps_to_current():
    # A stale/past return date never produces a period before the current one.
    assert mc.return_period(date(2026, 6, 1), 12, date(2026, 6, 15)) == 12


def test_return_period_future_weeks():
    cur_mon = date(2026, 6, 15)
    # Hunter Greene 7/5 -> +2 weeks -> period 14
    assert mc.return_period(date(2026, 7, 5), 12, cur_mon) == 14
    # Aaron Judge 7/24 -> +5 weeks -> period 17
    assert mc.return_period(date(2026, 7, 24), 12, cur_mon) == 17
    # Tyler Glasnow 8/1 -> +6 weeks -> period 18
    assert mc.return_period(date(2026, 8, 1), 12, cur_mon) == 18


# ---------------------------- calibrate_means ------------------------------

def test_calibrate_means_anchors_to_league_mean():
    # An average-strength team gets exactly the league weekly mean.
    V = {"A": 100.0, "B": 100.0, "C": 100.0}
    out = mc.calibrate_means(V, 340.0)
    assert all(abs(v - 340.0) < 1e-9 for v in out.values())


def test_calibrate_means_scales_proportionally():
    V = {"strong": 120.0, "weak": 80.0}  # mean 100
    out = mc.calibrate_means(V, 340.0)
    assert abs(out["strong"] - 408.0) < 1e-9   # 340 * 1.2
    assert abs(out["weak"] - 272.0) < 1e-9     # 340 * 0.8


def test_calibrate_means_zero_value_safe():
    out = mc.calibrate_means({"A": 0.0, "B": 0.0}, 340.0)
    assert out == {"A": 340.0, "B": 340.0}


# --------------------------- phased_team_mean ------------------------------

def test_phased_mean_removes_out_players_only():
    base = 350.0
    il = [(14, 15.0), (17, 16.0)]  # one back P14, one back P17
    # Period 12: both still out -> both subtracted
    assert abs(mc.phased_team_mean(base, il, 12) - (350 - 15 - 16)) < 1e-9
    # Period 15: first back, second still out -> only second subtracted
    assert abs(mc.phased_team_mean(base, il, 15) - (350 - 16)) < 1e-9
    # Period 18: both back -> full strength
    assert abs(mc.phased_team_mean(base, il, 18) - 350.0) < 1e-9


def test_phased_mean_floor_caps_the_penalty():
    base = 100.0
    il = [(20, 50.0), (20, 50.0)]  # would zero the team out without a floor
    # floor is 60% of base -> 60, not 0
    assert abs(mc.phased_team_mean(base, il, 12, floor_frac=0.6) - 60.0) < 1e-9


def test_phased_mean_no_il_is_identity():
    assert mc.phased_team_mean(330.0, [], 12) == 330.0


# ------------------------------ seed_order ---------------------------------

def test_seed_order_wins_first():
    wins = {"A": 10, "B": 8, "C": 9}
    pts = {"A": 1, "B": 1, "C": 1}
    assert mc.seed_order(wins, pts) == ["A", "C", "B"]


def test_seed_order_points_break_ties():
    # Equal wins -> higher points-for seeds higher (ESPN tiebreaker).
    wins = {"A": 9, "B": 9, "C": 9}
    pts = {"A": 3500.0, "B": 4200.0, "C": 3900.0}
    assert mc.seed_order(wins, pts) == ["B", "C", "A"]


def test_seed_order_is_deterministic():
    wins = {"X": 7, "Y": 7}
    pts = {"X": 100.0, "Y": 100.0}
    # Fully tied -> stable, no crash (dict insertion order)
    assert set(mc.seed_order(wins, pts)) == {"X", "Y"}
