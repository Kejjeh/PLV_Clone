"""
Pipeline: Build fantasy target boards from master leaderboard exports.

Generates six CSV files under data/outputs/:

  hitter_buy_targets_YYYY.csv       -- strong Process+, weak surface xwOBA
  hitter_breakout_flags_YYYY.csv    -- elite Process+, surface not yet caught up
  hitter_regression_flags_YYYY.csv  -- strong xwOBA, weak Process+
  hitter_discipline_targets_YYYY.csv-- top Decision+
  hitter_power_targets_YYYY.csv     -- top Power+
  pitcher_plv_targets_YYYY.csv      -- top PLV, rolling strength, result divergence

All boards include a `tag` column (reason for inclusion), `confidence`
(stage-appropriate label), and `season_stage` (early/mid/mature).

Thresholds are season-stage-aware. The core PLV and Process+ model scales
are unchanged — only workflow-layer heuristics adapt.
See docs/season_stage_thresholds.md for full calibration documentation.

Usage:
    from plv_clone.pipelines.build_target_boards import run
    boards = run(year=2024, config=cfg)
    boards = run(year=2026, config=cfg, stage="early")   # explicit override
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

from plv_clone.config import PipelineConfig, get_config
from plv_clone.utils.logging import get_logger
from plv_clone.utils.season_stage import (
    StageThresholds, get_thresholds, infer_stage,
)

logger = get_logger(__name__)

# Stable constants that don't vary by stage
_PP_ELITE    = 115.0   # Process+ top 10%
_DEC_ELITE   = 115.0   # Decision+ top 10%
_CON_STRONG  = 109.0   # Contact+ top 25%
_XWOBA_MEDIAN = 0.363  # xwOBA median (2023-2025)
_XWOBA_P75   = 0.400   # xwOBA top quartile


def run(
    year: int,
    config: PipelineConfig | None = None,
    stage: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Build all target boards for *year* and write CSVs.

    Parameters
    ----------
    year:   Season year.
    config: PipelineConfig (uses default if None).
    stage:  'early' | 'mid' | 'mature'. If None, auto-detected from median PA.

    Returns dict mapping board name -> DataFrame. Each DataFrame includes
    a `season_stage` column recording which thresholds were applied.
    """
    cfg = config or get_config()

    # ── Load source data ──────────────────────────────────────────────────
    hitter_path  = cfg.outputs_dir / f"master_hitter_{year}.csv"
    pitcher_path = cfg.outputs_dir / f"master_pitcher_{year}.csv"
    roll_h_path  = cfg.outputs_dir / f"process_plus_rolling_{year}.csv"
    roll_p_path  = cfg.outputs_dir / f"plv_rolling_{year}.csv"

    if not hitter_path.exists():
        raise FileNotFoundError(
            f"master_hitter_{year}.csv not found. Run `plv build-exports {year}` first."
        )

    hitters  = pd.read_csv(hitter_path)
    pitchers = pd.read_csv(pitcher_path) if pitcher_path.exists() else pd.DataFrame()

    rolling_h = (
        pd.read_csv(roll_h_path, parse_dates=["date"])
        if roll_h_path.exists() else pd.DataFrame()
    )
    rolling_p = (
        pd.read_csv(roll_p_path, parse_dates=["date"])
        if roll_p_path.exists() else pd.DataFrame()
    )

    # ── Determine season stage ────────────────────────────────────────────
    detected_stage = infer_stage(
        hitters=hitters if not hitters.empty else None,
        pitchers=pitchers if not pitchers.empty else None,
    )
    active_stage = stage if stage in ("early", "mid", "mature") else detected_stage
    t = get_thresholds(active_stage)
    logger.info(
        "Season stage: %s (detected=%s, active=%s)",
        t.stage_label, detected_stage, active_stage,
    )

    # ── Enrich hitters ────────────────────────────────────────────────────
    hitters = _add_confidence(
        hitters, pa_col="pa",
        tier_a=t.hitter_tier_a_pa, tier_b=t.hitter_tier_b_pa,
        tier_c=t.hitter_tier_c_pa, labels=t.hitter_tier_labels,
    )
    hitters = _add_rank_gap(hitters)
    hitters["season_stage"] = active_stage
    if not rolling_h.empty:
        hitters = _add_rolling_context_hitter(hitters, rolling_h, t)

    if not pitchers.empty:
        pitchers = _add_confidence(
            pitchers, pa_col="pitches",
            tier_a=t.pitcher_tier_a_pitches, tier_b=t.pitcher_tier_b_pitches,
            tier_c=t.pitcher_tier_c_pitches, labels=t.pitcher_tier_labels,
        )
        pitchers["season_stage"] = active_stage
    if not rolling_p.empty and not pitchers.empty:
        pitchers = _add_rolling_context_pitcher(pitchers, rolling_p, t)

    # ── Build each board ──────────────────────────────────────────────────
    boards: dict[str, pd.DataFrame] = {}

    boards["hitter_buy_targets"]        = _buy_targets(hitters, t)
    boards["hitter_breakout_flags"]     = _breakout_flags(hitters, t)
    boards["hitter_regression_flags"]   = _regression_flags(hitters, t)
    boards["hitter_discipline_targets"] = _discipline_targets(hitters, t)
    boards["hitter_power_targets"]      = _power_targets(hitters, t)
    if not pitchers.empty:
        boards["pitcher_plv_targets"]   = _pitcher_plv_targets(pitchers, t)

    # ── Write CSVs ────────────────────────────────────────────────────────
    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    for name, df in boards.items():
        path = cfg.outputs_dir / f"{name}_{year}.csv"
        df.to_csv(path, index=False)
        logger.info("Wrote %s: %d rows [stage=%s] -> %s", name, len(df), active_stage, path.name)

    return boards


