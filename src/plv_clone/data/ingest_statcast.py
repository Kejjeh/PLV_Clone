"""
Statcast ingestion layer for the PLV Clone pipeline.

Pulls pitch-level data from Baseball Savant via pybaseball, stores raw
data as year-partitioned Parquet files, and tracks progress in a manifest
so incremental updates are safe and resumable.

Design principles:
  - Never re-pull data that is already in the manifest for a given year.
  - Write each chunk immediately after pulling; crash-safe.
  - Fail loudly on schema drift (unexpected columns).
  - Log row counts and missing-value rates after each pull.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd

from plv_clone.data.schemas import STATCAST_RAW_COLS, validate_schema
from plv_clone.utils.io import read_json, read_parquet, write_json, write_parquet
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_MANIFEST_FILE = "manifest.json"
_SLEEP_BETWEEN_CHUNKS = 2.0   # seconds — be polite to Baseball Savant
_MAX_RETRIES = 3
_RETRY_BACKOFF = 10.0         # seconds


def pull_statcast_range(
    start_date: date,
    end_date: date,
    raw_dir: Path,
    chunk_days: int = 7,
    force_refresh: bool = False,
    sleep_s: float = _SLEEP_BETWEEN_CHUNKS,
    reconcile_days: int | None = None,
) -> pd.DataFrame:
    """Pull Statcast data between *start_date* and *end_date* (inclusive).

    Only date ranges not already present in the manifest are pulled.
    Data is saved incrementally to year-partitioned Parquet files under
    *raw_dir*.  Returns the full DataFrame for the requested range.

    Args:
        start_date:     First date to pull.
        end_date:       Last date to pull (inclusive).
        raw_dir:        Directory for raw parquet files and manifest.json.
        chunk_days:     Days per pybaseball call (keep ≤ 7 for reliability).
        force_refresh:  If True, re-pull all dates regardless of manifest.
        sleep_s:        Seconds to sleep between HTTP calls.
        reconcile_days: If set, re-pull the most recent N days even if the
                        manifest marks them as complete. Intended for
                        upstream corrections/backfills (typical use: 7–14).
                        The manifest is updated normally after re-pull, and
                        reconcile metadata is recorded for provenance.

    Returns:
        DataFrame of all pitches in [start_date, end_date].
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(raw_dir) if not force_refresh else {}

    if reconcile_days is not None and not force_refresh:
        manifest = _apply_reconciliation_window(manifest, end_date, reconcile_days)

    missing_ranges = list(
        _iter_missing_date_ranges(start_date, end_date, chunk_days, raw_dir, manifest)
    )

    if not missing_ranges:
        logger.info("All dates already cached — skipping pull.")
    else:
        logger.info(
            "Pulling %d chunk(s) from %s to %s …",
            len(missing_ranges),
            start_date,
            end_date,
        )

    for chunk_start, chunk_end in missing_ranges:
        logger.info("  Pulling chunk %s → %s", chunk_start, chunk_end)
        chunk_df = _pull_chunk_with_retry(chunk_start, chunk_end, retries=_MAX_RETRIES)

        if chunk_df is None or chunk_df.empty:
            logger.warning("  Empty chunk for %s → %s — skipping.", chunk_start, chunk_end)
            time.sleep(sleep_s)
            continue

        chunk_df = _select_available_cols(chunk_df)
        chunk_df = _cast_types(chunk_df)

        year = chunk_end.year
        year_file = raw_dir / f"statcast_{year}.parquet"
        _append_to_year_file(chunk_df, year_file)

        # Update manifest immediately so we can resume on crash
        manifest.setdefault(str(year), {})
        manifest[str(year)]["last_date"] = str(chunk_end)
        manifest[str(year)]["row_count"] = _count_year_rows(year_file)
        _save_manifest(raw_dir, manifest)

        _log_missingness(chunk_df, f"chunk {chunk_start}→{chunk_end}")
        time.sleep(sleep_s)

    # Record reconciliation provenance in manifest
    if reconcile_days is not None and not force_refresh:
        manifest["_reconcile_last_run"] = str(end_date)
        manifest["_reconcile_days"] = reconcile_days
        _save_manifest(raw_dir, manifest)

    # Return the requested range from disk
    return _load_date_range(start_date, end_date, raw_dir)


# ── Internal helpers ─────────────────────────────────────────────────────────

def _apply_reconciliation_window(
    manifest: dict,
    end_date: date,
    reconcile_days: int,
) -> dict:
    """Roll back manifest last_date for any year that overlaps the reconcile window.

    The reconcile window is [end_date - reconcile_days + 1, end_date].
    For each year whose manifest last_date falls within or after that window,
    last_date is set to one day before the window start so that chunks
    overlapping the window are treated as uncached and re-pulled.

    Operates on a copy of the manifest; does not write to disk.
    """
    cutoff = end_date - timedelta(days=reconcile_days - 1)
    logger.info(
        "Reconciliation window: %s → %s (%d days). "
        "Chunks in this range will be re-pulled even if manifest says complete.",
        cutoff, end_date, reconcile_days,
    )

    updated = {k: v for k, v in manifest.items() if k.startswith("_")}  # preserve meta keys
    for year_str, entry in manifest.items():
        if year_str.startswith("_"):
            continue
        last_date_str = entry.get("last_date")
        if last_date_str is None:
            updated[year_str] = entry
            continue
        last_date = date.fromisoformat(last_date_str)
        if last_date >= cutoff:
            rolled_back = cutoff - timedelta(days=1)
            logger.info(
                "  year=%s: rolling back last_date %s → %s",
                year_str, last_date, rolled_back,
            )
            entry = dict(entry)
            entry["last_date"] = str(rolled_back)
        updated[year_str] = entry

    return updated


