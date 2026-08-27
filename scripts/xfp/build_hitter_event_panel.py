"""build_hitter_event_panel — per-game hitter panel for the noise-floor study.

Hitter mirror of build_sp_event_panel. Captures team (for TRADE detection) and
the K/BB/PA components needed to compute within-season rate variation, plus the
BrownU hitter FP line:  R + TB + RBI + BB + HBP + SB - K
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MULTIYR = os.path.join(ROOT, "data/research/xfp_cache/hitters_multiyr_2015_2026.csv")
OUT = os.path.join(ROOT, "data/research/xfp_cache/hitter_event_panel_2017_2026.csv")

YEARS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
MIN_PA = 300
WORKERS = 8
FIELDS = ["batter", "year", "game_date", "team_id", "pa", "ab", "k", "bb",
          "h", "hr", "tb", "r", "rbi", "sb", "hbp", "fp"]


def fetch(job):
    bid, year = job
    url = (f"https://statsapi.mlb.com/api/v1/people/{bid}/stats"
           f"?stats=gameLog&group=hitting&season={year}")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            splits = json.load(r)["stats"][0]["splits"]
    except Exception:
        return []
    rows = []
    for s in sorted(splits, key=lambda x: x["date"]):
        st = s["stat"]
        pa = st.get("plateAppearances", 0)
        if not pa:
            continue
        h, d2, d3 = st.get("hits", 0), st.get("doubles", 0), st.get("triples", 0)
        hr = st.get("homeRuns", 0)
        tb = (h - d2 - d3 - hr) + 2 * d2 + 3 * d3 + 4 * hr
        k, bb = st.get("strikeOuts", 0), st.get("baseOnBalls", 0)
        rr, rbi = st.get("runs", 0), st.get("rbi", 0)
        sb, hbp = st.get("stolenBases", 0), st.get("hitByPitch", 0)
        tm = s.get("team") or {}
        rows.append({"batter": bid, "year": year, "game_date": s["date"],
                     "team_id": tm.get("id"), "pa": pa, "ab": st.get("atBats", 0),
                     "k": k, "bb": bb, "h": h, "hr": hr, "tb": tb, "r": rr,
                     "rbi": rbi, "sb": sb, "hbp": hbp,
                     "fp": rr + tb + rbi + bb + hbp + sb - k})
    return rows


def main() -> int:
    seen = set()
    with open(MULTIYR) as fh:
        for r in csv.DictReader(fh):
            y = int(r["year"])
            if y in YEARS and float(r.get("pa") or 0) >= MIN_PA:
                seen.add((int(r["batter"]), y))
    jobs = sorted(seen)
    print(f"fetching {len(jobs)} hitter-years ...", flush=True)
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for rows in ex.map(fetch, jobs):
            out.extend(rows)
            done += 1
            if done % 400 == 0:
                print(f"  {done}/{len(jobs)} ... {len(out)} games", flush=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} games -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