# ── Board builders ────────────────────────────────────────────────────────────

def _buy_targets(h: pd.DataFrame, t: StageThresholds) -> pd.DataFrame:
    """Process+ rank materially exceeds xwOBA rank — process ahead of results."""
    mask = (
        h["rank_gap"].gt(t.buy_rank_gap_min) &
        h["process_plus"].ge(t.buy_pp_floor) &
        h["pa"].ge(t.min_pa_for_boards)
    )
    if t.buy_dec_gate is not None:
        mask &= h["decision_plus"].ge(t.buy_dec_gate)
    df = h[mask].copy()
    df["tag"] = df.apply(lambda r: _buy_tag(r, t), axis=1)
    cols = _hitter_display_cols(df, extras=["rank_gap", "rolling_trend", "xwoba_vs_expected"])
    return df[cols].sort_values("rank_gap", ascending=False).reset_index(drop=True)


def _breakout_flags(h: pd.DataFrame, t: StageThresholds) -> pd.DataFrame:
    """Process+ elevated AND xwOBA not yet in top quartile — emerging elite."""
    mask = (
        h["process_plus"].ge(t.breakout_pp_min) &
        h["xwoba_actual"].lt(_XWOBA_P75) &
        h["pa"].ge(t.min_pa_for_boards)
    )
    if t.breakout_dec_gate is not None:
        mask &= h["decision_plus"].ge(t.breakout_dec_gate)
    df = h[mask].copy()
    df["tag"] = df.apply(lambda r: _breakout_tag(r, t), axis=1)
    cols = _hitter_display_cols(df, extras=["rolling_decision_30d", "rolling_trend"])
    return df[cols].sort_values("process_plus", ascending=False).reset_index(drop=True)


def _regression_flags(h: pd.DataFrame, t: StageThresholds) -> pd.DataFrame:
    """xwOBA rank materially exceeds Process+ rank — results ahead of process."""
    mask = (
        h["rank_gap"].lt(t.reg_rank_gap_max) &
        h["xwoba_actual"].ge(t.reg_xwoba_floor) &
        h["pa"].ge(t.min_pa_for_boards)
    )
    if t.reg_dec_gate is not None:
        mask &= h["decision_plus"].lt(t.reg_dec_gate)
    df = h[mask].copy()
    df["tag"] = df.apply(lambda r: _regression_tag(r, t), axis=1)
    cols = _hitter_display_cols(df, extras=["rank_gap", "rolling_trend", "xwoba_vs_expected"])
    return df[cols].sort_values("rank_gap").reset_index(drop=True)


