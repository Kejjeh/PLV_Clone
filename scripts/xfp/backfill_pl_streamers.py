"""Backfill PL SP-streamer rank tables for the whole season.

Parses the article HTML directly rather than summarizing it. Each edition
carries two FREE rank tables (day 1 and day 2 of its 3-day title); the third
day is PL-Pro gated and simply absent from the DOM, so it is never guessed at.

Table shape: Rank | Pitcher | Matchup | Rostership, with single-cell tier
header rows ("Auto Start", "Probably Start", "Questionable Start", "Do Not
Start") separating the blocks. Player names come from the <a class="player-tag">
anchor, which is stable across editions.

Writes one JSON per edition into data/research/pl_cache/streamer_backfill/ so a
re-run resumes instead of re-fetching (and so PL is hit once per edition, ever).
"""
from __future__ import annotations

import html as ihtml
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "pyproject.toml").is_file())
OUTDIR = ROOT / "data" / "research" / "pl_cache" / "streamer_backfill"
OUTDIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pl_fetch import CURL_UA, fetch_pl  # noqa: E402

# Kept for importers that still read `UA` (the header never was the problem —
# PL's filter fingerprints the TLS handshake, hence curl via lib.pl_fetch).
UA = {"User-Agent": CURL_UA}
DELAY = 1.5          # be a polite guest; ~70 requests over the season
TIMEOUT = 25

TIERS = {
    "auto start": "Auto-Start", "auto-start": "Auto-Start",
    "probably start": "Probably Start",
    "questionable start": "Questionable", "questionable": "Questionable",
    "do not start": "Do Not Start",
}


def iso_date(tok, season=2026):
    """PL day tokens are inconsistent across editions — '2026-06-27', '6/28',
    '7-4' all appear in the same cache. Anything not normalized to ISO silently
    fails the join to actuals and drops that whole day from the sample, so
    normalize here rather than filtering later.
    """
    if tok is None:
        return None
    s = str(tok).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    for sep in ("/", "-"):
        if sep in s:
            parts = [p for p in s.split(sep) if p]
            if len(parts) == 2:
                try:
                    m, d = int(parts[0]), int(parts[1])
                    return f"{season}-{m:02d}-{d:02d}"
                except ValueError:
                    return None
    return None


def md(d: date) -> str:
    return f"{d.month}-{d.day}"


def edition_url(d: date) -> str:
    return ("https://pitcherlist.com/starting-pitcher-streamer-ranks-fantasy-baseball-"
            f"{md(d)}-{md(d + timedelta(days=1))}-{md(d + timedelta(days=2))}/")


def strip_tags(s: str) -> str:
    return ihtml.unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def parse_rank_tables(page: str) -> list[list[dict]]:
    """Return one list of {rank, name, tier, opp} per rank table, in DOM order."""
    tables = []
    for tm in re.finditer(r"<table\b.*?</table>", page, re.S | re.I):
        block = tm.group(0)
        if "player-tag" not in block:
            continue                      # matchup-grid table, not a rank table
        rows, tier = [], None
        for rm in re.finditer(r"<tr\b.*?</tr>", block, re.S | re.I):
            tr = rm.group(0)
            cells = [strip_tags(c) for c in
                     re.findall(r"<t[dh]\b.*?</t[dh]>", tr, re.S | re.I)]
            joined = " ".join(c for c in cells if c).strip().lower()
            if joined in TIERS:           # single-cell tier banner
                tier = TIERS[joined]
                continue
            key = re.sub(r"[^a-z ]", "", joined)
            if key.strip() in TIERS:
                tier = TIERS[key.strip()]
                continue
            name_m = re.search(r'<a[^>]*class="[^"]*player-tag[^"]*"[^>]*>(.*?)</a>',
                               tr, re.S | re.I)
            if not name_m:
                continue
            name = strip_tags(name_m.group(1))
            rank = None
            for c in cells:
                if re.fullmatch(r"\d{1,3}", c.strip()):
                    rank = int(c.strip())
                    break
            if rank is None or not name:
                continue
            opp = next((c for c in cells if re.search(r"^(vs|@)\s", c.strip(), re.I)), None)
            rows.append(dict(rank=rank, name=name, tier=tier, opp=opp))
        if rows:
            tables.append(rows)
    return tables


def fetch(url: str):
    # curl, not requests: PL 403s python-requests site-wide (lib.pl_fetch).
    page = fetch_pl(url, max_time=TIMEOUT)
    return (page, "ok") if page is not None else (None, "fetch failed (non-200/timeout)")


def main(start: date, end: date):
    d = start
    stats = {"hit": 0, "miss": 0, "cached": 0, "rows": 0}
    while d <= end:
        out = OUTDIR / f"streamers_{d.isoformat()}.json"
        if out.exists():
            stats["cached"] += 1
            d += timedelta(days=2)
            continue
        url = edition_url(d)
        page, status = fetch(url)
        time.sleep(DELAY)
        if page is None:
            # Publishing skips days (off-days, ASG). Try the 1-day-shifted
            # edition before giving up on this slot.
            alt = d + timedelta(days=1)
            page, status = fetch(edition_url(alt))
            time.sleep(DELAY)
            if page is None:
                print(f"  {d} MISS ({status})")
                stats["miss"] += 1
                d += timedelta(days=2)
                continue
            d = alt
            url = edition_url(alt)
            out = OUTDIR / f"streamers_{d.isoformat()}.json"

        tables = parse_rank_tables(page)
        if not tables:
            print(f"  {d} no rank table parsed")
            stats["miss"] += 1
            d += timedelta(days=2)
            continue
        # table i corresponds to day i of the title window
        by_day = {}
        for i, rows in enumerate(tables[:2]):     # day 3 is paywalled
            day = (d + timedelta(days=i)).isoformat()
            by_day[day] = {r["name"]: {"rank": r["rank"], "tier": r["tier"],
                                       "opp": r["opp"]} for r in rows}
            stats["rows"] += len(rows)
        out.write_text(json.dumps(
            {"source_url": url, "fetched": d.isoformat(),
             "covers_dates": sorted(by_day), "ranks_by_day": by_day},
            indent=1), encoding="utf-8")
        print(f"  {d} OK  days={sorted(by_day)}  "
              f"rows={sum(len(v) for v in by_day.values())}")
        stats["hit"] += 1
        d += timedelta(days=2)
    print(f"\ndone: {stats}")


if __name__ == "__main__":
    a = sys.argv[1:]
    s = date.fromisoformat(a[0]) if a else date(2026, 4, 1)
    e = date.fromisoformat(a[1]) if len(a) > 1 else date(2026, 8, 7)
    main(s, e)
