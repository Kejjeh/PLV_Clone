"""pull_fg_ros_projections.py — daily FanGraphs rest-of-season projection snapshotter.

Pulls each RoS projection system for bat + pit from the free JSON API:
  https://www.fangraphs.com/api/projections?type={system}&stats={bat|pit}&pos=all
systems: steamerr (Steamer RoS), rzips (ZiPS RoS), ratcdc (ATC DC RoS),
         rfangraphsdc (FanGraphs Depth Charts RoS).

Cloudflare note (verified 2026-07-09): plain requests AND curl_cffi
impersonation get 403'd on this endpoint; **cloudscraper** gets through
(intermittently — so each fetch retries with a FRESH scraper instance).
If cloudscraper starts failing entirely, fall back to the
undetected-chromedriver pattern in scripts/xfp/pull_fg_undetected.py.

Per row:
  - maps to MLBAM via the payload's xMLBAMID field (fallback:
    pybaseball.chadwick_register() joined on key_fangraphs == playerid)
  - computes projected BrownU FP from counting stats:
      HITTER  brownu_fp = R + TB + RBI + BB + HBP + SB - SO
              (TB derived: H + 2B + 2*3B + 3*HR)
      PITCHER brownu_fp_sp = SO + IP*3.3 - H - 2*ER - BB - HBP
              brownu_fp_rp = brownu_fp_sp + 5*SV + 3*HLD
  - keeps ALL raw payload columns (projected PA and IP especially —
    playing time is the prize).

Output (date-keyed snapshots — accumulate now, validate in ~4 weeks):
  data/research/fg_proj_cache/{YYYY-MM-DD}_{system}_{bat|pit}.csv
  data/research/fg_proj_cache/manifest.csv
    (snapshot_date, system, stats, rows, mlbam_match_rate, fetched_at)

Idempotent: a (date, system, stats) snapshot that already exists on disk
is skipped. Fail-soft: a failed system/stats combo is reported and the
rest still run; exit code 0 unless EVERYTHING failed.

Usage:
    python scripts/xfp/pull_fg_ros_projections.py
    python scripts/xfp/pull_fg_ros_projections.py --systems steamerr,rzips
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from plv_clone.paths import ROOT  # noqa: E402

CACHE = ROOT / 'data' / 'research' / 'fg_proj_cache'
MANIFEST = CACHE / 'manifest.csv'

FG_API = 'https://www.fangraphs.com/api/projections'
SYSTEMS = ['steamerr', 'rzips', 'ratcdc', 'rfangraphsdc']
TODAY = date.today().isoformat()

_TAG_RE = re.compile(r'<[^>]+>')


def _clean(s):
    return _TAG_RE.sub('', s).strip() if isinstance(s, str) else s


def fetch(system: str, stats: str, tries: int = 6) -> list | None:
    """Fetch one system/stats payload. Fresh cloudscraper per attempt —
    the Cloudflare pass is intermittent, so retrying with a new session
    (new TLS fingerprint/cookies) is what actually works."""
    import cloudscraper
    last_err = None
    for i in range(tries):
        try:
            s = cloudscraper.create_scraper()
            r = s.get(FG_API, params={'type': system, 'stats': stats, 'pos': 'all'},
                      timeout=90)
            ctype = r.headers.get('content-type') or ''
            if r.status_code == 200 and 'json' in ctype:
                data = r.json()
                rows = data if isinstance(data, list) else data.get('data', [])
                if rows:
                    return rows
                last_err = 'empty payload'
            else:
                last_err = f'HTTP {r.status_code} ({ctype[:30]})'
        except Exception as e:
            last_err = str(e)[:120]
        time.sleep(2.0 * (i + 1))
    print(f'  ! {system}/{stats}: all {tries} attempts failed ({last_err})')
    return None


_CHADWICK = None


def _chadwick_fg_map() -> dict:
    """FG playerid -> MLBAM id, loaded lazily only if xMLBAMID has gaps."""
    global _CHADWICK
    if _CHADWICK is None:
        try:
            from pybaseball import chadwick_register
            reg = chadwick_register()
            reg = reg.dropna(subset=['key_fangraphs', 'key_mlbam'])
            _CHADWICK = dict(zip(reg['key_fangraphs'].astype(int),
                                 reg['key_mlbam'].astype(int)))
        except Exception as e:
            print(f'  ! chadwick fallback unavailable: {str(e)[:100]}')
            _CHADWICK = {}
    return _CHADWICK


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return pd.Series(0.0, index=df.index)


def _normalize_ip(ip: pd.Series) -> pd.Series:
    """FG display convention writes thirds as .1/.2. If EVERY fractional
    part is ~0/.1/.2, convert to true decimal innings; else pass through."""
    frac = (ip % 1).round(4)
    if frac.dropna().isin([0.0, 0.1, 0.2]).all():
        return ip.astype(float).apply(
            lambda x: int(x) + round((x - int(x)) * 10) / 3.0 if pd.notna(x) else x)
    return ip


def process(rows: list, stats: str) -> tuple[pd.DataFrame, float]:
    df = pd.DataFrame(rows)
    for c in ('PlayerName', 'ShortName', 'Team'):
        if c in df.columns:
            df[c] = df[c].map(_clean)

    # --- MLBAM mapping: xMLBAMID primary, chadwick(playerid) fallback ---
    mlbam = pd.to_numeric(df.get('xMLBAMID'), errors='coerce')
    missing = mlbam.isna() | (mlbam <= 0)
    if missing.any() and 'playerid' in df.columns:
        fg2mlb = _chadwick_fg_map()
        if fg2mlb:
            fgids = pd.to_numeric(df.loc[missing, 'playerid'], errors='coerce')
            mapped = pd.to_numeric(
                fgids.map(lambda x: fg2mlb.get(int(x)) if pd.notna(x) else None),
                errors='coerce')
            mlbam.loc[missing] = mapped.astype('float64')
    df.insert(0, 'mlbam_id', mlbam.astype('Int64'))
    match_rate = float(df['mlbam_id'].notna().mean())

    # --- BrownU FP ---
    if stats == 'bat':
        h, d2, d3, hr = _num(df, 'H'), _num(df, '2B'), _num(df, '3B'), _num(df, 'HR')
        tb = h + d2 + 2 * d3 + 3 * hr
        df['brownu_tb'] = tb
        df['brownu_fp'] = (_num(df, 'R') + tb + _num(df, 'RBI') + _num(df, 'BB')
                           + _num(df, 'HBP') + _num(df, 'SB') - _num(df, 'SO'))
        pa = _num(df, 'PA')
        df['brownu_fp_per_pa'] = (df['brownu_fp'] / pa).where(pa > 0)
        g = _num(df, 'G')
        df['brownu_fp_per_g'] = (df['brownu_fp'] / g).where(g > 0)
    else:
        ip = _normalize_ip(pd.to_numeric(df.get('IP'), errors='coerce'))
        df['ip_decimal'] = ip
        base = (_num(df, 'SO') + ip.fillna(0) * 3.3 - _num(df, 'H')
                - 2 * _num(df, 'ER') - _num(df, 'BB') - _num(df, 'HBP'))
        df['brownu_fp_sp'] = base
        from plv_clone.fantasy.scoring import DEFAULT as _SC
        df['brownu_fp_rp'] = (base + _SC.sv * _num(df, 'SV')
                              + _SC.hd * _num(df, 'HLD'))
        gs = _num(df, 'GS')
        df['brownu_fp_per_start'] = (base / gs).where(gs > 0)
        g = _num(df, 'G')
        df['brownu_fp_rp_per_g'] = (df['brownu_fp_rp'] / g).where(g > 0)
    return df, match_rate


def _append_manifest(entries: list[dict]) -> None:
    new = pd.DataFrame(entries)
    if MANIFEST.exists():
        old = pd.read_csv(MANIFEST)
        combined = pd.concat([old, new], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=['snapshot_date', 'system', 'stats'], keep='last')
    else:
        combined = new
    tmp = MANIFEST.with_suffix('.csv.tmp')
    combined.to_csv(tmp, index=False)
    tmp.replace(MANIFEST)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--systems', default=','.join(SYSTEMS))
    args = ap.parse_args()
    systems = [s.strip() for s in args.systems.split(',') if s.strip()]

    print(f'=== FanGraphs RoS projection snapshot {TODAY} ===')
    CACHE.mkdir(parents=True, exist_ok=True)

    entries, n_ok, n_skip, n_fail = [], 0, 0, 0
    for system in systems:
        for stats in ('bat', 'pit'):
            out = CACHE / f'{TODAY}_{system}_{stats}.csv'
            if out.exists():
                print(f'  = {system}/{stats}: snapshot exists, skip')
                n_skip += 1
                continue
            rows = fetch(system, stats)
            if rows is None:
                n_fail += 1
                continue
            df, match_rate = process(rows, stats)
            tmp = out.with_suffix('.csv.tmp')
            df.to_csv(tmp, index=False)
            tmp.replace(out)
            print(f'  + {system}/{stats}: {len(df)} rows, mlbam match {match_rate:.1%}')
            entries.append({
                'snapshot_date': TODAY, 'system': system, 'stats': stats,
                'rows': len(df), 'mlbam_match_rate': round(match_rate, 4),
                'fetched_at': datetime.now().isoformat(timespec='seconds'),
            })
            n_ok += 1
            time.sleep(2.0)  # be polite between combos

    if entries:
        _append_manifest(entries)
        print(f'  manifest updated ({MANIFEST.name})')
    print(f'  done: {n_ok} fetched, {n_skip} skipped, {n_fail} failed')
    return 0 if (n_ok + n_skip) > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
