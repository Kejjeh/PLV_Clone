#!/usr/bin/env python3
"""fetch_fangraphs_projections.py — pull RoS projections from FanGraphs.

FanGraphs publishes projection-system leaderboards as JSON at:
  https://www.fangraphs.com/api/projections?type=<system>&stats=<bat|pit>&pos=all&team=0&players=0&lg=all

Systems available: rosatc (ATC RoS), rossteamer (Steamer RoS), roszips (ZiPS RoS),
rosthebatx (TheBatX RoS).

Outputs to data/research/external_projections/<system>_<kind>_2026.csv with
the columns projection_ensemble.py expects: Name, PA, AB, H, 2B, 3B, HR, BB, HBP, SO
(plus pitcher cols: G, GS, IP, H, ER, BB, SO, HBP).

Usage:
    python scripts/fetch_fangraphs_projections.py
"""
from __future__ import annotations
import re
import time
import logging
from pathlib import Path
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "data" / "research" / "external_projections"

_FG_API = "https://www.fangraphs.com/api/projections"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Origin": "https://www.fangraphs.com",
    "Referer": "https://www.fangraphs.com/projections?",
}

SYSTEMS = {
    'atc':     'atc',
    'steamer': 'steamer',
    'zips':    'zips',
    'thebatx': 'thebatx',
}

_NAME_RE = re.compile(r"<[^>]+>")


def _get(params, timeout=20):
    try:
        from curl_cffi import requests as cfr
        return cfr.get(_FG_API, params=params, headers=_HEADERS,
                       timeout=timeout, impersonate="chrome124")
    except ImportError:
        import requests as req
        return req.get(_FG_API, params=params, headers=_HEADERS, timeout=timeout)


def _clean(s):
    if not isinstance(s, str):
        return s
    return _NAME_RE.sub("", s).strip()


def fetch(system: str, kind: str) -> pd.DataFrame:
    """system='atc'|'steamer'|'zips'|'thebatx'; kind='bat'|'pit'.
    rest=1 means rest-of-season projection."""
    params = {
        'type': system, 'stats': kind, 'pos': 'all',
        'team': 0, 'players': 0, 'lg': 'all', 'rest': 1,
    }
    for attempt in range(3):
        try:
            r = _get(params)
            r.raise_for_status()
            data = r.json()
            rows = data if isinstance(data, list) else data.get('data', [])
            log.info("  %s/%s: %d rows", system, kind, len(rows))
            return pd.DataFrame(rows)
        except Exception as e:
            log.warning("  attempt %d: %s", attempt + 1, e)
            time.sleep(2 * (attempt + 1))
    return pd.DataFrame()


def main():
    EXT.mkdir(parents=True, exist_ok=True)
    for sys_key, sys_name in SYSTEMS.items():
        for kind, label in [('bat', 'hitters'), ('pit', 'pitchers')]:
            df = fetch(sys_key, kind)
            if df.empty:
                continue
            # Clean PlayerName, ensure 'Name' column exists for downstream
            if 'PlayerName' in df.columns:
                df['PlayerName'] = df['PlayerName'].map(_clean)
                df['Name'] = df['PlayerName']
            elif 'Name' in df.columns:
                df['Name'] = df['Name'].map(_clean)
            # FanGraphs projection JSON usually returns: Name, Team, PA, AB, H, 1B, 2B, 3B, HR,
            # R, RBI, BB, IBB, SO, HBP, SF, SH, GDP, SB, CS, AVG, OBP, SLG, OPS, wOBA, wRC+
            # For pitchers: Name, Team, W, L, SV, G, GS, IP, H, ER, HR, SO, BB, HBP, BABIP, ...
            out = EXT / f"{sys_name}_{label}_2026.csv"
            df.to_csv(out, index=False)
            log.info("  wrote %s (%d cols, %d rows)", out, len(df.columns), len(df))
            time.sleep(1.0)


if __name__ == '__main__':
    main()
