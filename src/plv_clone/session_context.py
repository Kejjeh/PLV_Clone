"""SessionContext: bundled, mtime-invalidating loaders for the model+PL+FA-
snapshot artifacts that most analysis scripts read together.

Replaces the ad-hoc `@functools.lru_cache` loaders in
scripts/xfp/lib/cached_data.py for the common-case where a caller wants
a coherent SESSION-LEVEL view (rh3 + rp3 + rprs2 + master panels + PL +
FA snapshot) keyed on file mtimes so a daily refresh mid-session
invalidates stale reads.

Compared to `@lru_cache`, the SessionContext:
  - Invalidates per-loader on file mtime change (refresh mid-session).
  - Returns None instead of crashing when a file is missing.
  - Carries an optional snapshot_label so loaders can route to a frozen
    research copy (e.g. backtests).

Design intent: ONE SessionContext instance per CLI invocation. Cheap to
construct; lazy on first method call. Not thread-safe; analysis scripts
are single-process.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────
# Default path map. Override via __init__ kwargs for backtest / synthetic.
# ─────────────────────────────────────────────────────────────────────────

DEFAULT_PATHS: dict[str, str] = {
    "rh3":                    "data/outputs/xfp_rh3_projections.csv",
    "rp3":                    "data/outputs/xfp_rp3_projections.csv",
    "rprs2":                  "data/outputs/xfp_rprs2_projections.csv",
    "hitter_master":          "data/research/hitter_ratings_master.csv",
    "sp_master":              "data/research/sp_ratings_master.csv",
    "rp_master":              "data/research/rp_ratings_master.csv",
    "pl_top150":              "data/research/pl_cache/pl_hitters_top150.json",
    "pl_top100":              "data/research/pl_cache/pl_sps_top100.json",
    "fa_snapshot_rp":         "data/research/fa_snapshots/fa_pool_RP_latest.parquet",
}


@dataclass
class SessionContext:
    """Bundled loaders for the canonical model + PL + FA-snapshot files.

    Usage:
        ctx = SessionContext()
        rh3 = ctx.rh3()              # cached after first call
        rp3 = ctx.rp3()
        ...
        ctx.invalidate()             # force re-read on next call

    Loader methods: rh3, rp3, rprs2, hitter_master, sp_master, rp_master,
    pl_top150, pl_top100, fa_snapshot_rp. Nine total.
    """

    paths: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PATHS))
    snapshot_label: Optional[str] = None  # used as cache-key namespace
    _cache: dict[str, tuple[Any, float]] = field(default_factory=dict, init=False, repr=False)

    # ── Internal cache machinery ─────────────────────────────────────────
    def _read_through(self, name: str, loader):
        """Cache hit when (path, snapshot_label, mtime) all match prior read."""
        path = self.paths[name]
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        cached = self._cache.get(name)
        if cached is not None:
            value, cached_mtime = cached
            if cached_mtime == mtime:
                return value
        value = loader(path)
        self._cache[name] = (value, mtime)
        return value

    def invalidate(self, name: Optional[str] = None) -> None:
        """Drop the cache for one loader (by name) or all loaders."""
        if name is None:
            self._cache.clear()
        else:
            self._cache.pop(name, None)

    # ── Public loaders (9) ───────────────────────────────────────────────
    def rh3(self) -> Optional[pd.DataFrame]:
        return self._read_through("rh3", pd.read_csv)

    def rp3(self) -> Optional[pd.DataFrame]:
        return self._read_through("rp3", pd.read_csv)

    def rprs2(self) -> Optional[pd.DataFrame]:
        return self._read_through("rprs2", pd.read_csv)

    def hitter_master(self) -> Optional[pd.DataFrame]:
        return self._read_through("hitter_master", pd.read_csv)

    def sp_master(self) -> Optional[pd.DataFrame]:
        return self._read_through("sp_master", pd.read_csv)

    def rp_master(self) -> Optional[pd.DataFrame]:
        return self._read_through("rp_master", pd.read_csv)

    def pl_top150(self) -> Optional[dict]:
        return self._read_through("pl_top150", _load_json)

    def pl_top100(self) -> Optional[dict]:
        return self._read_through("pl_top100", _load_json)

    def fa_snapshot_rp(self) -> Optional[pd.DataFrame]:
        return self._read_through("fa_snapshot_rp", pd.read_parquet)


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


__all__ = ["SessionContext", "DEFAULT_PATHS"]
