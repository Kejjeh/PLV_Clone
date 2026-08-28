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


def sections(degraded) -> tuple[str, ...]:
    """The short section names out of ``record()``'s ``section: Type: msg`` lines.

    De-duplicated, first-seen order. Two failures inside ``extra_lenses`` are
    one degraded lens as far as a reader is concerned.
    """
    out: list[str] = []
    for entry in degraded or ():
        name = str(entry).split(':', 1)[0].strip()
        if name and name not in out:
            out.append(name)
    return tuple(out)


def caveat(degraded, *, max_named: int = 4) -> str | None:
    """One line to print above a verdict built on a degraded lens stack, or
    ``None`` when the build was healthy.

    The single owner of this wording (issue #57). Every surface that displays a
    verdict — the CLI card, the dashboard card, a skill's headline — renders
    THIS string, so a reader sees the same caveat everywhere and a wording
    change lands in one place rather than in a subset of call sites.
    """
    names = sections(degraded)
    if not names:
        return None
    shown = ', '.join(names[:max_named])
    if len(names) > max_named:
        shown += f', +{len(names) - max_named} more'
    n = len(names)
    return (
        f"⚠ Verdict built on a degraded lens stack "
        f"({n} lens{'es' if n != 1 else ''} unavailable: {shown}). "
        f"Refresh the missing substrate before treating this as a full-stack read."
    )
