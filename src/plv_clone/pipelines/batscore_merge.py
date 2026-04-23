"""
Pipeline: Merge Process+ hitter leaderboard with an external BatScore CSV.

BatScore/BatSignal is a proprietary framework — this pipeline accepts any CSV
that a user provides and aligns it with the Process+ master hitter leaderboard.

Outputs:
    data/outputs/fantasy_hitter_merged_YYYY.csv   -- merged file with comparison columns

If no BatScore file is provided, a template CSV is written with empty BatScore
columns so the file schema is preserved for downstream use.

Usage:
    from plv_clone.pipelines.batscore_merge import run
    merged = run(year=2024, batscore_path="path/to/batscore_2024.csv", config=cfg)

BatScore CSV requirements (flexible — column names detected automatically):
    - Player name column: 'Name', 'player_name', 'PlayerName', or 'name'
    - Player ID column (optional but recommended): 'MLBAMID', 'mlbam_id', 'player_id', 'batter'
    - Score column: 'BatScore', 'batscore', 'Score', 'score'
    - Any additional columns are preserved with a 'bs_' prefix to avoid conflicts
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

# Candidate column names (checked in order, first match wins)
_NAME_CANDIDATES   = ["Name", "player_name", "PlayerName", "name", "Player"]
_ID_CANDIDATES     = ["MLBAMID", "mlbam_id", "player_id", "batter", "mlb_id"]
_SCORE_CANDIDATES  = ["BatScore", "batscore", "Score", "score", "bat_score"]


def run(
    year: int,
    batscore_path: str | Path | None = None,
    config: PipelineConfig | None = None,
) -> pd.DataFrame:
    """Merge Process+ leaderboard with BatScore data for *year*.

    Parameters
    ----------
    year:
        Season year.
    batscore_path:
        Path to a BatScore CSV. If None or not found, writes a template CSV
        with empty BatScore columns.
    config:
        PipelineConfig (uses default if None).

    Returns
    -------
    Merged DataFrame with rank-divergence and agreement columns.
    """
    cfg = config or get_config()

    hitter_path = cfg.outputs_dir / f"master_hitter_{year}.csv"
    if not hitter_path.exists():
        raise FileNotFoundError(
            f"master_hitter_{year}.csv not found. Run `plv build-exports {year}` first."
        )

    hitters = pd.read_csv(hitter_path)
    logger.info("Loaded master_hitter_%d: %d hitters", year, len(hitters))

    # ── Add Process+ rank columns ─────────────────────────────────────────
    hitters = _add_process_ranks(hitters)

    # ── Load BatScore if provided ─────────────────────────────────────────
    bs_path = Path(batscore_path) if batscore_path else None

    if bs_path and bs_path.exists():
        batscore = pd.read_csv(bs_path)
        logger.info("Loaded BatScore file: %d rows, cols=%s", len(batscore), batscore.columns.tolist())
        merged = _merge_batscore(hitters, batscore)
    else:
        if batscore_path:
            logger.warning("BatScore file not found: %s — writing template", batscore_path)
        else:
            logger.info("No BatScore path provided — writing template with empty BatScore columns")
        merged = _write_template(hitters)

    # ── Add comparison columns ────────────────────────────────────────────
    if "batscore" in merged.columns and merged["batscore"].notna().any():
        merged = _add_comparison_columns(merged)

    # ── Write output ──────────────────────────────────────────────────────
    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg.outputs_dir / f"fantasy_hitter_merged_{year}.csv"
    merged.to_csv(out_path, index=False)
    logger.info("Wrote fantasy_hitter_merged_%d.csv: %d rows -> %s", year, len(merged), out_path.name)

    return merged


# ── Internal helpers ──────────────────────────────────────────────────────────

def _add_process_ranks(h: pd.DataFrame) -> pd.DataFrame:
    """Add percentile rank columns for each Process+ component."""
    df = h.copy()
    for col, out in [
        ("process_plus",  "pp_rank"),
        ("decision_plus", "dec_rank"),
        ("contact_plus",  "con_rank"),
        ("power_plus",    "pow_rank"),
        ("xwoba_actual",  "xwoba_rank"),
    ]:
        if col in df.columns:
            df[out] = df[col].rank(pct=True).round(3)
    if "pp_rank" in df.columns and "xwoba_rank" in df.columns:
        df["rank_gap"] = (df["pp_rank"] - df["xwoba_rank"]).round(3)
    return df


def _detect_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first candidate column found in *df*, case-insensitive."""
    col_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in col_lower:
            return col_lower[cand.lower()]
    return None


def _normalize_name(s: pd.Series) -> pd.Series:
    """Lowercase, strip accents approximately, strip punctuation for fuzzy matching."""
    return (
        s.str.lower()
         .str.normalize("NFKD")
         .str.encode("ascii", errors="ignore")
         .str.decode("ascii")
         .str.replace(r"[^a-z ]", "", regex=True)
         .str.strip()
    )