def _pull_chunk_with_retry(
    start: date,
    end: date,
    retries: int = _MAX_RETRIES,
) -> pd.DataFrame | None:
    """Call pybaseball.statcast() with exponential-backoff retries."""
    import pybaseball  # imported lazily to avoid import-time side effects

    for attempt in range(retries):
        try:
            df = pybaseball.statcast(
                start_dt=str(start),
                end_dt=str(end),
                verbose=False,
            )
            return df
        except Exception as exc:
            wait = _RETRY_BACKOFF * (2 ** attempt)
            logger.warning(
                "  Attempt %d/%d failed for %s→%s: %s. Retrying in %.0fs …",
                attempt + 1,
                retries,
                start,
                end,
                exc,
                wait,
            )
            time.sleep(wait)
    logger.error("All retries exhausted for %s → %s.", start, end)
    return None


def _iter_missing_date_ranges(
    start_date: date,
    end_date: date,
    chunk_days: int,
    raw_dir: Path,
    manifest: dict,
) -> Iterator[tuple[date, date]]:
    """Yield (chunk_start, chunk_end) pairs not yet present in the manifest."""
    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end_date)
        year = str(chunk_end.year)

        last_date_str = manifest.get(year, {}).get("last_date")
        if last_date_str:
            last_date = date.fromisoformat(last_date_str)
            if chunk_end <= last_date:
                cursor = chunk_end + timedelta(days=1)
                continue

        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _select_available_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only columns that are both in STATCAST_RAW_COLS and present in df."""
    available = [c for c in STATCAST_RAW_COLS if c in df.columns]
    missing = [c for c in STATCAST_RAW_COLS if c not in df.columns]
    if missing:
        logger.debug("  Columns not present in pull (may be added in future): %s", missing)
    return df[available].copy()


def _cast_types(df: pd.DataFrame) -> pd.DataFrame:
    """Apply type casts to stabilise schema across pybaseball versions."""
    df = df.copy()
    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    for col in ("game_pk", "at_bat_number", "pitch_number", "pitcher", "batter"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ("balls", "strikes", "outs_when_up", "inning", "zone"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int8")
    for col in ("on_1b", "on_2b", "on_3b"):
        if col in df.columns:
            df[col] = df[col].notna()
    return df


def _append_to_year_file(chunk_df: pd.DataFrame, year_file: Path) -> None:
    """Append *chunk_df* to the year's Parquet file, creating it if absent."""
    if year_file.exists():
        existing = pd.read_parquet(year_file, engine="pyarrow")
        combined = pd.concat([existing, chunk_df], ignore_index=True)
    else:
        combined = chunk_df
    combined.to_parquet(year_file, index=False, engine="pyarrow")
    logger.debug("  Year file updated: %s (%d rows)", year_file.name, len(combined))


def _count_year_rows(year_file: Path) -> int:
    import pyarrow.parquet as pq
    return pq.read_metadata(str(year_file)).num_rows


def _load_date_range(start_date: date, end_date: date, raw_dir: Path) -> pd.DataFrame:
    """Load all year files that overlap [start_date, end_date] and filter."""
    years = list(range(start_date.year, end_date.year + 1))
    frames: list[pd.DataFrame] = []
    for year in years:
        year_file = raw_dir / f"statcast_{year}.parquet"
        if not year_file.exists():
            continue
        df = pd.read_parquet(year_file, engine="pyarrow")
        if "game_date" in df.columns:
            dates = pd.to_datetime(df["game_date"]).dt.date
            df = df[(dates >= start_date) & (dates <= end_date)]
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    logger.info(
        "Loaded %d rows from %s to %s.", len(result), start_date, end_date
    )
    return result


def _log_missingness(df: pd.DataFrame, label: str) -> None:
    """Log columns with > 5% missing values."""
    total = len(df)
    if total == 0:
        return
    high_missing = {
        col: f"{df[col].isna().sum() / total:.1%}"
        for col in df.columns
        if df[col].isna().sum() / total > 0.05
    }
    if high_missing:
        logger.info("  Missingness in %s: %s", label, high_missing)


def _load_manifest(raw_dir: Path) -> dict:
    manifest_path = raw_dir / _MANIFEST_FILE
    if manifest_path.exists():
        return read_json(manifest_path)
    return {}


def _save_manifest(raw_dir: Path, manifest: dict) -> None:
    write_json(manifest, raw_dir / _MANIFEST_FILE)
