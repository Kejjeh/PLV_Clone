"""Tests for the prior-year peg classifier.

The board exists because field-relative ranks cannot see mean-reversion. On
2026-08-09 rh3 rank, recent FP/g and the optimizer all preferred Caleb Durbin
over Jarren Duran; pegged to their own 2025 baselines the order reversed,
because Durbin was outproducing a decayed process and Duran was underproducing
an intact one. These lock the asymmetry that produced that reversal.
"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import pandas as pd  # noqa: E402

from run_prior_year_peg import (  # noqa: E402
    BLEND_W1, FLAT_BAND, METRICS, PRIOR_MIN_PA, baseline_level, classify,
)


def _hist(*seasons):
    """(year, pa, fp_per_pa) rows in the multiyr cache's shape."""
    return pd.DataFrame([{"year": y, "pa": pa, "fp_per_pa_actual": fp}
                         for y, pa, fp in seasons])


# ── the baseline is a blend, not last season alone ───────────────────────────
# Validated 2026-08-09 (n=1165): 1yr r=0.501/MAE=0.1010, 3yr r=0.558/MAE=0.0915,
# blend 40/60 r=0.562/MAE=0.0906. The edge is asymmetric — after a CAREER year a
# 1-year peg is biased -0.083 while 3-year is -0.012 — which is why the blend
# exists rather than either endpoint.

def test_the_baseline_blends_last_year_with_the_three_year_level():
    h = _hist((2023, 600, 0.500), (2024, 600, 0.500), (2025, 600, 0.600))
    base, three, mode = baseline_level(h, 2025)
    assert three is not None
    assert base == pytest.approx(BLEND_W1 * 0.600 + (1 - BLEND_W1) * three)
    assert base < 0.600, "a career year must be pulled DOWN toward the 3yr level"
    assert "40%" in mode


def test_a_career_year_is_discounted_and_a_down_year_lifted():
    """The two directions the bias table describes, in miniature."""
    up = baseline_level(_hist((2023, 600, 0.50), (2024, 600, 0.50), (2025, 600, 0.70)), 2025)[0]
    down = baseline_level(_hist((2023, 600, 0.50), (2024, 600, 0.50), (2025, 600, 0.30)), 2025)[0]
    assert 0.50 < up < 0.70
    assert 0.30 < down < 0.50


def test_the_window_is_three_seasons_not_the_whole_career():
    """A player's 2015 peak must not anchor a 2026 baseline."""
    h = _hist((2019, 600, 5.0), (2023, 600, 0.50), (2024, 600, 0.50), (2025, 600, 0.50))
    base, three, _ = baseline_level(h, 2025)
    assert three == pytest.approx(0.50)
    assert base == pytest.approx(0.50)


def test_thin_seasons_do_not_join_the_three_year_level():
    """A 40-PA cameo is not a season; letting it weight the level would import
    exactly the small-sample noise the peg's stabilization gates exclude."""
    h = _hist((2024, PRIOR_MIN_PA - 1, 5.0), (2025, 600, 0.50))
    base, three, mode = baseline_level(h, 2025)
    assert three is None and base == pytest.approx(0.50)
    assert "1yr only" in mode


def test_a_single_prior_season_falls_back_to_last_year_and_says_so():
    """The rookie/sophomore case (Caleb Durbin, 2026-08-09). Falling back is
    fine; falling back SILENTLY would misreport what the gap was measured
    against."""
    base, three, mode = baseline_level(_hist((2025, 600, 0.606)), 2025)
    assert base == pytest.approx(0.606)
    assert three is None
    assert "1yr only" in mode


def test_the_three_year_level_is_pa_weighted():
    """A 600-PA season must outweigh a 200-PA one."""
    h = _hist((2023, 200, 0.900), (2024, 600, 0.500), (2025, 600, 0.500))
    _, three, _ = baseline_level(h, 2025)
    assert three == pytest.approx((200 * 0.9 + 600 * 0.5 + 600 * 0.5) / 1400)
    assert three < (0.9 + 0.5 + 0.5) / 3, "must not be a simple mean"


