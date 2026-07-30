"""Pull 2026 season-to-date FG pitcher snapshot WITH counting stats + Stuff+
(sp_stuff/pb_stuff) for the live Stuff+ / floor / sustainability lenses.

Writes data/research/fg_asof/fg_pit_2026_current.csv.

Robustness (2026-07-20 fix — this was a silent 6-day failure):
  1. Tries a browserless cloudscraper fetch FIRST (fast, no Chrome). If
     FanGraphs' Cloudflare is lax this succeeds in ~2s; when it hardens
     (currently 403) we fall through to a real browser.
  2. Chrome fallback AUTO-DETECTS the installed version — the old hardcoded
     version_main=148 broke the moment Chrome auto-updated (the actual cause
     of the daily-refresh flake). Pass --chrome-version N to pin if needed.
     (2026-07-30 fix: version_main=None is NOT auto-detection — undetected-
     chromedriver then downloads the LATEST driver, which races AHEAD of the
     installed browser between Chrome auto-updates; driver 151 vs browser 150
     froze this scrape 07-15..07-30. Now we read the REAL installed major from
     the registry/install dir, and on a driver/browser mismatch error we parse
     the browser version out of the message and retry once with that major.)
  3. VALIDATES the pull (non-empty + Stuff+ present) and only overwrites the
     good file when valid — never clobbers a working snapshot with an empty
     failed pull.
  4. EXITS NON-ZERO on failure so the daily refresh's fail-soft run() logs a
     visible warning instead of a false success (the silent-failure root
     cause). Pairs with the model-health fg_scrape_silent_fail tripwire.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "fg_asof"
COLS = {
    'xMLBAMID': 'mlb_id', 'Name': 'player_name_fg', 'Team': 'team', 'Season': 'season',
    'IP': 'ip', 'G': 'g', 'GS': 'gs', 'SO': 'so', 'H': 'h', 'ER': 'er', 'BB': 'bb', 'HBP': 'hbp',
    'K%': 'k_pct', 'BB%': 'bb_pct', 'SwStr%': 'swstr_pct', 'SIERA': 'siera',
    'sp_stuff': 'stuff_plus', 'sp_location': 'location_plus', 'sp_pitching': 'pitching_plus',
    'pb_stuff': 'pb_stuff', 'pb_command': 'pb_command',
}
API = ('https://www.fangraphs.com/api/leaders/major-league/data?'
       'pos=all&stats=pit&lg=all&qual=0&season=2026&season1=2026'
       '&startdate=2026-03-01&enddate=2026-12-31&month=1000&team=0'
       '&pageitems=1000&pagenum=1&ind=0&type=8')
WARM = 'https://www.fangraphs.com/leaders/major-league?stats=pit&season=2026&type=8'


def _clean(v):
    return re.sub(r'<[^>]+>', '', v).strip() if isinstance(v, str) else v


def _frame_from_rows(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame([{dst: _clean(rr.get(sk)) for sk, dst in COLS.items()} for rr in rows])
    df['mlb_id'] = pd.to_numeric(df['mlb_id'], errors='coerce').astype('Int64')
    return df


def _valid(df: pd.DataFrame) -> bool:
    """A real pull: enough rows AND Stuff+ actually populated (the whole point)."""
    return (df is not None and len(df) >= 200
            and 'stuff_plus' in df.columns
            and pd.to_numeric(df['stuff_plus'], errors='coerce').notna().sum() >= 100)


def _try_cloudscraper() -> list[dict] | None:
    """Browserless fast path. Returns rows or None (Cloudflare block / no lib)."""
    try:
        import cloudscraper
    except ImportError:
        return None
    try:
        s = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        s.get(WARM, timeout=40)
        r = s.get(API, timeout=60)
        if r.status_code == 200:
            return json.loads(r.text).get('data', [])
        print(f"  cloudscraper: HTTP {r.status_code} (Cloudflare challenge) — "
              f"falling back to a real browser", flush=True)
    except Exception as e:
        print(f"  cloudscraper failed ({type(e).__name__}: {e}) — falling back", flush=True)
    return None


def _installed_chrome_major() -> int | None:
    """Detect the REAL installed Chrome major version (Windows). Do NOT rely
    on uc's version_main=None default — that downloads the LATEST chromedriver,
    which mismatches the browser whenever Chrome's auto-update lags the driver
    release (the 2026-07-15..30 freeze: driver 151, browser 150). Registry
    first, then the versioned install dir Chrome leaves next to chrome.exe."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    for base in (Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')) / 'Google' / 'Chrome' / 'Application',
                 Path(os.environ.get('LOCALAPPDATA', r'C:\_')) / 'Google' / 'Chrome' / 'Application'):
        try:
            vers = [p.name for p in base.iterdir() if re.fullmatch(r'\d+(\.\d+){3}', p.name)]
            if vers:
                return max(int(v.split('.')[0]) for v in vers)
        except Exception:
            pass
    return None


