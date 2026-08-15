"""Tests for lib/milb_translation — AAA->MLB rookie hitter FP translation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

MT = pytest.importorskip("scripts.xfp.lib.milb_translation")

BAEZ_2026_AAA = {
    "pa": 461, "r": 79, "tb": 235, "rbi": 90,
    "bb": 37, "hbp": 9, "sb": 21, "k": 136,
}


def test_translate_computes_fp_per_pa_from_a_real_aaa_line():
    out = MT.translate_milb_to_mlb(BAEZ_2026_AAA)
    assert out["fp_per_pa"] == pytest.approx(0.498, abs=0.01)


def test_translate_computes_fp_per_game_at_default_pace():
    out = MT.translate_milb_to_mlb(BAEZ_2026_AAA)
    assert out["fp_per_game"] == pytest.approx(2.09, abs=0.05)


def test_translate_rejects_zero_or_negative_pa():
    with pytest.raises(ValueError):
        MT.translate_milb_to_mlb({**BAEZ_2026_AAA, "pa": 0})
    with pytest.raises(ValueError):
        MT.translate_milb_to_mlb({**BAEZ_2026_AAA, "pa": -10})


# ── blending the AAA prior with real MLB sample as it accrues ──────────────

def test_blend_with_zero_mlb_pa_returns_the_pure_translated_prior():
    out = MT.blend_with_mlb_actual(translated_rate=0.30, mlb_rate=0.05, mlb_n=0, credibility_n=50)
    assert out == 0.30


def test_blend_converges_toward_mlb_actual_as_sample_grows():
    out = MT.blend_with_mlb_actual(translated_rate=0.30, mlb_rate=0.05, mlb_n=5000, credibility_n=50)
    assert out == pytest.approx(0.05, abs=0.005)


def test_blend_halfway_when_mlb_n_equals_credibility_n():
    out = MT.blend_with_mlb_actual(translated_rate=0.30, mlb_rate=0.10, mlb_n=50, credibility_n=50)
    assert out == pytest.approx(0.20, abs=1e-9)


def test_blend_rejects_negative_mlb_n_and_non_positive_credibility_n():
    with pytest.raises(ValueError):
        MT.blend_with_mlb_actual(translated_rate=0.3, mlb_rate=0.1, mlb_n=-1, credibility_n=50)
    with pytest.raises(ValueError):
        MT.blend_with_mlb_actual(translated_rate=0.3, mlb_rate=0.1, mlb_n=10, credibility_n=0)


# ── validating the translation itself against real historical outcomes ─────

def test_summarize_backtest_reports_n_and_mean_error():
    rows = [{"pred": 0.50, "actual": 0.40}, {"pred": 0.30, "actual": 0.30}]
    out = MT.summarize_backtest(rows)
    assert out["n"] == 2
    assert out["mean_error"] == pytest.approx(0.05, abs=1e-9)


def test_summarize_backtest_reports_mean_abs_error_and_rmse():
    # errors: +0.1 and -0.2 -> mean_abs_error=0.15, rmse=sqrt((0.01+0.04)/2)
    rows = [{"pred": 0.50, "actual": 0.40}, {"pred": 0.10, "actual": 0.30}]
    out = MT.summarize_backtest(rows)
    assert out["mean_abs_error"] == pytest.approx(0.15, abs=1e-9)
    assert out["rmse"] == pytest.approx(0.15811, abs=1e-4)


def test_summarize_backtest_pearson_r_is_perfect_on_a_perfect_line():
    rows = [{"pred": p, "actual": 2 * p} for p in (0.1, 0.2, 0.3, 0.4)]
    out = MT.summarize_backtest(rows)
    assert out["pearson_r"] == pytest.approx(1.0, abs=1e-9)
    assert out["r_squared"] == pytest.approx(1.0, abs=1e-9)


def test_summarize_backtest_pearson_r_is_zero_on_uncorrelated_data():
    rows = [{"pred": 0.1, "actual": 0.3}, {"pred": 0.2, "actual": 0.1},
            {"pred": 0.3, "actual": 0.4}, {"pred": 0.4, "actual": 0.2}]
    out = MT.summarize_backtest(rows)
    assert out["pearson_r"] == pytest.approx(0.0, abs=1e-9)


def test_summarize_backtest_regression_recovers_a_known_line():
    # actual = 0.2 + 0.5*pred, exactly
    rows = [{"pred": p, "actual": 0.2 + 0.5 * p} for p in (0.1, 0.3, 0.5, 0.7)]
    out = MT.summarize_backtest(rows)
    assert out["regression_intercept"] == pytest.approx(0.2, abs=1e-9)
    assert out["regression_slope"] == pytest.approx(0.5, abs=1e-9)


def test_summarize_backtest_rejects_fewer_than_two_rows():
    with pytest.raises(ValueError):
        MT.summarize_backtest([])
    with pytest.raises(ValueError):
        MT.summarize_backtest([{"pred": 0.5, "actual": 0.4}])


# ── matching/assembly logic used to build a backtest from raw MLB Stats API pulls ──

def test_target_aaa_year_uses_prior_year_for_an_early_season_debut():
    # opening-day-ish debut -> the player made the team from LAST year's AAA level
    assert MT.target_aaa_year("2024-03-28") == 2023


def test_target_aaa_year_uses_same_year_for_a_midseason_debut():
    # called up mid-season -> this year's AAA stint (pre-callup) is the relevant one
    assert MT.target_aaa_year("2024-07-01") == 2024


def test_pick_mlb_actual_returns_first_year_meeting_the_pa_floor():
    stats_by_year = {
        2024: {"plateAppearances": 40},   # too thin, cup of coffee
        2025: {"plateAppearances": 150},  # first real sample
        2026: {"plateAppearances": 500},
    }
    out = MT.pick_mlb_actual(stats_by_year, debut_year=2024, min_pa=100)
    assert out == {"plateAppearances": 150}


def test_pick_mlb_actual_returns_none_when_nothing_qualifies():
    stats_by_year = {2024: {"plateAppearances": 40}, 2025: {"plateAppearances": 60}}
    out = MT.pick_mlb_actual(stats_by_year, debut_year=2024, min_pa=100)
    assert out is None


def _api_stat(**kw):
    base = {"plateAppearances": 0, "runs": 0, "totalBases": 0, "rbi": 0,
            "baseOnBalls": 0, "hitByPitch": 0, "stolenBases": 0, "strikeOuts": 0}
    base.update(kw)
    return base


def test_build_backtest_row_combines_translation_and_actual_fp_per_pa():
    aaa = _api_stat(plateAppearances=461, runs=79, totalBases=235, rbi=90,
                     baseOnBalls=37, hitByPitch=9, stolenBases=21, strikeOuts=136)
    mlb = _api_stat(plateAppearances=100, runs=15, totalBases=40, rbi=15,
                     baseOnBalls=8, hitByPitch=1, stolenBases=3, strikeOuts=30)
    row = MT.build_backtest_row("Test Player", aaa, mlb)
    assert row["name"] == "Test Player"
    assert row["pred"] == pytest.approx(0.498, abs=0.01)
    assert row["actual"] == pytest.approx((15 + 40 + 15 + 8 + 1 + 3 - 30) / 100, abs=1e-9)


def test_build_backtest_row_returns_none_when_aaa_sample_too_thin():
    aaa = _api_stat(plateAppearances=80, runs=10, totalBases=30, rbi=10,
                     baseOnBalls=5, hitByPitch=1, stolenBases=2, strikeOuts=20)
    mlb = _api_stat(plateAppearances=100, runs=15, totalBases=40, rbi=15,
                     baseOnBalls=8, hitByPitch=1, stolenBases=3, strikeOuts=30)
    assert MT.build_backtest_row("Test Player", aaa, mlb) is None