def test_blend_weight_favours_the_three_year_level():
    """The fitted optimum put most of the weight on the multi-year level; a
    weight above 0.5 would invert the validated finding."""
    assert 0.0 < BLEND_W1 < 0.5


# ── the four regimes ─────────────────────────────────────────────────────────

def test_above_prior_with_process_support_is_sustained():
    regime, _ = classify(fp_gap=+0.15, support=5, oppose=1)
    assert regime == "SUSTAINED"


def test_above_prior_without_process_support_is_overextended():
    """The Durbin case: +0.142 fp/PA over his 2025 level on 1 metric toward /
    5 away. Output ahead of a process that did not improve regresses."""
    regime, why = classify(fp_gap=+0.142, support=1, oppose=5)
    assert regime == "OVEREXTENDED"
    assert "regression" in why


def test_below_prior_with_process_support_is_recovering():
    """The Jarren case: -0.043 fp/PA under his 2025 level on 3 toward / 2 away."""
    regime, why = classify(fp_gap=-0.043, support=3, oppose=2)
    assert regime == "RECOVERING"
    assert "climbing back" in why


def test_below_prior_without_process_support_is_stalled():
    regime, _ = classify(fp_gap=-0.15, support=1, oppose=4)
    assert regime == "STALLED"


def test_the_canonical_reversal_holds():
    """Same direction of PRODUCTION would rank Durbin first; the peg must put
    them in opposite regimes. This is the whole reason the board exists."""
    durbin, _ = classify(fp_gap=+0.142, support=1, oppose=5)
    duran, _ = classify(fp_gap=-0.043, support=3, oppose=2)
    assert durbin == "OVEREXTENDED" and duran == "RECOVERING"
    assert durbin != duran


# ── the flat band ────────────────────────────────────────────────────────────

def test_small_moves_are_at_level_not_a_regime():
    """A tiny fp/PA move is noise. Calling it RECOVERING or OVEREXTENDED would
    manufacture a story out of sampling error."""
    for gap in (0.0, FLAT_BAND - 0.001, -(FLAT_BAND - 0.001)):
        regime, _ = classify(fp_gap=gap, support=5, oppose=0)
        assert regime == "AT-LEVEL", gap


def test_flat_band_is_symmetric():
    above, _ = classify(fp_gap=+FLAT_BAND, support=4, oppose=0)
    below, _ = classify(fp_gap=-FLAT_BAND, support=4, oppose=0)
    assert above == "SUSTAINED" and below == "RECOVERING"


def test_a_strong_process_vote_cannot_override_the_direction():
    """Support decides WHICH regime within a direction; it must never flip the
    direction itself. An overperformer with good process is SUSTAINED, never
    RECOVERING."""
    assert classify(fp_gap=+0.20, support=6, oppose=0)[0] == "SUSTAINED"
    assert classify(fp_gap=-0.20, support=6, oppose=0)[0] == "RECOVERING"


def test_a_tied_process_vote_resolves_pessimistically():
    """support == oppose is not support. A tie must NOT be read as
    confirmation in either direction — the burden of proof sits with the
    claim that something changed."""
    assert classify(fp_gap=+0.10, support=2, oppose=2)[0] == "OVEREXTENDED"
    assert classify(fp_gap=-0.10, support=2, oppose=2)[0] == "STALLED"


def test_zero_readable_metrics_does_not_manufacture_support():
    """When nothing cleared its minimum the vote is 0/0 — a tie — so the
    player lands in the sceptical regime rather than being credited."""
    assert classify(fp_gap=+0.10, support=0, oppose=0)[0] == "OVEREXTENDED"
    assert classify(fp_gap=-0.10, support=0, oppose=0)[0] == "STALLED"


# ── evidence set ─────────────────────────────────────────────────────────────

def test_lagging_power_metrics_are_never_evidence():
    """HR needs 275 PA and ISO 275 AB to stabilize — neither is readable in a
    half-season window, so neither may vote. This is the lagging-indicator trap
    the whole approach routes around."""
    for banned in ("hr", "hr_ppa", "hr_per_pa", "iso", "slg"):
        assert banned not in METRICS, f"{banned!r} must not be a peg metric"


