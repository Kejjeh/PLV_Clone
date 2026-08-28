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

import requests  # noqa: F401  (kept: other callers import UA/this module)

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pl_cache import (  # noqa: E402
    PL_CACHE_DIR, _cache_is_stale, _latest_published_edition, _now_et, sp_week_of,
)
from lib.pl_fetch import CURL_UA as _CURL_UA, fetch_pl  # noqa: E402,F401

YEAR = 2026
UA = {"User-Agent": "Mozilla/5.0 (compatible; plv-clone-pl-cache/1.0)"}

# (cache file, min valid count, universe label)
# Streamer floor is 40: one edition carries two FREE day-tables of ~25-45 rows
# each (day 3 is PL-Pro gated), so a healthy pull lands ~60-90 flat rows.
_VALID_MIN = {"pl_sps_top100.json": 90, "pl_hitters_top150.json": 140,
              "pl_closers.json": 90, "pl_sp_streamers_latest.json": 40}


def _sp_week(monday: date) -> int:
    return sp_week_of(monday)  # single owner: lib.pl_cache (don't-do #18)


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


def closers_url_candidates(latest_tuesday: date):
    """Yield (url, edition_tuesday) newest-first (issue #35). Mirrors
    sp_url_candidates: PL slips the reliever article to Wednesday on holiday
    weeks, and a single-URL fetch stranded the cache indefinitely."""
    for wk_back in range(3):
        tue = latest_tuesday - timedelta(days=7 * wk_back)
        for day_off in (0, 1):  # Tuesday, then the holiday-shifted Wednesday
            yield closers_url(tue + timedelta(days=day_off)), tue


def hitter_edition_stamp(prev_week, prev_fetched, resolved_week, calendar_wed):
    """The `fetched` stamp for the hitter cache (issue #35). Re-serving the
    already-cached week keeps the OLD stamp so staleness keeps accruing —
    stamping the calendar date made a week-behind cache look current."""
    if prev_week is not None and prev_fetched and resolved_week == prev_week:
        try:
            return date.fromisoformat(str(prev_fetched))
        except ValueError:
            pass
    return calendar_wed


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
    """Parse PL's reliever article.

    The article carries TWO structures and only one of them is a RANKING:

    1. A global ranked table -- identical markup to the SP Top 100
       (``td.rank`` + ``td.name``), 100 rows, ordered by PL's actual
       saves+holds valuation. THIS is the ranking.
    2. Per-team "CLOSER SITUATION" boxes giving role + save-chance %.
       These are role CONTEXT for one bullpen, not a cross-team ordering.

    Until 2026-08-18 this function ignored (1) entirely and SYNTHESIZED a rank
    by sorting (2) on role-priority then save%. That ordering does not match
    PL's published list and produced real errors: Latz parsed #9 vs a true #6,
    Montgomery #21 vs a true #14, and Aroldis Chapman landed at #20 on a
    save_pct of 0. Ranks now come from the ranked table; the role boxes are
    kept as ``roles`` because save-chance % is genuinely useful and appears
    nowhere else.

    Returns ({name: rank}, {name: {role, save_pct, move}}).
    """
    import html as _html
    ranks, _pos = parse_rank_table(html_text, 100)

    # PL's own week-over-week move lives in the ranked table's last cell
    # ("+16", "-3", "+UR", "-"). Prefer it over diffing two cached editions:
    # it is authoritative and survives a skipped edition.
    #
    # The page carries the CURRENT ranked table AND last week's, so a given
    # pitcher appears twice with different rank/move. Document order puts the
    # current table first, so FIRST WINS here -- exactly as parse_rank_table
    # dedupes. Letting the last win silently swapped in stale moves (Tanner
    # Scott read -1 from the prior table instead of his true +16).
    moves = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S):
        nm = re.search(r'<td class="name"><a[^>]*>([^<]+)</a>', tr)
        if not nm:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 5:
            continue
        name = _html.unescape(nm.group(1)).strip()
        if name in moves:
            continue
        mv = _html.unescape(re.sub(r"<[^>]+>", "", cells[-1])).strip()
        moves[name] = mv

    # Role / save-chance % from the per-team boxes (context, never the rank).
    # Parsed structurally off the 3-cell role row rather than by a regex that
    # assumed the percent sat in <em> -- it does not always, and the optional
    # group silently yielded 0% (Chapman read 0 on a real 75).
    roles = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) != 3:
            continue
        nm = re.search(r'<a[^>]*player/[^>]*>([^<]+)</a>', cells[1])
        if not nm:
            continue
        name = _html.unescape(nm.group(1)).strip()
        if not name or name in roles:
            continue
        role = _html.unescape(re.sub(r"<[^>]+>", "", cells[0])).strip()
        pct = re.sub(r"[^0-9]", "", re.sub(r"<[^>]+>", "", cells[2]))
        roles[name] = {"role": role or None,
                       "save_pct": int(pct) if pct else None}

    for name, mv in moves.items():
        roles.setdefault(name, {"role": None, "save_pct": None})["move"] = mv
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
    """Fetch a PL article — delegates to lib.pl_fetch, the curl workaround's
    single owner (PL's bot filter 403s python-requests on its TLS handshake)."""
    return fetch_pl(url)


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
        wrote_cl = False
        last_cl = None
        for url, ed_tue in closers_url_candidates(tue):
            last_cl = url
            html = _fetch(url)
            if not html:
                continue
            ranks, roles = parse_closers(html)
            if len(ranks) >= _VALID_MIN["pl_closers.json"]:
                _write_cache("pl_closers.json", url, ranks, ed_tue, extra={"roles": roles})
                wrote_cl = True
                break
        if not wrote_cl:
            print(f"  closers fetch failed (tried Tue/Wed across 3 weeks); last: {last_cl}",
                  file=sys.stderr)
    else:
        print("  closers current — skip")
    # Hitters — Wednesday edition (position-tiered; try recent week-number URLs)
    if force or _stale("pl_hitters_top150.json", cur, now):
        wed = _latest_published_edition(now, 2)
        # The hitter week number lags the SP week UNPREDICTABLY, so we probe
        # backwards and take the newest week that resolves. The edition date
        # stamped below is the calendar Wednesday, which is NOT necessarily the
        # week that answered: on 2026-08-18, weeks 22 and 21 both 404'd and
        # week 20 served -- yet the payload was stamped 2026-08-12 exactly as
        # the previous week-19 pull had been. Two different editions carrying an
        # identical `fetched` date made the cache look current while it sat a
        # full week behind. Record the resolved week so staleness can be judged
        # on CONTENT rather than on the calendar.
        for url, _w in hitters_urls(_sp_week(_latest_published_edition(now, 0))):
            html = _fetch(url)
            if html:
                ranks, positions = parse_rank_table(html, 150)
                if len(ranks) >= _VALID_MIN["pl_hitters_top150.json"]:
                    _prev = _load_cache_raw("pl_hitters_top150.json")
                    stamp = hitter_edition_stamp(
                        (_prev.get("week") if _prev else None),
                        (_prev.get("fetched") if _prev else None), _w, wed)
                    _write_cache("pl_hitters_top150.json", url, ranks, stamp,
                                 extra={"positions": positions, "week": _w})
                    break
        else:
            print("  hitters: no week-number URL returned a full list (best-effort)", file=sys.stderr)
    else:
        print("  hitters current — skip")
    # SP streamers — rolling 2-3 day editions (two free day-tables; day 3 gated)
    if force or _stale("pl_sp_streamers_latest.json", cur, now):
        refresh_streamers(now)
    else:
        print("  streamers current — skip")


