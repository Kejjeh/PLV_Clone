"""
Pipeline: Score pitcher PLV/PLA using PLPlvModel and write output CSV.

Outputs: data/outputs/pl_plv_{year}.csv

Data source is chosen based on the trained model's rv_method:
  "plv_raw"       -- loads from plv_scores/ (expected-value model; best quality)
  "delta_run_exp" -- loads from pitch_features/
  "xwoba_blend"   -- loads from pitch_features/

If rv_method is "plv_raw" but plv_scores are unavailable for the target year,
falls back to pitch_features with delta_run_exp and warns that quality may differ.

If a Pitcher List reference CSV exists for the target year, also prints a
validation report (r, MAE, top-10 disagreements).
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


def run(year: int, config: PipelineConfig | None = None) -> pd.DataFrame:
    """Score pitchers for *year* with PLPlvModel and write pl_plv_{year}.csv.

    Args:
        year:   Season year to score (e.g. 2026).
        config: PipelineConfig (uses get_config() if None).

    Returns:
        Pitcher-level DataFrame with pl_plv, pl_pla, and per-pitch-type columns.
    """
    cfg = config or get_config()

    scaling_path = cfg.models_dir / "pl_plv_scaling.json"
    if not scaling_path.exists():
        raise FileNotFoundError(
            f"PLPlvModel not trained yet -- scaling params not found at {scaling_path}.\n"
            "Run `plv train-pl-plv` first."
        )

    model = PLPlvModel.load(cfg.models_dir)
    rv_method = model.scaling_params.get("rv_method", "delta_run_exp")

    # ── Load pitch data ────────────────────────────────────────────────────
    scores_dir = cfg.processed_dir / "plv_scores" / f"year={year}"
    pitch_dir = cfg.processed_dir / "pitch_features" / f"year={year}"

    if rv_method == "plv_components" and scores_dir.exists():
        logger.info("Loading plv_scores for year=%d (rv_method=plv_components) ...", year)
        pitch_df = read_parquet(scores_dir, columns=_COMPONENT_COLS)
    elif rv_method == "plv_components" and not scores_dir.exists():
        logger.warning(
            "rv_method=plv_components but plv_scores not found for year=%d. "
            "Falling back to delta_run_exp from pitch_features -- scores will differ.",
            year,
        )
        if not pitch_dir.exists():
            raise FileNotFoundError(
                f"Neither plv_scores nor pitch_features found for year={year}."
            )
        pitch_df = read_parquet(pitch_dir, columns=_PITCH_COLS)
        model = PLPlvModel(scaling_params=dict(model.scaling_params, rv_method="delta_run_exp"))
    elif rv_method == "plv_raw" and scores_dir.exists():
        logger.info("Loading plv_scores for year=%d (rv_method=plv_raw) ...", year)
        pitch_df = read_parquet(scores_dir, columns=_PLV_SCORE_COLS)
    elif rv_method == "plv_raw" and not scores_dir.exists():
        logger.warning(
            "rv_method=plv_raw but plv_scores not found for year=%d. "
            "Falling back to delta_run_exp from pitch_features -- scores may differ.",
            year,
        )
        if not pitch_dir.exists():
            raise FileNotFoundError(
                f"Neither plv_scores nor pitch_features found for year={year}."
            )
        pitch_df = read_parquet(pitch_dir, columns=_PITCH_COLS)
        model = PLPlvModel(scaling_params=dict(model.scaling_params, rv_method="delta_run_exp"))
    else:
        if not pitch_dir.exists():
            raise FileNotFoundError(
                f"Pitch features not found for year={year}. "
                "Run `plv build-features` to generate them."
            )
        logger.info("Loading pitch features for year=%d (rv_method=%s) ...", year, rv_method)
        pitch_df = read_parquet(pitch_dir, columns=_PITCH_COLS)

    logger.info("  %d pitches loaded.", len(pitch_df))

    # ── Determine min_pitches threshold ────────────────────────────────────
    ref_path = _REF_DIR / f"pl_plv_{year}.csv"
    if ref_path.exists():
        ref_df = load_and_clean_reference(ref_path)
        min_pitches = 400 if len(ref_df) >= 400 else 200
        logger.info(
            "Reference CSV found (%d pitchers) -> min_pitches=%d", len(ref_df), min_pitches
        )
    else:
        ref_df = None
        min_pitches = 200  # safe default -- better to include than silently drop
        logger.info("No reference CSV for year=%d -> min_pitches=200 (default).", year)

    scored = model.score_pitches(pitch_df)
    agg = model.aggregate(scored, min_pitches=min_pitches, year=year)
    logger.info("Aggregated: %d qualified pitchers (min_pitches=%d).", len(agg), min_pitches)

    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg.outputs_dir / f"pl_plv_{year}.csv"
    agg.to_csv(out_path, index=False)
    logger.info("Wrote %s", out_path)

    if ref_df is not None:
        _print_validation(agg, ref_df, year)

    return agg


# ── Internal helpers ───────────────────────────────────────────────────────

def _print_validation(agg: pd.DataFrame, ref_df: pd.DataFrame, year: int) -> None:
    ref_clean = ref_df.rename(columns={"MLBAMID": "pitcher"}).copy()
    ref_clean["pitcher"] = ref_clean["pitcher"].astype(int)
    merged = agg.merge(ref_clean[["pitcher", "PLV", "PLA"]], on="pitcher", how="inner")

    if merged.empty:
        logger.warning("No matching pitchers between output and reference for year=%d.", year)
        return

    r_plv, _ = pearsonr(merged["pl_plv"], merged["PLV"])
    mae_plv = (merged["pl_plv"] - merged["PLV"]).abs().mean()
    r_pla, _ = pearsonr(merged["pl_pla"], merged["PLA"])
    mae_pla = (merged["pl_pla"] - merged["PLA"]).abs().mean()

    print(f"\n-- Validation vs PL Reference ({year}) --")
    print(f"  N matched   : {len(merged)}")
    print(f"  r(PLV)      : {r_plv:.4f}   MAE(PLV): {mae_plv:.4f}")
    print(f"  r(PLA)      : {r_pla:.4f}   MAE(PLA): {mae_pla:.4f}")

    merged = merged.copy()
    merged["plv_delta"] = (merged["pl_plv"] - merged["PLV"]).abs()
    top10 = merged.nlargest(10, "plv_delta")[
        ["pitcher_name", "PLV", "pl_plv", "plv_delta"]
    ]
    print("\n  Top-10 PLV disagreements:")
    print(f"  {'Pitcher':<25} {'PL_PLV':>7} {'Our_PLV':>8} {'|d|':>6}")
    print(f"  {'-'*25} {'-------':>7} {'--------':>8} {'------':>6}")
    for _, row in top10.iterrows():
        print(
            f"  {row['pitcher_name']:<25} {row['PLV']:>7.3f} "
            f"{row['pl_plv']:>8.3f} {row['plv_delta']:>6.3f}"
        )
    print()
