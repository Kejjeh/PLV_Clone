"""build_milb_hitter_counting.py — per-hitter MiLB season counting stats.

Mirrors build_milb_pitcher_counting.py for hitters. Pulls AAA (sportId=11)
and AA (sportId=12), 2015-2026.

Output:
  data/research/xfp_cache/milb_hitter_stats_{year}_{level}.json
  data/research/xfp_cache/milb_hitters_2015_2026.csv  (consolidated, with rates)
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
LEVELS = {11: 'AAA', 12: 'AA'}

KEEP_FIELDS = [
    'age', 'gamesPlayed',
    'plateAppearances', 'atBats', 'hits', 'doubles', 'triples', 'homeRuns',
    'baseOnBalls', 'intentionalWalks', 'strikeOuts', 'hitByPitch',
    'sacFlies', 'sacBunts', 'runs', 'rbi', 'totalBases',
    'groundOuts', 'airOuts', 'groundIntoDoublePlay',
    'stolenBases', 'caughtStealing', 'numberOfPitches',
    'avg', 'obp', 'slg', 'ops', 'babip', 'groundOutsToAirouts',
]


def fetch_year_level(year: int, sport_id: int, page_size: int = 1000) -> list[dict]:
    rows = []
    offset = 0
    while True:
        url = ('https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting'
               f'&season={year}&sportId={sport_id}&playerPool=All'
               f'&limit={page_size}&offset={offset}')
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
        except Exception as exc:
            print(f'  [{year}/sport={sport_id}] offset={offset} ERROR: {exc}')
            break
        splits = r.json().get('stats', [{}])[0].get('splits', [])
        if not splits:
            break
        for s in splits:
            stat = s.get('stat', {})
            player = s.get('player', {})
            row = {
                'batter': int(player.get('id') or 0),
                'name': player.get('fullName'),
                'season': int(s.get('season') or year),
                'level': LEVELS.get(sport_id, str(sport_id)),
                'team_id': (s.get('team') or {}).get('id'),
                'team_abbr': (s.get('team') or {}).get('abbreviation'),
            }
            for f in KEEP_FIELDS:
                v = stat.get(f)
                if isinstance(v, str):
                    try:
                        row[f] = float(v) if '.' in v else int(v)
                    except ValueError:
                        row[f] = v
                else:
                    row[f] = v
            rows.append(row)
        if len(splits) < page_size:
            break
        offset += page_size
        time.sleep(0.2)
    return rows


def derive_rates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ('plateAppearances', 'atBats', 'hits', 'doubles', 'triples',
              'homeRuns', 'baseOnBalls', 'strikeOuts', 'hitByPitch',
              'totalBases', 'stolenBases', 'caughtStealing',
              'groundOuts', 'airOuts'):
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    pa = df['plateAppearances'].replace(0, np.nan)
    ab = df['atBats'].replace(0, np.nan)
    df['k_pct'] = df['strikeOuts'] / pa
    df['bb_pct'] = df['baseOnBalls'] / pa
    df['k_minus_bb_pct'] = df['k_pct'] - df['bb_pct']
    df['hr_per_pa'] = df['homeRuns'] / pa
    df['xbh_per_pa'] = (df['doubles'] + df['triples'] + df['homeRuns']) / pa
    df['iso'] = (df['totalBases'] - df['hits']) / ab  # SLG - AVG
    sb_attempts = df['stolenBases'] + df['caughtStealing']
    df['sb_attempts_per_pa'] = sb_attempts / pa
    df['sb_success'] = df['stolenBases'] / sb_attempts.replace(0, np.nan)
    out_total = (df['groundOuts'] + df['airOuts']).replace(0, np.nan)
    df['gb_pct_outs'] = df['groundOuts'] / out_total
    return df


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for year in YEARS:
        for sport_id, level in LEVELS.items():
            cache = CACHE / f'milb_hitter_stats_{year}_{level}.json'
            if cache.exists():
                rows = json.loads(cache.read_text(encoding='utf-8'))
                print(f'[{year}/{level}] cached: {len(rows)}')
            else:
                print(f'[{year}/{level}] fetching...', flush=True)
                rows = fetch_year_level(year, sport_id)
                if not rows:
                    print(f'  0 rows; skipping write')
                    continue
                cache.write_text(json.dumps(rows, indent=2), encoding='utf-8')
                print(f'  wrote {len(rows)} rows')
            all_rows.extend(rows)
    if not all_rows:
        print('No rows; abort.')
        return
    df = pd.DataFrame(all_rows)
    df = derive_rates(df)
    df = df.sort_values(['batter', 'season', 'level']).reset_index(drop=True)
    out = CACHE / 'milb_hitters_2015_2026.csv'
    df.to_csv(out, index=False)
    print(f'\nConsolidated -> {out}: {len(df)} rows ({df["batter"].nunique()} unique hitters)')
    print('Coverage by year/level:')
    print(df.groupby(['season', 'level']).size().unstack(fill_value=0).to_string())


if __name__ == '__main__':
    main()