def _discipline_targets(h: pd.DataFrame, t: StageThresholds) -> pd.DataFrame:
    """Decision+ in top 25% — most stable early-season metric."""
    mask = (
        h["decision_plus"].ge(t.discipline_dec_min) &
        h["pa"].ge(t.min_pa_for_boards)
    )
    df = h[mask].copy()
    df["tag"] = df.apply(lambda r: _discipline_tag(r, t), axis=1)
    cols = _hitter_display_cols(df, extras=["rolling_decision_30d"])
    return df[cols].sort_values("decision_plus", ascending=False).reset_index(drop=True)


def _power_targets(h: pd.DataFrame, t: StageThresholds) -> pd.DataFrame:
    """Power+ above stage threshold — xwOBA above pitch expectation."""
    mask = (
        h["power_plus"].ge(t.power_pow_min) &
        h["pa"].ge(t.min_pa_for_boards)
    )
    df = h[mask].copy()
    df["tag"] = df.apply(lambda r: _power_tag(r, t), axis=1)
    cols = _hitter_display_cols(df, extras=["xwoba_actual", "xwoba_vs_expected"])
    return df[cols].sort_values("power_plus", ascending=False).reset_index(drop=True)


def _pitcher_plv_targets(p: pd.DataFrame, t: StageThresholds) -> pd.DataFrame:
    """PLV above stage threshold, or strong rolling + result divergence."""
    mask = (
        p["plv"].ge(t.plv_strong) &
        p["pitches"].ge(t.min_pitches_for_boards)
    )
    elite = p[mask].copy()
    elite["tag"] = elite.apply(lambda r: _plv_tag(r, t), axis=1)

    if "whiff_pct" in p.columns and "xwoba_model" in p.columns:
        diverge_mask = (
            p["plv"].ge(t.plv_median) &
            p["plv"].lt(t.plv_strong) &
            p["whiff_pct"].ge(0.36) &
            p["xwoba_model"].le(0.350) &
            p["pitches"].ge(t.min_pitches_for_boards)
        )
        diverge = p[diverge_mask].copy()
        diverge["tag"] = "PLV-result divergence: whiff rate elite, results may catch up"
        elite = pd.concat([elite, diverge], ignore_index=True).drop_duplicates(subset=["pitcher"])

    cols = _pitcher_display_cols(elite)
    return elite[cols].sort_values("plv", ascending=False).reset_index(drop=True)


# ── Tag generators ────────────────────────────────────────────────────────────

def _buy_tag(row: pd.Series, t: StageThresholds) -> str:
    parts = []
    pp = row.get("process_plus", 0)
    if pp >= _PP_ELITE:
        parts.append("Process+ elite")
    elif pp >= 108:
        parts.append("Process+ strong")
    else:
        parts.append("Process+ above avg")
    gap = row.get("rank_gap", 0)
    if gap >= 0.30:
        parts.append("large rank divergence (process >> results)")
    else:
        parts.append("process ahead of results")
    if row.get("decision_plus", 0) >= t.discipline_dec_min:
        parts.append("disciplined")
    if row.get("power_plus", 0) >= t.power_pow_min:
        parts.append("quality contact")
    if row.get("rolling_trend", "") == "hot":
        parts.append("rolling hot")
    if t.stage != "mature":
        parts.append(f"[{t.stage_label}]")
    return "; ".join(parts)


def _breakout_tag(row: pd.Series, t: StageThresholds) -> str:
    parts = []
    if row.get("process_plus", 0) >= _PP_ELITE:
        parts.append("Process+ elite")
    else:
        parts.append("Process+ strong")
    if row.get("decision_plus", 0) >= _DEC_ELITE:
        parts.append("elite discipline")
    elif row.get("decision_plus", 0) >= t.discipline_dec_min:
        parts.append("strong discipline")
    if row.get("contact_plus", 0) >= _CON_STRONG:
        parts.append("contact quality")
    trend = row.get("rolling_trend", "")
    if trend == "hot":
        parts.append("trending up")
    parts.append("surface stats not yet elite")
    if t.stage != "mature":
        parts.append(f"[{t.stage_label}]")
    return "; ".join(parts)


