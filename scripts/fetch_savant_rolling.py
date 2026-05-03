"""
fetch_savant_rolling.py — Pull Baseball Savant rolling xwOBA leaderboards.

Replicates what the MLB Fantasy 2026 Apps Script does, but in Python:
  - Fetches rolling xwOBA leaderboard for batters at 50 / 100 / 250 PA minimums
  - Fetches rolling ERA/whiff leaderboard for pitchers at 100 / 250 BF minimums
  - Computes THEN / NOW / Δ by diffing against the previous snapshot
  - Writes savant_rolling_batters_2026.parquet and savant_rolling_pitchers_2026.parquet
    to data/outputs/ for the dashboard to consume

Usage:
    python scripts/fetch_savant_rolling.py [--year 2026]

Run daily via cron (example):
    0 7 * * * cd /path/to/plv_clone && python scripts/fetch_savant_rolling.py --year 2026

Run this alongside `plv build-exports` in your daily pipeline.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import time
from pathlib import Path
from datetime import date

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "data" / "outputs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://baseballsavant.mlb.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def _fetch_csv(url: str, retries: int = 3, delay: float = 2.0) -> pd.DataFrame | None:
    """Try the Savant CSV export endpoint — cleanest path if it works."""
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=30)
            if r.status_code == 200 and r.text.strip().startswith(("name", "last")):
                return pd.read_csv(io.StringIO(r.text))
            log.debug(f"CSV endpoint returned status {r.status_code}, trying HTML parse")
            return None
        except Exception as e:
            log.warning(f"CSV fetch attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def _fetch_html_bucket(url: str, bucket: str, kind: str = "Batter") -> list[dict] | None:
    """
    Parse Savant rolling leaderboard HTML and extract a bucket's JSON array.
    Savant embeds data as e.g. "Batter50":[...] or "Pitcher100":[...].
    Falls back to bare numeric key '"50":[' for older page formats.

    Args:
        url:    Full URL to fetch
        bucket: The numeric bucket size, e.g. "50", "100", "250"
        kind:   "Batter" or "Pitcher"
    """
    try:
        r = SESSION.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.error(f"HTML fetch failed: {e}")
        return None

    html = r.text

    # Current Savant format: "Batter50":[ or "Pitcher100":[
    candidates = [
        f'"{kind}{bucket}":[',
        f'"{kind}{bucket}": [',
        f'"{bucket}":['    ,  # legacy bare-number key
        f"'{bucket}':["   ,  # single-quote variant
    ]
    key_pos = -1
    for key in candidates:
        key_pos = html.find(key)
        if key_pos != -1:
            break
    if key_pos == -1:
        log.warning(f"Bucket '{bucket}' not found in HTML response")
        return None

    start = html.index("[", key_pos)
    depth = 0
    in_string = False
    escaped = False
    end = -1

    for i in range(start, len(html)):
        ch = html[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        log.warning(f"Could not find closing bracket for bucket '{bucket}'")
        return None

    try:
        return json.loads(html[start:end])
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse error for bucket '{bucket}': {e}")
        return None


def _normalise_player_name(raw: str) -> str:
    """Convert 'Last, First' → 'First Last' for consistent matching."""
    if "," in raw:
        parts = raw.split(",", 1)
        return f"{parts[1].strip()} {parts[0].strip()}"
    return raw.strip()


# ── Savant fetchers ───────────────────────────────────────────────────────────

def fetch_batter_rolling(year: int, min_pa: int) -> pd.DataFrame | None:
    """
    Fetch rolling xwOBA leaderboard for batters.
    Returns DataFrame with columns: player_name, pa, xwoba_rolling, xwoba_on_contact
    """
    base = "https://baseballsavant.mlb.com/leaderboard/rolling"

    # Try CSV endpoint first (cleanest)
    csv_url = f"{base}?type=batter&year={year}&min={min_pa}&csv=true"
    df = _fetch_csv(csv_url)
    if df is not None and not df.empty:
        log.info(f"  CSV OK: batters min_pa={min_pa}, {len(df)} rows")
        return _normalise_batter_df(df, min_pa)

    # Fall back to HTML parsing
    log.info(f"  Trying HTML parse for batters bucket={min_pa}...")
    html_url = f"{base}?type=batter&year={year}"
    rows = _fetch_html_bucket(html_url, str(min_pa), kind="Batter")
    if rows is None:
        # Last resort: fetch plain rolling page (contains all buckets)
        rows = _fetch_html_bucket(base, str(min_pa), kind="Batter")
    if rows is None:
        log.warning(f"  Could not fetch batter data for min_pa={min_pa}")
        return None

    df = pd.DataFrame(rows)
    log.info(f"  HTML parse OK: batters min_pa={min_pa}, {len(df)} rows, cols={list(df.columns)[:6]}")
    return _normalise_batter_df(df, min_pa)


def _normalise_batter_df(df: pd.DataFrame, min_pa: int) -> pd.DataFrame:
    """
    Standardise Savant rolling leaderboard response for batters.

    Savant HTML format (current):
        player_name, cat_bin, last_x_xwoba (NOW), penultimate_x_xwoba (THEN), xwoba_delta (Δ)

    CSV export format (fallback):
        name / last_name, first_name → player_name; est_woba → xwoba_rolling
    """
    # CSV fallback renames (keep backward compat)
    csv_col_map = {
        "name": "player_name",
        "last_name, first_name": "player_name",
        "est_woba": "xwoba_rolling",
        "est_woba_using_speedangle": "xwoba_rolling",
        "xwoba": "xwoba_rolling",
    }
    df = df.rename(columns={k: v for k, v in csv_col_map.items() if k in df.columns})

    # HTML format: map current column names to our standard names
    if "last_x_xwoba" in df.columns:
        df = df.rename(columns={
            "last_x_xwoba":        "xwoba_now",
            "penultimate_x_xwoba": "xwoba_then",
            "xwoba_delta":         "xwoba_delta",
        })
        # Use cat_bin as min_pa if available (more reliable than function arg)
        if "cat_bin" in df.columns:
            df["min_pa"] = pd.to_numeric(df["cat_bin"], errors="coerce").fillna(min_pa).astype(int)
        else:
            df["min_pa"] = min_pa
        xwoba_col = "xwoba_now"
    else:
        # CSV path: xwoba_rolling already set above
        df["min_pa"] = min_pa
        df["xwoba_now"] = df.get("xwoba_rolling")
        df["xwoba_then"] = None
        df["xwoba_delta"] = None
        xwoba_col = "xwoba_now"

    # Normalise "Last, First" → "First Last"
    if "player_name" in df.columns:
        df["player_name"] = df["player_name"].astype(str).apply(_normalise_player_name)

    if "player_name" not in df.columns or xwoba_col not in df.columns:
        log.warning(f"  Missing required columns in batter data — skipping (cols: {list(df.columns)[:8]})")
        return pd.DataFrame()

    keep = [c for c in ["player_name", "min_pa", "xwoba_now", "xwoba_then", "xwoba_delta"] if c in df.columns]
    return df[keep].dropna(subset=["xwoba_now"])


def fetch_pitcher_rolling(year: int, min_bf: int) -> pd.DataFrame | None:
    """
    Fetch rolling leaderboard for pitchers.
    Returns DataFrame with columns: player_name, bf, xera_rolling, whiff_pct
    """
    base = "https://baseballsavant.mlb.com/leaderboard/rolling"

    csv_url = f"{base}?type=pitcher&year={year}&min={min_bf}&csv=true"
    df = _fetch_csv(csv_url)
    if df is not None and not df.empty:
        log.info(f"  CSV OK: pitchers min_bf={min_bf}, {len(df)} rows")
        return _normalise_pitcher_df(df, min_bf)

    log.info(f"  Trying HTML parse for pitchers bucket={min_bf}...")
    html_url = f"{base}?type=pitcher&year={year}"
    rows = _fetch_html_bucket(html_url, str(min_bf), kind="Pitcher")
    if rows is None:
        rows = _fetch_html_bucket(base, str(min_bf), kind="Pitcher")
    if rows is None:
        log.warning(f"  Could not fetch pitcher data for min_bf={min_bf}")
        return None

    df = pd.DataFrame(rows)
    log.info(f"  HTML parse OK: pitchers min_bf={min_bf}, {len(df)} rows")
    return _normalise_pitcher_df(df, min_bf)


def _normalise_pitcher_df(df: pd.DataFrame, min_bf: int) -> pd.DataFrame:
    """
    Standardise Savant rolling leaderboard response for pitchers.

    Savant HTML format (current):
        player_name, cat_bin, last_x_xwoba (xwOBA against NOW),
        penultimate_x_xwoba (THEN), xwoba_delta (Δ, lower = improving for pitchers)

    Note: For pitchers a *lower* xwoba_now = better. Dashboard should sort ascending.
    """
    # CSV fallback renames
    csv_col_map = {
        "name": "player_name",
        "last_name, first_name": "player_name",
        "xera": "xwoba_against_now",
        "est_era": "xwoba_against_now",
        "xwoba": "xwoba_against_now",
        "est_woba": "xwoba_against_now",
        "whiff_percent": "whiff_pct",
    }
    df = df.rename(columns={k: v for k, v in csv_col_map.items() if k in df.columns})

    # HTML format
    if "last_x_xwoba" in df.columns:
        df = df.rename(columns={
            "last_x_xwoba":        "xwoba_against_now",
            "penultimate_x_xwoba": "xwoba_against_then",
            "xwoba_delta":         "xwoba_against_delta",
        })
        if "cat_bin" in df.columns:
            df["min_bf"] = pd.to_numeric(df["cat_bin"], errors="coerce").fillna(min_bf).astype(int)
        else:
            df["min_bf"] = min_bf
        xwoba_col = "xwoba_against_now"
    else:
        df["min_bf"] = min_bf
        if "xwoba_against_now" not in df.columns:
            df["xwoba_against_now"] = None
        df["xwoba_against_then"] = None
        df["xwoba_against_delta"] = None
        xwoba_col = "xwoba_against_now"

    if "player_name" in df.columns:
        df["player_name"] = df["player_name"].astype(str).apply(_normalise_player_name)

    if "player_name" not in df.columns:
        return pd.DataFrame()

    keep = [c for c in ["player_name", "min_bf", "xwoba_against_now", "xwoba_against_then",
                         "xwoba_against_delta", "whiff_pct"] if c in df.columns]
    return df[keep].dropna(subset=[xwoba_col])


# ── Main ──────────────────────────────────────────────────────────────────────

def run(year: int) -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # ── Batters: 50 / 100 / 250 PA buckets ────────────────────────────────────
    log.info("Fetching batter rolling leaderboards...")
    batter_frames = []
    for min_pa in [50, 100, 250]:
        df = fetch_batter_rolling(year, min_pa)
        if df is not None and not df.empty:
            batter_frames.append(df)
        time.sleep(1.5)  # be polite to Savant

    if batter_frames:
        batters = pd.concat(batter_frames, ignore_index=True)

        # Pivot all PA levels into wide format: xwoba_l50_now, xwoba_l100_now, xwoba_l250_now
        # Savant already supplies THEN (penultimate window) and Δ per bucket.
        # We use the 50-PA bucket as the primary NOW/THEN/Δ since it's most reactive.
        b50 = batters[batters["min_pa"] == 50].copy() if "min_pa" in batters.columns else batters.copy()

        wide = batters.pivot_table(
            index="player_name",
            columns="min_pa",
            values="xwoba_now",
            aggfunc="first",
        ).reset_index()
        wide.columns = ["player_name"] + [f"xwoba_l{int(c)}" for c in wide.columns[1:]]

        # Attach THEN / Δ from the 50-PA bucket (most current signal)
        if "xwoba_then" in b50.columns:
            wide = wide.merge(
                b50[["player_name", "xwoba_then", "xwoba_delta"]].rename(
                    columns={"xwoba_then": "xwoba_then", "xwoba_delta": "xwoba_delta"}
                ),
                on="player_name", how="left",
            )

        wide["fetch_date"] = today
        out_path = OUTPUTS / f"savant_rolling_batters_{year}.parquet"
        wide.to_parquet(out_path, index=False)

        log.info(f"Wrote {len(wide)} batter rows → {out_path.name}")
        log.info(f"  Columns: {list(wide.columns)}")

        # Preview top movers
        if "xwoba_delta" in wide.columns:
            movers = wide.dropna(subset=["xwoba_delta"]).sort_values("xwoba_delta", ascending=False)
            log.info("  Top 5 trending up (xwOBA Δ):")
            for _, row in movers.head(5).iterrows():
                log.info(f"    {row['player_name']}: +{row['xwoba_delta']:.3f}")
    else:
        log.warning("No batter data retrieved — check network / Savant availability")

    # ── Pitchers: 100 / 250 BF buckets ────────────────────────────────────────
    log.info("\nFetching pitcher rolling leaderboards...")
    pitcher_frames = []
    for min_bf in [100, 250]:
        df = fetch_pitcher_rolling(year, min_bf)
        if df is not None and not df.empty:
            pitcher_frames.append(df)
        time.sleep(1.5)

    if pitcher_frames:
        pitchers = pd.concat(pitcher_frames, ignore_index=True)

        # Use 100-BF bucket for primary NOW/THEN/Δ
        p100 = pitchers[pitchers["min_bf"] == 100].copy() if "min_bf" in pitchers.columns else pitchers.copy()

        wide_p = pitchers.pivot_table(
            index="player_name",
            columns="min_bf",
            values="xwoba_against_now",
            aggfunc="first",
        ).reset_index()
        wide_p.columns = ["player_name"] + [f"xwoba_against_l{int(c)}bf" for c in wide_p.columns[1:]]

        # Attach THEN / Δ from the 100-BF bucket
        if "xwoba_against_then" in p100.columns:
            wide_p = wide_p.merge(
                p100[["player_name", "xwoba_against_then", "xwoba_against_delta"]],
                on="player_name", how="left",
            )

        wide_p["fetch_date"] = today
        out_path = OUTPUTS / f"savant_rolling_pitchers_{year}.parquet"
        wide_p.to_parquet(out_path, index=False)

        log.info(f"Wrote {len(wide_p)} pitcher rows to {out_path.name}")
        log.info(f"  Columns: {list(wide_p.columns)}")

        if "xwoba_against_delta" in wide_p.columns:
            best = wide_p.dropna(subset=["xwoba_against_delta"]).sort_values("xwoba_against_delta")
            log.info("  Top 5 improving pitchers (xwOBA against delta, most negative = best):")
            for _, row in best.head(5).iterrows():
                log.info(f"    {row['player_name']}: {row['xwoba_against_delta']:.3f}")
    else:
        log.warning("No pitcher data retrieved")

    log.info("Done. Run `streamlit run app/dashboard.py` to see updated Rolling Trends.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch Baseball Savant rolling leaderboards")
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    run(args.year)
