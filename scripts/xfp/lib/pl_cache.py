"""Pitcher List rank lookup + stale-cache warnings."""
from __future__ import annotations
import json, os, sys
from datetime import date, datetime, time, timedelta

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo('America/New_York')
except Exception:  # pragma: no cover
    _ET = None

from .bucket_dispatch import _norm
from .cached_data import _load_pl_cache, _load_pl_streamer_cache, PL_CACHE_DIR

# ── PL publish cadence (which DAY each ranking drops + the ET TIME it lands) ──
# Staleness is cadence- AND time-aware: a weekly ranking is stale only once its NEXT
# edition has ACTUALLY published. PL drops each article ~6-7 PM ET on its day, so we
# treat an edition as available at 19:00 ET (7 PM) on its weekday — a run at Tue 4 AM
# sees only Monday's SP list as new, not Tuesday's closers (those land Tue evening).
# Evidence from the article URLs:
#   Top 100 SP — Monday    ("...6-15-week-13", "...6-22-week-14")
#   Closers/relievers — ~Tuesday ("...closers-holds-solds-6-16", a Tue)
#   Top 150 hitters — ~Wednesday (lagged the SP list; "week-12" on a Fri when SP=week-13)
#   SP streamers — rolling 2-3 day windows ("...6-19-6-20-6-21")
# ('weekly', weekday) where Monday=0; ('rolling', max_age_days).
PL_PUBLISH_CADENCE = {
    'pl_sps_top100.json':          ('weekly', 0),   # Monday
    'pl_closers.json':             ('weekly', 1),   # ~Tuesday
    'pl_hitters_top150.json':      ('weekly', 2),   # ~Wednesday
    'pl_sp_streamers_latest.json': ('rolling', 2),  # every ~2 days
}
PL_PUBLISH_HOUR_ET = 19  # articles land ~6-7 PM ET; treat as out at 7 PM

# ── PL edition-week numbering (SINGLE owner — build/backfill import from here) ──
# Anchor: SP "Week 14" == Monday 2026-06-22 (from the live article URL).
PL_WEEK_ANCHOR_MONDAY = date(2026, 6, 22)
PL_WEEK_ANCHOR_NUM = 14
# Hitter editions carry the SP week number or lag it by one; a bigger gap means
# the payload is at least a whole edition behind whatever the stamp claims.
PL_WEEK_LAG_OK = 1


def sp_week_of(monday: date) -> int:
    """PL's edition-week number for the SP list published on `monday`."""
    return PL_WEEK_ANCHOR_NUM + (monday - PL_WEEK_ANCHOR_MONDAY).days // 7


def _now_et() -> datetime:
    return datetime.now(_ET) if _ET else datetime.now()


def _latest_published_edition(now_et: datetime, weekday: int) -> date:
    """Most recent date on `weekday` whose ~7 PM ET publish moment is already past."""
    d = now_et.date()
    cand = d - timedelta(days=(d.weekday() - weekday) % 7)
    pub_moment = datetime.combine(cand, time(PL_PUBLISH_HOUR_ET), tzinfo=now_et.tzinfo)
    if pub_moment > now_et:        # this cycle's edition hasn't dropped yet
        cand -= timedelta(days=7)  # -> the prior week's is the latest live one
    return cand


def _cache_is_stale(fname: str, fetched: date, now_et: datetime | None = None,
                    week: int | None = None) -> tuple[bool, str]:
    """Cadence- and ET-time-aware staleness. Returns (is_stale, human_reason).

    `week` is the payload's recorded edition-week number, when it carries one
    (the hitter cache does). The week path only ever TIGHTENS the verdict: it
    catches content sitting an edition behind while the `fetched` stamp looks
    current (the 2026-08-18 laundered-stamp failure documented in
    build_pl_cache — two different editions carrying an identical stamp), but
    it never calls a calendar-stale cache fresh. Callers without the payload
    in hand omit it and get the calendar path unchanged.
    """
    now_et = now_et or _now_et()
    mode, val = PL_PUBLISH_CADENCE.get(fname, ('rolling', 7))
    if mode == 'weekly' and week is not None:
        cur = sp_week_of(_latest_published_edition(now_et, 0))
        if week < cur - PL_WEEK_LAG_OK:
            return True, (
                f"content is edition week {week} while PL's numbering is at week {cur} "
                f"— beyond the normal {PL_WEEK_LAG_OK}-week lag; stale regardless of "
                f"the {fetched} stamp")
    if mode == 'rolling':
        age = (now_et.date() - fetched).days
        return age > val, f"{age}d old (rolling, refresh every {val}d)"
    pub = _latest_published_edition(now_et, val)  # latest edition actually out now
    wd = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][val]
    if fetched < pub:
        return True, f"new {wd} edition out ({pub}, ~7pm ET); cache fetched {fetched}"
    return False, f"current (latest live {wd} edition {pub} already cached)"

PL_CACHE_FILES = {
    'H':         'pl_hitters_top150.json',
    'SP':        'pl_sps_top100.json',
    'SP_STREAM': 'pl_sp_streamers_latest.json',
    'RP':        'pl_closers.json',
}

# Article-universe sizes — distinguishes "snubbed" (UR) from "out-of-scope" (—).
PL_UNIVERSE_SIZE = {'H': 150, 'SP': 100, 'RP': 100}


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
    # Universe = the parsed table when we have it (issue #35 — the closers
    # parser moved 50 -> 100 rows and the static size silently lagged);
    # static size is only the no-cache floor.
    universe = max(PL_UNIVERSE_SIZE.get(bucket, 150), len(ranks))
    if isinstance(model_rank, int) and model_rank > universe:
        return '—', fetched
    return 'UR', fetched


def pl_injured_tier(name: str, bucket: str = 'SP'):
    """Return (tier|None, injury|None, cache_date) from PL's injured table.

    PL removes injured arms from the main 100 and lists them separately with the
    tier they'd hold if healthy, so `pl_rank` correctly reports 'UR' for them
    while PL in fact has an explicit opinion. Call this whenever a 'UR' needs
    disambiguating between "PL dropped him" and "PL rates him but he's hurt" —
    the IL-stash decision depends entirely on that difference.

    Deliberately separate from pl_rank(): the tier is a RANGE string ("21-30"),
    not an int, and pl_rank's (int|'UR'|'—') contract has ~20 consumers.
    """
    cache = _load_pl_cache(PL_CACHE_FILES[bucket])
    fetched = cache.get('fetched')
    nk = _norm(name)
    for pl_name, info in (cache.get('injured') or {}).items():
        if _norm(pl_name) == nk:
            return info.get('tier'), info.get('injury'), fetched
    return None, None, fetched


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
        except Exception as e:
            print(f"WARN {fname} is UNREADABLE — {e}", file=sys.stderr)
            continue
        fetched = cache.get('fetched')
        if not fetched:
            continue
        try:
            fdate = datetime.strptime(fetched[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        stale, reason = _cache_is_stale(fname, fdate, week=cache.get('week'))
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
        stale, reason = _cache_is_stale(fname, fdate, week=cache.get('week'))
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
