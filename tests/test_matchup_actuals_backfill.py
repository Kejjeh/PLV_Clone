"""Regression tests for scripts/xfp/fetch_closed_matchup_actuals.py.

These pin the 2026-07-30 correctness fix (track I5, memo
data/research/validation_runs/pwin_mean_bias_2026-07-30.md).

The defect: the backfill decided "is the period closed?" from the ISO week of
the first snapshot and read finals through ``espn_api``'s
``league.box_scores(matchup_period=N)``.  ``H2HPointsBoxScore`` prefers
``totalPointsLive`` whenever the payload carries it — which for a request
whose ``scoringPeriodId`` is TODAY is the current DAY's points, not the
matchup total.  Five of eleven live 2026 periods were stored with single-day
scores as finals (period 13 as 25.7-64.5; the true final is 322.1-331.3), and
one of them flipped the recorded win/loss.  Those labels are what the
win-probability calibration harness graded against.

``test_espn_api_boxscore_prefers_live_points`` documents the OLD behaviour on
the very same payload, so these tests fail if anyone routes the backfill back
through ``box_scores()``.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

fca = importlib.import_module('scripts.xfp.fetch_closed_matchup_actuals')


# --- fixtures modelled on the real 2026 period-13 payload -------------------
LIGERS = 3
OPP = 5


def _entry(period, my_total, opp_total, winner, live=None):
    home = {'teamId': LIGERS, 'totalPoints': my_total}
    away = {'teamId': OPP, 'totalPoints': opp_total}
    if live is not None:
        home['totalPointsLive'] = live[0]
        away['totalPointsLive'] = live[1]
    return {'matchupPeriodId': period, 'winner': winner, 'home': home, 'away': away}


SCHEDULE = [
    # period 13 finished 322.1-331.3, but the payload still carries the live
    # single-day totals that corrupted the store.
    _entry(13, 322.1, 331.3, 'AWAY', live=(25.7, 64.5)),
    _entry(16, 362.3, 246.7, 'HOME'),
    _entry(17, 92.4, 125.0, 'UNDECIDED', live=(92.4, 125.0)),
]


def test_finals_use_total_points_not_live():
    assert fca.finals_from_schedule(SCHEDULE, LIGERS, 13) == (322.1, 331.3)


def test_espn_api_boxscore_prefers_live_points():
    """The OLD read path returns the single-day score on this same payload."""
    box = importlib.import_module('espn_api.baseball.box_score')
    bs = box.H2HPointsBoxScore(SCHEDULE[0], {}, 2026, 13)
    assert (bs.home_score, bs.away_score) == (25.7, 64.5)
    assert (bs.home_score, bs.away_score) != fca.finals_from_schedule(
        SCHEDULE, LIGERS, 13)


def test_undecided_matchup_raises_rather_than_returning_a_partial():
    with pytest.raises(fca.PeriodNotFinal):
        fca.finals_from_schedule(SCHEDULE, LIGERS, 17)


def test_missing_matchup_raises():
    with pytest.raises(fca.MatchupNotFound):
        fca.finals_from_schedule(SCHEDULE, LIGERS, 99)


def test_missing_total_points_raises_no_silent_zero():
    bad = [{'matchupPeriodId': 4, 'winner': 'HOME',
            'home': {'teamId': LIGERS}, 'away': {'teamId': OPP, 'totalPoints': 1.0}}]
    with pytest.raises(KeyError):
        fca.finals_from_schedule(bad, LIGERS, 4)


def _write_history(path: Path) -> None:
    pd.DataFrame([
        {'date': '2026-06-22', 'period': 13, 'win_probability': 0.74,
         'model_version': 'baseline', 'actual_my_final': None,
         'actual_opp_final': None},
        {'date': '2026-07-20', 'period': 16, 'win_probability': 0.99,
         'model_version': 'baseline', 'actual_my_final': 43.8,
         'actual_opp_final': 31.2},
        {'date': '2026-07-27', 'period': 17, 'win_probability': 0.80,
         'model_version': 'baseline', 'actual_my_final': None,
         'actual_opp_final': None},
    ]).to_csv(path, index=False)


def test_run_backfill_writes_final_not_live_and_skips_open_period(tmp_path, monkeypatch):
    hist = tmp_path / 'predictions_history.csv'
    _write_history(hist)
    monkeypatch.setattr(fca, 'HISTORY', hist)
    new, total, rows = fca.run_backfill(verbose=False, schedule=SCHEDULE,
                                        my_team_id=LIGERS)
    out = pd.read_csv(hist)
    p13 = out[out['period'] == 13].iloc[0]
    assert (p13['actual_my_final'], p13['actual_opp_final']) == (322.1, 331.3)
    # period 17 is UNDECIDED -> must stay NaN, not receive the live 92.4-125.0
    assert out[out['period'] == 17]['actual_my_final'].isna().all()
    assert new == 1 and total == 2 and rows == 3


def test_repair_overwrites_a_corrupted_stored_actual(tmp_path, monkeypatch):
    hist = tmp_path / 'predictions_history.csv'
    _write_history(hist)
    monkeypatch.setattr(fca, 'HISTORY', hist)
    # default run must NOT touch the already-populated (corrupt) period-16 row
    fca.run_backfill(verbose=False, schedule=SCHEDULE, my_team_id=LIGERS)
    assert pd.read_csv(hist).query('period == 16')['actual_my_final'].iloc[0] == 43.8
    fca.run_backfill(verbose=False, repair=True, schedule=SCHEDULE,
                     my_team_id=LIGERS)
    fixed = pd.read_csv(hist).query('period == 16').iloc[0]
    assert (fixed['actual_my_final'], fixed['actual_opp_final']) == (362.3, 246.7)
