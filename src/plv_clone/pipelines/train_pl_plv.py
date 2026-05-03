"""
Pipeline: Fit PLPlvModel scaling parameters from a reference season.

Method sweep (best r wins):
  1. plv_components -- OLS on 7 model-probability features from plv_scores (best ~0.85)
  2. plv_raw        -- single plv_raw feature from plv_scores (~0.50)
  3. delta_run_exp  -- raw Statcast run-expectancy change from pitch_features (~0.33)
  4. xwoba_blend    -- delta_run_exp with xwOBA substituted for BIP (~0.35)

plv_components is tried first because it achieves the best out-of-sample correlation
with PL's published PLV by combining our LightGBM model probability outputs via OLS.
It requires plv_scores/ parquet (not just pitch_features/).

Recommended training year: 2025 (full season, 518 reference pitchers).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from scipy.stats import pearsonr

from plv_clone.config import PipelineConfig, get_config
from plv_clone.models.pl_plv_model import (
    COMPONENT_FEATS,
    PLPlvModel,
    load_and_clean_reference,
)
from plv_clone.utils.io import read_parquet
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_REF_DIR = Path("data/reference/pitcher_list")
_XWOBA_SCALES = [0.28, 0.30, 0.32, 0.34]
_MIN_R_THRESHOLD = 0.92

_PITCH_COLS = [
    "pitcher",
    "player_name",
    "pitch_type",
    "delta_run_exp",
    "is_in_play",
    "estimated_woba_using_speedangle",
]
_PLV_SCORE_COLS = [
    "pitcher",
    "player_name",
    "pitch_type",
    "plv_raw",
]
_COMPONENT_COLS = ["pitcher", "player_name", "pitch_type"] + COMPONENT_FEATS


def run(
    train_year: int = 2025,
    config: PipelineConfig | None = None,
) -> PLPlvModel:
    """Fit and save PLPlvModel scaling parameters.

    Args:
        train_year: Season year whose reference CSV is used to fit OLS transforms.
        config:     PipelineConfig (uses get_config() if None).

    Returns:
        Fitted PLPlvModel with scaling_params populated and saved to models_dir.
    """
    cfg = config or get_config()

    ref_path = _REF_DIR / f"pl_plv_{train_year}.csv"
    if not ref_path.exists():
        raise FileNotFoundError(
            f"Reference CSV not found: {ref_path}\n"
            f"Expected Pitcher List data at data/reference/pitcher_list/pl_plv_{train_year}.csv"
        )

    pitch_dir = cfg.processed_dir / "pitch_features" / f"year={train_year}"
    if not pitch_dir.exists():
        raise FileNotFoundError(
            f"Pitch features not found for year={train_year}.\n"
            "Run `plv build-features` to generate them."
        )

    logger.info("Loading reference: %s", ref_path.name)
    ref_df = load_and_clean_reference(ref_path)
    logger.info("  %d reference pitchers.", len(ref_df))

    best_model: PLPlvModel | None = None
    best_r: float = -1.0

    # -- Method 1: plv_components from plv_scores (best quality) --------------
    scores_dir = cfg.processed_dir / "plv_scores" / f"year={train_year}"
    if scores_dir.exists():
        logger.info("Loading plv_scores for year=%d (plv_components method) ...", train_year)
        comp_df = read_parquet(scores_dir, columns=_COMPONENT_COLS)
        logger.info("  %d pitches loaded.", len(comp_df))
        candidate = PLPlvModel()
        r = candidate.fit_scaling(comp_df, ref_df, rv_method="plv_components")
        logger.info("plv_components method: r(PLV)=%.4f", r)
        if r > best_r:
            best_r = r
            best_model = candidate
    else:
        logger.info("plv_scores not found for year=%d -- skipping plv_components.", train_year)

    # -- Method 2: plv_raw from plv_scores ------------------------------------
    if scores_dir.exists() and best_r < _MIN_R_THRESHOLD:
        logger.info("r=%.4f below threshold, trying plv_raw ...", best_r)
        plv_df = read_parquet(scores_dir, columns=_PLV_SCORE_COLS)
        candidate = PLPlvModel()
        r = candidate.fit_scaling(plv_df, ref_df, rv_method="plv_raw")
        logger.info("plv_raw method: r(PLV)=%.4f", r)
        if r > best_r:
            best_r = r
            best_model = candidate
    elif not scores_dir.exists():
        logger.info("plv_scores not found for year=%d -- skipping plv_raw method.", train_year)

    # -- Method 3: delta_run_exp from pitch_features ---------------------------
    logger.info("Loading pitch features for year=%d ...", train_year)
    pitch_df = read_parquet(pitch_dir, columns=_PITCH_COLS)
    logger.info("  %d pitches loaded.", len(pitch_df))

    if best_r < _MIN_R_THRESHOLD:
        candidate = PLPlvModel()
        r = candidate.fit_scaling(pitch_df, ref_df, rv_method="delta_run_exp")
        logger.info("delta_run_exp method: r(PLV)=%.4f", r)
        if r > best_r:
            best_r = r
            best_model = candidate

    # -- Method 4: xwOBA blend (only if simple delta_run_exp is best and below threshold) --
    best_method = best_model.scaling_params.get("rv_method", "delta_run_exp") if best_model else "delta_run_exp"
    if best_r < _MIN_R_THRESHOLD and best_method not in ("plv_components", "plv_raw"):
        logger.info("Best r=%.4f < %.2f -- sweeping xwOBA blend ...", best_r, _MIN_R_THRESHOLD)
        for scale in _XWOBA_SCALES:
            candidate = PLPlvModel()
            r = candidate.fit_scaling(
                pitch_df, ref_df, rv_method="xwoba_blend", xwoba_scale=scale
            )
            logger.info("  xwoba_scale=%.2f -> r(PLV)=%.4f", scale, r)
            if r > best_r:
                best_r = r
                best_model = candidate
    else:
        logger.info("r(PLV)=%.4f meets threshold -- skipping xwOBA blend.", best_r)

    model = best_model  # type: ignore[assignment]
    rv_method = model.scaling_params.get("rv_method", "delta_run_exp")
    logger.info("Selected method: %s (r=%.4f)", rv_method, best_r)

    # -- Fit report -----------------------------------------------------------
    if rv_method == "plv_components" and scores_dir.exists():
        src_df = read_parquet(scores_dir, columns=_COMPONENT_COLS)
    elif rv_method in ("plv_raw", "plv_components") and scores_dir.exists():
        src_df = read_parquet(scores_dir, columns=_PLV_SCORE_COLS)
    else:
        src_df = pitch_df

    _print_fit_report(model, src_df, ref_df, train_year)

    model.save(cfg.models_dir)
    logger.info("PLPlvModel saved to %s/pl_plv_scaling.json", cfg.models_dir)
    return model


# -- Internal helpers ---------------------------------------------------------

def _print_fit_report(
    model: PLPlvModel,
    pitch_df: pd.DataFrame,
    ref_df: pd.DataFrame,
    year: int,
) -> None:
    scored = model.score_pitches(pitch_df)
    agg = model.aggregate(scored, min_pitches=1)

    ref_clean = ref_df.rename(columns={"MLBAMID": "pitcher"}).copy()
    ref_clean["pitcher"] = ref_clean["pitcher"].astype(int)
    merged = agg.merge(ref_clean[["pitcher", "PLV", "PLA"]], on="pitcher", how="inner")

    if merged.empty:
        logger.warning("No matched pitchers for fit report.")
        return

    r_plv, _ = pearsonr(merged["pl_plv"], merged["PLV"])
    mae_plv = (merged["pl_plv"] - merged["PLV"]).abs().mean()
    r_pla, _ = pearsonr(merged["pl_pla"], merged["PLA"])
    mae_pla = (merged["pl_pla"] - merged["PLA"]).abs().mean()

    rv_method = model.scaling_params.get("rv_method", "delta_run_exp")
    print(f"\n-- PLPlvModel Fit Report ({year}) --")
    print(f"  rv_method   : {rv_method}")
    if rv_method == "xwoba_blend":
        print(f"  xwoba_scale : {model.scaling_params.get('xwoba_scale', '?'):.2f}")
    print(f"  N matched   : {len(merged)}")
    print(f"  r(PLV)      : {r_plv:.4f}   MAE(PLV): {mae_plv:.4f}")
    print(f"  r(PLA)      : {r_pla:.4f}   MAE(PLA): {mae_pla:.4f}")

    pt_fitted = list(model.scaling_params.get("pt_slopes", {}).keys())
    print(f"  PT fitted   : {', '.join(pt_fitted) or 'none (global fallback)'}")
    print()