def _regression_tag(row: pd.Series, t: StageThresholds) -> str:
    xwoba = row.get("xwoba_actual", 0)
    if xwoba >= _XWOBA_P75:
        parts = ["surface xwOBA elite (top 25%)"]
    elif xwoba >= _XWOBA_MEDIAN:
        parts = ["surface xwOBA above avg"]
    else:
        parts = ["surface xwOBA OK"]
    gap = row.get("rank_gap", 0)
    if gap <= -0.35:
        parts.append("large rank divergence (results >> process)")
    else:
        parts.append("results ahead of process")
    if row.get("decision_plus", 0) < 94:
        parts.append("chasing (low Decision+)")
    if row.get("power_plus", 0) < 94:
        parts.append("contact below pitch expectation")
    if row.get("process_plus", 0) < 90:
        parts.append("Process+ very weak — high regression risk")
    else:
        parts.append("Process+ below average")
    return "; ".join(parts)


def _discipline_tag(row: pd.Series, t: StageThresholds) -> str:
    parts = []
    if row.get("decision_plus", 0) >= _DEC_ELITE:
        parts.append("Decision+ elite (top 10%)")
    else:
        parts.append("Decision+ strong (top 25%)")
    if row.get("swing_pct", 1) < 0.45:
        parts.append("selective swinger")
    if row.get("chase_pct", 1) < 0.24:
        parts.append("low chase rate")
    if row.get("process_plus", 0) >= 108:
        parts.append("Process+ strong")
    return "; ".join(parts)


def _power_tag(row: pd.Series, t: StageThresholds) -> str:
    parts = []
    if row.get("power_plus", 0) >= _PP_ELITE:
        parts.append("Power+ elite (top 10%)")
    else:
        parts.append("Power+ strong (top 25%)")
    if row.get("xwoba_vs_expected", 0) > 0.030:
        parts.append("xwOBA above model expectation")
    if row.get("process_plus", 0) >= 108:
        parts.append("Process+ also strong")
    elif row.get("process_plus", 0) < 96:
        parts.append("Process+ weak — power may not be sustainable")
    return "; ".join(parts)


def _plv_tag(row: pd.Series, t: StageThresholds) -> str:
    parts = []
    if row.get("plv", 0) >= t.plv_elite:
        parts.append("PLV elite (top 10%)")
    else:
        parts.append("PLV strong (top 25%)")
    if row.get("whiff_pct", 0) >= 0.39:
        parts.append("elite whiff rate")
    if row.get("rolling_plv_30d") is not None:
        rp = row.get("rolling_plv_30d", 0)
        if isinstance(rp, float) and rp >= t.plv_strong:
            parts.append("rolling also strong")
    if row.get("rolling_trend_pitcher", "") == "hot":
        parts.append("recent form improving")
    return "; ".join(parts)


# ── Enrichment helpers ────────────────────────────────────────────────────────

def _add_rank_gap(h: pd.DataFrame) -> pd.DataFrame:
    """Add pp_rank, xwoba_rank, and rank_gap columns.

    rank_gap = Process+ percentile rank - xwOBA percentile rank.
    Positive: process ahead of results (buy signal).
    Negative: results ahead of process (regression risk).
    """
    df = h.copy()
    if "process_plus" in df.columns and "xwoba_actual" in df.columns:
        df["pp_rank"]     = df["process_plus"].rank(pct=True)
        df["xwoba_rank"]  = df["xwoba_actual"].rank(pct=True)
        df["rank_gap"]    = (df["pp_rank"] - df["xwoba_rank"]).round(3)
    return df


def _add_confidence(
    df: pd.DataFrame,
    pa_col: str = "pa",
    tier_a: int = 400,
    tier_b: int = 250,
    tier_c: int = 0,
    labels: tuple = ("Tier A", "Tier B", "Tier C"),
) -> pd.DataFrame:
    df = df.copy()
    conditions = [
        df[pa_col] >= tier_a,
        df[pa_col] >= tier_b,
        df[pa_col] >= tier_c,
    ]
    choices = list(labels)
    df["confidence"] = np.select(conditions, choices, default=labels[2])
    return df


