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
RP3_IL_FIXED_NAME = "xfp_rp3_projections_il_fixed.csv"
RPRS2_NAME = "xfp_rprs2_projections.csv"

# The il_fixed shim (live ESPN IL status patched onto rp3) is preferred only
# while it's fresh relative to the canonical rp3; older than this it's treated
# as stale and we fall back to canonical (the matchup-audit freshness contract).
IL_FIXED_MAX_STALE_SECONDS = 24 * 3600


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

    def rp3(self, live_il: bool = False) -> pd.DataFrame:
        """Starting-pitcher rest-of-season projections (per-start scale).

        ``live_il=True`` prefers the ``il_fixed`` shim (live ESPN IL status
        patched onto rp3) — but only while it's fresh relative to canonical;
        once it's >24h staler than canonical it's ignored and canonical is used
        (a regenerated rp3 must not be shadowed by a stale shim). This is the
        freshness guard that used to live inline in the matchup's
        ``_select_rp3_path``.
        """
        if not live_il:
            return self._load(RP3_NAME)
        canonical = self._dir / RP3_NAME
        shim = self._dir / RP3_IL_FIXED_NAME
        if not shim.exists():
            return self._load(RP3_NAME)
        if not canonical.exists():
            return self._load(RP3_IL_FIXED_NAME)
        try:
            stale = canonical.stat().st_mtime - shim.stat().st_mtime
            if stale > IL_FIXED_MAX_STALE_SECONDS:
                print(
                    f"  ⚠ {RP3_IL_FIXED_NAME} is {stale / 3600:.1f}h older than "
                    f"{RP3_NAME} — using canonical rp3. Re-run fix_il_flag_from_espn.py."
                )
                return self._load(RP3_NAME)
        except OSError:
            return self._load(RP3_NAME)
        return self._load(RP3_IL_FIXED_NAME)

    def rprs2(self) -> pd.DataFrame:
        """Reliever rest-of-season projections (includes SV/HLD scoring)."""
        return self._load(RPRS2_NAME)

    def clear(self) -> None:
        """Drop the in-process cache (force a re-read on next access)."""
        self._cache.clear()


# Default process-wide store. Callers: `from plv_clone.projections import PROJECTIONS`.
PROJECTIONS = ProjectionStore()
