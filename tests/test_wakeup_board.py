"""Tests for the wake-up board's classifier.

The board exists because HR rate needs ~275 PA to stabilize, so a HR run is a
lagging indicator by construction. It reads bat speed instead (r>=0.70 by 25-30
swings) — but bat speed has a documented failure mode: ranking on the YoY DELTA
inverts the board, surfacing a player washing out a slow start ahead of a
genuinely elite bat.

These lock the LEVEL-FIRST contract that prevents that inversion.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from run_wakeup_board import (  # noqa: E402
    LEVEL_PCTL_FLOOR, MIN_SW_DELTA, MIN_SW_LEVEL, STEP_MPH, classify,
)


def row(**kw):
    base = dict(bs_pctl=90.0, d_bat_speed=0.0, n_sw=600.0)
    base.update(kw)
    return pd.Series(base)


def test_elite_level_with_a_step_is_the_top_tag():
    tag, score = classify(row(bs_pctl=98.0, d_bat_speed=3.31))
    assert tag == "LEVEL+STEP"
    assert score > 98.0, "a step should add to the level, not replace it"


def test_elite_level_without_a_step_still_qualifies():
    tag, _ = classify(row(bs_pctl=87.0, d_bat_speed=-0.18))
    assert tag == "LEVEL", "an already-elite bat is interesting even when flat"


def test_the_bichette_inversion_cannot_happen():
    """THE canonical trap. Bichette 2026: +1.21 mph YoY off a 24th-pctile level
    (a slow start washing out) vs Cam Smith: a 98th-pctile level with a +3.31
    step. Delta-ranking puts Bichette on top; this board must not."""
    bichette, b_score = classify(row(bs_pctl=24.0, d_bat_speed=1.21))
    smith, s_score = classify(row(bs_pctl=98.0, d_bat_speed=3.31))
    assert bichette == "STEP-ONLY"
    assert smith == "LEVEL+STEP"
    assert s_score > b_score, "level must dominate the ordering, never the step"


def test_a_big_step_cannot_lift_a_poor_level_over_a_good_one():
    """Even an enormous step from a weak level must stay below a plain strong
    level — otherwise the bonus term reintroduces delta-ranking by the back
    door."""
    _, weak_huge_step = classify(row(bs_pctl=30.0, d_bat_speed=9.0))
    _, strong_flat = classify(row(bs_pctl=85.0, d_bat_speed=0.0))
    assert strong_flat > weak_huge_step


def test_step_bonus_is_bounded_so_one_outlier_cannot_dominate():
    _, a = classify(row(bs_pctl=70.0, d_bat_speed=3.0))
    _, b = classify(row(bs_pctl=70.0, d_bat_speed=30.0))
    assert a == b, "the step bonus must saturate"


def test_level_floor_is_the_tag_boundary():
    assert classify(row(bs_pctl=LEVEL_PCTL_FLOOR, d_bat_speed=0.0))[0] == "LEVEL"
    assert classify(row(bs_pctl=LEVEL_PCTL_FLOOR - 1, d_bat_speed=2.0))[0] == "STEP-ONLY"


def test_delta_needs_more_swings_than_a_level():
    """A YoY delta carries ~sqrt(2)x a level's noise, so the 200-swing delta
    gate must NOT be relaxed just because a level reads at 80."""
    assert MIN_SW_DELTA > MIN_SW_LEVEL
    # enough swings to read a level, not enough to trust the delta
    tag, _ = classify(row(bs_pctl=90.0, d_bat_speed=2.0, n_sw=MIN_SW_DELTA - 1))
    assert tag == "LEVEL", "an ungated delta must not be promoted to a step"
    tag, _ = classify(row(bs_pctl=90.0, d_bat_speed=2.0, n_sw=MIN_SW_DELTA))
    assert tag == "LEVEL+STEP"


def test_thin_samples_are_refused_not_guessed():
    assert classify(row(n_sw=MIN_SW_LEVEL - 1))[0] == "THIN"
    assert classify(row(bs_pctl=float("nan")))[0] == "THIN"
    assert classify(row(n_sw=0))[0] == "THIN"


def test_a_step_below_threshold_is_not_a_step():
    tag, _ = classify(row(bs_pctl=90.0, d_bat_speed=STEP_MPH - 0.01))
    assert tag == "LEVEL"
    tag, _ = classify(row(bs_pctl=90.0, d_bat_speed=STEP_MPH))
    assert tag == "LEVEL+STEP"


def test_negative_step_never_counts_as_waking_up():
    tag, _ = classify(row(bs_pctl=90.0, d_bat_speed=-3.0))
    assert tag == "LEVEL"
    tag, _ = classify(row(bs_pctl=40.0, d_bat_speed=-3.0))
    assert tag == "THIN", "poor level + falling bat speed is not a wake-up"


def test_board_never_ranks_on_home_runs_or_iso():
    """HR (275 PA) and ISO (275 AB) are too slow to read in-window. They must
    not appear as ranking inputs — the whole point of the board."""
    import inspect

    import run_wakeup_board as mod
    src = inspect.getsource(mod.classify)
    for banned in ("hr", "iso", "home_run", "slg"):
        assert banned not in src.lower().replace("history", ""), (
            f"{banned!r} must not influence the wake-up ranking")
