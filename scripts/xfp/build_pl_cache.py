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


def sp_url(monday: date) -> str:
    return (f"https://pitcherlist.com/top-100-starting-pitchers-for-{YEAR}-fantasy-baseball-"
            f"{_md(monday)}-week-{_sp_week(monday)}-rankings/")


def closers_url(tuesday: date) -> str:
    return (f"https://pitcherlist.com/fantasy-reliever-rankings-closers-holds-solds-"
            f"{_md(tuesday)}/")


def hitters_urls(sp_week: int):
    # hitter week number lags the SP week unpredictably -> try a few recent ones
    for w in (sp_week, sp_week - 1, sp_week - 2):
        yield f"https://pitcherlist.com/top-150-hitters-for-fantasy-baseball-{YEAR}-week-{w}/", w


def parse_ranks(html_text: str, limit: int) -> dict:
    """Extract {player_name: rank} from a PL article's HTML (regex over unescaped text)."""
    import html as _html
    txt = _html.unescape(re.sub(r"<[^>]+>", " ", html_text))
    out = {}
    for rk, nm in re.findall(
            r"(?<![\d.])(\d{1,3})\.\s+([A-Z][A-Za-zÀ-ſ.'\" -]{2,30}?)"
            r"(?=\s{2,}|\s*[,(–-])", txt):
        rk = int(rk)
        if 1 <= rk <= limit and rk not in (v for v in out.values()):
            name = nm.strip()
            if name and name not in out:
                out[name] = rk
    # keep one name per rank, ranks 1..limit
    by_rank = {}
    for name, rk in out.items():
        by_rank.setdefault(rk, name)
    return {name: rk for rk, name in sorted(by_rank.items()) if rk <= limit}


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


def parse_hitters(html_text: str):
    """Parse PL's position-tiered Top-150 hitters (no global numbering). Returns
    ({name: rank}, {name: position}). 'rank' is article appearance order — the only
    signal available; the list is grouped by fielding position, not globally ranked."""
    import html as _html
    pat = re.compile(
        r'(?:font-size:\s*16pt[^>]*><strong>([^<]+)</strong>)'
        r'|(?:<a class="player-tag" href="https://pitcherlist\.com/player/[^>]+>([^<]+)</a>)')
    ranks, positions, cur = {}, {}, ""
    for m in pat.finditer(html_text):
        if m.group(1):
            cur = m.group(1).strip()
        elif m.group(2):
            name = _html.unescape(m.group(2)).strip()
            if name and name not in ranks:
                ranks[name] = len(ranks) + 1
                positions[name] = cur
    return ranks, positions


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
    # SP — Monday edition
    if force or _stale("pl_sps_top100.json", cur, now):
        mon = _latest_published_edition(now, 0)
        html = _fetch(sp_url(mon))
        if html:
            _write_cache("pl_sps_top100.json", sp_url(mon), parse_ranks(html, 100), mon)
        else:
            print(f"  SP fetch failed: {sp_url(mon)}", file=sys.stderr)
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
                ranks, positions = parse_hitters(html)
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
