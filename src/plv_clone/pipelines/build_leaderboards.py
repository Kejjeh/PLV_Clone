"""
Pipeline: Build PLV pitcher leaderboards from scored pitch data.

Uses DuckDB for efficient aggregation over hive-partitioned Parquet files.

Outputs:
  - data/outputs/plv_leaderboard_{year}.parquet
  - data/outputs/plv_leaderboard_{year}.csv
  - data/outputs/plv_by_pitch_type_{year}.parquet
  - data/outputs/plv_by_pitch_type_{year}.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def run(
    year: int,
    config: PipelineConfig | None = None,
    output_format: str = "both",
    min_pitches: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build PLV pitcher leaderboard and pitch-type breakdown for *year*.

    Args:
        year:          Season year to aggregate (e.g. 2025).
        config:        PipelineConfig (uses get_config() if None).
        output_format: 'parquet', 'csv', or 'both'.
        min_pitches:   Minimum pitch count for qualification (default: config value).

    Returns:
        Tuple of (pitcher_leaderboard, pitch_type_leaderboard) DataFrames.
    """
    cfg = config or get_config()
    min_p = min_pitches if min_pitches is not None else cfg.min_pitches_plv

    scores_dir = cfg.processed_dir / "plv_scores" / f"year={year}"
    if not scores_dir.exists():
        raise FileNotFoundError(
            f"No PLV scores found for year={year}. "
            f"Run `plv score-plv {year}` first."
        )

    logger.info("Building PLV leaderboards for year=%d (min_pitches=%d) …", year, min_p)

    import duckdb
    conn = duckdb.connect()

    parquet_glob = str(scores_dir / "*.parquet").replace("\\", "/")
    # DuckDB needs a forward-slash glob
    conn.execute(f"CREATE VIEW plv_scores AS SELECT * FROM read_parquet('{parquet_glob}')")

    # ── Pitcher-level leaderboard ─────────────────────────────────────────
    pitcher_lb = conn.execute(f"""
        SELECT
            pitcher,
            player_name,
            COUNT(*)                                  AS pitches,
            AVG(plv)                                  AS plv,
            AVG(plv_raw)                              AS plv_raw,
            AVG(p_swing)                              AS swing_rate,
            AVG(p_whiff_given_swing)                  AS whiff_rate,
            AVG(p_contact_given_swing)                AS contact_rate_given_swing,
            AVG(p_cs_given_take)                      AS called_strike_rate,
            AVG(e_xwoba_in_play)                      AS e_xwoba_in_play,
            STDDEV(plv)                               AS plv_std
        FROM plv_scores
        GROUP BY pitcher, player_name
        HAVING pitches >= {min_p}
        ORDER BY plv DESC
    """).df()

    # ── Pitch-type leaderboard ────────────────────────────────────────────
    pitch_type_lb = conn.execute(f"""
        SELECT
            pitcher,
            player_name,
            pitch_type,
            pitch_group,
            COUNT(*)                                  AS pitches,
            AVG(plv)                                  AS plv,
            AVG(plv_raw)                              AS plv_raw,
            AVG(release_speed)                        AS avg_velo,
            AVG(p_swing)                              AS swing_rate,
            AVG(p_whiff_given_swing)                  AS whiff_rate,
            AVG(e_xwoba_in_play)                      AS e_xwoba_in_play
        FROM plv_scores
        GROUP BY pitcher, player_name, pitch_type, pitch_group
        HAVING pitches >= 25
        ORDER BY plv DESC
    """).df()

    conn.close()

    # ── Add percentile ranks ──────────────────────────────────────────────
    pitcher_lb = _add_percentile_rank(pitcher_lb, "plv", "plv_pctile")
    pitch_type_lb = _add_percentile_rank(pitch_type_lb, "plv", "plv_pctile")

    _log_leaderboard_summary(pitcher_lb, label=f"Pitcher PLV {year}")

    # ── Write outputs ─────────────────────────────────────────────────────
    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    _write_output(pitcher_lb, cfg.outputs_dir / f"plv_leaderboard_{year}", output_format)
    _write_output(pitch_type_lb, cfg.outputs_dir / f"plv_by_pitch_type_{year}", output_format)

    logger.info(
        "Leaderboards written to %s", cfg.outputs_dir
    )
    return pitcher_lb, pitch_type_lb


def _add_percentile_rank(df: pd.DataFrame, col: str, out_col: str) -> pd.DataFrame:
    df = df.copy()
    df[out_col] = df[col].rank(pct=True).mul(100).round(1)
    return df


def _write_output(df: pd.DataFrame, base_path: Path, fmt: str) -> None:
    if fmt in ("parquet", "both"):
        df.to_parquet(str(base_path) + ".parquet", index=False)
        logger.debug("Wrote %s.parquet (%d rows)", base_path.name, len(df))
    if fmt in ("csv", "both"):
        df.to_csv(str(base_path) + ".csv", index=False)
        logger.debug("Wrote %s.csv (%d rows)", base_path.name, len(df))


def _log_leaderboard_summary(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        logger.warning("[%s] Empty leaderboard.", label)
        return
    logger.info(
        "[%s] %d qualified pitchers | PLV range: %.2f – %.2f | mean: %.2f",
        label,
        len(df),
        df["plv"].min(),
        df["plv"].max(),
        df["plv"].mean(),
    )
    if len(df) >= 10:
        top5 = df.nlargest(5, "plv")[["player_name", "pitches", "plv"]]
        bottom5 = df.nsmallest(5, "plv")[["player_name", "pitches", "plv"]]
        logger.info("Top 5:\n%s", top5.to_string(index=False))
        logger.info("Bottom 5:\n%s", bottom5.to_string(index=False))
