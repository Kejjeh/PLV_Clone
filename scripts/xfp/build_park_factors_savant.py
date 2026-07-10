"""build_park_factors_savant.py

Fetches Baseball Savant seasonal park factors (official Statcast park
factors) and caches them for the `ros_park_factor_weighted` candidate
feature (rh3 + rp3 validation, pre-registered 2026-07-09).

Endpoint (free, no auth):
  https://baseballsavant.mlb.com/leaderboard/statcast-park-factors
    ?type=year&year={Y}&batSide=&stat=index_wOBA&condition=All&rolling=3&csv=true

NOTE: despite csv=true the endpoint returns the page HTML; the data is
embedded as `var data = [...]` JSON. We parse that. Verified 2026-07-09:
with rolling=3 the payload rows carry key_is_year_rolling=1,
key_num_years_rolling=3, key_year={Y} — i.e. the 3-year rolling window
ENDING at year Y (PA-weighted across the window).

LEAKAGE SAFETY (Rule 8): downstream, outcome year T uses the pull with
key_year = T-1 (window T-3..T-1). Nothing from year T leaks in.

Output: data/research/xfp_cache/park_factors_savant.csv
  columns: key_year, n_years_rolling, venue_id, venue_name, main_team_id,
           team_abbr, name_display_club, n_pa, index_woba, index_runs,
           index_hr
Idempotent: years already present in the cache are not re-fetched.
Polite: 2s sleep between requests.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
OUT_CSV = CACHE / "park_factors_savant.csv"

# key_year values needed: T-1 for outcome years 2018, 2019, 2021..2026.
# We fetch the full contiguous 2017-2025 range (2019 unused but cheap).
FETCH_YEARS = list(range(2017, 2026))

URL_TMPL = (
    "https://baseballsavant.mlb.com/leaderboard/statcast-park-factors"
    "?type=year&year={year}&batSide=&stat=index_wOBA&condition=All"
    "&rolling={rolling}&csv=true"
)

# rolling=3 is the primary variant; rolling=1 (single-year) is the
# fallback for team-years whose current park lacks a full 3-yr window
# (ATL 2017-18, TEX 2020-21, TOR 2020, ATH/TB 2025).
ROLLING_VARIANTS = [3, 1]

# MLBAM team_id -> statcast team abbreviation (matches statcast parquet
# home_team/away_team values; AZ not ARI, ATH not OAK, CWS not CHW).
TEAM_ID_TO_ABBR = {
    108: "LAA", 109: "AZ", 110: "BAL", 111: "BOS", 112: "CHC",
    113: "CIN", 114: "CLE", 115: "COL", 116: "DET", 117: "HOU",
    118: "KC", 119: "LAD", 120: "WSH", 121: "NYM", 133: "ATH",
    134: "PIT", 135: "SD", 136: "SEA", 137: "SF", 138: "STL",
    139: "TB", 140: "TEX", 141: "TOR", 142: "MIN", 143: "PHI",
    144: "ATL", 145: "CWS", 146: "MIA", 147: "NYY", 158: "MIL",
}

KEEP_NUMERIC = ["n_pa", "index_woba", "index_runs", "index_hr"]


def fetch_year(year: int, rolling: int) -> pd.DataFrame:
    url = URL_TMPL.format(year=year, rolling=rolling)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = re.search(r"var data = ", html)
    if not m:
        raise RuntimeError(f"[{year}] no embedded `var data =` found")
    payload, _ = json.JSONDecoder().raw_decode(html[m.end():])
    rows = []
    for r in payload:
        tid = int(r["main_team_id"])
        rows.append({
            "key_year": int(r["key_year"]),
            "n_years_rolling": int(r.get("key_num_years_rolling", 0) or 0),
            "venue_id": int(r["venue_id"]),
            "venue_name": r.get("venue_name"),
            "main_team_id": tid,
            "team_abbr": TEAM_ID_TO_ABBR.get(tid),
            "name_display_club": r.get("name_display_club"),
            "n_pa": r.get("n_pa"),
            "index_woba": r.get("index_woba"),
            "index_runs": r.get("index_runs"),
            "index_hr": r.get("index_hr"),
        })
    df = pd.DataFrame(rows)
    for c in KEEP_NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df["key_year"].nunique() != 1 or int(df["key_year"].iloc[0]) != year:
        raise RuntimeError(f"[{year}] payload key_year mismatch: "
                           f"{df['key_year'].unique()}")
    return df


def main() -> None:
    print("=== build_park_factors_savant ===")
    existing = pd.read_csv(OUT_CSV) if OUT_CSV.exists() else pd.DataFrame()
    have = (
        set(zip(existing["key_year"], existing["n_years_rolling"]))
        if len(existing) else set()
    )

    frames = [existing] if len(existing) else []
    for yr in FETCH_YEARS:
        for rolling in ROLLING_VARIANTS:
            if (yr, rolling) in have:
                print(f"  [{yr} r={rolling}] already cached, skip")
                continue
            df = fetch_year(yr, rolling)
            frames.append(df)
            print(f"  [{yr} r={rolling}] fetched {len(df)} venues  "
                  f"index_woba range [{df['index_woba'].min():.0f}, "
                  f"{df['index_woba'].max():.0f}]  "
                  f"unmapped_team_ids={df['team_abbr'].isna().sum()}")
            time.sleep(2)  # be polite to Savant

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["key_year", "n_years_rolling", "venue_id"])
    out = out.sort_values(["key_year", "n_years_rolling", "team_abbr"])
    out.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV}: {len(out)} rows, "
          f"years {sorted(out['key_year'].unique())}")

    # === Step 2.5 data-coverage pre-check ===
    # Requirement: for every key_year, the union of (rolling-3 primary,
    # rolling-1 fallback) covers all 30 teams with non-null index_woba.
    print("\n=== Step 2.5 coverage pre-check (rolling-3 with rolling-1 fallback) ===")
    ok = True
    all_teams = set(TEAM_ID_TO_ABBR.values())
    for yr in FETCH_YEARS:
        r3 = out[(out["key_year"] == yr) & (out["n_years_rolling"] == 3)
                 & out["index_woba"].notna()]
        r1 = out[(out["key_year"] == yr) & (out["n_years_rolling"] == 1)
                 & out["index_woba"].notna()]
        covered = set(r3["team_abbr"]) | set(r1["team_abbr"])
        missing = all_teams - covered
        fallback = sorted(all_teams - set(r3["team_abbr"]))
        flag = "OK" if not missing else "FAIL"
        if missing:
            ok = False
        print(f"  key_year={yr}: r3_teams={r3['team_abbr'].nunique()} "
              f"r1_fallback_needed={fallback if fallback else '-'} "
              f"missing_after_fallback={sorted(missing) if missing else '-'}  {flag}")
    print(f"\n  Pre-check: {'PASS' if ok else 'FAIL — inspect above'}")


if __name__ == "__main__":
    main()
