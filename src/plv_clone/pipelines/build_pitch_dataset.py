"""
Pipeline: Build the pitch-level feature dataset.

Orchestrates:
  1. Statcast ingestion (with manifest-based incremental updates)
  2. Cleaning (outcome normalisation, pitch key enforcement)
  3. Pitch feature engineering (movement, location, count)
  4. Context feature engineering (velocity delta, pitch-in-AB)
  5. Batter tendency features (expanding window, no leakage)
  6. Write to hive-partitioned Parquet under processed_dir/pitch_features/

Usage (via CLI or direct call):
    from plv_clone.pipelines.build_pitch_dataset import run
    run(start_date=date(2021, 4, 1), end_date=date(2023, 11, 1), config=cfg)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.data.clean_statcast import clean_statcast
from plv_clone.data.ingest_statcast import pull_statcast_range
from plv_clone.data.schemas import validate_schema, FEATURE_COLS_PLV
from plv_clone.features.batter_features import build_batter_features
from plv_clone.features.context_features import build_context_features
from plv_clone.features.pitch_features import build_pitch_features
from plv_clone.utils.io import write_parquet
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def _load_raw_from_cache(start_date: date, end_date: date, raw_dir: Path) -> pd.DataFrame:
    """Load raw data directly from year-partitioned parquet files (no network calls)."""
    years = range(start_date.year, end_date.year + 1)
    parts = []
    for yr in years:
        p = raw_dir / f"statcast_{yr}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "game_date" in df.columns:
                df["game_date"] = pd.to_datetime(df["game_date"])
                mask = (df["game_date"].dt.date >= start_date) & (df["game_date"].dt.date <= end_date)
                df = df[mask]
            parts.append(df)
            logger.info("Loaded %d rows from %s", len(df), p.name)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def run(
    start_date: date,
    end_date: date,
    config: PipelineConfig | None = None,
    force_refresh: bool = False,
    skip_pull: bool = False,
) -> Path:
    """Build the cleaned and feature-engineered pitch dataset.

    Args:
        start_date:    First game date to include.
        end_date:      Last game date to include (inclusive).
        config:        PipelineConfig instance (uses get_config() if None).
        force_refresh: Re-pull raw data even if already cached.
        skip_pull:     Load directly from cached parquet files without any network calls.

    Returns:
        Path to the written Parquet dataset directory.
    """
    cfg = config or get_config()
    logger.info(
        "build_pitch_dataset: %s to %s", start_date, end_date
    )

    # ── 1. Ingest ─────────────────────────────────────────────────────────
    if skip_pull:
        logger.info("skip_pull=True — loading from cached parquet files.")
        raw_df = _load_raw_from_cache(start_date, end_date, cfg.raw_data_dir)
    else:
        raw_df = pull_statcast_range(
            start_date=start_date,
            end_date=end_date,
            raw_dir=cfg.raw_data_dir,
            chunk_days=cfg.statcast_chunk_days,
            force_refresh=force_refresh,
        )
    if raw_df.empty:
        logger.warning("No data returned for %s to %s. Exiting.", start_date, end_date)
        return cfg.processed_dir / "pitch_features"

    logger.info("Ingested %d raw pitches.", len(raw_df))

    # ── 2. Clean ──────────────────────────────────────────────────────────
    clean_df = clean_statcast(raw_df)
    logger.info("Cleaned: %d pitches.", len(clean_df))

    # ── 3. Pitch features ─────────────────────────────────────────────────
    feat_df = build_pitch_features(clean_df)

    # ── 4. Context features ───────────────────────────────────────────────
    feat_df = build_context_features(feat_df)

    # ── 5. Batter features ────────────────────────────────────────────────
    feat_df = build_batter_features(feat_df)

    # ── 6. Add year partition column ──────────────────────────────────────
    if "game_date" in feat_df.columns:
        feat_df["year"] = pd.to_datetime(feat_df["game_date"]).dt.year
    else:
        feat_df["year"] = start_date.year

    # ── 7. Write ──────────────────────────────────────────────────────────
    out_dir = cfg.processed_dir / "pitch_features"
    write_parquet(
        feat_df,
        out_dir,
        partition_cols=["year"],
    )
    logger.info(
        "Wrote %d rows to %s (partitioned by year).", len(feat_df), out_dir
    )
    return out_dir
