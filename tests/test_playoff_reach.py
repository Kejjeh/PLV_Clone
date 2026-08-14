"""Playoff periods must be weighted by P(you actually play them).

AUDIT 2026-08-14. The period board sums xfp_p20 + xfp_p21 + xfp_p22 + xfp_p23
into one `ros_total` at FULL weight. p21/p22/p23 are playoff ROUNDS, and summing
them undiscounted asserts P(reach round 3) = 1.0. It is not: the live sim has
P(title) = 0.157, so the deepest round is reached maybe a quarter of the time.

The consequence is not cosmetic. Undiscounted, the two 2-week playoff rounds
carry ~2/3 of a player's `ros_total`, so the board ranks by "who is best in the
championship round" rather than "who adds the most expected value" — and it does
so invisibly. A player who is elite in p22/p23 but replaceable in p20 is being
credited for weeks he plays 29% of the time.

MODEL (documented, deliberately simple, and self-checking)
----------------------------------------------------------
The sim does not export per-round win probabilities. It exports enough to pin
them down under one stated assumption: a constant per-round win probability q.

    P(title) = P(bye) * q^(R-1)  +  P(no bye) * q^R

with R = number of rounds and byes going to the top seeds. Solve for q by
bisection (the RHS is strictly increasing in q, so the root is unique), then

    P(reach round 1) = P(no bye)
    P(reach round k) = P(bye)*q^(k-2) + P(no bye)*q^(k-1)   for k >= 2

This reproduces the sim's own P(title) BY CONSTRUCTION, which is the property
worth having: the weights cannot silently disagree with the payload they came
from. Constant-q is an approximation (a 3-seed is likelier to win round 1 than
round 2), and it is labelled as such rather than dressed up.

Everything degrades to None — never 1.0 — when the payload can't support it.
Silently defaulting to 1.0 is precisely the bug being fixed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.playoff_reach import reach_probabilities  # noqa: E402

# Live 2026 shape: 6 playoff teams, rounds at periods 21/22/23, Josh never a
# top-2 seed (seed_dist_miss_then_1toN = [miss, s1..s6]).
LIVE = {"period": 19, "playoff_teams": 6, "reg_season_end": 20,
        "playoff_rounds": [[21, 1], [22, 2], [23, 2]],
        "josh": {"p_playoffs": 1.0, "p_title": 0.1568,
                 "seed_dist_miss_then_1toN": [0.0, 0.0, 0.0, 0.0422,
                                              0.5508, 0.3144, 0.0926]}}


def test_regular_season_periods_are_certain():
    r = reach_probabilities(LIVE)
    assert r["reach"][20] == 1.0, "period 20 is a regular-season week; it happens"


def test_playoff_reach_decays_round_over_round():
    r = reach_probabilities(LIVE)
    reach = r["reach"]
    assert reach[21] == pytest.approx(1.0)          # no bye -> plays round 1
    assert reach[22] < reach[21]
    assert reach[23] < reach[22]
    # The headline defect: the board had been using 1.0 here.
    assert reach[23] < 0.5, "P(reach the championship round) cannot be ~1"


def test_weights_reproduce_the_sims_own_p_title():
    """Self-consistency: P(reach final round) * q must equal payload P(title)."""
    r = reach_probabilities(LIVE)
    q = r["q_per_round"]
    assert r["reach"][23] * q == pytest.approx(LIVE["josh"]["p_title"], abs=1e-6)
    assert 0.0 < q < 1.0


def test_bye_seeds_skip_round_one():
    pay = {"playoff_teams": 6, "playoff_rounds": [[21, 1], [22, 2], [23, 2]],
           "josh": {"p_playoffs": 1.0, "p_title": 0.25,
                    # 60% chance of a top-2 seed => 40% chance of playing round 1
                    "seed_dist_miss_then_1toN": [0.0, 0.35, 0.25, 0.2, 0.2,
                                                 0.0, 0.0]}}
    r = reach_probabilities(pay)
    assert r["reach"][21] == pytest.approx(0.40)
    assert r["p_bye"] == pytest.approx(0.60)
    # A bye seed is IN round 2 for free, so round-2 reach exceeds round-1 reach.
    assert r["reach"][22] > r["reach"][21]


def test_missing_playoff_odds_returns_none_never_one():
    """The whole point: absence must not read as certainty."""
    r = reach_probabilities({"playoff_rounds": [[21, 1]], "josh": {}})
    assert r["reach"] is None and r["status"] == "unavailable"
    assert "p_title" in r["note"]


def test_missed_playoffs_scales_every_round():
    """P(playoffs) < 1 multiplies through; it is not a separate caveat."""
    pay = {"playoff_teams": 6, "playoff_rounds": [[21, 1], [22, 2], [23, 2]],
           "josh": {"p_playoffs": 0.5, "p_title": 0.05,
                    "seed_dist_miss_then_1toN": [0.5, 0.0, 0.0, 0.1, 0.2,
                                                 0.1, 0.1]}}
    r = reach_probabilities(pay)
    assert r["reach"][21] == pytest.approx(0.5), (
        "no bye mass, so round-1 reach IS P(playoffs)")
    assert r["reach"][20] == 1.0, "the regular season happens either way"


def test_reach_weighted_total_discounts_the_deep_rounds():
    from lib.playoff_reach import reach_weighted_total
    r = reach_probabilities(LIVE)
    per_period = {20: 100.0, 21: 100.0, 22: 200.0, 23: 200.0}
    raw = sum(per_period.values())
    wt = reach_weighted_total(per_period, r["reach"])
    assert wt < raw
    assert wt == pytest.approx(100.0 + 100.0 * r["reach"][21]
                               + 200.0 * r["reach"][22]
                               + 200.0 * r["reach"][23])


def test_reach_weighted_total_refuses_unknown_weights():
    from lib.playoff_reach import reach_weighted_total
    assert reach_weighted_total({20: 10.0}, None) is None
    # A period with no weight must not be silently dropped or silently kept.
    with pytest.raises(KeyError):
        reach_weighted_total({20: 10.0, 99: 5.0}, {20: 1.0})
