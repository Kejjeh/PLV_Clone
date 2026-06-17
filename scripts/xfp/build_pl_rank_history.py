"""build_pl_rank_history.py — archive Pitcher List rank caches as date-keyed snapshots.

The four PL caches in data/research/pl_cache/ are overwrite-style (last fetch
only) for hitters_top150 / sps_top100 / closers. Without a date-keyed history
we cannot compute week-over-week Δ-rank — the central feature of the
opponent-action predictor for managers who follow PL.

What this script does (idempotent):
  - For each canonical cache file (pl_hitters_top150.json, pl_sps_top100.json,
    pl_closers.json), if its `fetched` date is newer than the most recent
    archived snapshot, write a copy to pl_<name>_<fetched_date>.json.
  - Skips the streamer cache — already date-keyed at write time.

Output: data/research/pl_cache/pl_<name>_YYYY-MM-DD.json (one per refresh).

Atomic write via temp+rename. Never overwrites an existing dated snapshot.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from plv_clone.paths import ROOT
CACHE = ROOT / 'data' / 'research' / 'pl_cache'

CANONICAL = [
    'pl_hitters_top150.json',
    'pl_sps_top100.json',
    'pl_closers.json',
]


def archive_one(canonical_name: str) -> tuple[str, str | None]:
    """Returns (action, archive_path_or_none). action in {wrote, skip-existing, skip-empty, skip-no-date}."""
    src = CACHE / canonical_name
    if not src.exists():
        return ('skip-empty', None)
    try:
        payload = json.loads(src.read_text(encoding='utf-8'))
    except Exception as e:
        return (f'skip-error:{e}', None)
    fetched = payload.get('fetched')
    if not fetched:
        return ('skip-no-date', None)
    ranks = payload.get('ranks') or {}
    if not ranks:
        return ('skip-empty', None)
    stem = canonical_name.replace('.json', '')
    dest = CACHE / f'{stem}_{fetched}.json'
    if dest.exists():
        return ('skip-existing', str(dest))
    tmp = dest.with_suffix('.json.tmp')
    shutil.copy2(src, tmp)
    tmp.replace(dest)
    return ('wrote', str(dest))


def main() -> int:
    print('=== PL rank history archiver ===')
    n_wrote = 0
    for name in CANONICAL:
        action, dest = archive_one(name)
        print(f'  {name:30s}  {action:20s}  {dest or ""}')
        if action == 'wrote':
            n_wrote += 1
    print(f'archived {n_wrote} new snapshot(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
