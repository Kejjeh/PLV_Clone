"""
Central configuration for the PLV Clone pipeline.

All pipeline modules import `get_config()` and never read environment
variables directly. Settings can be overridden via a .env file or by
setting PLV_* environment variables.
"""

from __future__ import annotations

import functools
from datetime import date
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PLV_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Data directories ─────────────────────────────────────────────────
    raw_data_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    models_dir: Path = Path("data/models")
    outputs_dir: Path = Path("data/outputs")

    # ── Time splits ──────────────────────────────────────────────────────
    train_start: date = date(2021, 4, 1)
    train_end: date = date(2023, 11, 1)
    val_start: date = date(2024, 3, 20)
    val_end: date = date(2024, 10, 31)
    test_start: date = date(2025, 3, 20)
    test_end: date = date(2025, 11, 1)

    # Set to True to extend training back to 2020 (COVID-shortened season)
    include_2020: bool = False

    # ── Qualification thresholds ─────────────────────────────────────────
    min_pitches_plv: int = 100
    min_pa_process: int = 150

    # ── LightGBM hyperparameters ─────────────────────────────────────────
    lgbm_n_estimators: int = 800
    lgbm_learning_rate: float = 0.05
    lgbm_num_leaves: int = 63
    lgbm_early_stopping: int = 50
    random_seed: int = 42

    # ── Scaling targets ──────────────────────────────────────────────────
    plv_league_avg: float = 5.0
    plus_metric_center: float = 100.0
    plus_metric_std_scale: float = 10.0

    # ── Ingestion ────────────────────────────────────────────────────────
    statcast_chunk_days: int = 7

    @field_validator("raw_data_dir", "processed_dir", "models_dir", "outputs_dir", mode="before")
    @classmethod
    def _make_path(cls, v: str | Path) -> Path:
        return Path(v)

    @property
    def effective_train_start(self) -> date:
        """Returns train_start, or 2020-07-23 if include_2020 is True."""
        if self.include_2020:
            return date(2020, 7, 23)
        return self.train_start


@functools.lru_cache(maxsize=1)
def get_config() -> PipelineConfig:
    """Return the singleton PipelineConfig instance."""
    return PipelineConfig()
