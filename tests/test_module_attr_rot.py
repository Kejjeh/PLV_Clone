"""Policy guard: no script may reference a module attribute that no longer exists.

WHY THIS EXISTS
---------------
`scripts/xfp/verdict_backtest.py` called `RH3._signal` / `RP3._signal`. Commit
de9f6e6 ("model vectorization") deleted both helpers and inlined an equivalent
`np.select` into each pipeline's `main()`. Nothing re-pointed the backtest, so
`run_hitters()` and `run_pitchers()` raised `AttributeError` on EVERY
invocation from that commit until 2026-07-29 — and 931 tests passed the whole
time, because no test ever executed those functions and no test checked that
the names they reference still exist.

This is a whole CLASS of rot: an analysis script reaches into a production
module by attribute, production refactors, the script dies silently because
nothing imports or runs it in CI. A targeted smoke test (see
tests/test_verdict_backtest_hosts.py) fixes one instance. This test fixes the
class, statically and cheaply:

  for every first-party module alias bound by an import in a scanned file,
  import the module and assert every `alias.attr` referenced in that file
  actually exists on it.

Deliberate scope limits that keep this NON-FLAKY (each one is a false-negative
we accept, never a false positive):
  * Only first-party roots (plv_clone / lib / app). Third-party attribute
    surfaces move with pinned versions and are not our rot to police.
  * Only aliases that resolve to a real `ModuleType`. Classes and functions
    imported by name are not checked (an instance attribute set in __init__ is
    invisible to a static hasattr check).
  * An alias that is ever rebound in the file (assignment, function parameter,
    comprehension target...) is dropped — the `alias.attr` might be on a
    completely different object.
  * The scanned FILE is only parsed, never imported. Scripts have import-time
    side effects; the modules they reference are library code and safe to
    import.
"""
from __future__ import annotations

