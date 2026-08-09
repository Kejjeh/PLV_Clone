"""build_hitter_luck_baseline — per-season actual-vs-expected wOBA, all hitters.

WHY THIS CACHE EXISTS
---------------------
The luck lens reads `gap = wOBA - xwOBA` and calls anything past +/-0.020
OVERPERFORMING / UNDERPERFORMING. That threshold is calibrated to the FIELD,
where the gap centers on zero (2025, 300+ PA: mean -0.001, sd 0.018) and
genuinely mean-reverts.

Some hitters' personal mean is not zero. Jose Altuve beat his xwOBA in 10 of
11 full seasons at a PA-weighted +0.030 — a 94th-percentile single-season
figure that he has now repeated for a decade. Reading his 2026 +0.030 as
"due for negative regression" (as the field-relative lens did on 2026-08-09)
is a false alarm: it is his norm, not his luck. xwOBA is built from exit
velocity and launch angle alone, so it is structurally blind to where a ball
is hit and who is running — a hitter can beat it repeatably.

You cannot tell those apart without the player's own history, and the local
`hitters_multiyr` cache cannot supply it: its `woba_v_sum` column is the
EXPECTED value, so actual-minus-expected is identically 0.000 for every
player-season in it. Savant's expected_statistics leaderboard carries both.

This writes one row per player-season. The BASELINE ITSELF IS NOT COMPUTED
HERE — `expected_stats.personal_luck_baseline` derives it at read time, so the
sample gates and the persistence thresholds stay in code (and under test)
rather than baked into a CSV that would silently go stale against them.

Refresh cadence: seasonal data, so weekly is ample. Cheap (one request per
season) and safe to re-run — it overwrites.

Usage
  python scripts/xfp/build_hitter_luck_baseline.py
  python scripts/xfp/build_hitter_luck_baseline.py --start 2015 --end 2026
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from plv_clone.paths import ROOT as PKG_ROOT  # noqa: E402

OUT = PKG_ROOT / "data" / "research" / "xfp_cache" / "hitter_luck_seasons.csv"
URL = ("https://baseballsavant.mlb.com/leaderboard/expected_statistics"
       "?type=batter&year={year}&position=&team=&filterType=bip&min={min_bip}&csv=true")
UA = {"User-Agent": "Mozilla/5.0"}


def fetch_season(year: int, min_bip: int = 50, timeout: int = 60) -> pd.DataFrame | None:
    """One season of (player_id, pa, woba, est_woba) from Savant, or None."""
    r = requests.get(URL.format(year=year, min_bip=min_bip), headers=UA, timeout=timeout)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text))
    d.columns = [c.strip().strip('"') for c in d.columns]
    idc = next((c for c in d.columns if "player_id" in c), None)
    need = {"pa", "woba", "est_woba"}
    if idc is None or not need.issubset(d.columns):
        return None
    d = d.rename(columns={idc: "batter"})[["batter", "pa", "woba", "est_woba"]]
    d["year"] = year
    # gap > 0 = beat his expected line. This is the quantity the baseline
    # averages; keeping it in the cache makes the file readable by hand.
    d["gap"] = d["woba"] - d["est_woba"]
    return d.dropna(subset=["batter", "pa", "woba", "est_woba"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=2015, help="first season (Statcast era)")
    ap.add_argument("--end", type=int, default=2026)
    ap.add_argument("--min-bip", type=int, default=50,
                    help="Savant leaderboard floor; low so part-timers are kept")
    a = ap.parse_args()

    frames, failed = [], []
    for yr in range(a.start, a.end + 1):
        try:
            d = fetch_season(yr, a.min_bip)
        except Exception as exc:                     # network / Savant shape change
            failed.append((yr, str(exc)[:60]))
            continue
        if d is None or d.empty:
            failed.append((yr, "no usable columns"))
            continue
        frames.append(d)
        print(f"  {yr}: {len(d):5d} player-seasons")

    if not frames:
        print("no seasons fetched — leaving the existing cache untouched", file=sys.stderr)
        return 1
    out = pd.concat(frames, ignore_index=True).sort_values(["batter", "year"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"\nwrote {OUT.relative_to(PKG_ROOT)} — {len(out)} rows, "
          f"{out['batter'].nunique()} hitters, {out['year'].min()}-{out['year'].max()}")
    print(f"field gap: mean {out['gap'].mean():+.4f}  sd {out['gap'].std():.4f}")
    if failed:
        # Loud, not silent: a partial cache changes who clears the season gate.
        print(f"WARNING: {len(failed)} season(s) missing: {failed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
