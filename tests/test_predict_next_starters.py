"""Tests for predict_next_starters — the rotation-cycle walk-forward.

Locks the rule the sweep actually validated (k=5 GAMES back, not days), the
reassignment when the cycle arm pitched too recently to hold the turn, and the
two-tier confidence contract. Pure functions over synthetic history — no network.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "predict_next_starters", _ROOT / "scripts" / "xfp" / "predict_next_starters.py")
pns = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pns)

ROT = ["Ace", "Two", "Three", "Four", "Five"]


def _start(day, pid, name, team="SEA", et="7:10PM"):
    return {"date": f"2026-07-{day:02d}", "pitcher_id": pid, "pitcher_name": name,
            "team": team, "opp": "TEX", "home_away": "home", "park": team,
            "first_pitch_et": et, "source": "mlb_api"}


def _clean_history(last_day=31, turns=4):
    """A textbook 5-man rotation, one game per day, ending on `last_day`."""
    hist, day = [], last_day - (turns * 5) + 1
    for _ in range(turns):
        for i, name in enumerate(ROT):
            hist.append(_start(day, 100 + i, name))
            day += 1
    return hist


def test_predicts_the_arm_five_games_back():
    hist = _clean_history(last_day=31)          # Jul 31 = Five (index 4)
    p = pns.predict_team(hist, "2026-08-01")
    assert p["pitcher_name"] == "Ace"           # Ace last went Jul 27 -> 5 days
    assert p["rest_days"] == 5 and p["confidence"] == "HIGH"
    assert p["clean_cycle"] is True


def test_counts_games_not_days_so_an_off_day_does_not_shift_the_slot():
    """Idle Jul 31: the slot does not advance, the arm just gets a 6th day."""
    on_day = pns.predict_team(_clean_history(last_day=31), "2026-08-01")
    idle_day = pns.predict_team(_clean_history(last_day=30), "2026-08-01")
    assert on_day["pitcher_name"] == idle_day["pitcher_name"] == "Ace"
    assert on_day["rest_days"] == 5 and idle_day["rest_days"] == 6
    assert idle_day["confidence"] == "HIGH"     # 6 days is still a real turn


def test_cycle_arm_is_reassigned_when_he_just_pitched():
    """A four-man stretch puts the k=5 arm on 1 day's rest — reassign, drop tier."""
    hist = [_start(day, 100 + i % 4, ROT[i % 4])
            for i, day in enumerate(range(24, 32))]   # A B C D A B C D, Jul 24-31
    assert hist[-1]["pitcher_name"] == "Four" and hist[-5]["pitcher_name"] == "Four"
    p = pns.predict_team(hist, "2026-08-01")
    assert p["pitcher_name"] != "Four"          # 1 day rest is impossible
    assert p["confidence"] == "LOW"             # reassignment always drops the tier
    assert "reassigned" in p["note"]
    assert pns.MIN_REST <= p["rest_days"] <= pns.MAX_REST


def test_arms_scheduled_two_or_three_days_out_are_never_predicted():
    """Anyone starting Jul 30/31 cannot also hold the Aug 2 turn."""
    hist = _clean_history(last_day=31)
    p = pns.predict_team(hist, "2026-08-02")
    recent = {h["pitcher_name"] for h in hist
              if h["date"] >= "2026-07-30"}      # rest <= 3 from Aug 2
    assert p["pitcher_name"] not in recent


def test_spot_starter_is_low_confidence_even_on_a_clean_cycle():
    hist = _clean_history(last_day=26)
    # a one-off arm takes the next five turns' slot at the front of the cycle
    for day, (pid, name) in zip(range(27, 32),
                                [(999, "Spot"), (101, "Two"), (102, "Three"),
                                 (103, "Four"), (104, "Five")]):
        hist.append(_start(day, pid, name))
    p = pns.predict_team(hist, "2026-08-01")
    assert p["pitcher_name"] == "Spot" and p["starts_in_window"] == 1
    assert p["confidence"] == "LOW"


def test_runner_up_is_a_different_arm_with_a_real_turn_of_rest():
    hist = _clean_history(last_day=31)
    p = pns.predict_team(hist, "2026-08-01")
    assert p["runner_up"] and p["runner_up"] != p["pitcher_name"]


def test_empty_history_yields_no_prediction():
    assert pns.predict_team([], "2026-08-01") == {}


def test_build_predictions_skips_sides_that_already_have_a_starter():
    hist = _clean_history(last_day=31)
    target = [
        {"date": "2026-08-01", "team": "SEA", "opp": "TEX", "home_away": "home",
         "park": "SEA", "first_pitch_et": "4:10PM", "pitcher_id": "", "source": ""},
        {"date": "2026-08-01", "team": "TEX", "opp": "SEA", "home_away": "away",
         "park": "SEA", "first_pitch_et": "4:10PM", "pitcher_id": 555,
         "pitcher_name": "Posted Arm", "source": "mlb_api"},
    ]
    preds = pns.build_predictions(hist + target, "2026-08-01", rp3={},
                                 predicted_at="T")
    assert [p["team"] for p in preds] == ["SEA"]   # TEX already posted
    assert preds[0]["predicted_pitcher"] == "Ace"


def test_rp3_annotation_joins_on_predicted_id():
    hist = _clean_history(last_day=31)
    target = [{"date": "2026-08-01", "team": "SEA", "opp": "TEX", "home_away": "home",
               "park": "SEA", "first_pitch_et": "4:10PM", "pitcher_id": "",
               "source": ""}]
    rp3 = {100: {"rank": "36", "per_start": "12.91", "dq": "data_driven_full"}}
    p = pns.build_predictions(hist + target, "2026-08-01", rp3=rp3,
                              predicted_at="T")[0]
    assert p["rp3_rank"] == "36" and p["dq"] == "data_driven_full"


def test_predictions_are_sorted_by_first_pitch():
    hist_a = _clean_history(last_day=31)
    hist_b = [dict(h, team="LAD", park="LAD") for h in _clean_history(last_day=31)]
    target = [
        {"date": "2026-08-01", "team": "LAD", "opp": "SF", "home_away": "home",
         "park": "LAD", "first_pitch_et": "10:10PM", "pitcher_id": "", "source": ""},
        {"date": "2026-08-01", "team": "SEA", "opp": "TEX", "home_away": "home",
         "park": "SEA", "first_pitch_et": "4:10PM", "pitcher_id": "", "source": ""},
    ]
    preds = pns.build_predictions(hist_a + hist_b + target, "2026-08-01", rp3={},
                                 predicted_at="T")
    assert [p["team"] for p in preds] == ["SEA", "LAD"]


def test_cycle_constant_is_five():
    """The sweep peaked hard at 5 (k=4 -> 4%, k=6 -> 16%); guard the constant."""
    assert pns.CYCLE == 5
