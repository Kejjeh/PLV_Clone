"""Pull FanGraphs pitcher data 2020-2025 (Stuff+/Location+/Pitching+ available 2020+)."""
from __future__ import annotations
import sys, time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT / 'scripts'))

from fetch_fangraphs import run

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

if __name__ == '__main__':
    for yr in YEARS:
        out = ROOT / 'data' / 'outputs' / f'fangraphs_pitchers_{yr}.csv'
        if out.exists():
            print(f'[{yr}] cached -> {out.name}', flush=True)
            continue
        print(f'[{yr}] pulling FanGraphs ...', flush=True)
        try:
            run(yr)
        except Exception as e:
            print(f'[{yr}] FAILED: {e}', flush=True)
        time.sleep(2.0)  # be polite to FG
    print('=== FG history pull DONE ===', flush=True)
