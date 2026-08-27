"""Which lenses degraded during this build — readable by the caller, not just stderr.

WHY THIS EXISTS
The fail-soft lens handlers (``extra_lenses._warn``, ``boom_stack._warn``,
``hitter_boom_stack._warn``) print a stderr breadcrumb and carry on. That was
the 2026-07-04 fix for silent excepts hiding dead lenses for weeks, and for a
human watching a terminal it works.

It does nothing for a *programmatic* caller. `triangulate_player` returned a
verdict with no indication that two lenses had been suppressed, so a checkout
missing `statcast_2026.parquet` produced a DIFFERENT verdict for the same
player -- CAUTION -> MIXED -- and the result dict looked entirely healthy.
That is the exact hazard CLAUDE.md don't-do #12 is about: a verdict may change
only on new data or a corrected error, and never silently.

So this records the same suppressions the breadcrumbs describe, and callers
attach them to their output. Rule 13: recording a degradation cannot move a
rank, and a healthy build records nothing.

Usage (import relatively from inside ``lib``, e.g. ``from .lens_health import
record`` -- an absolute ``lib.`` import only resolves when ``scripts/xfp`` is on
sys.path, which is the very bug that motivated this module)::

    reset()                     # start of a build
    record("extra_lenses.trend_lens", exc)
    snapshot()                  # -> ("extra_lenses.trend_lens: FileNotFoundError ...",)
"""
from __future__ import annotations

import threading

_LOCK = threading.Lock()
_DEGRADED: list[str] = []


def record(section: str, exc: BaseException) -> None:
    """Note that ``section`` failed and was suppressed. Never raises."""
    try:
        entry = f"{section}: {type(exc).__name__}: {exc}"
        with _LOCK:
            if entry not in _DEGRADED:
                _DEGRADED.append(entry)
    except Exception:
        pass


def snapshot() -> tuple[str, ...]:
    """The suppressions recorded so far, in first-seen order."""
    with _LOCK:
        return tuple(_DEGRADED)


def reset() -> None:
    """Clear the registry (call at the start of a build)."""
    with _LOCK:
        _DEGRADED.clear()
