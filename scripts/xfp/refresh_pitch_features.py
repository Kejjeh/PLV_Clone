"""refresh_pitch_features.py — keep data/processed/pitch_features/year=<Y> current.

The PLV research pipeline (plv_clone.pipelines.build_pitch_dataset) owns these
parquets; the xfp chain only READS them — build_sp_archetypes.build_pitch_arsenal
derives the pitch-mix columns in sp_ratings_master.csv (FB/SL/CB/CH/FS %,
primary/secondary group, pitch_archetype, arsenal_entropy). Pitch-mix shares
drift slowly and the full-season feature rebuild costs minutes, so the default
cadence is weekly: skip when the current-year partition is younger than
--max-age-days. The raw pull underneath is manifest-incremental (only missing
days are fetched); the partition write is delete_matching (idempotent).
"""
from __future__ import annotations
import argparse
import os
import time
from datetime import date, timedelta
from pathlib import Path

from plv_clone.paths import ROOT

SEASON_START = {2026: date(2026, 3, 25)}


def newest_mtime(part_dir: Path) -> float:
    files = list(part_dir.glob('*.parquet'))
    return max((f.stat().st_mtime for f in files), default=0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=date.today().year)
    ap.add_argument('--max-age-days', type=float, default=7.0,
                    help='skip rebuild when the year partition is younger than this')
    ap.add_argument('--force', action='store_true', help='rebuild regardless of age')
    args = ap.parse_args()

    # PipelineConfig data paths are relative — anchor to the repo root.
    os.chdir(ROOT)

    part_dir = ROOT / 'data' / 'processed' / 'pitch_features' / f'year={args.year}'
    mtime = newest_mtime(part_dir) if part_dir.exists() else 0.0
    age_days = (time.time() - mtime) / 86400 if mtime else float('inf')
    print(f'pitch_features year={args.year}: age {age_days:.1f}d '
          f'(threshold {args.max_age_days}d)', flush=True)
    if not args.force and age_days < args.max_age_days:
        print('  fresh enough — skipping rebuild')
        return

    from plv_clone.pipelines.build_pitch_dataset import run
    start = SEASON_START.get(args.year, date(args.year, 3, 1))
    end = date.today() - timedelta(days=1)
    print(f'  rebuilding {start} → {end} ...', flush=True)
    out = run(start_date=start, end_date=end)
    print(f'  done → {out}')


if __name__ == '__main__':
    main()
