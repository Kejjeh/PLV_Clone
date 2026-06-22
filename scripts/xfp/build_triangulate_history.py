"""build_triangulate_history.py — persist triangulate verdicts over time.

Builds / appends a long-format parquet of every triangulate verdict ever emitted
so we can answer "when did X flip from HOLD to DROP" and audit verdict stability
(CLAUDE.md #12 — never flip a verdict silently; this is the audit trail).

Output: data/research/triangulate_universe/triangulate_verdict_history.parquet
Columns:
  snapshot_date, run_id, player_name, bucket, position_group,
  verdict, verdict_top, category, owner_team, confidence, headline_proj

Two modes:
  reconstruct  RECONSTRUCT the full history from the existing dated run files
               (snapshots/triangulate_*.csv + sibling .json manifests, plus the
               hidden .tri_team_fa_out.* skill outputs). Idempotent — dedupes on
               (run_id, player_name). This is the one-time backfill.
  --append CSV append ONE run's rows to the existing parquet (nightly use). Reads
               the freshly-written snapshot CSV (and, if given, its run manifest
               for the run_id). Atomic write; dedupes; rotates if unbounded.

Usage:
  python scripts/xfp/build_triangulate_history.py reconstruct
  python scripts/xfp/build_triangulate_history.py --append <snapshot_csv> [--run-id ID]

Determinism: scripts never mint an id from a fresh now(). run_id is read from the
sibling .json manifest, derived from the snapshot file mtime, or parsed from the
dated filename — same rule as snapshots.derive_run_id.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd

from scripts.xfp.lib.snapshots import SNAPSHOT_DIR, derive_run_id

UNIVERSE_DIR = 'data/research/triangulate_universe'
HISTORY_PATH = os.path.join(UNIVERSE_DIR, 'triangulate_verdict_history.parquet')

# Long-format schema (one row per player per run).
HISTORY_COLS = [
    'snapshot_date', 'run_id', 'player_name', 'bucket', 'position_group',
    'verdict', 'verdict_top', 'category', 'owner_team', 'confidence',
    'headline_proj',
]

# Keep the history bounded — cap distinct runs retained (oldest dropped).
MAX_RUNS = 400

# Extra dated run files outside snapshots/ that also carry real run rows.
EXTRA_RUN_FILES = [
    'data/research/.tri_team_fa_out.csv',
    'data/research/.tri_grouped.csv',
]


def _date_from_name(path: str) -> str | None:
    m = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(path))
    return m.group(1) if m else None


def _run_id_for(csv_path: str) -> tuple[str, str]:
    """Return (run_id, snapshot_date) for a snapshot/run CSV. Prefers the sibling
    .json manifest's run_id; otherwise derives deterministically."""
    snapshot_date = _date_from_name(csv_path) or ''
    manifest = os.path.splitext(csv_path)[0] + '.json'
    if os.path.exists(manifest):
        try:
            with open(manifest, encoding='utf-8') as f:
                m = json.load(f)
            rid = str(m.get('run_id') or derive_run_id(csv_path))
            if not snapshot_date and len(rid) >= 8:
                snapshot_date = f"{rid[:4]}-{rid[4:6]}-{rid[6:8]}"
            return rid, snapshot_date
        except Exception:
            pass
    rid = derive_run_id(csv_path)
    if not snapshot_date and len(rid) >= 8:
        snapshot_date = f"{rid[:4]}-{rid[4:6]}-{rid[6:8]}"
    return rid, snapshot_date


def _rows_from_csv(csv_path: str, run_id: str | None = None,
                   snapshot_date: str | None = None) -> pd.DataFrame:
    """Project ONE run CSV down to the history schema. Tolerant of missing columns
    (older snapshots predate position_group / owner_team)."""
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"  [skip] {csv_path}: {type(e).__name__}: {e}")
        return pd.DataFrame(columns=HISTORY_COLS)
    if df.empty or 'player_name' not in df.columns:
        return pd.DataFrame(columns=HISTORY_COLS)
    if run_id is None or snapshot_date is None:
        rid, sdate = _run_id_for(csv_path)
        run_id = run_id or rid
        snapshot_date = snapshot_date or sdate
    out = pd.DataFrame()
    out['player_name'] = df['player_name'].astype(str)
    out['snapshot_date'] = snapshot_date
    out['run_id'] = str(run_id)
    for col in ('bucket', 'position_group', 'verdict', 'verdict_top',
                'category', 'owner_team', 'confidence', 'headline_proj'):
        out[col] = df[col] if col in df.columns else None
    # Drop unresolved placeholder rows (no verdict).
    out = out[out['verdict'].notna()] if 'verdict' in df.columns else out
    return out[HISTORY_COLS]


