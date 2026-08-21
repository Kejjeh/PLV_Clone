"""Atomic CSV writes for artifacts with uncoordinated readers (issue #34).

A plain to_csv truncates the file first; a reader landing mid-write gets an
EmptyDataError (nightly triangulate, 2026-08-18). Write tmp then replace —
os.replace is atomic on the same filesystem on both Windows and POSIX.
"""
from pathlib import Path


def atomic_to_csv(df, path, **kwargs) -> None:
    path = Path(path)
    kwargs.setdefault('index', False)
    tmp = path.with_suffix(path.suffix + '.tmp')
    df.to_csv(tmp, **kwargs)
    tmp.replace(path)
