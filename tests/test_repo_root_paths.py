"""Guard against the repo-root path-drift bug class.

On 2026-07-19 (commit b42b561) 96 scripts were archived one directory deeper
without updating their hardcoded ``ROOT = Path(__file__).resolve().parents[N]``.
``ROOT`` silently began resolving to ``<repo>/scripts``, so baseline data files
failed ``.exists()`` and were replaced with ``0.0`` constants — a Rule 9 baseline
degraded without a single error message. Measured cost on rh3: cross-year r
0.6418 -> 0.6050 (-0.0368) against a +0.005 promotion gate.

The bug is fully machine-detectable, so it should never recur. See
``docs/rh3_harness_root_bug_2026-07-28.md``.

Two tests:
  1. every hardcoded ``parents[N]`` repo-root anchor still resolves to the repo root
  2. the preferred marker-based form actually finds the root from any depth
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())

SKIP_DIRS = {".git", "node_modules", ".cache", ".venv", "venv", "__pycache__", "xfp-model", "build"}

# Variable names that denote the repository root by convention.
ROOTISH_NAMES = {"ROOT", "_ROOT", "REPO_ROOT", "_REPO_ROOT", "PROJECT_ROOT", "pre_reg_path"}

# Anchors that deliberately point somewhere OTHER than the repo root.
# (path, variable) -> what it is actually anchored to, for the failure message.
INTENTIONAL_NON_ROOT = {
    ("scripts/xfp/lib/rating_arc.py", "_XFP"): "scripts/xfp (added to sys.path)",
}

ASSIGN_RE = re.compile(
    r"^[ \t]*(?P<var>[A-Za-z_]\w*)\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[(?P<n>\d+)\]\s*$",
    re.M,
)


def _python_files() -> list[Path]:
    return [
        f
        for f in REPO_ROOT.rglob("*.py")
        if not (SKIP_DIRS & set(f.parts)) and f != Path(__file__)
    ]


def _anchors() -> list[tuple[Path, str, int]]:
    """Every `VAR = Path(__file__).resolve().parents[N]` in the repo."""
    found = []
    for f in _python_files():
        try:
            src = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "parents[" not in src:
            continue
        for m in ASSIGN_RE.finditer(src):
            found.append((f, m.group("var"), int(m.group("n"))))
    return found


def test_hardcoded_parents_anchors_resolve_to_repo_root():
    """A `parents[N]` repo-root anchor must actually land on the repo root.

    If this fails, a file moved and its hardcoded depth did not follow. Fix by
    switching that line to the marker-based form::

        ROOT = next(p for p in Path(__file__).resolve().parents
                    if (p / "pyproject.toml").is_file())

    which survives any future move. If the anchor intentionally points somewhere
    else, add it to INTENTIONAL_NON_ROOT above.
    """
    anchors = _anchors()
    assert anchors, "found no parents[N] anchors at all — the detection regex is probably broken"

    broken = []
    for f, var, n in anchors:
        rel = f.relative_to(REPO_ROOT).as_posix()
        if (rel, var) in INTENTIONAL_NON_ROOT:
            continue
        if var not in ROOTISH_NAMES and not re.search(
            rf"\b{re.escape(var)}\s*/\s*['\"](data|src|scripts|app|docs|tests)['\"]",
            f.read_text(encoding="utf-8"),
        ):
            continue  # not a repo-root anchor
        resolved = f.parents[n] if n < len(f.parents) else None
        if resolved != REPO_ROOT:
            broken.append(f"  {rel}\n      {var} = parents[{n}] -> {resolved}")

    assert not broken, (
        "repo-root anchors that no longer resolve to the repo root "
        f"({len(broken)}):\n" + "\n".join(broken)
    )


def test_intentional_non_root_anchors_are_still_accurate():
    """Keep the allowlist honest: entries must exist and still be non-root.

    Without this, a stale allowlist entry would mask a real regression.
    """
    for (rel, var), description in INTENTIONAL_NON_ROOT.items():
        f = REPO_ROOT / rel
        assert f.is_file(), f"stale allowlist entry: {rel} no longer exists — remove it"
        src = f.read_text(encoding="utf-8")
        m = re.search(
            rf"^[ \t]*{re.escape(var)}\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[(\d+)\]\s*$",
            src,
            re.M,
        )
        assert m, f"stale allowlist entry: {rel} no longer defines {var} that way — remove it"
        resolved = f.parents[int(m.group(1))]
        assert resolved != REPO_ROOT, (
            f"{rel}:{var} now resolves to the repo root ({description} no longer applies) "
            "— drop it from INTENTIONAL_NON_ROOT so it is covered by the main test"
        )


@pytest.mark.parametrize(
    "start",
    [
        "scripts/xfp/research",
        "scripts/xfp/_attic",
        "scripts/xfp/archive",
        "src/plv_clone/models/xfp",
        "tests",
    ],
)
def test_marker_walkup_finds_root_from_any_depth(start):
    """The recommended marker form must work from every tree it is used in."""
    d = REPO_ROOT / start
    if not d.exists():
        pytest.skip(f"{start} not present")
    probe = d / "_probe.py"  # need not exist; parents[] is purely lexical
    found = next(p for p in probe.resolve().parents if (p / "pyproject.toml").is_file())
    assert found == REPO_ROOT
