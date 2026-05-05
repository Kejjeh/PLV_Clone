#!/usr/bin/env python3
"""
fetch_fangraphs.py — Pull FanGraphs leaderboard data for pitchers and batters.

Supplements our Savant/PLV pipeline with:
  • Stuff+ / Location+ / Pitching+  (sp_stuff, sp_location, sp_pitching)
  • SIERA, xFIP, FIP for pitchers
  • wRC+, xwOBA, Barrel%, HardHit% for batters
  • SwStr%, K%, BB%, K-BB% for both

FanGraphs is more current than Baseball Savant (~0–1 day lag vs 1–4 days).

Outputs (written to data/outputs/):
  fangraphs_pitchers_{year}.csv   — pitcher stats + Stuff+/Location+/Pitching+
  fangraphs_batters_{year}.csv    — batter stats + wRC+/xwOBA/Barrel%

Join key: xMLBAMID (== Statcast pitcher / batter column).

Usage:
    python scripts/fetch_fangraphs.py [--year 2026]

Run alongside fetch_savant_rolling.py in your daily pipeline.
"""
from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

ROOT    = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "data" / "outputs"

# FanGraphs major-league leaders API.
# NOTE: FanGraphs uses Cloudflare; requests from datacenter / CI IPs will get
# 403 Forbidden. Run this script from your local machine (residential IP).
# curl_cffi (pip install curl_cffi) uses real browser TLS fingerprinting and
# bypasses Cloudflare on residential IPs. Falls back to plain requests.
_FG_API = "https://www.fangraphs.com/api/leaders/major-league/data"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://www.fangraphs.com",
    "Referer": "https://www.fangraphs.com/leaders/major-league?",
}


def _get(url: str, params: dict, timeout: int = 20):
    """HTTP GET with curl_cffi (Chrome TLS fingerprint) → falls back to requests."""
    try:
        from curl_cffi import requests as cfr
        return cfr.get(url, params=params, headers=_HEADERS,
                       timeout=timeout, impersonate="chrome124")
    except ImportError:
        pass
    import requests as req
    return req.get(url, params=params, headers=_HEADERS, timeout=timeout)

_NAME_RE = re.compile(r"<[^>]+>")


def _clean_name(raw: str) -> str:
    """Strip HTML anchor tags: '<a href="...">Last, First</a>' → 'Last, First'."""
    if not isinstance(raw, str):
        return str(raw)
    return _NAME_RE.sub("", raw).strip()


def _fetch(stats: str, year: int, min_pa: int = 10, retries: int = 3, delay: float = 2.0) -> list[dict]:
    """Fetch one page of FG leaderboard data (stats='pit' or 'bat')."""
    params = {
        "pos": "all",
        "stats": stats,
        "lg": "all",
        "qual": min_pa,
        "season": year,
        "season1": year,
        "month": 0,
        "team": 0,
        "pageitems": 500,
        "pagenum": 1,
        "ind": 0,
        "type": 8,   # "standard + advanced" — includes sp_stuff/sp_location/sp_pitching
    }
    for attempt in range(retries):
        try:
            r = _get(_FG_API, params=params)
            r.raise_for_status()
            data = r.json()
            rows = data.get("data", [])
            log.info("  FG %s: %d rows (HTTP 200)", stats, len(rows))
            return rows
        except Exception as exc:
            log.warning("  Attempt %d/%d failed: %s", attempt + 1, retries, exc)
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    log.error("  All %d attempts failed for stats=%s", retries, stats)
    return []


# ── Column selections ──────────────────────────────────────────────────────────

_PITCHER_COLS = {
    # join key
    "xMLBAMID":    "mlb_id",
    # identity
    "Name":        "player_name_fg",
    "Team":        "team",
    "Season":      "season",
    "IP":          "ip",
    "G":           "g",
    "GS":          "gs",
    # core results
    "ERA":         "era",
    "FIP":         "fip",
    "xFIP":        "xfip",
    "SIERA":       "siera",
    "xERA":        "xera",
    "WHIP":        "whip",
    # rate stats
    "K%":          "k_pct",
    "BB%":         "bb_pct",
    "K-BB%":       "k_minus_bb_pct",
    "SwStr%":      "swstr_pct",
    "CSW%":        "csw_pct",   # may not exist — filled None if absent
    "C+SwStr%":    "c_plus_swstr_pct",
    "HR/FB":       "hr_fb",
    "GB%":         "gb_pct",
    "LOB%":        "lob_pct",
    # Statcast/quality
    "Barrel%":     "barrel_pct",
    "HardHit%":    "hard_hit_pct",
    "EV":          "avg_ev",
    # ── The money columns ──────────────────────────────────────────────────────
    "sp_stuff":    "stuff_plus",
    "sp_location": "location_plus",
    "sp_pitching": "pitching_plus",
    # FanGraphs pitch-behavior composite (different model from sp_*)
    "pb_stuff":    "pb_stuff",
    "pb_command":  "pb_command",
    "pb_xRV100":   "pb_xrv100",
}

