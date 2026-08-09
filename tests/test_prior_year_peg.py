"""Tests for the prior-year peg classifier.

The board exists because field-relative ranks cannot see mean-reversion. On
2026-08-09 rh3 rank, recent FP/g and the optimizer all preferred Caleb Durbin
over Jarren Duran; pegged to their own 2025 baselines the order reversed,
because Durbin was outproducing a decayed process and Duran was underproducing
an intact one. These lock the asymmetry that produced that reversal.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from run_prior_year_peg import FLAT_BAND, METRICS, classify  # noqa: E402


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