def refresh_streamers(now):
    """Pull the newest SP-streamer edition into pl_sp_streamers_latest.json.

    Until 2026-08-28 this cache had NO auto-refresher — build_pl_cache covered
    the three weekly lists while the rolling streamer file was refreshed by
    hand, which is exactly how it sat 10 days stale at the 08-28 handoff.

    An edition's URL is dated by its first covered day, so the edition covering
    today is dated today, yesterday, or the day before. Probe newest-first and
    keep the newest FREE day-table at or before today (day 3 is paywalled and
    absent from the DOM, so a today-2 edition contributes yesterday's table —
    still 8 days fresher than the stale cache this replaces). Flat `ranks`
    mirror the hand-built schema: {name: {rank, tier, opp, date}}, stamped
    `fetched` = the edition's first day so rolling staleness keeps accruing
    from CONTENT age, never the pull date.
    """
    from backfill_pl_streamers import edition_url, parse_rank_tables

    today = now.date()
    # Probe TOMORROW first: PL posts an edition the evening before its first
    # covered day, so the newest edition is often forward-dated (caught
    # 2026-08-28 — the 8/29-8/31 edition dropped on the 28th and a
    # backward-only probe kept re-serving the 8/27 one).
    for back in range(-1, 3):
        ed = today - timedelta(days=back)
        url = edition_url(ed)
        html = _fetch(url)
        if not html:
            continue
        tables = parse_rank_tables(html)
        if not tables:
            continue
        by_day, flat, primary = {}, {}, None
        for i, rows in enumerate(tables[:2]):  # free tables only
            day = ed + timedelta(days=i)
            # future days are KEPT — a forward-dated edition is the point of
            # the tomorrow-probe; benching decisions need tomorrow's slate.
            by_day[day.isoformat()] = {
                r["name"]: {"rank": r["rank"], "tier": r["tier"], "opp": r["opp"]}
                for r in rows}
            primary = day  # tables run oldest->newest; last wins
        if primary is None:
            continue
        for day_iso in sorted(by_day):
            md_tag = f"{int(day_iso[5:7])}/{int(day_iso[8:10])}"
            for name, info in by_day[day_iso].items():
                flat[name] = {**info, "date": md_tag}
        if _write_cache(
                "pl_sp_streamers_latest.json", url, flat, ed,
                extra={"covers_dates": sorted(by_day),
                       "primary_date": primary.isoformat(),
                       "ranks_by_day": by_day,
                       "note": "auto-pulled; free day-tables only (day 3 is PL-Pro gated)"}):
            return
    print("  streamers: no edition URL in the last 3 days returned a rank table",
          file=sys.stderr)


def _load_cache_raw(fname):
    """Existing cache payload as a dict, or None (issue #35)."""
    path = Path(PL_CACHE_DIR) / fname
    if not path.exists():
        return None
    try:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


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
    if f is None:
        return True
    raw = _load_cache_raw(fname)
    return _cache_is_stale(fname, f, now,
                           week=(raw.get("week") if raw else None))[0]


if __name__ == "__main__":
    force = "--force" in sys.argv
    print("=== PL cache auto-pull (cadence-gated) ===")
    refresh(force=force)
