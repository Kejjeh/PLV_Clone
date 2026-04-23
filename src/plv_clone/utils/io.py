"""
I/O helpers for the PLV Clone pipeline.

Centralises all parquet and JSON reads/writes so the rest of the codebase
never touches PyArrow or json directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


# ── Parquet ──────────────────────────────────────────────────────────────────

def write_parquet(
    df: pd.DataFrame,
    path: Path,
    partition_cols: list[str] | None = None,
    existing_data_behavior: str = "delete_matching",
) -> None:
    """Write a DataFrame to Parquet.

    If *partition_cols* is provided the data is written as a Hive-partitioned
    dataset under *path* (treated as a directory).  Otherwise a single file is
    written to *path*.

    ``existing_data_behavior="delete_matching"`` (default) ensures re-runs are
    idempotent: all existing files in matching partitions are removed before
    writing.  PyArrow's previous default ``"overwrite_or_ignore"`` would
    silently accumulate duplicate files across runs because each write generates
    a new UUID filename.
    """
    path = Path(path)
    if partition_cols:
        path.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_to_dataset(
            table,
            root_path=str(path),
            partition_cols=partition_cols,
            existing_data_behavior=existing_data_behavior,
        )
        logger.debug("Wrote %d rows (partitioned) → %s", len(df), path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False, engine="pyarrow")
        logger.debug("Wrote %d rows → %s", len(df), path)


def read_parquet(
    path: Path,
    columns: list[str] | None = None,
    filters: list | None = None,
) -> pd.DataFrame:
    """Read Parquet from a file or a partitioned dataset directory."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Parquet path not found: {path}")
    if path.is_dir():
        dataset = ds.dataset(str(path), format="parquet", partitioning="hive")
        table = dataset.to_table(columns=columns, filter=_build_filter(filters))
        df = table.to_pandas()
    else:
        df = pd.read_parquet(path, columns=columns, filters=filters, engine="pyarrow")
    logger.debug("Read %d rows from %s", len(df), path)
    return df


def _build_filter(filters: list | None) -> Any | None:
    """Convert a list of (col, op, val) tuples to a PyArrow expression, or None."""
    if not filters:
        return None
    import pyarrow.compute as pc
    exprs = []
    for col, op, val in filters:
        field = ds.field(col)
        if op == "==":
            exprs.append(field == val)
        elif op == ">=":
            exprs.append(field >= val)
        elif op == "<=":
            exprs.append(field <= val)
        elif op == ">":
            exprs.append(field > val)
        elif op == "<":
            exprs.append(field < val)
        elif op == "in":
            exprs.append(pc.is_in(field, pa.array(val)))
        else:
            raise ValueError(f"Unsupported filter operator: {op}")
    result = exprs[0]
    for e in exprs[1:]:
        result = result & e
    return result


# ── JSON ─────────────────────────────────────────────────────────────────────

def write_json(obj: dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
    logger.debug("Wrote JSON → %s", path)


def read_json(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Utilities ────────────────────────────────────────────────────────────────

def ensure_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
