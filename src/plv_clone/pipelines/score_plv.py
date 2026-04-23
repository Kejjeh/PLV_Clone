"""
Pipeline: Score pitches with the trained PLVModel.

Usage:
    from plv_clone.pipelines.score_plv import run
    scored_df = run(year=2024, config=cfg)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.models.plv_model import PLVModel
from plv_clone.utils.io import read_parquet, write_parquet
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def run(
    year: int,
    config: PipelineConfig | None = None,
) -> pd.DataFrame:
    """Score all pitches for *year* using the trained PLVModel.

    Args:
        year:   Season year to score (e.g. 2025).
        config: PipelineConfig instance (uses get_config() if None).

    Returns:
        Pitch-level DataFrame with PLV columns.
    """
    cfg = config or get_config()

    # ── Load model ────────────────────────────────────────────────────────
    logger.info("Loading PLVModel from %s …", cfg.models_dir)
    plv_model = PLVModel.load(cfg.models_dir)

    # ── Load feature data ─────────────────────────────────────────────────
    year_dir = cfg.processed_dir / "pitch_features" / f"year={year}"
    if not year_dir.exists():
        raise FileNotFoundError(
            f"No feature data found for year={year}. "
            f"Run `plv build-features` for that year first."
        )
    logger.info("Loading features for year=%d …", year)
    df = read_parquet(year_dir)
    logger.info("Loaded %d pitches for year=%d.", len(df), year)

    # Drop unknown outcomes before scoring
    if "resolved_outcome" in df.columns:
        df = df[df["resolved_outcome"] != "unknown"].copy()

    # ── Score ─────────────────────────────────────────────────────────────
    logger.info("Scoring %d pitches …", len(df))
    scored_df = plv_model.score_pitches(df)

    # ── Write pitch-level scores ──────────────────────────────────────────
    out_dir = cfg.processed_dir / "plv_scores" / f"year={year}"
    write_parquet(scored_df, out_dir)
    logger.info("Wrote PLV scores → %s (%d rows)", out_dir, len(scored_df))

    return scored_df