def _atomic_write_parquet(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _dedupe_and_cap(df: pd.DataFrame) -> pd.DataFrame:
    """Dedupe on (run_id, player_name) keeping last, then cap to MAX_RUNS most
    recent run_ids so the file can't grow unbounded."""
    if df.empty:
        return df
    df = df.drop_duplicates(subset=['run_id', 'player_name'], keep='last')
    run_ids = sorted(df['run_id'].dropna().astype(str).unique())
    if len(run_ids) > MAX_RUNS:
        keep = set(run_ids[-MAX_RUNS:])
        df = df[df['run_id'].astype(str).isin(keep)]
    return df.sort_values(['run_id', 'player_name']).reset_index(drop=True)


def _load_existing() -> pd.DataFrame:
    if os.path.exists(HISTORY_PATH):
        try:
            return pd.read_parquet(HISTORY_PATH)
        except Exception as e:
            print(f"  [warn] could not read existing history ({e}); rebuilding fresh")
    return pd.DataFrame(columns=HISTORY_COLS)


def reconstruct() -> pd.DataFrame:
    """Rebuild the history parquet from every dated run file on disk."""
    parts = []
    n_files = 0
    if os.path.isdir(SNAPSHOT_DIR):
        for fn in sorted(os.listdir(SNAPSHOT_DIR)):
            if fn.endswith('.csv') and fn.startswith('triangulate_'):
                p = os.path.join(SNAPSHOT_DIR, fn)
                rows = _rows_from_csv(p)
                if not rows.empty:
                    parts.append(rows)
                    n_files += 1
    for p in EXTRA_RUN_FILES:
        if os.path.exists(p):
            rows = _rows_from_csv(p)
            if not rows.empty:
                parts.append(rows)
                n_files += 1
    if not parts:
        print("  (no run files found to reconstruct from)")
        df = pd.DataFrame(columns=HISTORY_COLS)
    else:
        df = pd.concat(parts, ignore_index=True)
    df = _dedupe_and_cap(df)
    _atomic_write_parquet(df, HISTORY_PATH)
    n_runs = df['run_id'].nunique() if not df.empty else 0
    print(f"reconstruct: {len(df)} rows across {n_runs} runs from {n_files} files")
    print(f"  -> {HISTORY_PATH}")
    return df


def append(csv_path: str, run_id: str | None = None) -> pd.DataFrame:
    """Append ONE run's rows (from a freshly-written snapshot CSV) to the parquet."""
    if not os.path.exists(csv_path):
        print(f"  [skip] append: {csv_path} does not exist")
        return _load_existing()
    new_rows = _rows_from_csv(csv_path, run_id=run_id)
    if new_rows.empty:
        print(f"  [warn] append: no rows extracted from {csv_path}")
        return _load_existing()
    existing = _load_existing()
    combined = pd.concat([existing, new_rows], ignore_index=True)
    combined = _dedupe_and_cap(combined)
    _atomic_write_parquet(combined, HISTORY_PATH)
    rid = new_rows['run_id'].iloc[0]
    print(f"append: +{len(new_rows)} rows (run_id={rid}); history now "
          f"{len(combined)} rows / {combined['run_id'].nunique()} runs")
    print(f"  -> {HISTORY_PATH}")
    return combined


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', nargs='?', default='reconstruct',
                    choices=['reconstruct'],
                    help='reconstruct the full history from existing run files')
    ap.add_argument('--append', default=None, metavar='SNAPSHOT_CSV',
                    help='Append ONE run from this snapshot CSV (nightly mode).')
    ap.add_argument('--run-id', default=None,
                    help='Explicit run_id for --append (else derived deterministically).')
    args = ap.parse_args()

    if args.append:
        append(args.append, run_id=args.run_id)
    else:
        reconstruct()


if __name__ == '__main__':
    main()
