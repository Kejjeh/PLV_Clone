"""Disk-cache for the expensive whole-league builds that the triangulate card pays on
EVERY invocation — the in-season archetype snapshots (~SP/H/RP, tens of seconds) and the
SP velo-decline map. Each is a pure function of the statcast cache files, so we key the
cache on the (mtime, size) signature of its declared dependency files plus a VERSION:

  * a daily statcast refresh changes statcast_2026.parquet's mtime/size  -> auto-invalidate
  * a build-logic change                                                 -> bump `version`

This collapses the cold ~tens-of-seconds build to a ~1-2s pickle load on every warm run,
which matters most for single-player / small-batch triangulate calls (they pay the full
build today) and lets --jobs parallelism actually scale (children load from disk instead
of each re-reading the big statcast parquet and thrashing I/O). The in-process @lru_cache
still sits on top, so within one process it is built/loaded at most once.

Writes are atomic (temp + os.replace) so concurrent --jobs children can't corrupt the file,
and a corrupt/unreadable entry is silently rebuilt. Pickle files are gitignored (CLAUDE.md #5).
"""
from __future__ import annotations
import glob
import hashlib
import os
import pickle
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_CACHE_DIR = _ROOT / 'data' / 'research' / 'xfp_cache' / '.build_cache'
STATCAST_2026 = str(_ROOT / 'data' / 'research' / 'xfp_cache' / 'statcast_2026.parquet')


def _dep_sig(dep_paths) -> str:
    parts = []
    for p in dep_paths:
        try:
            st = os.stat(p)
            parts.append(f"{os.path.basename(p)}:{int(st.st_mtime)}:{st.st_size}")
        except OSError:
            parts.append(f"{os.path.basename(p)}:missing")
    return hashlib.md5('|'.join(parts).encode()).hexdigest()[:16]


def disk_cached(name: str, builder, dep_paths, version: int = 1):
    """Return builder() result, cached to disk keyed on (version, dep file signatures).

    name       — stable cache name (one logical build)
    builder    — zero-arg callable that produces a picklable value
    dep_paths  — files whose (mtime,size) invalidate the cache when they change
    version    — bump when builder logic changes (forces a rebuild)
    """
    sig = f"{version}_{_dep_sig(dep_paths)}"
    path = _CACHE_DIR / f"{name}_{sig}.pkl"
    if path.exists():
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass  # corrupt/partial -> rebuild
    val = builder()
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f'.{os.getpid()}.tmp')
        with open(tmp, 'wb') as f:
            pickle.dump(val, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)  # atomic — concurrent jobs can't read a partial file
        for old in glob.glob(str(_CACHE_DIR / f"{name}_*.pkl")):  # prune stale versions
            if old != str(path):
                try:
                    os.remove(old)
                except OSError:
                    pass
    except Exception:
        pass  # caching is best-effort; never fail the build over a cache write
    return val