def _try_browser(chrome_version: int | None) -> list[dict] | None:
    """undetected-chromedriver path. version_main: pinned via --chrome-version,
    else the DETECTED installed major (never uc's latest-driver default)."""
    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("  undetected_chromedriver not installed", flush=True)
        return None
    if chrome_version is None:
        chrome_version = _installed_chrome_major()
        print(f"  installed Chrome major: {chrome_version or 'not detected'}", flush=True)
    d = None
    try:
        for attempt in range(2):
            o = uc.ChromeOptions()
            o.add_argument('--disable-blink-features=AutomationControlled')
            try:
                d = uc.Chrome(options=o, version_main=chrome_version)
                break
            except Exception as e:
                # Driver/browser major mismatch — the error message names the
                # REAL installed version; trust it, retry once with that major.
                m = re.search(r'urrent browser version is (\d+)', str(e))
                if attempt == 0 and m and int(m.group(1)) != chrome_version:
                    chrome_version = int(m.group(1))
                    print(f"  driver/browser mismatch — retrying with "
                          f"version_main={chrome_version}", flush=True)
                    continue
                raise
        d.get(WARM); time.sleep(12)
        resp = None
        for _ in range(3):
            js = (f'return await new Promise((r)=>{{fetch("{API}",{{credentials:"include"}})'
                  f'.then(x=>x.text().then(t=>r({{status:x.status,body:t}})))'
                  f'.catch(z=>r({{status:0,body:String(z)}}));}});')
            resp = d.execute_script(js)
            if resp.get('status') == 200:
                break
            time.sleep(5); d.get(WARM); time.sleep(8)
        if resp and resp.get('status') == 200:
            return json.loads(resp['body']).get('data', [])
        print(f"  browser: API returned status {resp.get('status') if resp else 'none'}", flush=True)
    except Exception as e:
        print(f"  browser path failed ({type(e).__name__}: {e})", flush=True)
    finally:
        if d is not None:
            try:
                d.quit()
            except Exception:
                pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--chrome-version', type=int, default=None,
                    help='pin undetected-chromedriver version_main (default: auto-detect)')
    ap.add_argument('--no-cloudscraper', action='store_true',
                    help='skip the browserless fast path, go straight to Chrome')
    args = ap.parse_args()

    rows = None if args.no_cloudscraper else _try_cloudscraper()
    if rows is None:
        rows = _try_browser(args.chrome_version)

    if not rows:
        print("FAIL: could not fetch the FG leaderboard by any path "
              "(Cloudflare blocks browserless; Chrome unavailable/failed here). "
              "Run on a machine with a current Chrome; the existing "
              "fg_pit_2026_current.csv is UNCHANGED.", flush=True)
        return 1

    df = _frame_from_rows(rows)
    if not _valid(df):
        n_stuff = pd.to_numeric(df.get('stuff_plus'), errors='coerce').notna().sum() if len(df) else 0
        print(f"FAIL: pulled {len(df)} rows but only {n_stuff} carry Stuff+ — "
              f"treating as a bad pull; NOT overwriting the good snapshot.", flush=True)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / 'fg_pit_2026_current.csv'
    df.to_csv(p, index=False)
    print(f"OK {len(df)} rows, stuff+={df['stuff_plus'].notna().sum()} -> {p.name}", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
