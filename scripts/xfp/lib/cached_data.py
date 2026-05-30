"""Cached loaders for projection CSVs, archetype panels, and PL cache JSON.

All loaders are wrapped with @lru_cache so each file is read at most once per process.
"""
from __future__ import annotations
import functools, glob, json, os
from datetime import datetime
import pandas as pd

from .bucket_dispatch import PROJECTIONS, ARCHETYPE_PANELS, _norm, _flip_lastfirst

PL_CACHE_DIR = 'data/research/pl_cache'


@functools.lru_cache(maxsize=None)
def _load_projection(bucket: str) -> pd.DataFrame:
    """Load + cache a projection CSV. Adds a normalized '_key' column."""
    df = pd.read_csv(PROJECTIONS[bucket])
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
