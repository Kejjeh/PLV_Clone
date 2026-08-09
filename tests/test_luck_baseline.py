"""Tests for the personal expected-vs-actual (luck) baseline.

The luck lens judged every hitter against zero because the FIELD's wOBA−xwOBA
gap centers on zero. Some hitters' does not: Jose Altuve beat his expected line
in 10 of 11 full seasons at a PA-weighted +0.030, so on 2026-08-09 the lens
reported him "due for negative regression" while he sat at exactly his career
norm. These lock the fix and — just as importantly — the two ways it could go
wrong: applying the career gap at FULL strength (validated as no better than
ignoring it), and letting the annotation quietly become a vote.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from lib.expected_stats import (  # noqa: E402
    LUCK_MIN_PA, LUCK_MIN_SEASONS, LUCK_SHRINK, LUCK_SOURCE_OFFSET,
    PERSISTENT_BAND, expected_vs_actual, personal_luck_baseline,
)

#: An Altuve-shaped history: beats his expected line every year at ~+0.030.
BEATER = [(650, 0.030), (600, 0.031), (680, 0.025), (660, 0.034)]


# ── the fix: a persistent beater at his own level is not "lucky" ─────────────

def test_persistent_beater_at_his_own_level_is_aligned():
    """The canonical failure. Raw gap +0.016 against a zero reference would be
    inside ALIGNED anyway, so use a gap that WOULD have tripped the old
    field-relative threshold and must not trip the personal one."""
    b = personal_luck_baseline(BEATER)
    assert b["profile"] == "PERSISTENT-BEATER"
    field = expected_vs_actual(0.300, 0.300 + 0.025)
    own = expected_vs_actual(0.300, 0.300 + 0.025, own_baseline=b["baseline"])
    assert field["regression"] == "OVERPERFORMING"   # the false alarm
    assert own["regression"] == "ALIGNED"            # the fix


def test_a_beater_can_still_be_flagged_when_he_exceeds_his_own_norm():
    """The baseline must not become a blanket pardon — it moves the reference,
    it does not remove the threshold."""
    b = personal_luck_baseline(BEATER)
    r = expected_vs_actual(0.300, 0.300 + 0.070, own_baseline=b["baseline"])
    assert r["regression"] == "OVERPERFORMING"
    assert r["excess"] == pytest.approx(0.070 - b["baseline"])


def test_a_beater_below_his_own_baseline_is_owed_bounce():
    """A hitter who normally gains +0.016 and is currently at −0.010 has lost
    more than the field-relative reading shows."""
    b = personal_luck_baseline(BEATER)
    r = expected_vs_actual(0.300, 0.300 - 0.010, own_baseline=b["baseline"])
    assert r["regression"] == "UNDERPERFORMING"
    assert r["excess"] < -0.020


# ── shrinkage: the load-bearing part ─────────────────────────────────────────

def test_the_baseline_is_shrunk_not_the_raw_career_gap():
    """Validated leave-one-season-out (n=1583): full-personal scores MAE 0.0164,
    identical to ignoring history entirely; only the shrunk version (0.0154)
    beats the field zero. Applying the career gap at face value overshoots."""
    b = personal_luck_baseline(BEATER)
    assert b["baseline"] != pytest.approx(b["career_gap"])
    assert abs(b["baseline"]) < abs(b["career_gap"])
    assert b["baseline"] == pytest.approx(LUCK_SHRINK * b["career_gap"])


def test_shrink_is_a_proper_fraction():
    """0 would discard a validated signal (r=0.334); >=1 would assert the trait
    does not regress, which the fitted slope 0.527 [0.452, 0.604] contradicts."""
    assert 0.0 < LUCK_SHRINK < 1.0


def test_shrink_matches_the_fitted_slope_within_its_confidence_interval():
    assert 0.452 <= LUCK_SHRINK <= 0.604


# ── sample gates: absent history must mean "field", never "no tendency" ──────

def test_too_few_seasons_returns_none():
    assert personal_luck_baseline(BEATER[:LUCK_MIN_SEASONS - 1]) is None


def test_too_few_pa_returns_none():
    thin = [(50, 0.030), (60, 0.031), (70, 0.025)]
    assert sum(pa for pa, _ in thin) < LUCK_MIN_PA
    assert personal_luck_baseline(thin) is None


def test_none_falls_back_to_exact_legacy_behaviour():
    """A caller with no history must get byte-identical tiers to before, so
    adding the baseline cannot silently reinterpret the whole league."""
    for gap in (-0.05, -0.021, -0.02, 0.0, 0.02, 0.021, 0.05):
        legacy = expected_vs_actual(0.300, 0.300 + gap)
        explicit = expected_vs_actual(0.300, 0.300 + gap, own_baseline=None)
        assert legacy["regression"] == explicit["regression"]
        assert explicit["excess"] == pytest.approx(gap)


def test_empty_history_returns_none_rather_than_a_zero_baseline():
    assert personal_luck_baseline([]) is None


# ── construction ─────────────────────────────────────────────────────────────

def test_the_baseline_is_pa_weighted_not_a_simple_mean():
    """A 600-PA season must count for more than a 60-PA one, or a fluke cup of
    coffee moves a career reference."""
    seasons = [(600, 0.000), (600, 0.000), (600, 0.000), (60, 0.100)]
    b = personal_luck_baseline(seasons)
    simple = sum(g for _, g in seasons) / len(seasons)
    assert b["career_gap"] < simple / 2


def test_nan_and_zero_pa_seasons_are_dropped():
    b = personal_luck_baseline(BEATER + [(0, 0.9), (float("nan"), 0.5)])
    assert b["n_seasons"] == len(BEATER)


def test_seasons_beat_counts_only_positive_gaps():
    b = personal_luck_baseline([(600, 0.03), (600, -0.01), (600, 0.02)])
    assert b["seasons_beat"] == 2


# ── profile labels ───────────────────────────────────────────────────────────

def test_profile_is_symmetric():
    beat = personal_luck_baseline([(650, +0.05)] * 3)
    under = personal_luck_baseline([(650, -0.05)] * 3)
    assert beat["profile"] == "PERSISTENT-BEATER"
    assert under["profile"] == "PERSISTENT-UNDER"


def test_an_ordinary_hitter_gets_no_persistence_label():
    b = personal_luck_baseline([(650, 0.002), (650, -0.003), (650, 0.001)])
    assert b["profile"] == "FIELD-NORMAL"


def test_persistent_band_is_anchored_to_half_the_luck_threshold():
    """Below half a tier the personal baseline cannot change any verdict, so
    labelling a 'profile' there would be naming noise."""
    assert PERSISTENT_BAND == pytest.approx(0.020 / 2)


def test_the_label_is_judged_on_the_shrunk_value():
    """A career gap that survives shrinkage is a tendency; one that does not is
    a small effect dressed up by ignoring regression."""
    b = personal_luck_baseline([(650, PERSISTENT_BAND * 1.05)] * 3)
    assert b["baseline"] < PERSISTENT_BAND
    assert b["profile"] == "FIELD-NORMAL"


# ── unit harmonisation between the two xwOBA sources ────────────────────────
# The baseline is Savant's expected line; the current gap is computed locally.
# They correlate at 0.973 but the local gap runs ~+0.007 hotter, which is
# enough to move a tier — Altuve's excess is +0.023 (OVERPERFORMING) raw and
# +0.016 (ALIGNED) harmonised, and only the harmonised value agrees with his
# Savant season gap.

def test_source_offset_is_a_small_positive_correction():
    """A large offset would mean the two xwOBA implementations disagree about
    more than units and should not be differenced at all; zero would mean the
    correction had been quietly disabled."""
    assert 0.0 < LUCK_SOURCE_OFFSET < 0.020


def test_the_offset_is_smaller_than_the_tier_threshold():
    """A calibration constant bigger than the threshold it feeds would be
    deciding the verdict by itself."""
    assert LUCK_SOURCE_OFFSET < 0.020


def test_expected_vs_actual_stays_unit_agnostic():
    """The pure comparator must NOT apply the offset — it has no idea which
    source its inputs came from. Harmonisation belongs at the measurement
    boundary (hitter_expected), so a caller passing two Savant-units numbers
    is not silently corrected for a mismatch that isn't there."""
    r = expected_vs_actual(0.300, 0.320, own_baseline=0.010)
    assert r["excess"] == pytest.approx(0.020 - 0.010)


# ── the peg keeps it an ANNOTATION ───────────────────────────────────────────

def test_classify_cannot_see_the_luck_read():
    """The peg REPORTS the excess and must never classify on it. Wiring it as a
    vote would be an unvalidated number-mover (Rule 13). This is the guard the
    xwOBACON episode earned: that signal sat documented-but-unwired for exactly
    as long as nothing asserted the connection either way."""
    import inspect

    from run_prior_year_peg import classify
    params = set(inspect.signature(classify).parameters)
    assert not (params & {"luck", "excess", "own_baseline", "xwoba", "woba"}), (
        "classify() must stay blind to the luck lens — it is an annotation")


def test_the_peg_regime_is_unchanged_by_any_luck_value():
    from run_prior_year_peg import classify
    base = classify(fp_gap=+0.142, support=1, oppose=5)[0]
    assert base == "OVEREXTENDED"
    # there is no argument by which luck could alter it — signature is fixed
    assert classify(fp_gap=+0.142, support=1, oppose=5, xc_yoy=0.0)[0] == base
