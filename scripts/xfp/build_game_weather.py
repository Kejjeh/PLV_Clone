"""build_game_weather.py — fetch per-game temperature for 2018-2025.

Calls MLB Stats API schedule endpoint with weather hydrate (one call per day,
~180 days/season × 8 seasons = ~1500 calls). Output:

  data/research/xfp_cache/game_weather.csv
    Columns: game_pk, game_date, venue, condition, temp_f, wind, dome
"""
from __future__ import annotations
import time
from pathlib import Path
from datetime import date, timedelta
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'game_weather.csv'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]

# Domed/closed-roof venues (consistent climate)
DOMED_VENUES = {
    'Tropicana Field', 'Rogers Centre', 'Globe Life Field', 'loanDepot park',
    'American Family Field', 'Minute Maid Park', 'Daikin Park',
    # Retractable but typically closed:
    'Chase Field',
}


def fetch_day(d: date) -> list[dict]:
    """Fetch weather for all regular-season games on date d."""
    url = ('https://statsapi.mlb.com/api/v1/schedule'
           f'?sportId=1&startDate={d.isoformat()}&endDate={d.isoformat()}&hydrate=weather')
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f'  [{d}] error: {e}')
        return []
    data = r.json()
    rows = []
    for date_block in data.get('dates', []):
        for g in date_block.get('games', []):
            if g.get('gameType') != 'R':
                continue
            w = g.get('weather') or {}
            venue = (g.get('venue') or {}).get('name')
            temp_str = w.get('temp')
            try:
                temp_f = int(temp_str) if temp_str else None
            except (ValueError, TypeError):
                temp_f = None
            rows.append({
                'game_pk': g.get('gamePk'),
                'game_date': d.isoformat(),
                'venue': venue,
                'condition': w.get('condition'),
                'temp_f': temp_f,
                'wind': w.get('wind'),
                'dome': venue in DOMED_VENUES,
            })
    return rows


def main():
    if OUT.exists():
        existing = pd.read_csv(OUT)
        existing_dates = set(existing['game_date'])
        print(f'[weather] {len(existing)} rows already cached, '
              f'{len(existing_dates)} days covered')
    else:
        existing = pd.DataFrame()
        existing_dates = set()

    new_rows = []
    for year in YEARS:
        # MLB regular season: typically late March → end September; expand to be safe
        start = date(year, 3, 20)
        end = date(year, 10, 5)
        d = start
        while d <= end:
            iso = d.isoformat()
            if iso in existing_dates:
                d += timedelta(days=1)
                continue
            rows = fetch_day(d)
            if rows:
                new_rows.extend(rows)
            time.sleep(0.15)
            d += timedelta(days=1)
        print(f'  [{year}] up to {end} — {len(new_rows)} new rows so far')

    if not new_rows:
        print('No new data fetched.')
        return
    new_df = pd.DataFrame(new_rows)
    if not existing.empty:
        out = pd.concat([existing, new_df], ignore_index=True)
        out = out.drop_duplicates('game_pk', keep='last')
    else:
        out = new_df
    out.to_csv(OUT, index=False)
    print(f'Wrote {OUT}: {len(out)} total games '
          f'({out["temp_f"].notna().sum()} with temperature)')


if __name__ == '__main__':
    main()
