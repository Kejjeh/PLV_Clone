"""ProjectionStore — the single seam for loading the validated model projection
artifacts (rh3 / rp3 / rprs2).

Every dashboard and skill that needs a projection CSV used to read it inline
(``pd.read_csv(OUT / 'xfp_rp3_projections.csv')``), each with its own path
constant and no shared cache. This module owns *where* the artifacts live and
*how* they load (memoized per process), so a path change, a schema concern, or
the live-IL override (see note) lives in one place instead of N callers.

Paths resolve relative to the repo root via ``__file__`` (src/plv_clone/ ->
repo root), so the store works regardless of the caller's CWD or which machine
it runs on — no hardcoded absolute root.

Fail-soft: a missing artifact returns an empty DataFrame (the dashboards treat
an empty projection as "axis unavailable" rather than crashing).

NOTE — live-IL override: the matchup prefers ``xfp_rp3_projections_il_fixed.csv``
(live ESPN IL status patched on top of rp3) behind a freshness guard. That
override belongs here as ``rp3(live_il=True)`` and will land when the matchup is
migrated onto the store; for now ``rp3()`` returns the canonical projection.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUTS = _REPO_ROOT / "data" / "outputs"

RH3_NAME = "xfp_rh3_projections.csv"
RP3_NAME = "xfp_rp3_projections.csv"
RPRS2_NAME = "xfp_rprs2_projections.csv"


class ProjectionStore:
    """Memoized loader for the rh3 / rp3 / rprs2 projection artifacts.

    A default singleton ``PROJECTIONS`` is provided for callers; tests can build
    their own ``ProjectionStore(outputs_dir=tmp)`` to inject fixtures.
    """

    def __init__(self, outputs_dir: Optional[Path] = None):
        self._dir = Path(outputs_dir) if outputs_dir is not None else _DEFAULT_OUTPUTS
        self._cache: dict[str, pd.DataFrame] = {}

    def _load(self, name: str) -> pd.DataFrame:
        if name not in self._cache:
            path = self._dir / name
            self._cache[name] = pd.read_csv(path) if path.exists() else pd.DataFrame()
        return self._cache[name]

    def rh3(self) -> pd.DataFrame:
        """Hitter rest-of-season projections (per-game scale)."""
        return self._load(RH3_NAME)

    def rp3(self) -> pd.DataFrame:
        """Starting-pitcher rest-of-season projections (per-start scale).

        Returns the canonical projection. The live-IL override (il_fixed shim +
        freshness guard) will be exposed here as ``rp3(live_il=True)`` when the
        matchup migrates onto the store.
        """
        return self._load(RP3_NAME)

    def rprs2(self) -> pd.DataFrame:
        """Reliever rest-of-season projections (includes SV/HLD scoring)."""
        return self._load(RPRS2_NAME)

    def clear(self) -> None:
        """Drop the in-process cache (force a re-read on next access)."""
        self._cache.clear()


# Default process-wide store. Callers: `from plv_clone.projections import PROJECTIONS`.
PROJECTIONS = ProjectionStore()
