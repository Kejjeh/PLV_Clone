"""build_pitcher_counting.py — per-pitcher season counting stats from MLB API.

Mirrors `build_hitter_counting.py` (implicitly part of build_hitters_multiyr.py)
but for the pitching side. We need this primarily for RP role classification:
  - saves, holds, blown_saves, games_pitched, games_started, IP, ER

Output: data/research/xfp_cache/pitcher_counting_stats_{year}.json
        list of dicts keyed on `pitcher` (MLB id)
"""
from __future__ import annotations
import json
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
YEARS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

# Stats we want from MLB API (paginated; up to 1000 per request).
KEEP_STAT_FIELDS = [
    'gamesPlayed', 'gamesStarted', 'gamesPitched', 'gamesFinished',
    'inningsPitched', 'outs', 'battersFaced',
    'wins', 'losses', 'saves', 'saveOpportunities', 'holds', 'blownSaves',
    'strikeOuts', 'baseOnBalls', 'hits', 'earnedRuns', 'homeRuns',
    'hitByPitch', 'wildPitches', 'balks',
    'era', 'whip',
]


def fetch_year(year: int, page_size: int = 1000) -> list[dict]:
    """Fetch all pitcher counting stats for a single season."""
    all_rows: list[dict] = []
    offset = 0
    while True:
        url = ('https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching'
               f'&season={year}&playerPool=All&limit={page_size}&offset={offset}')
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
        except Exception as exc:
            print(f'  [{year}] offset={offset} ERROR: {exc}')
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
                'team_id': (s.get('team') or {}).get('id'),
                'team_abbr': (s.get('team') or {}).get('abbreviation'),
            }
            for f in KEEP_STAT_FIELDS:
                v = stat.get(f)
                if isinstance(v, str):
                    # Convert numeric strings (e.g., "12.1" IP, "3.45" ERA)
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


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    from datetime import date as _date
    _t = _date.today()
    _cur = _t.year if _t.month >= 3 else _t.year - 1
    for year in YEARS:
        out_path = CACHE / f'pitcher_counting_stats_{year}.json'
        # Inverse of the hitters bug (audit 2026-07-04): this refetched EVERY
        # immutable year daily. Completed years with a cache are skipped.
        if year < _cur and out_path.exists():
            print(f'[{year}] immutable year cached - skipping fetch', flush=True)
            continue
        print(f'[{year}] fetching pitcher counting stats...', flush=True)
        rows = fetch_year(year)
        out_path.write_text(json.dumps(rows, indent=2), encoding='utf-8')
        # Sanity check: top SV-getters
        rows_sv = sorted(rows, key=lambda r: -(r.get('saves') or 0))
        print(f'  wrote {len(rows)} rows -> {out_path.name}')
        print(f'  top 5 by saves:')
        for r in rows_sv[:5]:
            print(f'    {r.get("name","?"):<24s}  SV={r.get("saves"):>3}  '
                  f'HLD={r.get("holds"):>3}  G={r.get("gamesPitched"):>3}  '
                  f'IP={r.get("inningsPitched")}')


if __name__ == '__main__':
    main()
