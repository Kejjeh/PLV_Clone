"""
Season stage detection and stage-aware threshold constants.

The core PLV and Process+ model scales are FROZEN — this module only affects
workflow-layer heuristics: confidence tiers, board thresholds, labels, and
dashboard warnings.

Stage detection uses the league median PA (hitters) or median pitches (pitchers)
of the loaded dataset. This is purely data-driven and works correctly for any
year, including historical review.

Stages
------
EARLY   league median hitter PA  < 150  (approx. March 20 – May 15)
MID     league median hitter PA  150-320 (approx. May 16 – July 25)
MATURE  league median hitter PA  > 320  (approx. July 26+)

Calibration basis: 2023–2025 full-season data (n=1,200+ hitter-seasons).
2026 used only to validate early-season behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

# ── Stage boundaries (hitter PA, pitcher pitches) ────────────────────────────
_PA_EARLY_MAX    = 150
_PA_MID_MAX      = 320
_PITCH_EARLY_MAX = 200
_PITCH_MID_MAX   = 500

STAGES = ("early", "mid", "mature")


def infer_stage(
    hitters: pd.DataFrame | None = None,
    pitchers: pd.DataFrame | None = None,
    season_date: date | None = None,
) -> str:
    """Infer season stage.

    Priority order:
    1. ``season_date`` (calendar date) — preferred; avoids PA-qualification bias.
    2. League median PA of *hitters* (must be an unfiltered or lightly-filtered
       population to give a valid signal; qualified-only exports skew high).
    3. League median pitches of *pitchers*.
    4. 'mature' fallback.

    Calendar cutoffs (from docs/season_stage_thresholds.md):
        early  : before  May 16   (approx. March 20 – May 15)
        mid    : May 16 – July 25  (approx. May 16 – July 25)
        mature : July 26+
    """
    if season_date is not None:
        month_day = (season_date.month, season_date.day)
        if month_day < (5, 16):
            return "early"
        if month_day < (7, 26):
            return "mid"
        return "mature"

    if hitters is not None and not hitters.empty and "pa" in hitters.columns:
        median_pa = float(hitters["pa"].median())
        if median_pa < _PA_EARLY_MAX:
            return "early"
        if median_pa < _PA_MID_MAX:
            return "mid"
        return "mature"

    if pitchers is not None and not pitchers.empty and "pitches" in pitchers.columns:
        median_pitches = float(pitchers["pitches"].median())
        if median_pitches < _PITCH_EARLY_MAX:
            return "early"
        if median_pitches < _PITCH_MID_MAX:
            return "mid"
        return "mature"

    return "mature"


@dataclass
class StageThresholds:
    """All workflow-layer thresholds for one season stage."""

    stage: str

    # ── Confidence tier PA boundaries (hitters) ──────────────────────────────
    hitter_tier_a_pa:   int = 400
    hitter_tier_b_pa:   int = 250
    hitter_tier_c_pa:   int = 150   # minimum to appear on any board
    hitter_tier_labels: tuple = ("Tier A", "Tier B", "Tier C")

    # ── Confidence tier pitch boundaries (pitchers) ──────────────────────────
    pitcher_tier_a_pitches: int = 1000
    pitcher_tier_b_pitches: int = 400
    pitcher_tier_c_pitches: int = 100
    pitcher_tier_labels:    tuple = ("Tier A", "Tier B", "Tier C")

    # ── Board filter minimums ─────────────────────────────────────────────────
    min_pa_for_boards:      int = 150
    min_pitches_for_boards: int = 100

    # ── Buy-target thresholds ─────────────────────────────────────────────────
    buy_rank_gap_min:    float = 0.15   # process+ rank - xwoba rank
    buy_pp_floor:        float = 100.0  # Process+ minimum
    buy_dec_gate:        float | None = None  # Decision+ gate (None = no gate)

    # ── Regression-flag thresholds ────────────────────────────────────────────
    reg_rank_gap_max:    float = -0.15  # negative = xwoba rank > process+ rank
    reg_xwoba_floor:     float = 0.350  # minimum xwOBA to flag
    reg_dec_gate:        float | None = None  # require Decision+ below this (None = no gate)

    # ── Breakout-flag thresholds ──────────────────────────────────────────────
    breakout_pp_min:     float = 110.0
    breakout_dec_gate:   float | None = None  # Decision+ must also be elevated

    # ── Discipline / Power thresholds ─────────────────────────────────────────
    discipline_dec_min:  float = 109.0   # top 25% stable across seasons
    power_pow_min:       float = 107.0   # top 25%

    # ── Rolling trend thresholds (decision_value_mean) ────────────────────────
    rolling_hot_dec:     float = 0.083   # ≈ p75 of 2023-2025 rolling
    rolling_warm_dec:    float = 0.066   # ≈ p50

    # ── PLV thresholds ────────────────────────────────────────────────────────
    plv_strong:  float = 5.17   # top 25% stable across seasons
    plv_elite:   float = 5.30   # top 10%
    plv_median:  float = 5.01

    # ── Dashboard labels ──────────────────────────────────────────────────────
    stage_label:   str = "Mature Season"
    stage_color:   str = "green"
    stage_warning: str | None = None


def get_thresholds(stage: str) -> StageThresholds:
    """Return the StageThresholds instance for *stage*.

    Parameters
    ----------
    stage : 'early' | 'mid' | 'mature'
    """
    if stage == "early":
        return _EARLY
    if stage == "mid":
        return _MID
    return _MATURE


# ── Stage definitions ─────────────────────────────────────────────────────────
#
# Calibration notes (2023–2025 data, n ≈ 1,200 hitter-seasons):
#
#   Process+ std at full season:  ~10.6
#   Process+ std at 50-150 PA:    ~16.2  (+53%)
#   Power+ std at 50-150 PA:      ~15.6  (+47%)
#   Decision+ std is more stable:  ~12-14 early vs ~11 mature
#
#   rank_gap std: 0.115 early, 0.148-0.157 mature.
#   PP >= 110 catches top 33% early vs top 18% mature — needs gating.
#   Decision+ is the most reliable early signal (split-half r=0.741 at 50 PA).
#
#   Rolling thresholds (p50=0.066, p75=0.083) are stable across seasons.
#   PLV distribution barely moves across stages.

_MATURE = StageThresholds(
    stage="mature",
    # Confidence tiers
    hitter_tier_a_pa=400,   hitter_tier_b_pa=250,   hitter_tier_c_pa=150,
    hitter_tier_labels=("Tier A", "Tier B", "Tier C"),
    pitcher_tier_a_pitches=1000, pitcher_tier_b_pitches=400, pitcher_tier_c_pitches=100,
    pitcher_tier_labels=("Tier A", "Tier B", "Tier C"),
    min_pa_for_boards=150,  min_pitches_for_boards=100,
    # Buy/regression
    buy_rank_gap_min=0.15,  buy_pp_floor=100.0,  buy_dec_gate=None,
    reg_rank_gap_max=-0.15, reg_xwoba_floor=0.350, reg_dec_gate=None,
    # Breakout/discipline/power
    breakout_pp_min=110.0,  breakout_dec_gate=None,
    discipline_dec_min=109.0, power_pow_min=107.0,
    # Rolling
    rolling_hot_dec=0.083, rolling_warm_dec=0.066,
    # PLV
    plv_strong=5.17, plv_elite=5.30, plv_median=5.01,
    # Labels
    stage_label="Mature Season", stage_color="green",
    stage_warning=None,
)

_MID = StageThresholds(
    stage="mid",
    # Confidence tiers — lower PA floor, different labels
    hitter_tier_a_pa=200,   hitter_tier_b_pa=100,   hitter_tier_c_pa=50,
    hitter_tier_labels=("Building", "Early Signal", "Limited"),
    pitcher_tier_a_pitches=400, pitcher_tier_b_pitches=200, pitcher_tier_c_pitches=75,
    pitcher_tier_labels=("Building", "Early Signal", "Limited"),
    min_pa_for_boards=50,  min_pitches_for_boards=75,
    # Buy/regression — slightly stricter rank_gap; no component gates yet
    buy_rank_gap_min=0.17,  buy_pp_floor=101.0,  buy_dec_gate=None,
    reg_rank_gap_max=-0.17, reg_xwoba_floor=0.350, reg_dec_gate=94.0,
    # Breakout — keep PP threshold; add modest Decision+ gate
    breakout_pp_min=110.0,  breakout_dec_gate=109.0,
    discipline_dec_min=109.0, power_pow_min=108.0,
    # Rolling — unchanged (stable across seasons)
    rolling_hot_dec=0.083, rolling_warm_dec=0.066,
    # PLV — unchanged
    plv_strong=5.17, plv_elite=5.30, plv_median=5.01,
    # Labels
    stage_label="Mid Season", stage_color="blue",
    stage_warning=(
        "Mid-season mode. Process+ and Power+ are building signal (100-200 PA). "
        "Decision+ is reliable. Use rolling trends to confirm any flag."
    ),
)

_EARLY = StageThresholds(
    stage="early",
    # Confidence tiers — small-sample labels
    hitter_tier_a_pa=80,    hitter_tier_b_pa=40,    hitter_tier_c_pa=0,
    hitter_tier_labels=("Signal", "Watch", "Too Early"),
    pitcher_tier_a_pitches=150, pitcher_tier_b_pitches=75, pitcher_tier_c_pitches=0,
    pitcher_tier_labels=("Signal", "Watch", "Too Early"),
    min_pa_for_boards=40,  min_pitches_for_boards=75,
    # Buy — stricter rank_gap to cut through noise; Decision+ gate required
    # Rationale: Process+ std is 53% wider early. rank_gap std=0.115.
    # 0.20 threshold = 1.74 std deviations (top ~4%), ensuring real signal.
    buy_rank_gap_min=0.20,  buy_pp_floor=102.0,  buy_dec_gate=109.0,
    # Regression — require Decision+ to be weak (not just Power+ noise)
    # Power+ has 47% wider std early; bad Power+ alone is not meaningful.
    reg_rank_gap_max=-0.20, reg_xwoba_floor=0.350, reg_dec_gate=97.0,
    # Breakout — must have BOTH PP elevated AND elite Decision+
    # PP >= 110 catches top 33% early-season (vs 18% mature). Need D+ gate.
    breakout_pp_min=110.0,  breakout_dec_gate=112.0,
    # Discipline — Decision+ is reliable at 50 PA (split-half r=0.741). Keep same.
    discipline_dec_min=109.0,
    # Power — raise bar because Power+ std is 47% wider early
    # 110 ≈ p75 of early-season distribution (vs p75 = 107 at full season)
    power_pow_min=110.0,
    # Rolling — unchanged (distribution is stable)
    rolling_hot_dec=0.083, rolling_warm_dec=0.066,
    # PLV — unchanged (most stable metric)
    plv_strong=5.17, plv_elite=5.30, plv_median=5.01,
    # Labels
    stage_label="Early Season", stage_color="orange",
    stage_warning=(
        "Early-season mode (< 150 PA median). Process+ and Power+ are noisy at "
        "small samples. Decision+ is the most reliable signal. "
        "Board flags require stronger evidence and use tighter thresholds."
    ),
)
