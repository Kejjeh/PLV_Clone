"""backfill_pl_cache — recover PL editions missing from pl_cache/ (one-off, idempotent).

Two gaps this closes:
  1. SEASON START. The cache begins at SP week 10 (5/26) and hitter week 9 (5/30).
     Every edition before that — the whole first two months — was never archived,
     so any player who got hurt early reads as "never ranked" for the entire year.
     Canonical: Glasnow peaked at #10 (wk 7) and Pivetta at #22 (wk 3); both showed
     UR in all 12 cached editions.
  2. CORRUPT SCRAPES. pl_hitters_top150_2026-06-09.json holds 4 of 150 ranks. A
     short parse must never be archived as if it were an edition.

Writes DATED snapshots (pl_<series>_<edition>.json) matching the archiver's schema,
plus the `injured` table now captured by build_pl_cache.parse_injured_table.
Never overwrites a healthy existing snapshot unless --force.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pl_cache import (  # noqa: E402
    UA, YEAR, _sp_url, _sp_week, parse_injured_table, parse_rank_table,
)
from lib.pl_cache import (  # noqa: E402
    PL_CACHE_DIR, PL_WEEK_ANCHOR_MONDAY, PL_WEEK_ANCHOR_NUM,
)

MIN_SP, MIN_H = 90, 140


def _monday_for_week(week: int) -> date:
    # single anchor owner: lib.pl_cache (don't-do #18)
    return PL_WEEK_ANCHOR_MONDAY + timedelta(days=7 * (week - PL_WEEK_ANCHOR_NUM))


def _fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=UA, timeout=30)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def _published_date(html: str) -> str | None:
    """PL stamps the real publish time in og/article meta — trust it over the slug."""
    for pat in (r'property="article:published_time"\s+content="(\d{4}-\d{2}-\d{2})',
                r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})'):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def _write(fname: str, payload: dict, force: bool) -> str:
    path = Path(PL_CACHE_DIR) / fname
    if path.exists() and not force:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if len(existing.get("ranks") or {}) >= len(payload["ranks"]):
                return "skip-existing"
        except Exception:
            pass
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return "wrote"


def backfill_sp(weeks, force=False):
    for wk in weeks:
        mon = _monday_for_week(wk)
        html = url = None
        for off in (0, 1, 2):  # Mon, holiday-shifted Tue, occasional Wed
            cand = _sp_url(mon + timedelta(days=off), wk)
            html = _fetch(cand)
            if html:
                url = cand
                break
        if not html:
            print(f"  wk{wk:<3} SP  MISS   (no URL resolved around {mon})")
            continue
        ranks, _pos = parse_rank_table(html, 100)
        injured = parse_injured_table(html)
        if len(ranks) < MIN_SP:
            print(f"  wk{wk:<3} SP  SHORT  parsed {len(ranks)} < {MIN_SP} — refusing to archive")
            continue
        ed = _published_date(html) or (mon.isoformat())
        payload = {"fetched": ed, "source_url": url, "ranks": ranks, "injured": injured}
        act = _write(f"pl_sps_top100_{ed}.json", payload, force)
        print(f"  wk{wk:<3} SP  {act:<13} {ed}  ranks={len(ranks)} injured={len(injured)}")


def backfill_hitters(weeks, force=False):
    for wk in weeks:
        url = f"https://pitcherlist.com/top-150-hitters-for-fantasy-baseball-{YEAR}-week-{wk}/"
        html = _fetch(url)
        if not html:
            print(f"  wk{wk:<3} H   MISS   {url}")
            continue
        ranks, positions = parse_rank_table(html, 150)
        if len(ranks) < MIN_H:
            print(f"  wk{wk:<3} H   SHORT  parsed {len(ranks)} < {MIN_H} — refusing to archive")
            continue
        ed = _published_date(html)
        if not ed:
            print(f"  wk{wk:<3} H   NO-DATE (cannot date the edition) — skipped")
            continue
        payload = {"fetched": ed, "source_url": url, "ranks": ranks, "positions": positions}
        act = _write(f"pl_hitters_top150_{ed}.json", payload, force)
        print(f"  wk{wk:<3} H   {act:<13} {ed}  ranks={len(ranks)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sp-weeks", default="2-13")
    ap.add_argument("--hitter-weeks", default="1-13")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-hitters", action="store_true")
    ap.add_argument("--skip-sp", action="store_true")
    a = ap.parse_args()

    def rng(s):
        lo, _, hi = s.partition("-")
        return range(int(lo), int(hi or lo) + 1)

    print("=== PL cache backfill ===")
    if not a.skip_sp:
        backfill_sp(rng(a.sp_weeks), a.force)
    if not a.skip_hitters:
        backfill_hitters(rng(a.hitter_weeks), a.force)
