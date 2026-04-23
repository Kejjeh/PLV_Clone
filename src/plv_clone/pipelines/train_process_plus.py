"""
Pipeline: Fit Process+ scaling parameters.

No new LightGBM models are trained here. The five PLV sub-models must already
be trained and saved. This pipeline:

  1. Loads the trained PLVModel.
  2. Loads training-set features.
  3. Scores training pitches with per-pitch component values.
  4. Fits scaling parameters from the qualified training-population distribution.
  5. Saves process_plus_scaling_params.json.

Usage:
    from plv_clone.pipelines.train_process_plus import run
    pp_model = run(config=cfg)
"""

from __future__ import annotations

import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.models.process_plus_model import ProcessPlusModel
from plv_clone.utils.io import read_parquet
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def run(config: PipelineConfig | None = None) -> ProcessPlusModel:
    """Fit Process+ scaling params and return the assembled ProcessPlusModel.

    Args:
        config: PipelineConfig instance (uses get_config() if None).

    Returns:
        ProcessPlusModel with scaling params saved to models_dir.
    """
    cfg = config or get_config()

    # ── 1. Load PLVModel ────────────────────────────────────────────────────
    logger.info("Loading trained PLVModel from %s …", cfg.models_dir)
    from plv_clone.models.plv_model import PLVModel
    plv_model = PLVModel.load(cfg.models_dir)

    # ── 2. Load training feature data ───────────────────────────────────────
    logger.info("Loading training feature data …")
    train_df = _load_years(cfg.processed_dir / "pitch_features", cfg)
    if train_df.empty:
        raise RuntimeError(
            "No training feature data found. "
            "Run `plv build-features` for training years first."
        )

    train_df = _drop_unknown(train_df)
    logger.info("Training data: %d pitches", len(train_df))

    # ── 3. Build ProcessPlusModel and fit scaling params ─────────────────────
    pp_model = ProcessPlusModel(plv_model=plv_model)
    pp_model.fit_scaling_params(
        train_df,
        min_pa=cfg.min_pa_process,
        center=cfg.plus_metric_center,
        std_scale=cfg.plus_metric_std_scale,
    )

    # ── 4. Save ─────────────────────────────────────────────────────────────
    pp_model.save(cfg.models_dir)

    logger.info("train_process_plus complete. Scaling params saved to %s", cfg.models_dir)
    return pp_model


# ── Data loading helpers (mirrors train_plv.py) ─────────────────────────────

def _load_years(features_dir, cfg: PipelineConfig) -> pd.DataFrame:
    train_start_year = cfg.effective_train_start.year
    train_end_year   = cfg.train_end.year
    return _load_year_range(features_dir, train_start_year, train_end_year)


def _load_year_range(features_dir, start_year: int, end_year: int) -> pd.DataFrame:
    from pathlib import Path
    features_dir = Path(features_dir)
    frames = []
    for year in range(start_year, end_year + 1):
        year_dir = features_dir / f"year={year}"
        if year_dir.exists():
            try:
                df = read_parquet(year_dir)
                frames.append(df)
                logger.debug("  Loaded year=%d: %d rows", year, len(df))
            except Exception as e:
                logger.warning("  Could not load year=%d: %s", year, e)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _drop_unknown(df: pd.DataFrame) -> pd.DataFrame:
    if "resolved_outcome" in df.columns:
        n_before = len(df)
        df = df[df["resolved_outcome"] != "unknown"].copy()
        n_dropped = n_before - len(df)
        if n_dropped > 0:
            logger.debug("Dropped %d 'unknown' outcome rows.", n_dropped)
    return df