def test_every_peg_metric_has_a_stabilization_minimum():
    """A metric with no published minimum cannot be gated, so it must not be
    in the evidence set."""
    from plv_clone.stabilization import HITTER_MINS
    for met in METRICS:
        assert met in HITTER_MINS, f"{met} has no stabilization minimum"


def test_metric_directions_are_correct():
    """A sign error here silently inverts every verdict on the board."""
    lower_is_better = {"k_pct", "chase", "whiff", "swstr"}
    higher_is_better = {"zswing", "hard_hit"}
    for met, (sign, _col) in METRICS.items():
        if met in lower_is_better:
            assert sign == -1, f"{met} should score LOWER as better"
        elif met in higher_is_better:
            assert sign == +1, f"{met} should score HIGHER as better"
        else:
            raise AssertionError(f"unclassified peg metric {met!r} — "
                                 "add it to this test's direction sets")


# ── noise floor: magnitude must clear noise before direction means anything ──
# Found 2026-08-09 running the first cohort sweep. The vote was unweighted, so
# a -0.0pp SwStr move and a -0.3pp chase move both scored as "toward prior
# level" and OUTVOTED a +10.6pp K% collapse — returning RECOVERING for Eugenio
# Suárez, whom every other lens had as a hard FADE.

def test_noise_floors_are_scaled_per_metric():
    """Spreads differ by >2x across these metrics (hard-hit SD 7.9pp vs SwStr
    3.5pp), so one uniform floor would be simultaneously too strict for SwStr
    and too loose for hard-hit."""
    from run_prior_year_peg import METRICS, NOISE_FLOOR_PP
    assert set(NOISE_FLOOR_PP) == set(METRICS), "every peg metric needs a floor"
    assert all(v > 0 for v in NOISE_FLOOR_PP.values())
    assert NOISE_FLOOR_PP["hard_hit"] > NOISE_FLOOR_PP["swstr"] * 1.5


def test_a_near_zero_delta_must_not_vote():
    """The Suárez failure in miniature: two noise-level 'improvements' must not
    outvote one real deterioration."""
    from run_prior_year_peg import NOISE_FLOOR_PP
    for met, floor in NOISE_FLOOR_PP.items():
        assert abs(-0.05) < floor, f"{met}: a 0.05pp move must be below the floor"


# ── xwOBACON tie-break (the validated recovery-template condition) ───────────

def test_stable_contact_breaks_a_tied_vote_toward_recovering():
    """Jarren Duran 2026-08-09: 2 toward / 2 away with xwOBACON flat at -0.002.
    The validated rule (memory gotcha #8) says stable contact means prior
    recoveries predict this one — so a tie must not fall through to STALLED."""
    regime, why = classify(fp_gap=-0.043, support=2, oppose=2, xc_yoy=-0.002)
    assert regime == "RECOVERING"
    assert "recovery-template" in why


def test_declining_contact_leaves_a_tied_vote_stalled():
    """The Turner pattern: contact eroding YoY means the recovery ceiling sits
    BELOW prior troughs, so a tie stays STALLED."""
    regime, _ = classify(fp_gap=-0.043, support=2, oppose=2, xc_yoy=-0.060)
    assert regime == "STALLED"


def test_the_tie_break_cannot_override_a_decided_vote():
    """It breaks TIES only. Stable contact must not rescue a player whose
    readable process is actually moving away from his level."""
    regime, _ = classify(fp_gap=-0.20, support=0, oppose=3, xc_yoy=0.000)
    assert regime == "STALLED"


def test_the_tie_break_never_touches_the_above_prior_side():
    """An overperformer with rock-stable contact is still OVEREXTENDED —
    stability there says the surplus is NOT contact-driven, which is evidence
    AGAINST him, never for him."""
    regime, _ = classify(fp_gap=+0.142, support=2, oppose=2, xc_yoy=0.000)
    assert regime == "OVEREXTENDED"


def test_missing_xwobacon_falls_back_to_the_pessimistic_tie():
    regime, _ = classify(fp_gap=-0.10, support=2, oppose=2, xc_yoy=None)
    assert regime == "STALLED"
