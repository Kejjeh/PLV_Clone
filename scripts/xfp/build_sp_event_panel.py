"""build_sp_event_panel — per-appearance SP panel WITH the fields needed to
classify in-season events.

The base game-log panel keeps only pitching lines. Classifying events needs two
more things it never captured:

  team          to detect a TRADE (team changes mid-season)
  gamesStarted  to detect a ROLE change (relief appearances between starts),
                which means relief outings must be KEPT, not filtered out

Cohort matches the base panel so results are comparable.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MULTIYR = os.path.join(ROOT, "data/research/xfp_cache/sp_multiyr_2015_2025.csv")
OUT = os.path.join(ROOT, "data/research/xfp_cache/sp_event_panel_2017_2026.csv")

YEARS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
MIN_GS = 15
WORKERS = 8

FIELDS = ["pitcher", "year", "game_date", "gs", "team_id", "team",
          "ip", "k", "bb", "h", "er", "hbp", "tbf", "fp"]


def ip_to_float(s):
    w, _, f = str(s).partition(".")
    return int(w) + (int(f) / 3 if f else 0.0)


def fetch(pid_year):
    pid, year = pid_year
    url = (f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
           f"?stats=gameLog&group=pitching&season={year}")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            splits = json.load(r)["stats"][0]["splits"]
    except Exception:
        return []
    rows = []
    for s in sorted(splits, key=lambda x: x["date"]):
        st = s["stat"]
        ip = ip_to_float(st["inningsPitched"])
        k, h = st["strikeOuts"], st["hits"]
        er, bb, hbp = st["earnedRuns"], st["baseOnBalls"], st["hitByPitch"]
        tm = s.get("team") or {}
        rows.append({
            "pitcher": pid, "year": year, "game_date": s["date"],
            "gs": st.get("gamesStarted", 0),
            "team_id": tm.get("id"), "team": tm.get("abbreviation") or tm.get("name"),
            "ip": round(ip, 4), "k": k, "bb": bb, "h": h, "er": er, "hbp": hbp,
            "tbf": st.get("battersFaced", 0),
            "fp": round(k + ip * 3.3 - h - 2 * er - bb - hbp, 4),
        })
    return rows


def main() -> int:
    seen = set()
    with open(MULTIYR) as fh:
        for r in csv.DictReader(fh):
            y = int(r["year"])
            if y in YEARS and float(r.get("gs") or 0) >= MIN_GS:
                seen.add((int(r["pitcher"]), y))
    jobs = sorted(seen)
    print(f"fetching {len(jobs)} pitcher-years (incl. relief appearances) ...", flush=True)
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for rows in ex.map(fetch, jobs):
            out.extend(rows)
            done += 1
            if done % 300 == 0:
                print(f"  {done}/{len(jobs)} ... {len(out)} appearances", flush=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} appearances -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
