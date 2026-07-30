"""Tests for the empirical stabilization minimums (plv_clone.stabilization).

These lock the MEASURED values from the two 2026-07-29 pre-registered studies
so a future edit cannot quietly loosen a gate back toward a hand-picked number.
If a value here needs to change, it changes because a new study measured it —
update the memo, the module docstring, and this test together.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from plv_clone import stabilization as S  # noqa: E402


# ── The measured values (locked) ─────────────────────────────────────────────

def test_hitter_minimums_match_the_study():
    """Part A of inseason_delta_grid_2026-07-29.md, 91,628 snapshots."""
    assert S.minimum("chase", "H") == (150, S.OOZ_PITCHES)
    assert S.minimum("zswing", "H") == (150, S.IZ_PITCHES)
    assert S.minimum("whiff", "H") == (150, S.SWINGS)
    assert S.minimum("swstr", "H") == (150, S.PITCHES)
    assert S.minimum("k_pct", "H") == (50, S.PA)
    assert S.minimum("hard_hit", "H") == (50, S.BIP)
    assert S.minimum("barrel", "H") == (50, S.BIP)
    # The two corrections that mattered most vs prior practice.
    assert S.minimum("bb_pct", "H") == (175, S.PA)
    assert S.minimum("hr_ppa", "H") == (275, S.PA)
    assert S.minimum("xwoba_ppa", "H") == (225, S.PA)
    assert S.minimum("iso", "H") == (275, S.AB)


def test_pitcher_minimums_match_the_study():
    """pitcher_cutoff_stabilization_2026-07-29.md, 26,958 SP + 42,978 RP."""
    assert S.minimum("velo", "SP") == (150, S.PITCHES)
    assert S.minimum("velo", "RP") == (150, S.PITCHES)
    assert S.minimum("whiff", "SP") == (150, S.SWINGS)
    assert S.minimum("swstr", "SP") == (175, S.PITCHES)
    assert S.minimum("swstr", "RP") == (200, S.PITCHES)
    assert S.minimum("k_pct", "SP") == (100, S.TBF)
    assert S.minimum("k_pct", "RP") == (125, S.TBF)
    assert S.minimum("gb", "SP") == (50, S.BIP)


def test_bb_pct_gate_is_not_the_old_60_pa_handpick():
    """A 60-PA walk-rate read was the pre-study practice; it must now fail."""
    assert not S.is_sufficient(60, "bb_pct", "H")
    assert not S.is_sufficient(174, "bb_pct", "H")
    assert S.is_sufficient(175, "bb_pct", "H")


def test_swing_decision_gate_relaxed_from_300_to_150():
    """The old 300-pitch hand-pick was 2x conservative."""
    assert S.is_sufficient(150, "chase", "H")
    assert S.is_sufficient(150, "whiff", "SP")


# ── Never-stabilizes contract ────────────────────────────────────────────────

@pytest.mark.parametrize("metric", ["chase", "bb_pct", "hard_hit", "barrel", "hr_rate"])
def test_sp_unstabilizable_metrics_refuse_a_gate(metric):
    """Asking for a threshold on an unstabilizable metric is a design bug."""
    assert metric in S.NEVER_STABILIZES["SP"]
    with pytest.raises(ValueError, match="never stabilizes"):
        S.minimum(metric, "SP")


def test_rp_unstabilizable_set():
    assert {"chase", "bb_pct", "woba_agn"} <= S.NEVER_STABILIZES["RP"]


def test_hitters_have_no_unstabilizable_metrics():
    """Every hitter metric studied did stabilize at some sample size."""
    assert S.NEVER_STABILIZES["H"] == frozenset()


def test_insufficient_reports_unstabilizable_as_unusable():
    out = S.insufficient(["velo", "chase"], {"velo": 999, "chase": 999}, "SP")
    assert out == ["chase"]


# ── gate() behaviour ─────────────────────────────────────────────────────────

def test_gate_blanks_undersized_and_passes_sufficient():
    assert math.isnan(S.gate(0.09, 60, "bb_pct", "H"))
    assert S.gate(0.09, 200, "bb_pct", "H") == 0.09


@pytest.mark.parametrize("bad", [None, float("nan"), "", "abc"])
def test_gate_treats_missing_or_junk_denominator_as_insufficient(bad):
    assert math.isnan(S.gate(1.23, bad, "k_pct", "H"))


def test_gate_custom_fill():
    assert S.gate(0.09, 10, "bb_pct", "H", fill=None) is None


def test_is_sufficient_boundary_is_inclusive():
    n, _ = S.minimum("k_pct", "H")
    assert S.is_sufficient(n, "k_pct", "H")
    assert not S.is_sufficient(n - 1, "k_pct", "H")


# ── Provenance honesty ───────────────────────────────────────────────────────

def test_bat_speed_graduated_to_a_measured_entry():
    """2026-07-29: bat speed was promoted out of LITERATURE_ONLY once the daily
    store made it measurable. Forward r never falls below +0.70 anywhere in the
    curve; both crossings clear by 25-30 swings; ceil-25 rule gives 50."""
    assert S.minimum("bat_speed", "H") == (50, S.SWINGS)
    assert "bat_speed" in S.HITTER_MINS
    assert "bat_speed" not in S.LITERATURE_ONLY
    # it clears r=0.70, so it must NOT be labelled directional-only
    assert "bat_speed" not in S.NEVER_HIGH_CONFIDENCE["H"]
    assert "literature" not in S.describe("bat_speed", "H")


def test_bat_speed_is_the_cheapest_hitter_gate():
    """It should be reachable in ~a week of playing time — cheaper than every
    other hitter metric, which is the whole practical point."""
    n_bs, _ = S.minimum("bat_speed", "H")
    for other in ("chase", "k_pct", "bb_pct", "xwoba_ppa", "iso"):
        assert n_bs <= S.minimum(other, "H")[0], other


def test_swing_length_remains_literature_only():
    """gf bridge carries batSpeed but not swing_length — coverage too thin to
    derive a crossing, so the borrowed number must stay flagged."""
    assert "swing_length" in S.LITERATURE_ONLY
    assert "literature" in S.describe("swing_length", "H")


def test_directional_only_metrics_are_labelled():
    assert "directional only" in S.describe("bb_pct", "H")
    assert "directional only" in S.describe("iso", "H")


def test_unknown_metric_raises_rather_than_guessing():
    with pytest.raises(S.UnknownMetric):
        S.minimum("vibes", "H")


def test_unknown_side_raises():
    with pytest.raises(S.UnknownMetric):
        S.minimum("k_pct", "XX")


# ── Model-universe filters are re-exported, not redefined ────────────────────

def test_model_universe_filters_come_from_the_models():
    """stabilization.py must not fork these values — it imports them."""
    if not S._MODEL_FILTERS_AVAILABLE:
        pytest.skip("model modules unavailable in this env")
    from plv_clone.models.xfp.rh3 import EVAL_PA_MIN, ROS_PA_MIN
    from plv_clone.models.xfp.rp3 import EVAL_GS_MIN, ROS_GS_MIN
    assert S.EVAL_PA_MIN == EVAL_PA_MIN
    assert S.ROS_PA_MIN == ROS_PA_MIN
    assert S.EVAL_GS_MIN == EVAL_GS_MIN
    assert S.ROS_GS_MIN == ROS_GS_MIN


def test_every_registered_minimum_has_a_known_unit():
    units = {S.PITCHES, S.OOZ_PITCHES, S.IZ_PITCHES, S.SWINGS,
             S.PA, S.TBF, S.BIP, S.AB}
    for side, table in S.MINS_BY_SIDE.items():
        for metric, (n, unit) in table.items():
            assert unit in units, f"{side}/{metric} has unit {unit!r}"
            assert n > 0 and n % 25 == 0, f"{side}/{metric} min {n} not ceil-25"
