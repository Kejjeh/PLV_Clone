"""Behavioral tests for lib.availability — the IL-return volume overlay.

Motivation (2026-08-12): every projection miss that session was an
availability error, not a rate error — Cruz projected at season pace
(2.25 PA/tg) when his when-active rate was 4.42 and his return was 2 days
out. The overlay's contract: fix exactly that class of case, and change
NOTHING for steady-state players (the validated volume model owns those).
"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))

from lib.availability import ros_volume  # noqa: E402


SIX_DATES = [date(2026, 8, d) for d in (13, 14, 16, 17, 18, 19)]


def test_active_steady_hitter_passes_through_model_volume():
    """An everyday healthy hitter keeps the validated model's volume —
    the overlay must not touch the cases the volume model already owns."""
    out = ros_volume(
        {
            "bucket": "H",
            "status": "ACTIVE",
            "model_pa_per_teamgame": 3.5,
            "when_active_pa_per_game": 3.6,
            "return_date": None,
        },
        team_remaining_dates=SIX_DATES,
        today=date(2026, 8, 12),
    )
    assert out["proj_ros_pa"] == pytest.approx(3.5 * 6)
    assert out["source"] == "model_passthrough"
    assert out["frac_available"] == pytest.approx(1.0)


def test_il_hitter_with_return_date_gets_when_active_rate_after_return():
    """The Cruz case: an IL'd hitter's volume = when-active PA/game x team
    games ON or after the return date — pace-forward zeros are discarded."""
    out = ros_volume(
        {
            "bucket": "H",
            "status": "IL",
            "model_pa_per_teamgame": 2.25,       # pace poisoned by injury zeros
            "when_active_pa_per_game": 4.42,
            "return_date": date(2026, 8, 16),    # 3rd of the 6 remaining dates
        },
        team_remaining_dates=SIX_DATES,
        today=date(2026, 8, 12),
    )
    assert out["proj_ros_pa"] == pytest.approx(4.42 * 4)
    assert out["frac_available"] == pytest.approx(4 / 6)
    assert out["source"] == "il_return_overlay"


def test_when_active_rate_counts_distinct_at_bats_per_game_played():
    """PA per game actually played, from pitch-level rows: distinct
    (game_pk, at_bat_number) for THIS batter, over games he appeared in.
    Multiple pitches per PA and other batters' rows must not inflate it."""
    import pandas as pd

    from lib.availability import when_active_pa_rate

    rows = []
    # our batter: game 1 -> 4 PA, game 2 -> 5 PA (two pitches each), game 3 -> 3 PA
    for game, n_pa in ((1001, 4), (1002, 5), (1003, 3)):
        for ab in range(1, n_pa + 1):
            for pitch in (1, 2):
                rows.append({"game_pk": game, "at_bat_number": ab,
                             "batter": 665833, "pitch_number": pitch})
    # a different batter in the same games — must be ignored
    for ab in range(1, 9):
        rows.append({"game_pk": 1001, "at_bat_number": 90 + ab,
                     "batter": 571970, "pitch_number": 1})
    df = pd.DataFrame(rows)

    assert when_active_pa_rate(df, 665833) == pytest.approx(12 / 3)


def test_il_hitter_without_return_date_keeps_model_volume_and_flags_it():
    """No return date -> the overlay must NOT invent one. Model volume stays,
    with an explicit flag so boards can render the uncertainty."""
    out = ros_volume(
        {
            "bucket": "H",
            "status": "IL",
            "model_pa_per_teamgame": 2.2,
            "when_active_pa_per_game": 4.4,
            "return_date": None,
        },
        team_remaining_dates=SIX_DATES,
        today=date(2026, 8, 12),
    )
    assert out["proj_ros_pa"] == pytest.approx(2.2 * 6)
    assert out["source"] == "model_passthrough"
    assert "no_return_date" in out["flags"]


def test_il_sp_with_return_date_gets_rotation_share_minus_ramp():
    """A returning SP takes every 5th team game after his return date, with a
    ramp discount for the stretch-out outings (Glasnow's ~4-inning first
    start back). 20 games after return -> 4.0 raw starts - 0.6 ramp = 3.4."""
    dates = [date(2026, 8, 20 + i) if i < 12 else date(2026, 9, i - 11)
             for i in range(25)]  # 25 remaining team games
    out = ros_volume(
        {
            "bucket": "SP",
            "status": "IL",
            "return_date": dates[5],   # 20 team games on/after return
        },
        team_remaining_dates=dates,
        today=date(2026, 8, 12),
    )
    assert out["proj_ros_starts"] == pytest.approx(20 / 5 - 0.6)
    assert out["source"] == "il_return_overlay"
    assert "rehab_ramp" in out["flags"]


def test_active_hitter_with_shrinking_recent_usage_is_flagged_not_repriced():
    """The Muncy pattern: recent PA/teamgame well under the model's number
    means the ROLE may be shrinking. v1 surfaces the flag; the volume itself
    stays on the validated model (a blend ships only if the backtest earns it)."""
    out = ros_volume(
        {
            "bucket": "H",
            "status": "ACTIVE",
            "model_pa_per_teamgame": 3.45,
            "when_active_pa_per_game": 3.5,
            "recent_pa_per_teamgame": 2.6,   # L14 usage, 0.85 under model
            "return_date": None,
        },
        team_remaining_dates=SIX_DATES,
        today=date(2026, 8, 12),
    )
    assert out["proj_ros_pa"] == pytest.approx(3.45 * 6)   # unchanged
    assert "role_shrink" in out["flags"]