_BATTER_COLS = {
    # join key
    "xMLBAMID":          "mlb_id",
    # identity
    "Name":              "player_name_fg",
    "Team":              "team",
    "Season":            "season",
    "G":                 "g",
    "PA":                "pa",
    # core results
    "AVG":               "avg",
    "OBP":               "obp",
    "SLG":               "slg",
    "wOBA":              "woba",
    "wRC+":              "wrc_plus",
    "ISO":               "iso",
    "BABIP":             "babip",
    # expected stats
    "xwOBA":             "xwoba_fg",
    "xAVG":              "xavg",
    "xSLG":              "xslg",
    # plate discipline
    "K%":                "k_pct",
    "BB%":               "bb_pct",
    "SwStr%":            "swstr_pct",
    "O-Swing%":          "o_swing_pct",
    "Z-Contact%":        "z_contact_pct",
    "Contact%":          "contact_pct_fg",
    # batted-ball quality
    "Barrel%":           "barrel_pct",
    "HardHit%":          "hard_hit_pct",
    "EV":                "avg_ev",
    "maxEV":             "max_ev",
    # bat tracking (new 2024+)
    "AvgBatSpeed":       "avg_bat_speed",
    "BlastSwing%":       "blast_swing_pct",
    "BlastContact%":     "blast_contact_pct",
    "SquaredUpSwing%":   "squared_up_swing_pct",
    "SquaredUpContact%": "squared_up_contact_pct",
}


def _extract(rows: list[dict], col_map: dict[str, str]) -> pd.DataFrame:
    """Pull only mapped columns from raw FG rows, rename, clean HTML."""
    records = []
    for row in rows:
        rec: dict = {}
        for src, dst in col_map.items():
            val = row.get(src)
            if isinstance(val, str) and "<" in val:
                val = _clean_name(val)
            rec[dst] = val
        records.append(rec)
    df = pd.DataFrame(records)
    # Ensure mlb_id is int where possible
    if "mlb_id" in df.columns:
        df["mlb_id"] = pd.to_numeric(df["mlb_id"], errors="coerce").astype("Int64")
    # pct columns: FG returns 0-1 floats; convert to percentage for readability
    pct_cols = [c for c in df.columns if c.endswith("_pct")]
    for c in pct_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        # Only multiply if values are clearly 0-1 scale
        if df[c].dropna().between(0, 1).all():
            df[c] = (df[c] * 100).round(2)
    return df


# ── Main ───────────────────────────────────────────────────────────────────────

def run(year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    # ── Pitchers ──────────────────────────────────────────────────────────────
    log.info("Fetching FanGraphs pitcher data (year=%d) …", year)
    pit_rows = _fetch("pit", year, min_pa=10)
    if pit_rows:
        pit_df = _extract(pit_rows, _PITCHER_COLS)
        # Validate Stuff+ is populated
        stuffplus_present = pit_df["stuff_plus"].notna().sum()
        log.info(
            "  Pitchers: %d rows | Stuff+ populated: %d (%.0f%%)",
            len(pit_df), stuffplus_present,
            100 * stuffplus_present / max(len(pit_df), 1),
        )
        out_path = OUTPUTS / f"fangraphs_pitchers_{year}.csv"
        pit_df.to_csv(out_path, index=False)
        log.info("  Written → %s", out_path.name)

        # Quick summary
        with_stuff = pit_df[pit_df["stuff_plus"].notna()].sort_values("stuff_plus", ascending=False)
        if not with_stuff.empty:
            log.info("  Top 5 Stuff+: %s",
                     with_stuff[["player_name_fg", "stuff_plus", "location_plus", "pitching_plus"]].head(5).to_string(index=False))
    else:
        pit_df = pd.DataFrame()
        log.warning("  No pitcher data retrieved.")

    time.sleep(1.5)   # be polite

    # ── Batters ───────────────────────────────────────────────────────────────
    log.info("Fetching FanGraphs batter data (year=%d) …", year)
    bat_rows = _fetch("bat", year, min_pa=10)
    if bat_rows:
        bat_df = _extract(bat_rows, _BATTER_COLS)
        log.info("  Batters: %d rows | wRC+ populated: %d",
                 len(bat_df), bat_df["wrc_plus"].notna().sum())
        out_path = OUTPUTS / f"fangraphs_batters_{year}.csv"
        bat_df.to_csv(out_path, index=False)
        log.info("  Written → %s", out_path.name)
    else:
        bat_df = pd.DataFrame()
        log.warning("  No batter data retrieved.")

    return pit_df, bat_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2026)
    args = ap.parse_args()
    pit_df, bat_df = run(args.year)
    if pit_df.empty and bat_df.empty:
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
