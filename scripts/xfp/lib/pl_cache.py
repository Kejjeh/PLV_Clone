"""Pitcher List rank lookup + stale-cache warnings."""
from __future__ import annotations
import json, os, sys
from datetime import date, datetime

from .bucket_dispatch import _norm
from .cached_data import _load_pl_cache, _load_pl_streamer_cache, PL_CACHE_DIR

PL_CACHE_FILES = {
    'H':         'pl_hitters_top150.json',
    'SP':        'pl_sps_top100.json',
    'SP_STREAM': 'pl_sp_streamers_latest.json',
    'RP':        'pl_closers.json',
}

# Article-universe sizes — distinguishes "snubbed" (UR) from "out-of-scope" (—).
PL_UNIVERSE_SIZE = {'H': 150, 'SP': 100, 'RP': 50}


def pl_rank(name: str, bucket: str, model_rank=None):
    """Return (rank|'UR'|'—', cache_date)."""
    cache = _load_pl_cache(PL_CACHE_FILES[bucket])
    ranks = cache.get('ranks', {})
    fetched = cache.get('fetched')
    nk = _norm(name)
    for pl_name, rk in ranks.items():
        if _norm(pl_name) == nk:
            return rk, fetched
    if not ranks:
        return '—', None
    universe = PL_UNIVERSE_SIZE.get(bucket, 150)
    if isinstance(model_rank, int) and model_rank > universe:
        return '—', fetched
    return 'UR', fetched


def pl_streamer_rank(name: str):
    """For SPs only: return (rank+tier string, opp, cache_date)."""
    cache, date_str = _load_pl_streamer_cache()
    ranks = cache.get('ranks', {})
    fetched = cache.get('fetched') or date_str
    nk = _norm(name)
    for pl_name, info in ranks.items():
        if _norm(pl_name) == nk:
            return f"#{info.get('rank','?')} [{info.get('tier','?')}]", info.get('opp'), fetched
    return '—', None, fetched


def _warn_stale_caches():
    """Walk the 4 PL cache files; warn on stale entries. Print to stderr."""
    today = date.today()
    items = [
        ('pl_hitters_top150.json', 7),
        ('pl_sps_top100.json',     7),
        ('pl_closers.json',        7),
        ('pl_sp_streamers_latest.json', 2),
    ]
    for fname, thresh in items:
        path = os.path.join(PL_CACHE_DIR, fname)
        if not os.path.exists(path):
            print(f"WARN {fname} is MISSING", file=sys.stderr)
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            continue
        fetched = cache.get('fetched')
        if not fetched:
            continue
        try:
            fdate = datetime.strptime(fetched[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        age = (today - fdate).days
        if age > thresh:
            print(f"WARN {fname} is {age}d stale (fetched {fetched})", file=sys.stderr)
