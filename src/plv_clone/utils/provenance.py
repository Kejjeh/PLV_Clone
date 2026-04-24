"""
Artifact provenance helpers.

Every major pipeline run writes a build_meta_{year}.json sidecar to
outputs_dir so consumers (dashboard, CI, humans) can tell:

  - when the artifact was built
  - what year / source inputs it covers
  - which config thresholds were active
  - which model version it depends on
  - whether the artifact is potentially stale

Schema (all fields optional-ish, present as available):
  built_at          ISO-8601 UTC timestamp
  year              int
  exports           list of output names written this run
  min_pa_process    int   -- hitter qualification threshold
  min_pitches_plv   int   -- pitcher qualification threshold
  model_version     str   -- from version_info.json, if present
  source_date_min   str   -- earliest game_date in scored data
  source_date_max   str   -- latest  game_date in scored data
  rolling_days      int   -- rolling window used
  stage_detected    str   -- season stage inferred at build time
  enrichment_cache  dict  -- freshness of each enrichment snapshot used
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def write_build_meta(
    outputs_dir: Path,
    year: int,
    *,
    suffix: str = "",
    exports: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    models_dir: Path | None = None,
) -> Path:
    """Write a JSON provenance sidecar to *outputs_dir*.

    Parameters
    ----------
    outputs_dir : Directory where exports live (data/outputs/).
    year        : Season year.
    suffix      : Optional name disambiguator, e.g. "_boards" or "_fantasy".
    exports     : List of output names written this run.
    extra       : Any additional key/value pairs to embed.
    models_dir  : If given, reads version_info.json for model_version.

    Returns the path of the written file.
    """
    meta: dict[str, Any] = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "year": year,
        "exports": exports or [],
    }

    if models_dir is not None:
        vi_path = models_dir / "version_info.json"
        if vi_path.exists():
            try:
                vi = json.loads(vi_path.read_text())
                meta["model_version"] = vi.get("version") or vi.get("model_version")
            except Exception:
                pass

    if extra:
        meta.update(extra)

    outputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = outputs_dir / f"build_meta_{year}{suffix}.json"
    out_path.write_text(json.dumps(meta, indent=2, default=str))
    logger.info("Provenance written → %s", out_path.name)
    return out_path


def read_build_meta(outputs_dir: Path, year: int, suffix: str = "") -> dict[str, Any] | None:
    """Read and return the build metadata for *year*, or None if absent."""
    path = outputs_dir / f"build_meta_{year}{suffix}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.warning("Could not read build meta %s: %s", path.name, exc)
        return None
