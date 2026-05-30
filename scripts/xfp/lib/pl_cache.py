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


# ---- refresh-instructions helper ---------------------------------------

_CACHE_REFRESH_SPEC = [
    ('pl_hitters_top150.json',       7, 'hitters', 'pitcherlist.com top 150 hitters {YEAR} week {WEEK}'),
    ('pl_sps_top100.json',           7, 'sps',     'pitcherlist.com top 100 starting pitchers {YEAR} week {WEEK}'),
    ('pl_closers.json',              7, 'closers', 'pitcherlist.com closers and saves {YEAR} week {WEEK}'),
    ('pl_sp_streamers_latest.json',  2, 'streamers', 'pitcherlist.com SP streamers week {WEEK} {YEAR}'),
]


def print_refresh_instructions() -> None:
    """Print step-by-step WebSearch + WebFetch instructions for stale caches."""
    today = date.today()
    year = today.year
    # Rough ISO week within the season — close enough for a search hint
    week = today.isocalendar().week

    print("=== PL cache refresh check ===\n")
    any_stale = False
    for fname, thresh, _kind, query_tmpl in _CACHE_REFRESH_SPEC:
        path = os.path.join(PL_CACHE_DIR, fname)
        if not os.path.exists(path):
            any_stale = True
            print(f"MISSING: {fname}. To create:")
            _print_refresh_block(fname, query_tmpl.format(YEAR=year, WEEK=week))
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception as e:
            print(f"UNREADABLE: {fname} ({e})\n")
            continue
        fetched = cache.get('fetched')
        if not fetched:
            print(f"NO-DATE: {fname} (no 'fetched' field — treat as stale)\n")
            any_stale = True
            continue
        try:
            fdate = datetime.strptime(fetched[:10], '%Y-%m-%d').date()
        except ValueError:
            print(f"BAD-DATE: {fname} (fetched={fetched})\n")
            continue
        age = (today - fdate).days
        if age > thresh:
            any_stale = True
            print(f"STALE: {fname} ({age}d old, threshold {thresh}d). To refresh:")
            _print_refresh_block(fname, query_tmpl.format(YEAR=year, WEEK=week))
        else:
            print(f"FRESH: {fname} ({age}d old, threshold {thresh}d)\n")

    if not any_stale:
        print("All PL caches are fresh — nothing to do.")


def _print_refresh_block(fname: str, query: str) -> None:
    print(f"  1. WebSearch \"{query}\" with allowed_domains=['pitcherlist.com']")
    print(f"  2. WebFetch the latest URL, ask for the FULL list as `rank. Player Name`")
    print(f"  3. Save to {PL_CACHE_DIR}/{fname} with schema "
          "{source_url, fetched, week, ranks}")
    print()
