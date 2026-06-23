"""Pitcher List rank lookup + stale-cache warnings."""
from __future__ import annotations
import json, os, sys
from datetime import date, datetime, timedelta

from .bucket_dispatch import _norm
from .cached_data import _load_pl_cache, _load_pl_streamer_cache, PL_CACHE_DIR

# ── PL publish cadence (when each ranking DROPS, inferred from article dates) ──
# Staleness is cadence-aware, not flat calendar age: a weekly ranking is stale only
# once its NEXT edition has actually published. Evidence from the article URLs:
#   Top 100 SP — Monday    (titles dated to the week's Monday: "6-15 week-13",
#                           "6-22 week-14")
#   Closers/relievers — ~Tuesday (article dated "...closers-holds-solds-6-16", a Tue)
#   Top 150 hitters — ~mid-week (~Wednesday; lagged the SP list — was "week-12" on a
#                           Friday when SP was already "week-13")
#   SP streamers — rolling 2-3 day windows ("...6-19-6-20-6-21"), refresh every ~2 days
# ('weekly', weekday) where Monday=0; ('rolling', max_age_days).
PL_PUBLISH_CADENCE = {
    'pl_sps_top100.json':          ('weekly', 0),   # Monday
    'pl_closers.json':             ('weekly', 1),   # ~Tuesday
    'pl_hitters_top150.json':      ('weekly', 2),   # ~Wednesday
    'pl_sp_streamers_latest.json': ('rolling', 2),  # every ~2 days
}


def _last_weekday_on_or_before(today: date, weekday: int) -> date:
    """Most recent date <= today that falls on `weekday` (Mon=0)."""
    return today - timedelta(days=(today.weekday() - weekday) % 7)


def _cache_is_stale(fname: str, fetched: date, today: date) -> tuple[bool, str]:
    """Cadence-aware staleness. Returns (is_stale, human_reason)."""
    mode, val = PL_PUBLISH_CADENCE.get(fname, ('rolling', 7))
    if mode == 'rolling':
        age = (today - fetched).days
        return age > val, f"{age}d old (rolling, refresh every {val}d)"
    pub = _last_weekday_on_or_before(today, val)  # this cycle's publish date
    wd = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][val]
    if fetched < pub:
        return True, f"new {wd} edition out ({pub}); cache fetched {fetched}"
    return False, f"current ({wd} edition {pub} already cached)"

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
    """Walk the 4 PL cache files; warn on stale entries (cadence-aware). Print to stderr."""
    today = date.today()
    for fname in PL_PUBLISH_CADENCE:
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
        stale, reason = _cache_is_stale(fname, fdate, today)
        if stale:
            print(f"WARN {fname} is STALE — {reason}", file=sys.stderr)


# ---- refresh-instructions helper ---------------------------------------

_CACHE_REFRESH_SPEC = [
    ('pl_hitters_top150.json',       'hitters', 'pitcherlist.com top 150 hitters {YEAR} week {WEEK}'),
    ('pl_sps_top100.json',           'sps',     'pitcherlist.com top 100 starting pitchers {YEAR} week {WEEK}'),
    ('pl_closers.json',              'closers', 'pitcherlist.com closers and saves {YEAR} week {WEEK}'),
    ('pl_sp_streamers_latest.json',  'streamers', 'pitcherlist.com SP streamers week {WEEK} {YEAR}'),
]


def print_refresh_instructions() -> None:
    """Print step-by-step WebSearch + WebFetch instructions for stale caches."""
    today = date.today()
    year = today.year
    # Rough ISO week within the season — close enough for a search hint
    week = today.isocalendar().week

    print("=== PL cache refresh check (cadence-aware) ===\n")
    any_stale = False
    for fname, _kind, query_tmpl in _CACHE_REFRESH_SPEC:
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
        stale, reason = _cache_is_stale(fname, fdate, today)
        if stale:
            any_stale = True
            print(f"STALE: {fname} — {reason}. To refresh:")
            _print_refresh_block(fname, query_tmpl.format(YEAR=year, WEEK=week))
        else:
            print(f"FRESH: {fname} — {reason}\n")

    if not any_stale:
        print("All PL caches are fresh — nothing to do.")


def _print_refresh_block(fname: str, query: str) -> None:
    print(f"  1. WebSearch \"{query}\" with allowed_domains=['pitcherlist.com']")
    print(f"  2. WebFetch the latest URL, ask for the FULL list as `rank. Player Name`")
    print(f"  3. Save to {PL_CACHE_DIR}/{fname} with schema "
          "{source_url, fetched, week, ranks}")
    print()
