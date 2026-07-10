"""Cached loaders for projection CSVs, archetype panels, and PL cache JSON.

All loaders are wrapped with @lru_cache so each file is read at most once per process.
"""
from __future__ import annotations
import functools, glob, json, os
from datetime import datetime
import pandas as pd

from .bucket_dispatch import PROJECTIONS, ARCHETYPE_PANELS, _norm, _flip_lastfirst

PL_CACHE_DIR = 'data/research/pl_cache'

# Load-bearing columns every consumer (model_row, the seam, the dashboards) relies on.
# Validated at load so a model-pipeline refactor that drops a headline/id column fails
# LOUDLY here with a clear message, instead of a cryptic KeyError deep inside model_row.
REQUIRED_COLUMNS = {
    'H':  ('batter', 'player_name', 'rank', 'xfp_rh3_per_game'),
    'SP': ('pitcher', 'player_name', 'rank', 'xfp_rp3_per_start'),
    'RP': ('pitcher', 'name_api', 'rank', 'xfp_ros'),
}


@functools.lru_cache(maxsize=None)
def _load_rp_volume_g() -> dict:
    """mlbam -> implied RoS relief appearances (proj_ros_g) from the RP volume
    model (validated 2026-07-10, rp_volume_model_2026-07-10.md). Used to convert
    rprs2's RoS-total headline into the FP/appearance unit the decision settler
    scores against. Empty dict when the volume CSV is absent (fail-soft: the
    settlement-unit proj is then unavailable, never silently wrong)."""
    path = 'data/outputs/xfp_rp_volume_projections.csv'
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)[['mlbam_id', 'proj_ros_g']].dropna()
    return {int(m): float(g) for m, g in zip(df['mlbam_id'], df['proj_ros_g'])}


@functools.lru_cache(maxsize=None)
def _load_projection(bucket: str) -> pd.DataFrame:
    """Load + cache a projection CSV. Adds a normalized '_key' column.

    Validates the load-bearing schema up front (REQUIRED_COLUMNS) so a missing headline
    or id column surfaces as a clear ProjectionSchema error, not a downstream KeyError.
    """
    path = PROJECTIONS[bucket]
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS.get(bucket, ()) if c not in df.columns]
    if missing:
        raise ValueError(
            f"projection schema error: {bucket} CSV {path} is missing required "
            f"column(s) {missing}. A model refactor likely dropped them — fix the "
            f"pipeline or REQUIRED_COLUMNS. Present: {sorted(df.columns)[:12]}...")
    if bucket == 'H':
        df['_key'] = df['player_name'].apply(_norm)
    elif bucket == 'SP':
        df['_key'] = df['player_name'].apply(_flip_lastfirst).apply(_norm)
    else:  # RP
        df['_key'] = df['name_api'].apply(_norm)
    return df


@functools.lru_cache(maxsize=None)
def _load_archetype(bucket: str):
    """Load + cache an archetype panel parquet."""
    panel_path = ARCHETYPE_PANELS[bucket]
    if not os.path.exists(panel_path):
        return None
    p = pd.read_parquet(panel_path)
    name_col = 'player_name' if 'player_name' in p.columns else 'name'
    p['_key'] = p[name_col].apply(_norm)
    return p


@functools.lru_cache(maxsize=None)
def _load_pl_cache(filename: str) -> dict:
    path = os.path.join(PL_CACHE_DIR, filename)
    if not os.path.exists(path):
        return {'fetched': None, 'source_url': None, 'ranks': {}}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


@functools.lru_cache(maxsize=None)
def _load_pl_streamer_cache() -> tuple[dict, str]:
    """Find newest pl_sp_streamers_*.json by filename date; fall back to latest."""
    pattern = os.path.join(PL_CACHE_DIR, 'pl_sp_streamers_*.json')
    candidates = []
    for path in glob.glob(pattern):
        base = os.path.basename(path)
        if base == 'pl_sp_streamers_latest.json':
            continue
        stem = base[len('pl_sp_streamers_'):-len('.json')]
        try:
            datetime.strptime(stem, '%Y-%m-%d')
            candidates.append((stem, path))
        except ValueError:
            continue
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        date_str, path = candidates[0]
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f), date_str
    cache = _load_pl_cache('pl_sp_streamers_latest.json')
    return cache, cache.get('fetched', '') or ''