def _add_rolling_context_hitter(
    hitters: pd.DataFrame,
    rolling: pd.DataFrame,
    t: StageThresholds,
) -> pd.DataFrame:
    """Add latest 30-day rolling decision value and trend label per hitter."""
    if rolling.empty or "decision_value_mean" not in rolling.columns:
        return hitters

    rolling = rolling.sort_values("date")
    latest  = rolling.groupby("batter").last().reset_index()[
        ["batter", "decision_value_mean", "contact_value_mean", "power_value_mean", "pa"]
    ].rename(columns={
        "decision_value_mean": "rolling_decision_30d",
        "contact_value_mean":  "rolling_contact_30d",
        "power_value_mean":    "rolling_power_30d",
        "pa":                  "rolling_pa_30d",
    })

    # Trend: compare latest vs second-to-last window
    prior = rolling.groupby("batter").nth(-2).reset_index()[
        ["batter", "decision_value_mean"]
    ].rename(columns={"decision_value_mean": "_prior_dec"})

    trend = latest.merge(prior, on="batter", how="left")
    trend["rolling_trend"] = np.where(
        trend["rolling_decision_30d"] >= t.rolling_hot_dec, "hot",
        np.where(
            trend["rolling_decision_30d"] >= t.rolling_warm_dec, "warm",
            np.where(
                trend["rolling_decision_30d"].notna() &
                trend["_prior_dec"].notna() &
                (trend["rolling_decision_30d"] > trend["_prior_dec"]),
                "improving",
                "cold",
            )
        )
    )
    trend = trend.drop(columns=["_prior_dec"])

    return hitters.merge(trend, on="batter", how="left")


def _add_rolling_context_pitcher(
    pitchers: pd.DataFrame,
    rolling: pd.DataFrame,
    t: StageThresholds,
) -> pd.DataFrame:
    """Add latest 30-day rolling PLV per pitcher."""
    if rolling.empty or "plv" not in rolling.columns:
        return pitchers

    latest = (
        rolling.sort_values("date")
        .groupby("pitcher")
        .last()
        .reset_index()[["pitcher", "plv", "pitches"]]
        .rename(columns={"plv": "rolling_plv_30d", "pitches": "rolling_pitches_30d"})
    )
    prior = (
        rolling.sort_values("date")
        .groupby("pitcher")
        .nth(-2)
        .reset_index()[["pitcher", "plv"]]
        .rename(columns={"plv": "_prior_plv"})
    )
    trend = latest.merge(prior, on="pitcher", how="left")
    trend["rolling_trend_pitcher"] = np.where(
        trend["rolling_plv_30d"] >= t.plv_strong, "hot",
        np.where(
            trend["rolling_plv_30d"].notna() &
            trend["_prior_plv"].notna() &
            (trend["rolling_plv_30d"] > trend["_prior_plv"]),
            "improving",
            "flat",
        )
    )
    trend = trend.drop(columns=["_prior_plv"])
    return pitchers.merge(trend, on="pitcher", how="left")


# ── Column selectors ──────────────────────────────────────────────────────────

_BASE_HITTER_COLS = [
    "batter_name", "batter", "pa", "confidence",
    "primary_position", "fantasy_positions_display",
    "process_plus", "decision_plus", "contact_plus", "power_plus",
    "swing_pct", "chase_pct", "xwoba_actual",
    "tag",
]

_BASE_PITCHER_COLS = [
    "player_name", "pitcher", "pitches", "confidence",
    "plv", "plv_pctile", "swing_pct", "whiff_pct", "cs_pct", "xwoba_model",
    "tag",
]


def _hitter_display_cols(df: pd.DataFrame, extras: list[str] | None = None) -> list[str]:
    base = [c for c in _BASE_HITTER_COLS if c in df.columns]
    for col in (extras or []):
        if col in df.columns and col not in base:
            # Insert rolling cols before tag
            tag_idx = base.index("tag") if "tag" in base else len(base)
            base.insert(tag_idx, col)
    return base


def _pitcher_display_cols(df: pd.DataFrame) -> list[str]:
    cols = [c for c in _BASE_PITCHER_COLS if c in df.columns]
    for extra in ("rolling_plv_30d", "rolling_pitches_30d", "rolling_trend_pitcher"):
        if extra in df.columns and extra not in cols:
            tag_idx = cols.index("tag") if "tag" in cols else len(cols)
            cols.insert(tag_idx, extra)
    return cols
