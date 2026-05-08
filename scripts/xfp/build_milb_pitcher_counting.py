"""build_milb_pitcher_counting.py — per-pitcher MiLB season counting stats.

Mirrors `build_pitcher_counting.py` but adds &sportId for MiLB levels:
  sportId=11 -> Triple-A (AAA)
  sportId=12 -> Double-A  (AA)

Output:
  data/research/xfp_cache/milb_pitcher_stats_{year}_{level}.json   per (year, level)
  data/research/xfp_cache/milb_pitchers_2015_2026.csv              consolidated

We pull 2015-2026 across AAA + AA. Used by MT1 (carryover screen) and MT2
(translation model) to project MLB FP for pitchers without sufficient MLB
sample (rookies, partial-season call-ups).
"""
from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
YEARS = list(range(2015, 2027))
LEVELS = {
    11: 'AAA',
    12: 'AA',
}

KEEP_STAT_FIELDS = [
    'gamesPlayed', 'gamesStarted', 'gamesPitched', 'gamesFinished',
    'inningsPitched', 'outs', 'battersFaced',
    'wins', 'losses', 'saves', 'saveOpportunities', 'holds', 'blownSaves',
    'strikeOuts', 'baseOnBalls', 'hits', 'earnedRuns', 'homeRuns',
    'hitByPitch', 'wildPitches', 'balks',
    'era', 'whip',
]


def fetch_year_level(year: int, sport_id: int, page_size: int = 1000) -> list[dict]:
    """Fetch all pitcher counting stats for a single (season, sportId)."""
    all_rows: list[dict] = []
    offset = 0
    while True:
        url = ('https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching'
               f'&season={year}&sportId={sport_id}'
               f'&playerPool=All&limit={page_size}&offset={offset}')
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
        except Exception as exc:
            print(f'  [{year}/sport={sport_id}] offset={offset} ERROR: {exc}')
            break
        data = r.json()
        splits = data.get('stats', [{}])[0].get('splits', [])
        if not splits:
            break
        for s in splits:
            stat = s.get('stat', {})
            player = s.get('player', {})
            row = {
                'pitcher': int(player.get('id') or 0),
                'name': player.get('fullName'),
                'season': int(s.get('season') or year),
                'level': LEVELS.get(sport_id, str(sport_id)),
                'sport_id': sport_id,
                'team_id': (s.get('team') or {}).get('id'),
                'team_abbr': (s.get('team') or {}).get('abbreviation'),
            }
            for f in KEEP_STAT_FIELDS:
                v = stat.get(f)
                if isinstance(v, str):
                    try:
                        row[f] = float(v) if '.' in v else int(v)
                    except ValueError:
                        row[f] = v
                else:
                    row[f] = v
            all_rows.append(row)
        if len(splits) < page_size:
            break
        offset += page_size
        time.sleep(0.2)
    return all_rows


def derive_rates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    bf = pd.to_numeric(df['battersFaced'], errors='coerce').fillna(0)
    k = pd.to_numeric(df['strikeOuts'], errors='coerce').fillna(0)
    bb = pd.to_numeric(df['baseOnBalls'], errors='coerce').fillna(0)
    hr = pd.to_numeric(df['homeRuns'], errors='coerce').fillna(0)
    hits = pd.to_numeric(df['hits'], errors='coerce').fillna(0)
    er = pd.to_numeric(df['earnedRuns'], errors='coerce').fillna(0)
    ip_str = df['inningsPitched'].astype(str)

    def ip_to_float(s: str) -> float:
        if not s or s == 'nan':
            return 0.0
        try:
            whole, _, frac = s.partition('.')
            whole_i = int(whole or 0)
            if frac == '1':
                return whole_i + 1/3
            if frac == '2':
                return whole_i + 2/3
            return float(s)
        except Exception:
            return 0.0

    ip = ip_str.apply(ip_to_float)
    df['ip'] = ip
    bf_safe = bf.replace(0, np.nan)
    ip_safe = ip.replace(0, np.nan)
    df['k_pct'] = (k / bf_safe).astype(float)
    df['bb_pct'] = (bb / bf_safe).astype(float)
    df['k_minus_bb_pct'] = df['k_pct'] - df['bb_pct']
    df['hr_per_9'] = (hr * 9 / ip_safe).astype(float)
    df['h_per_9'] = (hits * 9 / ip_safe).astype(float)
    df['er_per_9'] = (er * 9 / ip_safe).astype(float)
    g = pd.to_numeric(df['gamesPitched'], errors='coerce').fillna(0)
    df['ip_per_g'] = (ip / g.replace(0, np.nan)).astype(float)
    return df


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    for year in YEARS:
        for sport_id, level in LEVELS.items():
            out_path = CACHE / f'milb_pitcher_stats_{year}_{level}.json'
            if out_path.exists():
                # cache hit — load and skip refetch
                rows = json.loads(out_path.read_text(encoding='utf-8'))
                print(f'[{year}/{level}] cached: {len(rows)} rows')
            else:
                print(f'[{year}/{level}] fetching...', flush=True)
                rows = fetch_year_level(year, sport_id)
                if not rows:
                    print(f'  [{year}/{level}] 0 rows — skipping write')
                    continue
                out_path.write_text(json.dumps(rows, indent=2), encoding='utf-8')
                print(f'  wrote {len(rows)} rows -> {out_path.name}')
            all_rows.extend(rows)

    if not all_rows:
        print('No rows; aborting consolidated CSV.')
        return
    df = pd.DataFrame(all_rows)
    df = derive_rates(df)
    df = df.sort_values(['pitcher', 'season', 'level']).reset_index(drop=True)
    out_csv = CACHE / 'milb_pitchers_2015_2026.csv'
    df.to_csv(out_csv, index=False)
    print(f'Consolidated -> {out_csv}: {len(df)} rows ({df["pitcher"].nunique()} pitchers)')
    print('Coverage by year/level:')
    print(df.groupby(['season', 'level']).size().unstack(fill_value=0).to_string())


if __name__ == '__main__':
    main()
