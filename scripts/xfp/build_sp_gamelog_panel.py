"""Build a per-start SP game-log panel from the MLB Stats API.

Substrate for `validate_stuff_regime_delta.py`. Exists because the
in-season rolling panel (`rolling_pitchers_2018_2026.csv`) and the per-year
statcast parquets are not always available, while game logs give the
K / TBF / IP / H / ER / BB / HBP components the BrownU SP FP formula needs:

    FP = K + IP*3.3 - H - 2*ER - BB - HBP

Pitcher-year cohort is taken from sp_multiyr (gs >= MIN_GS) so the panel
matches the population the xfp models are fit on.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from plv_clone.fantasy.scoring import parse_ip as _canon_parse_ip  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MULTIYR = os.path.join(ROOT, "data/research/xfp_cache/sp_multiyr_2015_2025.csv")
OUT = os.path.join(ROOT, "data/research/xfp_cache/sp_gamelogs_2017_2026.csv")

YEARS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
MIN_GS = 15
WORKERS = 8

FIELDS = [
    "pitcher", "year", "start_idx", "game_date",
    "ip", "k", "h", "er", "bb", "hbp", "tbf", "fp",
]


def ip_to_float(s: str) -> float:
    """MLB reports IP as 5.1 / 5.2 meaning 5 1/3 / 5 2/3 innings."""
    # Delegates to the ONE canonical parser (issue #78). Fifteen private
    # copies of this logic is how two of them drifted (PR #77).
    return _canon_parse_ip(s, default=0.0)


def sp_fp(k: int, ip: float, h: int, er: int, bb: int, hbp: int) -> float:
    return k + ip * 3.3 - h - 2 * er - bb - hbp


def fetch(pid_year):
    pid, year = pid_year
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
        f"?stats=gameLog&group=pitching&season={year}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            splits = json.load(r)["stats"][0]["splits"]
    except Exception:
        return []
    rows, idx = [], 0
    for s in sorted(splits, key=lambda x: x["date"]):
        st = s["stat"]
        if st.get("gamesStarted") != 1:
            continue
        idx += 1
        ip = ip_to_float(st["inningsPitched"])
        k, h = st["strikeOuts"], st["hits"]
        er, bb, hbp = st["earnedRuns"], st["baseOnBalls"], st["hitByPitch"]
        rows.append({
            "pitcher": pid, "year": year, "start_idx": idx, "game_date": s["date"],
            "ip": round(ip, 4), "k": k, "h": h, "er": er, "bb": bb, "hbp": hbp,
            "tbf": st.get("battersFaced", 0),
            "fp": round(sp_fp(k, ip, h, er, bb, hbp), 4),
        })
    return rows


def cohort():
    seen = set()
    with open(MULTIYR) as fh:
        for r in csv.DictReader(fh):
            y = int(r["year"])
            if y in YEARS and float(r.get("gs") or 0) >= MIN_GS:
                seen.add((int(r["pitcher"]), y))
    return sorted(seen)


def main() -> int:
    jobs = cohort()
    print(f"fetching {len(jobs)} pitcher-years with {WORKERS} workers ...", flush=True)
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for rows in ex.map(fetch, jobs):
            out.extend(rows)
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(jobs)} ... {len(out)} starts", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} starts -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
