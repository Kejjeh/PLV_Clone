"""snapshot_projections.py — save current projections to a dated archive.

Each week, run this to snapshot xfp_rh3_projections.csv and xfp_rp3_projections.csv
into data/research/projection_snapshots/{YYYY-MM-DD}/. The accuracy tracker
later compares these snapshots against subsequent actual fp earned to measure
calibration over time.

Usage:
    python scripts/xfp/snapshot_projections.py
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import shutil

ROOT = Path('c:/Users/Joshua/plv_clone')
OUT = ROOT / 'data' / 'outputs'
SNAP = ROOT / 'data' / 'research' / 'projection_snapshots'

TO_COPY = [
    'xfp_rh3_projections.csv',
    'xfp_rp3_projections.csv',
]


def main():
    today = date.today().isoformat()
    snap_dir = SNAP / today
    snap_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for fname in TO_COPY:
        src = OUT / fname
        if not src.exists():
            print(f'  skip {fname}: not found')
            continue
        dst = snap_dir / fname
        shutil.copyfile(src, dst)
        written.append(fname)
        print(f'  wrote {dst}')

    if written:
        print(f'\nSnapshot saved to {snap_dir} ({len(written)} files)')
    else:
        print('No files snapshotted (no projection CSVs found).')


if __name__ == '__main__':
    main()
