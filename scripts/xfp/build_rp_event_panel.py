"""build_rp_event_panel — per-appearance RELIEF panel for the RP boom study.

The SP panel keeps starts (and the relief outings around them) for pitchers who
made >= 15 starts. Relievers never enter it. This builds the mirror cohort: the
394 arms carried by `xfp_rprs2_projections.csv`, all their RELIEF appearances
(`gamesStarted == 0`), with saves and holds so BrownU RP FP is computable.

    RP FP = K + IP*3.3 - H - 2*ER - BB - HBP + 5*SV + 3*HLD

Weights come from `plv_clone.fantasy.scoring.pitcher_fp`, never hardcoded --
the holds multiplier moved 2 -> 3 on 2026-08-12 and a hardcoded copy would
have silently frozen at 2 (tests/test_no_hardcoded_scoring_weights.py).

Consumed by `validate_boom_window.py` (PLV_BOOM_SIDE=RP) and
`fit_boom_shrinkage.py`. Rule 13: diagnostic panel, feeds no model.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from plv_clone.fantasy.scoring import pitcher_fp  # noqa: E402
from plv_clone.fantasy.scoring import parse_ip as _canon_parse_ip  # noqa: E402
RPRS2 = os.path.join(ROOT, "data/outputs/xfp_rprs2_projections.csv")
OUT = os.path.join(ROOT, "data/research/xfp_cache/rp_event_panel_2017_2026.csv")

YEARS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
WORKERS = 8

FIELDS = ["pitcher", "year", "game_date", "gs", "ip", "k", "bb", "h", "er",
          "hbp", "sv", "hld", "tbf", "fp"]


def ip_to_float(s):
    # Delegates to the ONE canonical parser (issue #78). Fifteen private
    # copies of this logic is how two of them drifted (PR #77).
    return _canon_parse_ip(s, default=0.0)


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
        if st.get("gamesStarted"):        # relief appearances only
            continue
        ip = ip_to_float(st["inningsPitched"])
        k, h = st["strikeOuts"], st["hits"]
        er, bb, hbp = st["earnedRuns"], st["baseOnBalls"], st["hitByPitch"]
        sv, hld = st.get("saves", 0), st.get("holds", 0)
        rows.append({
            "pitcher": pid, "year": year, "game_date": s["date"], "gs": 0,
            "ip": round(ip, 4), "k": k, "bb": bb, "h": h, "er": er, "hbp": hbp,
            "sv": sv, "hld": hld, "tbf": st.get("battersFaced", 0),
            "fp": round(pitcher_fp(k=k, ip=ip, h=h, er=er, bb=bb, hbp=hbp,
                                    sv=sv, hld=hld), 4),
        })
    return rows


def main() -> int:
    with open(RPRS2) as fh:
        # rprs2 keys pitchers by MLBAM in its `pitcher` column.
        ids = sorted({int(float(r["pitcher"])) for r in csv.DictReader(fh)
                      if (r.get("pitcher") or "").strip()
                      and r["pitcher"].lower() not in ("nan", "none")})
    jobs = [(pid, y) for pid in ids for y in YEARS]
    print(f"fetching {len(jobs)} pitcher-years ({len(ids)} arms) ...", flush=True)
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for rows in ex.map(fetch, jobs):
            out.extend(rows)
            done += 1
            if done % 500 == 0:
                print(f"  {done}/{len(jobs)} ... {len(out)} appearances", flush=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} relief appearances -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
