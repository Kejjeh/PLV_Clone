"""Shared loader for the per-game stolen-base gameLog cache.

The raw cache (data/research/xfp_cache/sb_gamelog_raw/{year}/{pid}.json) is
written by scripts/xfp/build_batter_sb_gamelog.py from the MLB Stats API
per-player gameLog (stats=gameLog&group=hitting). It exists because the
statcast `events` column NEVER carries stolen_base_* values (steals are
baserunning events, not batter-PA outcomes) — see
data/research/validation_runs/sb_target_fix_2026-07-10.md.

This module is the canonical parse/load path for that cache so consumers
(the rolling export in pipelines/build_exports.py, the gamelog builder's
assemble stage) share one idiom. Dates here are CALENDAR game dates, which
makes this the right source for arbitrary date-windowed SB aggregation
(the as-of CSV batter_sb_asof_2018_2026.csv is aligned to the rolling-grid
split_day cutoffs instead).

Freshness note: completed years are immutable; the in-progress year's cache
goes stale as the season progresses and is re-pulled by the daily refresh
(`build_batter_sb_gamelog.py pull --years <year> --force`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# Repo root (src/plv_clone/data/sb_gamelog.py -> parents[3]); the package is
# editable-installed from the repo, matching the scripts/ ROOT convention.
_REPO_ROOT = Path(__file__).resolve().parents[3]
SB_GAMELOG_RAW_DIR = _REPO_ROOT / "data" / "research" / "xfp_cache" / "sb_gamelog_raw"


def parse_games(data: dict) -> list[dict]:
    """Extract per-game (date, sb, pa) rows from a gameLog API response."""
    stats = data.get("stats", [])
    if not stats:
        return []
    rows = []
    for s in stats[0].get("splits", []):
        dt = s.get("date")
        st = s.get("stat", {})
        if not dt:
            continue
        rows.append({
            "date": dt,
            "sb": int(st.get("stolenBases") or 0),
            "pa": int(st.get("plateAppearances") or 0),
        })
    return rows


def load_sb_gamelog_year(year: int, raw_dir: Path | None = None) -> pd.DataFrame:
    """Load every cached batter gameLog for *year* into a long DataFrame.

    Returns columns: batter (int, MLBAM), date (datetime64), sb (int), pa (int).
    Batters absent from the cache simply have no rows (callers should treat
    missing as zero SB). Returns an empty, correctly-typed frame when the
    year directory does not exist.
    """
    ydir = (raw_dir or SB_GAMELOG_RAW_DIR) / str(year)
    rows: list[dict] = []
    if ydir.exists():
        for p in sorted(ydir.glob("*.json")):
            try:
                pid = int(p.stem)
                data = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, json.JSONDecodeError, OSError):
                continue  # corrupt/misnamed file — skip, caller sees no rows
            for g in parse_games(data):
                rows.append({"batter": pid, **g})
    df = pd.DataFrame(rows, columns=["batter", "date", "sb", "pa"])
    df["date"] = pd.to_datetime(df["date"])
    return df
