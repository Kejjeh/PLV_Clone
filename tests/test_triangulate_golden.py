"""Equivalence test for the triangulate performance optimization.

The speedups (lru_cache, disk-cache, `--jobs` subprocess sharding) MUST leave the batch
output unchanged: the parallel (sharded) run has to reassemble VALUE-FOR-VALUE to the
single-process run — including the cross-player `within_bucket_rank` / `floor_adj_rank`
finalizers, which are recomputed on the concatenated frame, not per shard.

This compares the two engine paths TO EACH OTHER over a fixed 80-player universe
(`tests/golden/triangulate_input.csv`), so it stays green across the daily data refreshes
that rebuild rp3/rh3/archetypes. (The one-time pre-vs-post-optimization equivalence was
verified at capture time against a frozen golden; a data-coupled golden could not survive
a refresh — parallel≡batch is the durable invariant the optimization actually needs to hold.)

Slow (runs the real batch subprocess twice); marked so it can be deselected.
"""
import os
import sys
import subprocess
import tempfile

import pandas as pd
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GIN = os.path.join(ROOT, 'tests', 'golden', 'triangulate_input.csv')



import pytest
pytestmark = pytest.mark.slow  # 22.8s = 42% of suite wall (audit 2026-07-04)

def _run_batch(out_path, extra=()):
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
    subprocess.run(
        [sys.executable, '-X', 'utf8', 'scripts/xfp/run_triangulate.py',
         '--names-file', GIN, '--csv-out', out_path, *extra],
        check=True, cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _read(path):
    return pd.read_csv(path).sort_values('player_name').reset_index(drop=True)


def _assert_value_identical(ref: pd.DataFrame, got: pd.DataFrame):
    assert list(got.columns) == list(ref.columns), (
        f"column set/order diverged:\n ref={list(ref.columns)}\n got={list(got.columns)}")
    assert len(got) == len(ref), f"row count {len(got)} != {len(ref)}"
    bad = []
    for c in ref.columns:
        a, b = ref[c], got[c]
        if a.dtype.kind in 'fi' and b.dtype.kind in 'fi':
            if not ((a.fillna(-9e18) - b.fillna(-9e18)).abs() < 1e-9).all():
                bad.append(c)
        else:
            if not (a.fillna('∅').astype(str) == b.fillna('∅').astype(str)).all():
                bad.append(c)
    assert not bad, f"parallel diverged from batch in columns: {bad}"


@pytest.mark.slow
def test_parallel_reassembles_identical_to_batch():
    """`--jobs 4` (sharded child processes) must produce the SAME output as the
    single-process batch, value-for-value — the core guarantee of the parallel speedup."""
    serial = tempfile.NamedTemporaryFile(suffix='.csv', delete=False).name
    parallel = tempfile.NamedTemporaryFile(suffix='.csv', delete=False).name
    _run_batch(serial)
    _run_batch(parallel, extra=('--jobs', '4'))
    _assert_value_identical(_read(serial), _read(parallel))
