"""build_pl_cache — auto-pull Pitcher List rankings into the pl_cache JSONs (no LLM).

Replaces the manual WebFetch refresh for the date-constructible PL articles. Cadence-gated
(only pulls a ranking once its new edition has actually published, ~7 PM ET on its day —
see lib.pl_cache.PL_PUBLISH_CADENCE), so it's safe to run every morning: the SP Top 100
(Monday) is picked up Tue AM, closers (Tue) Wed AM, hitters (Wed) Thu AM.

Parsing is a plain regex over the article text (PL lists rankings as "N. Player Name"),
validated by count and written fail-soft — a short/garbled parse NEVER overwrites a good
cache (the 2026-06-19 "hitter cache corrupted to 6 entries" guardrail).

SP + closers have DATE-based URLs (predictable). Hitters use a week-number URL that lags
the SP week unpredictably, so hitters are best-effort (tries a few recent week numbers).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pl_cache import (  # noqa: E402
    PL_CACHE_DIR, _cache_is_stale, _latest_published_edition, _now_et,
)

YEAR = 2026
# Anchor: SP "Week 14" == Monday 2026-06-22 (from the live article URL).
_WEEK_ANCHOR_MONDAY = date(2026, 6, 22)
_WEEK_ANCHOR_NUM = 14
UA = {"User-Agent": "Mozilla/5.0 (compatible; plv-clone-pl-cache/1.0)"}

# (cache file, min valid count, universe label)
_VALID_MIN = {"pl_sps_top100.json": 90, "pl_hitters_top150.json": 140, "pl_closers.json": 40}


def _sp_week(monday: date) -> int:
    return _WEEK_ANCHOR_NUM + (monday - _WEEK_ANCHOR_MONDAY).days // 7


def _md(d: date) -> str:
    return f"{d.month}-{d.day}"


def _sp_url(slug_date: date, week: int) -> str:
    return (f"https://pitcherlist.com/top-100-starting-pitchers-for-{YEAR}-fantasy-baseball-"
            f"{_md(slug_date)}-week-{week}-rankings/")


def sp_url(monday: date) -> str:
    return _sp_url(monday, _sp_week(monday))


def sp_url_candidates(latest_monday: date):
    """Yield (url, edition_monday) candidates, newest-first, for the SP Top 100.

    PL usually publishes on Monday, but occasionally slips to Tuesday on holiday
    weeks — e.g. 6/30 (week 15, July 4th week) and 5/26 (week 10, Memorial Day)
    are dated Tue, not the Monday our edition math computes — and it can skip or
    lag a week entirely. So for each of the latest three weeks we try the Monday
    slug AND the Tuesday (Monday+1) slug, and take the first that returns a full
    list — instead of failing outright the moment the exact-Monday URL 404s
    (which stranded the cache 13 days at week 14 when week 15 published as 6/30).
    """
    for wk_back in range(3):
        mon = latest_monday - timedelta(days=7 * wk_back)
        week = _sp_week(mon)
        for day_off in (0, 1):  # Monday, then the holiday-shifted Tuesday
            yield _sp_url(mon + timedelta(days=day_off), week), mon


def closers_url(tuesday: date) -> str:
    return (f"https://pitcherlist.com/fantasy-reliever-rankings-closers-holds-solds-"
            f"{_md(tuesday)}/")


def hitters_urls(sp_week: int):
    # hitter week number lags the SP week unpredictably -> try a few recent ones
    for w in (sp_week, sp_week - 1, sp_week - 2):
        yield f"https://pitcherlist.com/top-150-hitters-for-fantasy-baseball-{YEAR}-week-{w}/", w


def parse_rank_table(html_text: str, limit: int):
    """Parse PL's GLOBAL ranked table — used for BOTH the Top 100 SP and Top 150 hitters.
    Each ranked row is <tr>...<td class="rank">N</td><td class="name"><a>Player</a>...
    <td class="positions">POS</td>...</tr>. Returns ({name: rank}, {name: position}).
    (PL articles also include a secondary by-position tier block; iterating the rank-table
    <tr> rows specifically avoids picking that up — the bug that mis-ranked hitters.)"""
    import html as _html
    out, positions, taken = {}, {}, set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S):
        rk = re.search(r'<td class="rank">(\d+)</td>', tr)
        nm = re.search(r'<td class="name"><a[^>]*>([^<]+)</a>', tr)
        if not (rk and nm):
            continue
        rank = int(rk.group(1))
        name = _html.unescape(nm.group(1)).strip()
        # Dedupe on BOTH name and rank. A ranked list is a bijection: two players
        # sharing a rank means a row from a secondary table leaked in, and the
        # main table comes first in document order, so the first wins. Without
        # this the stray row silently becomes a peak — the cached 2026-07-18 SP
        # edition carried a phantom "#5" that outranked every real FA starter.
        if rank <= limit and name and name not in out and rank not in taken:
            out[name] = rank
            taken.add(rank)
            pos = re.search(r'<td class="positions">([^<]*)</td>', tr)
            if pos and pos.group(1).strip():
                positions[name] = pos.group(1).strip()
    return out, positions


def parse_injured_table(html_text: str):
    """Parse PL's "Injured Pitchers Who Will Be Considered When Healthy" table.

    PL pulls injured arms OUT of the main 100 and into a separate table holding
    the tier they'd occupy if healthy. Without this, every IL'd pitcher parses
    as absent and reads downstream as 'UR' — indistinguishable from "PL dropped
    him". Canonical miss: Glasnow (1-10) and Pivetta (21-30) were held at those
    tiers for 17 straight weeks while our cache showed them unranked all season.

    The tier is a RANGE ("21-30"), not an integer, so it is deliberately kept
    out of `ranks`: merging it there would corrupt rank arithmetic in every
    consumer and inflate the _write_cache count guard with non-rank rows.

    Rows: <td><a ... href=".../player/slug/">Name</a></td><td>Injury</td>
          <td>Tier</td>. Returns {name: {"tier": str, "injury": str}}.
    """
    import html as _html
    # Scope to the injured table: its branding title, through that table's end.
    title = re.search(r'<div class="title">([^<]*Injured[^<]*)</div>', html_text, re.I)
    if not title:
        return {}
    seg = html_text[title.end():]
    end = seg.find("</table>")
    if end == -1:
        return {}
    seg = seg[:end]

    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 3:
            continue
        nm = re.search(r"<a[^>]*>([^<]+)</a>", cells[0])
        if not nm:
            continue
        name = _html.unescape(nm.group(1)).strip()
        injury = _html.unescape(re.sub(r"<[^>]+>", "", cells[1])).strip()
        tier = _html.unescape(re.sub(r"<[^>]+>", "", cells[2])).strip()
        # A tier is always a range like "21-30"; anything else is a parse slip.
        if name and re.fullmatch(r"\d+\s*-\s*\d+", tier):
            out[name] = {"tier": tier.replace(" ", ""), "injury": injury}
    return out


# Reliever role -> rank tier (closers rank above setup above middle relief; within a
# tier, by descending save-chance %). Closer-ish roles all rank as "closer".
_CLOSER_ROLE_PRI = {"Closer": 0, "Co-Closer": 1, "Interim Closer": 2, "Closer?": 3,
                    "Setup Role": 4, "Middle Relief": 5}


def parse_closers(html_text: str):
    """Parse PL's per-team reliever TABLE (role / player / save%). Returns
    ({name: rank}, {name: {role, save_pct}}). Rank orders closers (by save% desc)
    above setup above middle relief — a faithful fantasy-reliever ranking."""
    import html as _html
    rows = re.findall(
        r'<td class="emphasis"><strong>([^<]+)</strong></td>\s*'
        r'<td><a[^>]*player/[^>]*>([^<]+)</a></td>'
        r'(?:\s*<td><em>([^<]*)</em></td>)?', html_text)
    recs = []
    for role, name, pct in rows:
        role = role.strip()
        name = _html.unescape(name).strip()
        sv = int(re.sub(r"[^0-9]", "", pct) or 0)
        if name:
            recs.append((role, name, sv))
    recs.sort(key=lambda r: (_CLOSER_ROLE_PRI.get(r[0], 9), -r[2]))
    ranks, roles = {}, {}
    for role, name, sv in recs:
        if name in ranks:
            continue
        ranks[name] = len(ranks) + 1
        roles[name] = {"role": role, "save_pct": sv}
    return ranks, roles


def _write_cache(fname: str, url: str, ranks: dict, edition: date, extra: dict | None = None) -> bool:
    min_n = _VALID_MIN.get(fname, 40)
    if len(ranks) < min_n:
        print(f"  SKIP {fname}: parsed only {len(ranks)} ranks (< {min_n}) — not overwriting",
              file=sys.stderr)
        return False
    path = Path(PL_CACHE_DIR) / fname
    payload = {"fetched": edition.isoformat(), "source_url": url, "ranks": ranks}
    if extra:
        payload.update(extra)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"  WROTE {fname}: {len(ranks)} ranks (edition {edition}) <- {url}")
    return True


def _fetch(url: str):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def refresh(force=False):
    now = _now_et()
    cur = {f: _cache_fetched(f) for f in _VALID_MIN}
    # SP — Monday edition (global ranked table)
    if force or _stale("pl_sps_top100.json", cur, now):
        latest_mon = _latest_published_edition(now, 0)
        wrote, last_url = False, None
        for url, edition in sp_url_candidates(latest_mon):
            last_url = url
            html = _fetch(url)
            if not html:
                continue
            ranks, _pos = parse_rank_table(html, 100)
            injured = parse_injured_table(html)
            if _write_cache("pl_sps_top100.json", url, ranks, edition,
                            extra={"injured": injured} if injured else None):
                wrote = True
                break
        if not wrote:
            print(f"  SP fetch failed (tried Mon/Tue across 3 weeks); last: {last_url}",
                  file=sys.stderr)
    else:
        print("  SP current — skip")
    # Closers — Tuesday edition (per-team role table -> role + save% + synthesized rank)
    if force or _stale("pl_closers.json", cur, now):
        tue = _latest_published_edition(now, 1)
        html = _fetch(closers_url(tue))
        if html:
            ranks, roles = parse_closers(html)
            _write_cache("pl_closers.json", closers_url(tue), ranks, tue, extra={"roles": roles})
        else:
            print(f"  closers fetch failed: {closers_url(tue)}", file=sys.stderr)
    else:
        print("  closers current — skip")
    # Hitters — Wednesday edition (position-tiered; try recent week-number URLs)
    if force or _stale("pl_hitters_top150.json", cur, now):
        wed = _latest_published_edition(now, 2)
        for url, _w in hitters_urls(_sp_week(_latest_published_edition(now, 0))):
            html = _fetch(url)
            if html:
                ranks, positions = parse_rank_table(html, 150)
                if len(ranks) >= _VALID_MIN["pl_hitters_top150.json"]:
                    _write_cache("pl_hitters_top150.json", url, ranks, wed,
                                 extra={"positions": positions})
                    break
        else:
            print("  hitters: no week-number URL returned a full list (best-effort)", file=sys.stderr)
    else:
        print("  hitters current — skip")


def _cache_fetched(fname):
    path = Path(PL_CACHE_DIR) / fname
    if not path.exists():
        return None
    try:
        return datetime.strptime(json.loads(path.read_text(encoding="utf-8"))
                                 .get("fetched", "")[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _stale(fname, cur, now):
    f = cur.get(fname)
    return True if f is None else _cache_is_stale(fname, f, now)[0]


if __name__ == "__main__":
    force = "--force" in sys.argv
    print("=== PL cache auto-pull (cadence-gated) ===")
    refresh(force=force)
