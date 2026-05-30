"""Triangulate engine library — importable from other skills.

Public API:
    from scripts.xfp.lib.triangulate_core import triangulate_player
"""
from .triangulate_core import (
    triangulate_player,
    model_row,
    archetype_row,
    synthesize,
    apply_overrides,
)
from .bucket_dispatch import (
    resolve_player,
    PROJECTIONS,
    ARCHETYPE_PANELS,
    _norm,
    _flip_lastfirst,
)
from .pl_cache import pl_rank, pl_streamer_rank, _warn_stale_caches
