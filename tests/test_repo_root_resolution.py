"""A driver must find the repo root from __file__, never from the cwd.

WHY THIS FILE EXISTS
Drivers reached the repo root three different ways (issue #72):

    sys.path.insert(0, str(ROOT))     # 109 sites — the convention
    sys.path.insert(0, str(REPO))     # 16 sites — same thing, different name
    sys.path.insert(0, '.')           # 23 sites — the CWD, not the repo

The third works when launched from the repo root and silently fails anywhere
else: cron, a CI runner, a different working directory. Combined with a
fail-soft import handler that is the 2026-08-18 shape — a feature that works
on one machine and is dead everywhere else, with nothing reporting it.

It also made the general version of PR #71's guard unwritable: deciding
whether a given driver can resolve `scripts.xfp.*` needed an AST heuristic,
and one keyed on the NAME `ROOT` flagged 22 files that were fine.

Standardised on a __file__-relative root 2026-08-27.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIP = ("_oneoff", "_attic", "_research", "archive")

_CWD_INSERT = re.compile(
    r"""sys\.path\.(?:insert\(\s*0\s*,\s*|append\(\s*)(?:['"]\.['"]|os\.getcwd\(\))"""
)


def _driver_files() -> list[Path]:
    # Underscore-prefixed files are ad-hoc scratch drivers (same convention as
    # test_failsoft_imports_resolve) — locally they're gitignored and untracked,
    # so flagging them fails developers' machines on files CI can never see
    # (2026-08-28: five local `scripts/_*.py` scratch runs did exactly that).
    return [p for p in sorted((ROOT / "scripts").rglob("*.py"))
            if not any(sd in str(p) for sd in SKIP)
            and not p.name.startswith("_")]


def test_no_driver_resolves_the_repo_root_from_the_cwd():
    offenders = []
    for path in _driver_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if _CWD_INSERT.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:70]}")
    assert not offenders, (
        "sys.path root taken from the CWD — works from the repo root and "
        "silently fails under cron / CI / any other launcher:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse a __file__-relative root: "
          "Path(__file__).resolve().parents[N].")


def test_every_declared_repo_root_actually_resolves_there():
    """An off-by-one in parents[N] is worse than the cwd form it replaced.

    It fails silently and points at scripts/ instead — which is exactly what
    the first pass of this change did before it was checked.
    """
    pat = re.compile(r"Path\(__file__\)\.resolve\(\)\.parents\[(\d+)\]")
    wrong = []
    for path in _driver_files():
        src = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(src.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            m = pat.search(line)
            if not m:
                continue
            # only check the ones bound to a repo-root-looking name
            if not re.search(r"\b(ROOT|REPO|_REPO_ROOT)\b\s*=", line):
                continue
            try:
                resolved = path.resolve().parents[int(m.group(1))]
            except IndexError:
                wrong.append(f"{path.relative_to(ROOT)}:{lineno}: parents index out of range")
                continue
            if resolved != ROOT:
                wrong.append(
                    f"{path.relative_to(ROOT)}:{lineno}: parents[{m.group(1)}] "
                    f"-> {resolved.name}/, not the repo root")
    assert not wrong, "repo-root declarations that do not resolve there:\n  " + "\n  ".join(wrong)


def test_the_scan_actually_sees_the_drivers():
    """Guard the guard — an empty file list passes everything vacuously."""
    assert len(_driver_files()) >= 100, (
        f"only {len(_driver_files())} driver files found; the walk is broken")