def _merge_batscore(hitters: pd.DataFrame, batscore: pd.DataFrame) -> pd.DataFrame:
    """Merge Process+ hitters with BatScore rows.

    Strategy:
    1. Try exact merge on MLBAM ID if both sides have it.
    2. Fall back to normalized name fuzzy merge (exact after normalization).
    Unmatched rows are retained with NaN BatScore columns.
    """
    # Detect columns in BatScore file
    bs_name_col  = _detect_column(batscore, _NAME_CANDIDATES)
    bs_id_col    = _detect_column(batscore, _ID_CANDIDATES)
    bs_score_col = _detect_column(batscore, _SCORE_CANDIDATES)

    if bs_score_col is None:
        logger.warning("Could not find a score column in BatScore file. Candidates: %s", _SCORE_CANDIDATES)
        return _write_template(hitters)

    logger.info("BatScore columns detected: name=%s, id=%s, score=%s", bs_name_col, bs_id_col, bs_score_col)

    # Rename all BatScore columns with 'bs_' prefix (except join keys)
    bs_rename = {}
    for col in batscore.columns:
        if col not in (bs_name_col, bs_id_col):
            bs_rename[col] = f"bs_{col}" if not col.startswith("bs_") else col
    batscore_renamed = batscore.rename(columns=bs_rename)
    bs_score_col_renamed = bs_rename.get(bs_score_col, bs_score_col)

    matched = 0

    # ── Strategy 1: ID join ───────────────────────────────────────────────
    if bs_id_col and "batter" in hitters.columns:
        try:
            batscore_renamed[bs_id_col] = batscore_renamed[bs_id_col].astype(int)
            hitters_temp = hitters.copy()
            hitters_temp["batter"] = hitters_temp["batter"].astype(int)
            merged = hitters_temp.merge(
                batscore_renamed.drop(columns=[bs_name_col] if bs_name_col else []),
                left_on="batter", right_on=bs_id_col, how="left",
            )
            if bs_id_col != "batter":
                merged = merged.drop(columns=[bs_id_col], errors="ignore")
            matched = merged[bs_score_col_renamed].notna().sum()
            logger.info("ID join: %d / %d hitters matched", matched, len(merged))
            if matched > 0:
                return _rename_score_col(merged, bs_score_col_renamed)
        except (ValueError, TypeError):
            logger.info("ID join failed (type error) — falling back to name join")

    # ── Strategy 2: Normalized name join ─────────────────────────────────
    if bs_name_col:
        hitters_j = hitters.copy()
        hitters_j["_norm_name"] = _normalize_name(hitters_j.get("batter_name", hitters_j.get("batter", pd.Series(dtype=str))).astype(str))
        bs_j = batscore_renamed.copy()
        bs_j["_norm_name"] = _normalize_name(batscore_renamed[bs_name_col].astype(str))

        merged = hitters_j.merge(
            bs_j.drop(columns=[bs_name_col], errors="ignore"),
            on="_norm_name", how="left",
        ).drop(columns=["_norm_name"])

        matched = merged[bs_score_col_renamed].notna().sum()
        logger.info("Name join: %d / %d hitters matched", matched, len(merged))
        _log_unmatched(hitters_j, bs_j, bs_score_col_renamed, merged)
        return _rename_score_col(merged, bs_score_col_renamed)

    logger.warning("No join key found — returning template")
    return _write_template(hitters)


def _rename_score_col(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    """Ensure the BatScore column is named 'batscore' for downstream consistency."""
    if score_col != "batscore" and score_col in df.columns:
        df = df.rename(columns={score_col: "batscore"})
    return df


def _log_unmatched(
    hitters_j: pd.DataFrame,
    bs_j: pd.DataFrame,
    score_col: str,
    merged: pd.DataFrame,
) -> None:
    unmatched_hitters = merged[merged[score_col].isna()]["batter_name"].head(10).tolist() if "batter_name" in merged.columns else []
    bs_names = set(bs_j["_norm_name"].dropna())
    unmatched_bs = [n for n in bs_names if n not in set(hitters_j["_norm_name"].dropna())][:10]
    if unmatched_hitters:
        logger.info("Unmatched Process+ hitters (sample): %s", unmatched_hitters)
    if unmatched_bs:
        logger.info("Unmatched BatScore rows (sample): %s", unmatched_bs)


def _write_template(hitters: pd.DataFrame) -> pd.DataFrame:
    """Return hitters with empty BatScore columns for template use."""
    df = hitters.copy()
    df["batscore"]      = np.nan
    df["batscore_rank"] = np.nan
    return df


def _add_comparison_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add rank-comparison columns after a successful BatScore merge."""
    df = df.copy()

    if "batscore" in df.columns:
        df["batscore_rank"] = df["batscore"].rank(pct=True).round(3)

    # Rank agreement: Process+ vs BatScore
    if "pp_rank" in df.columns and "batscore_rank" in df.columns:
        df["pp_vs_bs_gap"] = (df["pp_rank"] - df["batscore_rank"]).round(3)

        # Disagreement bucket
        conditions = [
            df["pp_vs_bs_gap"] > 0.25,   # Process+ likes, BatScore doesn't
            df["pp_vs_bs_gap"] < -0.25,  # BatScore likes, Process+ doesn't
        ]
        choices = ["process_ahead", "batscore_ahead"]
        df["pp_bs_agreement"] = np.select(conditions, choices, default="agree")

    # Component correlates with BatScore — Power+ expected to track most closely
    for comp_rank in ("pow_rank", "dec_rank", "con_rank"):
        if comp_rank in df.columns and "batscore_rank" in df.columns:
            df[f"{comp_rank}_vs_bs"] = (df[comp_rank] - df["batscore_rank"]).round(3)

    return df
