"""
Pipeline: Score pitches with Process+ component values.

Produces two outputs for each year:
  1. Pitch-level parquet with discipline_value / contact_value / power_value
     (at data/processed/process_plus_scores/year=YYYY/)
  2. Hitter-season leaderboard with Process+, Discipline+, Contact+, Power+
     (at data/outputs/process_plus_leaderboard_YYYY.{parquet,csv})

Usage:
    from plv_clone.pipelines.score_process_plus import run
    pitch_df, hitter_df = run(year=2024, config=cfg)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.models.process_plus_model import ProcessPlusModel
from plv_clone.utils.io import read_parquet, write_parquet
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def run(
    year: int,
    config: PipelineConfig | None = None,
    output_format: str = "both",
    min_pa: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score pitches for *year* with Process+ components.

    Args:
        year:          Season year to score (e.g. 2024).
        config:        PipelineConfig instance (uses get_config() if None).
        output_format: 'parquet', 'csv', or 'both' for the hitter leaderboard.
        min_pa:        Minimum PA for qualification (default: config value).

    Returns:
        Tuple of (pitch_level_df, hitter_leaderboard_df).
    """
    cfg    = config or get_config()
    min_pa = min_pa if min_pa is not None else cfg.min_pa_process

    # ── Load ProcessPlusModel ──────────────────────────────────────────────
    logger.info("Loading ProcessPlusModel from %s …", cfg.models_dir)
    pp_model = ProcessPlusModel.load(cfg.models_dir)

    # ── Load feature data ──────────────────────────────────────────────────
    year_dir = cfg.processed_dir / "pitch_features" / f"year={year}"
    if not year_dir.exists():
        raise FileNotFoundError(
            f"No feature data found for year={year}. "
            f"Run `plv build-features` for that year first."
        )
    logger.info("Loading features for year=%d …", year)
    df = read_parquet(year_dir)

    # Drop unknown outcomes
    if "resolved_outcome" in df.columns:
        df = df[df["resolved_outcome"] != "unknown"].copy()

    logger.info("Loaded %d pitches for year=%d.", len(df), year)

    # ── Score pitches ──────────────────────────────────────────────────────
    logger.info("Scoring %d pitches for Process+ …", len(df))
    scored_df = pp_model.score_pitches(df)

    # ── Write pitch-level scores ───────────────────────────────────────────
    out_dir = cfg.processed_dir / "process_plus_scores" / f"year={year}"
    write_parquet(scored_df, out_dir)
    logger.info("Wrote Process+ pitch scores → %s (%d rows)", out_dir, len(scored_df))

    # ── Aggregate hitter leaderboard ───────────────────────────────────────
    logger.info("Aggregating hitter leaderboard (min_pa=%d) …", min_pa)
    hitter_df = pp_model.aggregate_hitters(scored_df, min_pa=min_pa)

    _log_leaderboard_summary(hitter_df, label=f"Process+ {year}")

    # ── Write hitter leaderboard ───────────────────────────────────────────
    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    base = cfg.outputs_dir / f"process_plus_leaderboard_{year}"
    _write_output(hitter_df, base, output_format)

    logger.info("Process+ leaderboard written to %s", cfg.outputs_dir)
    return scored_df, hitter_df


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_output(df: pd.DataFrame, base_path: Path, fmt: str) -> None:
    if fmt in ("parquet", "both"):
        df.to_parquet(str(base_path) + ".parquet", index=False)
    if fmt in ("csv", "both"):
        df.to_csv(str(base_path) + ".csv", index=False)


def _log_leaderboard_summary(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        logger.warning("[%s] Empty leaderboard.", label)
        return
    logger.info(
        "[%s] %d qualified hitters | Process+ range: %.1f – %.1f | mean: %.1f",
        label, len(df),
        df["process_plus"].min(),
        df["process_plus"].max(),
        df["process_plus"].mean(),
    )
    if len(df) >= 10:
        top5    = df.nlargest(5, "process_plus")[["batter_name", "pa", "process_plus"]] \
                  if "batter_name" in df.columns \
                  else df.nlargest(5, "process_plus")[["batter", "pa", "process_plus"]]
        bottom5 = df.nsmallest(5, "process_plus")[["batter_name", "pa", "process_plus"]] \
                  if "batter_name" in df.columns \
                  else df.nsmallest(5, "process_plus")[["batter", "pa", "process_plus"]]
        logger.info("Top 5:\n%s",    top5.to_string(index=False))
        logger.info("Bottom 5:\n%s", bottom5.to_string(index=False))
