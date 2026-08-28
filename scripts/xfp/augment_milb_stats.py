"""augment_milb_stats.py — refetch MiLB pitcher stats with extended fields.

The original substrate was built with a narrow KEEP_STAT_FIELDS set. This
adds groundOuts, airOuts, numberOfPitches, strikePercentage, etc. for
GB% / pitch-efficiency features.

Output (rewrites): data/research/xfp_cache/milb_pitchers_2015_2026.csv
"""
from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from plv_clone.fantasy.scoring import parse_ip as _canon_parse_ip  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
YEARS = list(range(2015, 2027))
LEVELS = {11: 'AAA', 12: 'AA'}

EXT_FIELDS = [
    'gamesPlayed', 'gamesStarted', 'gamesPitched', 'gamesFinished',
    'inningsPitched', 'outs', 'battersFaced',
    'wins', 'losses', 'saves', 'saveOpportunities', 'holds', 'blownSaves',
    'strikeOuts', 'baseOnBalls', 'hits', 'earnedRuns', 'homeRuns',
    'hitByPitch', 'wildPitches', 'balks', 'era', 'whip',
    # NEW
    'groundOuts', 'airOuts', 'doubles', 'triples', 'atBats',
    'numberOfPitches', 'strikes', 'strikePercentage', 'pitchesPerInning',
    'groundOutsToAirouts', 'totalBases', 'age',
]


def fetch_year_level(year: int, sport_id: int, page_size: int = 1000) -> list[dict]:
    rows = []
    offset = 0
    while True:
        url = ('https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching'
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
                'pitcher': int(player.get('id') or 0),
                'name': player.get('fullName'),
                'season': int(s.get('season') or year),
                'level': LEVELS.get(sport_id, str(sport_id)),
                'sport_id': sport_id,
                'team_id': (s.get('team') or {}).get('id'),
                'team_abbr': (s.get('team') or {}).get('abbreviation'),
            }
            for f in EXT_FIELDS:
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


def ip_to_float(s) -> float:
    # Delegates to the ONE canonical parser (issue #78). Fifteen private
    # copies of this logic is how two of them drifted (PR #77).
    if s is None or str(s) in ('', 'nan'):
        return 0.0
    return _canon_parse_ip(s, default=0.0)


def main():
    all_rows = []
    for year in YEARS:
        for sport_id, level in LEVELS.items():
            cache = CACHE / f'milb_pitcher_stats_ext_{year}_{level}.json'
            if cache.exists():
                rows = json.loads(cache.read_text(encoding='utf-8'))
                print(f'[{year}/{level}] cached: {len(rows)}')
            else:
                print(f'[{year}/{level}] fetching extended fields...', flush=True)
                rows = fetch_year_level(year, sport_id)
                if rows:
                    cache.write_text(json.dumps(rows, indent=2), encoding='utf-8')
                    print(f'  wrote {len(rows)} rows')
                else:
                    print(f'  0 rows; skipping write')
                    continue
            all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    for c in ['battersFaced', 'strikeOuts', 'baseOnBalls', 'homeRuns', 'hits',
              'earnedRuns', 'gamesPitched', 'gamesStarted', 'groundOuts', 'airOuts',
              'numberOfPitches', 'strikes', 'doubles', 'triples', 'atBats',
              'totalBases', 'hitByPitch']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    df['ip'] = df['inningsPitched'].apply(ip_to_float)

    bf = df['battersFaced'].replace(0, np.nan)
    ip = df['ip'].replace(0, np.nan)
    g = df['gamesPitched'].replace(0, np.nan)
    out_grounders = df['groundOuts']
    out_air = df['airOuts']
    out_total = (out_grounders + out_air).replace(0, np.nan)

    df['k_pct'] = df['strikeOuts'] / bf
    df['bb_pct'] = df['baseOnBalls'] / bf
    df['k_minus_bb_pct'] = df['k_pct'] - df['bb_pct']
    df['hr_per_9'] = df['homeRuns'] * 9 / ip
    df['h_per_9'] = df['hits'] * 9 / ip
    df['er_per_9'] = df['earnedRuns'] * 9 / ip
    df['ip_per_g'] = df['ip'] / g
    df['gb_pct_outs'] = out_grounders / out_total  # GB share of outs (proxy)
    df['pitches_per_bf'] = df['numberOfPitches'] / bf
    df['strike_pct'] = pd.to_numeric(df['strikePercentage'], errors='coerce')
    df['gb_to_air'] = pd.to_numeric(df['groundOutsToAirouts'], errors='coerce')

    df = df.sort_values(['pitcher', 'season', 'level']).reset_index(drop=True)
    out_csv = CACHE / 'milb_pitchers_ext_2015_2026.csv'
    df.to_csv(out_csv, index=False)
    print(f'Wrote {out_csv}: {len(df)} rows')


if __name__ == '__main__':
    main()