import ast
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# `lib.*` resolves only with scripts/xfp on sys.path (see [tool.coverage.paths]);
# `app.*` resolves only with the repo root on sys.path.
for _p in (ROOT, ROOT / "src", ROOT / "scripts" / "xfp"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

FIRST_PARTY_ROOTS = ("plv_clone", "lib", "app")


def _module_aliases(tree: ast.AST) -> dict[str, str]:
    """alias name -> dotted path, for every import in the file."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    out[a.asname] = a.name
                elif "." not in a.name:
                    out[a.name] = a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:  # relative import — skip
                continue
            for a in node.names:
                if a.name == "*":
                    continue
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def _rebound_names(tree: ast.AST, names: set[str]) -> set[str]:
    """Names that are (re)bound anywhere in the file besides the import."""
    bad: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            targets = [node.target]
        elif isinstance(node, ast.withitem):
            if node.optional_vars is not None:
                targets = [node.optional_vars]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = node.args
            for a in (list(args.args) + list(args.posonlyargs) + list(args.kwonlyargs)
                      + [args.vararg, args.kwarg]):
                if a is not None and a.arg in names:
                    bad.add(a.arg)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                bad.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in names:
            bad.add(node.name)
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name) and n.id in names:
                    bad.add(n.id)
    return bad


def _resolve_module(dotted: str) -> types.ModuleType | None:
    """Import `dotted` as a module, or as parent.leaf; None if not a module."""
    try:
        return importlib.import_module(dotted)
    except Exception:
        pass
    if "." not in dotted:
        return None
    parent, leaf = dotted.rsplit(".", 1)
    try:
        obj = getattr(importlib.import_module(parent), leaf, None)
    except Exception:
        return None
    return obj if isinstance(obj, types.ModuleType) else None


def stale_attr_references(files) -> tuple[list[tuple], list[str]]:
    """Return (violations, skips). Violation = (file, lineno, alias, module, attr)."""
    violations: list[tuple] = []
    skips: list[str] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            skips.append(f"{path.name}: unparseable ({exc})")
            continue
        aliases = {k: v for k, v in _module_aliases(tree).items()
                   if v.split(".")[0] in FIRST_PARTY_ROOTS}
        if not aliases:
            continue
        for name in _rebound_names(tree, set(aliases)):
            aliases.pop(name, None)
        mods: dict[str, types.ModuleType] = {}
        for alias, dotted in aliases.items():
            mod = _resolve_module(dotted)
            if mod is None:
                skips.append(f"{path.name}: {dotted} (not an importable module)")
            else:
                mods[alias] = mod
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in mods
                    and not hasattr(mods[node.value.id], node.attr)):
                try:
                    label = str(path.relative_to(ROOT)).replace("\\", "/")
                except ValueError:  # tmp_path canaries live outside the repo
                    label = str(path)
                violations.append((
                    label,
                    node.lineno, node.value.id,
                    aliases[node.value.id], node.attr,
                ))
    return violations, skips


SCAN_DIRS = [
    ROOT / "scripts" / "xfp",
    ROOT / "scripts" / "xfp" / "lib",
    ROOT / "scripts" / "ci",
    ROOT / "src" / "plv_clone",
    ROOT / "app",
]


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        pattern = "**/*.py" if d.name in ("plv_clone",) else "*.py"
        files.extend(sorted(p for p in d.glob(pattern) if p.is_file()))
    return files


def test_scan_finds_files():
    """Sanity: the scan is actually looking at the code (guards a silent no-op)."""
    files = _scan_files()
    assert len(files) > 100, f"scan collected only {len(files)} files — glob is wrong"
    names = {f.name for f in files}
    assert "verdict_backtest.py" in names
    assert "rh3.py" in names


def test_no_stale_module_attribute_references():
    """No first-party `module.attr` reference may point at a deleted attribute.

    This is the general form of the 2026-07-29 verdict_backtest rot
    (`RH3._signal` / `RP3._signal` deleted by de9f6e6, referenced for weeks).
    """
    violations, _ = stale_attr_references(_scan_files())
    if violations:
        lines = "\n".join(
            f"  {f}:{ln}  {alias}.{attr}  ({alias} = {mod}) -> attribute missing"
            for f, ln, alias, mod, attr in violations)
        pytest.fail(
            f"{len(violations)} stale module-attribute reference(s) — the referenced "
            f"attribute no longer exists, so this code raises AttributeError when "
            f"executed:\n{lines}")


def test_guard_detects_a_planted_violation(tmp_path):
    """The guard must actually catch the exact defect it was written for.

    A green policy test that cannot fail is worse than no test. Plant the
    original `RH3._signal` call and assert it is reported.
    """
    canary = tmp_path / "canary_script.py"
    canary.write_text(
        "from plv_clone.models.xfp import rh3 as RH3\n"
        "def f(sub):\n"
        "    return sub.apply(RH3._signal, axis=1)\n",
        encoding="utf-8")
    violations, _ = stale_attr_references([canary])
    assert violations, "guard failed to detect a deleted-attribute reference"
    assert violations[0][2:] == ("RH3", "plv_clone.models.xfp.rh3", "_signal")


def test_guard_accepts_a_live_attribute(tmp_path):
    """And it must not fire on an attribute that DOES exist (no false positives)."""
    ok = tmp_path / "ok_script.py"
    ok.write_text(
        "from plv_clone.models.xfp import rh3 as RH3\n"
        "def f():\n"
        "    return RH3.ROLLING_CSV, RH3.compute_replacement_delta\n",
        encoding="utf-8")
    violations, _ = stale_attr_references([ok])
    assert violations == []


def test_guard_ignores_rebound_alias(tmp_path):
    """A rebound alias is dropped — that is how we stay free of false positives."""
    reb = tmp_path / "rebound_script.py"
    reb.write_text(
        "from plv_clone.models.xfp import rh3 as RH3\n"
        "RH3 = object()\n"
        "def f():\n"
        "    return RH3.totally_not_a_real_attribute\n",
        encoding="utf-8")
    violations, _ = stale_attr_references([reb])
    assert violations == []
