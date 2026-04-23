"""
Pipeline: Train all PLV sub-models.

Sequence:
  1. Load feature data for training years.
  2. Build and save the count value table (training data only).
  3. Train SwingModel on all pitches.
  4. Train CalledStrikeModel on takes only.
  5. Train ContactModel on swings only.
  6. Train FoulModel on contacts only.
  7. Train BattedBallValueModel on in-play pitches only.
  8. Compute PLV scaling params from training population.
  9. Assemble and save PLVModel.
 10. Evaluate all sub-models on the validation set.

Usage:
    from plv_clone.pipelines.train_plv import run
    plv_model = run(config=cfg)
"""

from __future__ import annotations

import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.data.schemas import FEATURE_COLS_PLV, FEATURE_COLS_BBV
from plv_clone.features.run_value_features import (
    build_count_value_table,
    load_count_value_table,
)
from plv_clone.models.batted_ball_value_model import BattedBallValueModel
from plv_clone.models.called_strike_model import CalledStrikeModel
from plv_clone.models.contact_whiff_model import ContactModel
from plv_clone.models.evaluation import evaluate_classifier, evaluate_regression
from plv_clone.models.foul_in_play_model import FoulModel
from plv_clone.models.plv_model import PLVModel
from plv_clone.models.swing_take_model import SwingModel
from plv_clone.utils.io import read_parquet
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def run(config: PipelineConfig | None = None) -> PLVModel:
    """Train all PLV sub-models and return the assembled PLVModel.

    Args:
        config: PipelineConfig instance (uses get_config() if None).

    Returns:
        Trained and saved PLVModel.
    """
    cfg = config or get_config()

    # ── 1. Load feature data ───────────────────────────────────────────────
    logger.info("Loading training feature data …")
    train_df = _load_years(cfg.processed_dir / "pitch_features", cfg)
    if train_df.empty:
        raise RuntimeError(
            "No training data found. Run `plv build-features` first."
        )

    logger.info("Loading validation feature data …")
    val_df = _load_year_range(
        cfg.processed_dir / "pitch_features",
        cfg.val_start.year,
        cfg.val_end.year,
    )

    logger.info(
        "Train: %d pitches | Val: %d pitches", len(train_df), len(val_df)
    )

    # ── 2. Count value table ──────────────────────────────────────────────
    logger.info("Building count value table …")
    count_table = build_count_value_table(train_df, cfg.models_dir)

    # ── 3. Train sub-models ───────────────────────────────────────────────
    lgbm_kwargs = dict(
        lgbm_params={
            "n_estimators": cfg.lgbm_n_estimators,
            "learning_rate": cfg.lgbm_learning_rate,
            "num_leaves": cfg.lgbm_num_leaves,
        },
        early_stopping_rounds=cfg.lgbm_early_stopping,
        random_seed=cfg.random_seed,
    )

    # 3a. SwingModel — all pitches
    logger.info("Training SwingModel …")
    swing_model = SwingModel(**lgbm_kwargs)
    train_clean = _drop_unknown(train_df)
    val_clean = _drop_unknown(val_df)
    swing_model.fit(train_clean, train_clean["is_swing"], val_clean, val_clean["is_swing"])

    # 3b. CalledStrikeModel — takes only
    logger.info("Training CalledStrikeModel …")
    cs_model = CalledStrikeModel(**lgbm_kwargs)
    train_takes = train_clean[train_clean["is_take"].astype(bool)]
    val_takes = val_clean[val_clean["is_take"].astype(bool)]
    cs_model.fit(train_takes, train_takes["is_called_strike"], val_takes, val_takes["is_called_strike"])

    # 3c. ContactModel — swings only
    logger.info("Training ContactModel …")
    contact_model = ContactModel(**lgbm_kwargs)
    train_swings = train_clean[train_clean["is_swing"].astype(bool)]
    val_swings = val_clean[val_clean["is_swing"].astype(bool)]
    contact_model.fit(train_swings, train_swings["is_contact"], val_swings, val_swings["is_contact"])

    # 3d. FoulModel — contacts only
    logger.info("Training FoulModel …")
    foul_model = FoulModel(**lgbm_kwargs)
    train_contacts = train_clean[train_clean["is_contact"].astype(bool)]
    val_contacts = val_clean[val_clean["is_contact"].astype(bool)]
    foul_model.fit(train_contacts, train_contacts["is_foul"], val_contacts, val_contacts["is_foul"])

    # 3e. BattedBallValueModel — in-play pitches with non-null xwOBA
    logger.info("Training BattedBallValueModel …")
    bbv_model = BattedBallValueModel(**lgbm_kwargs)
    train_ip = train_clean[
        train_clean["is_in_play"].astype(bool)
        & train_clean["estimated_woba_using_speedangle"].notna()
    ]
    val_ip = val_clean[
        val_clean["is_in_play"].astype(bool)
        & val_clean["estimated_woba_using_speedangle"].notna()
    ]
    bbv_model.fit(
        train_ip, train_ip["estimated_woba_using_speedangle"],
        val_ip, val_ip["estimated_woba_using_speedangle"],
    )

    # ── 4. Assemble PLVModel ───────────────────────────────────────────────
    logger.info("Assembling PLVModel …")
    plv_model = PLVModel(
        swing_model=swing_model,
        cs_model=cs_model,
        contact_model=contact_model,
        foul_model=foul_model,
        bbv_model=bbv_model,
        count_table=count_table,
    )

    # ── 5. Fit scaling params ──────────────────────────────────────────────
    logger.info("Computing PLV scaling parameters …")
    plv_model.fit_scaling_params(
        train_clean,
        min_pitches=cfg.min_pitches_plv,
        target_avg=cfg.plv_league_avg,
    )

    # ── 6. Save ────────────────────────────────────────────────────────────
    plv_model.save(cfg.models_dir)

    # ── 7. Evaluate on validation set ─────────────────────────────────────
    logger.info("=== Validation-set evaluation ===")
    evaluate_classifier(val_clean["is_swing"], swing_model.predict_proba(val_clean), label="SwingModel")
    evaluate_classifier(val_takes["is_called_strike"], cs_model.predict_proba(val_takes), label="CalledStrikeModel")
    evaluate_classifier(val_swings["is_contact"], contact_model.predict_proba(val_swings), label="ContactModel")
    evaluate_classifier(val_contacts["is_foul"], foul_model.predict_proba(val_contacts), label="FoulModel")
    evaluate_regression(
        val_ip["estimated_woba_using_speedangle"],
        bbv_model.predict(val_ip),
        label="BattedBallValueModel",
    )

    logger.info("train_plv complete. PLVModel saved to %s", cfg.models_dir)
    return plv_model


# ── Data loading helpers ─────────────────────────────────────────────────────

def _load_years(features_dir, cfg: PipelineConfig) -> pd.DataFrame:
    """Load feature data for all training years."""
    import pandas as pd
    from datetime import date

    train_start_year = cfg.effective_train_start.year
    train_end_year = cfg.train_end.year
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
    """Drop pitches with resolved_outcome == 'unknown' before modelling."""
    if "resolved_outcome" in df.columns:
        n_before = len(df)
        df = df[df["resolved_outcome"] != "unknown"].copy()
        n_dropped = n_before - len(df)
        if n_dropped > 0:
            logger.debug("Dropped %d 'unknown' outcome rows before modelling.", n_dropped)
    return df
