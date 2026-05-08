"""build_milb_pitcher_ages.py — fetch birthDate for every MiLB pitcher.

Output: data/research/xfp_cache/milb_pitcher_ages.csv
  Columns: pitcher (mlb id), birthDate, name
"""
from __future__ import annotations
import json
import time
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'milb_pitcher_ages.csv'


def fetch_people(ids: list[int], chunk: int = 100) -> list[dict]:
    out = []
    for i in range(0, len(ids), chunk):
        batch = ids[i:i + chunk]
        url = ('https://statsapi.mlb.com/api/v1/people'
               f'?personIds={",".join(str(x) for x in batch)}')
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
        except Exception as exc:
            print(f'  batch {i} ERROR: {exc}')
            continue
        data = r.json()
        for p in data.get('people', []):
            out.append({
                'pitcher': int(p.get('id')),
                'name': p.get('fullName'),
                'birthDate': p.get('birthDate'),
            })
        if i % 1000 == 0:
            print(f'  fetched {i+len(batch)}/{len(ids)}')
        time.sleep(0.15)
    return out


def main():
    milb = pd.read_csv(CACHE / 'milb_pitchers_2015_2026.csv')
    pitchers = sorted(milb['pitcher'].dropna().astype(int).unique().tolist())
    print(f'Fetching birthDates for {len(pitchers)} pitchers...')
    rows = fetch_people(pitchers)
    df = pd.DataFrame(rows).drop_duplicates(subset=['pitcher'])
    df.to_csv(OUT, index=False)
    print(f'Wrote {OUT}: {len(df)} rows')


if __name__ == '__main__':
    main()
