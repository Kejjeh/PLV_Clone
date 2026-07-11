"""build_batter_sb_gamelog.py — TRUE as-of stolen-base counts from the MLB
Stats API per-player gameLog (stats=gameLog&group=hitting).

Why this exists (sb_target_fix_2026-07-10.md): the statcast `events` column
NEVER carries stolen_base_* (SBs are baserunning events, not batter-PA
outcomes), and runner-id derivation was REJECTED (+24.6% league inflation,
biased toward non-stealers). The subseason horizons probe
(data/research/boxscore_era/subseason_horizons_2026-07-10.md) verified that
statsapi gameLog carries dated per-game SB fields reliably back to 1901 —
this is the leakage-safe as-of source that makes the rh3 feature
`sb_per_pa_to_sh` live.

Stages (resumable — every HTTP response is cached as JSON):

  python scripts/xfp/build_batter_sb_gamelog.py pull --years 2018,2019 [--max-seconds 540]
      Pull gameLog for every (batter, year) in the rolling substrate
      rolling_hitters_2018_2026.csv. Cache: data/research/xfp_cache/
      sb_gamelog_raw/{year}/{pid}.json (gitignored). Politeness: paced to
      <=2 req/s on request-start times. Exits 0 with "YEAR COMPLETE"/"PARTIAL"
      progress lines; re-invoke to resume.

  python scripts/xfp/build_batter_sb_gamelog.py assemble
      Build data/research/xfp_cache/batter_sb_asof_2018_2026.csv with one row
      per (batter, year, split_day) aligned to the EXACT (year, split_day,
      cutoff_date) grid of the rolling CSV:
        sb_to     = SB in games with date <= cutoff_date
        sb_last21 = SB in games with cutoff_date-21 < date <= cutoff_date
      Then HARD-GATES the source: per-year league gameLog SB total must match
      sum(mlb_sb) from hitter_counting_stats_{year}.json within +/-1% on the
      common batter set, and per-player-year r >= 0.99. Exit 2 on gate failure
      (the CSV is still written for forensics, with a .FAILED_GATE marker).

Refresh note: completed years are immutable; the in-progress year's cache
files go stale as the season progresses. Re-pull the current year with
`pull --years 2026 --force` (~600 calls, ~5 min) before regenerating the
rolling cache in a daily refresh.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RAW = CACHE / 'sb_gamelog_raw'
ROLLING_CSV = CACHE / 'rolling_hitters_2018_2026.csv'
OUT_CSV = CACHE / 'batter_sb_asof_2018_2026.csv'
BASE = 'https://statsapi.mlb.com/api/v1'
RATE_INTERVAL = 0.5   # >= 0.5s between request STARTS -> <= 2 req/s
TIMEOUT = 30

_last_request_start = 0.0


def _get(url: str) -> dict:
    global _last_request_start
    wait = _last_request_start + RATE_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request_start = time.monotonic()
    req = urllib.request.Request(
        url, headers={'User-Agent': 'plv-sb-gamelog/0.1'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode('utf-8'))


def gamelog_path(year: int, pid: int) -> Path:
    return RAW / str(year) / f'{pid}.json'


def fetch_gamelog(year: int, pid: int, force: bool = False) -> dict:
    p = gamelog_path(year, pid)
    if p.exists() and not force:
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            pass  # corrupt -> refetch
    url = (f'{BASE}/people/{pid}/stats?stats=gameLog&group=hitting'
           f'&season={year}')
    for attempt in range(3):
        try:
            data = _get(url)
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f'    retry {pid}/{year} after error: {e}', flush=True)
            time.sleep(2.0 * (attempt + 1))
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data), encoding='utf-8')
    tmp.replace(p)
    return data


def load_batter_years() -> pd.DataFrame:
    df = pd.read_csv(ROLLING_CSV, usecols=['batter', 'year'])
    return df.drop_duplicates().sort_values(['year', 'batter']).reset_index(drop=True)


def parse_games(data: dict) -> list[dict]:
    """Extract per-game (date, sb, pa) rows from a gameLog response."""
    stats = data.get('stats', [])
    if not stats:
        return []
    rows = []
    for s in stats[0].get('splits', []):
        dt = s.get('date')
        st = s.get('stat', {})
        if not dt:
            continue
        rows.append({
            'date': dt,
            'sb': int(st.get('stolenBases') or 0),
            'pa': int(st.get('plateAppearances') or 0),
        })
    return rows


def cmd_pull(years: list[int], max_seconds: float, force: bool) -> None:
    by = load_batter_years()
    t0 = time.monotonic()
    for year in years:
        pids = by.loc[by['year'] == year, 'batter'].astype(int).tolist()
        missing = [p for p in pids
                   if force or not gamelog_path(year, p).exists()]
        print(f'[{year}] {len(pids)} batter-years, {len(missing)} to pull',
              flush=True)
        done = 0
        for pid in missing:
            fetch_gamelog(year, pid, force=force)
            done += 1
            if done % 50 == 0:
                el = time.monotonic() - t0
                print(f'  [{year}] {done}/{len(missing)} pulled '
                      f'({el:.0f}s elapsed)', flush=True)
            if max_seconds and (time.monotonic() - t0) > max_seconds:
                print(f'  [{year}] PARTIAL — time budget hit at '
                      f'{done}/{len(missing)}; re-invoke to resume', flush=True)
                return
        print(f'  [{year}] YEAR COMPLETE ({len(pids)} cached)', flush=True)
    print('ALL REQUESTED YEARS COMPLETE', flush=True)


def build_long_table(by: pd.DataFrame) -> pd.DataFrame:
    """Per-game long table (batter, year, date, sb, pa) from the JSON cache."""
    rows = []
    n_missing = 0
    for year, pid in by[['year', 'batter']].itertuples(index=False):
        p = gamelog_path(int(year), int(pid))
        if not p.exists():
            n_missing += 1
            continue
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            n_missing += 1
            continue
        for g in parse_games(data):
            rows.append({'batter': int(pid), 'year': int(year), **g})
    if n_missing:
        print(f'  WARNING: {n_missing} batter-years missing from raw cache '
              f'(treated as zero-SB)', flush=True)
    long = pd.DataFrame(rows)
    if not long.empty:
        long['date'] = pd.to_datetime(long['date'])
    return long


def validate_source(long: pd.DataFrame, by: pd.DataFrame) -> bool:
    """HARD GATE: gameLog season sums vs mlb_sb from the counting-stats JSONs.
    League total within +/-1% per year (common batters) AND per-player-year
    r >= 0.99."""
    print('\n=== SOURCE VALIDATION (hard gate) ===', flush=True)
    season = (long.groupby(['batter', 'year'])['sb'].sum()
              .rename('gl_sb').reset_index())
    all_ok = True
    all_pairs = []
    for year in sorted(by['year'].unique()):
        cpath = CACHE / f'hitter_counting_stats_{year}.json'
        if not cpath.exists():
            print(f'  [{year}] counting-stats JSON missing — SKIP')
            continue
        cnts = pd.DataFrame(json.loads(cpath.read_text()))
        cnts = cnts[['batter', 'mlb_sb']].copy()
        cnts['batter'] = cnts['batter'].astype(int)
        yr = season[season['year'] == year]
        m = cnts.merge(yr, on='batter', how='inner')
        # batters in rolling substrate but absent from gameLog cache -> gl 0
        m['gl_sb'] = m['gl_sb'].fillna(0)
        tot_api, tot_gl = m['mlb_sb'].sum(), m['gl_sb'].sum()
        pct = (tot_gl - tot_api) / max(tot_api, 1) * 100
        r = float(np.corrcoef(m['mlb_sb'], m['gl_sb'])[0, 1])
        exact = float((m['mlb_sb'] == m['gl_sb']).mean())
        ok = abs(pct) <= 1.0 and r >= 0.99
        all_ok &= ok
        all_pairs.append(m.assign(year=year))
        print(f'  [{year}] n={len(m):4d}  mlb_sb={tot_api:5d}  '
              f'gamelog_sb={tot_gl:5d}  diff={pct:+.2f}%  r={r:.4f}  '
              f'exact-match={exact:.1%}  -> {"PASS" if ok else "FAIL"}')
    if all_pairs:
        allm = pd.concat(all_pairs)
        r_all = float(np.corrcoef(allm['mlb_sb'], allm['gl_sb'])[0, 1])
        print(f'  [ALL ] pooled r={r_all:.4f}  '
              f'league diff={(allm["gl_sb"].sum()-allm["mlb_sb"].sum())/max(allm["mlb_sb"].sum(),1)*100:+.2f}%')
    print(f'  GATE: {"PASS" if all_ok else "FAIL"}')
    return all_ok


def cmd_assemble() -> None:
    by = load_batter_years()
    grid = (pd.read_csv(ROLLING_CSV,
                        usecols=['year', 'split_day', 'cutoff_date'])
            .drop_duplicates().sort_values(['year', 'split_day']))
    grid['cutoff_date'] = pd.to_datetime(grid['cutoff_date'])
    print(f'Grid: {len(grid)} (year, split_day) cells; '
          f'{len(by)} batter-years', flush=True)

    long = build_long_table(by)
    print(f'Long table: {len(long)} player-games, '
          f'{long.groupby(["batter","year"]).ngroups} batter-years with games',
          flush=True)

    gate_ok = validate_source(long, by)

    # As-of aggregation aligned to the exact grid
    out_rows = []
    for year, g in grid.groupby('year'):
        yb = by.loc[by['year'] == year, 'batter'].astype(int)
        yl = long[long['year'] == year]
        for _, row in g.iterrows():
            cut = row['cutoff_date']
            w_to = yl[yl['date'] <= cut]
            w_21 = yl[(yl['date'] > cut - pd.Timedelta(days=21))
                      & (yl['date'] <= cut)]
            sb_to = w_to.groupby('batter')['sb'].sum()
            sb_21 = w_21.groupby('batter')['sb'].sum()
            d = pd.DataFrame({'batter': yb.values})
            d['year'] = int(year)
            d['split_day'] = int(row['split_day'])
            d['cutoff_date'] = cut.date()
            d['sb_to'] = d['batter'].map(sb_to).fillna(0).astype(int)
            d['sb_last21'] = d['batter'].map(sb_21).fillna(0).astype(int)
            out_rows.append(d)
    out = pd.concat(out_rows, ignore_index=True)
    out.to_csv(OUT_CSV, index=False)
    print(f'\nWrote {OUT_CSV}: {len(out)} rows')
    print('  league mean sb_to at final split per year:')
    fin = out.loc[out.groupby('year')['split_day'].transform('max')
                  == out['split_day']]
    print(fin.groupby('year')['sb_to'].agg(['mean', 'max']).to_string())

    marker = OUT_CSV.with_suffix('.FAILED_GATE')
    if not gate_ok:
        marker.write_text('source validation gate FAILED — do not consume')
        print('\nGATE FAILED — wrote .FAILED_GATE marker; exit 2')
        sys.exit(2)
    elif marker.exists():
        marker.unlink()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=['pull', 'assemble'])
    ap.add_argument('--years', type=str, default=None,
                    help='comma-separated years (pull stage)')
    ap.add_argument('--max-seconds', type=float, default=0.0,
                    help='pull stage: exit cleanly after N seconds')
    ap.add_argument('--force', action='store_true',
                    help='pull stage: re-fetch even if cached (in-progress year)')
    args = ap.parse_args()
    if args.stage == 'pull':
        if args.years:
            years = [int(y) for y in args.years.split(',')]
        else:
            years = sorted(load_batter_years()['year'].unique())
        cmd_pull(years, args.max_seconds, args.force)
    else:
        cmd_assemble()


if __name__ == '__main__':
    main()
