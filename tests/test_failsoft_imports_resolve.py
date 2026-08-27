"""A fail-soft `except` around an IMPORT hides a permanently dead feature.

WHY THIS EXISTS
`refresh_dashboards` step 7 is described in its own comment as "the SINGLE
loud checkpoint" for PL cache staleness. It imported
`scripts.xfp.lib.pl_cache`, which does not resolve when that driver runs:
sys.path[0] is scripts/xfp, and unlike most drivers refresh_dashboards never
puts the repo root on sys.path. The fail-soft handler swallowed the
ModuleNotFoundError and printed a one-line non-gating warning EVERY run, so
the checkpoint had never once executed and the SP cache sat 8 days stale
behind it before a human noticed (2026-08-18).

That is the failure mode of the pattern: a broken import inside a fail-soft
try is indistinguishable from a feature that legitimately had nothing to do.
It never fails CI, never crashes, and the feature is simply gone.

SCOPE — deliberately narrow, and why
Three broader drafts of this guard were each wrong, which is worth recording:

  1. Matching only `lib.*` meant the broken `scripts.xfp.lib.*` form dropped
     out of DISCOVERY rather than failing.
  2. Widening the matcher still passed, because pytest puts the repo ROOT on
     sys.path — so `scripts.xfp.*` resolves under test even where it cannot
     resolve for the driver. The test environment was more forgiving than
     production.
  3. Deciding per-file whether the repo root is on sys.path needs an AST
     heuristic, and mine missed real spellings: build_sp_alerts inserts
     `REPO`, run_trending inserts `'.'`. Files flagged as broken start fine.

So this file checks only what it can PROVE:

  * every fail-soft `lib.*` import must resolve from a driver's own directory
    (that path is guaranteed — scripts/xfp is sys.path[0] for any
    `python scripts/xfp/x.py`), and
  * refresh_dashboards specifically must not use the `scripts.xfp.*` spelling,
    because it is the one driver that never puts the repo root on sys.path.
    That is exactly where the 2026-08-18 bug lived and where it would recur.

Other drivers legitimately use `scripts.xfp.*` — they add the root themselves
first. Auditing that per file is issue material, not a provable assert here.
(Added 2026-08-27.)
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DRIVERS = ROOT / "scripts" / "xfp"

_SOFT = ("Exception", "BaseException", "ImportError", "ModuleNotFoundError")


def _failsoft_imports(prefix: tuple[str, ...]) -> list[tuple[str, int, str, str]]:
    sites: list[tuple[str, int, str, str]] = []
    for path in sorted(DRIVERS.glob("*.py")):
        if path.name.startswith("_"):
            continue  # ad-hoc / one-off scratch drivers
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            if not any(h.type is None
                       or (isinstance(h.type, ast.Name) and h.type.id in _SOFT)
                       for h in node.handlers):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.ImportFrom) and stmt.module \
                        and stmt.module.startswith(prefix):
                    for alias in stmt.names:
                        sites.append((path.name, stmt.lineno, stmt.module, alias.name))
    return sites


SITES = _failsoft_imports(("lib.",))

_PROBE = r"""
import importlib, json, sys
out = {}
for mod, sym in json.load(sys.stdin):
    key = mod + "." + sym
    try:
        m = importlib.import_module(mod)
    except BaseException as exc:
        out[key] = "%s: %s" % (type(exc).__name__, str(exc)[:120])
        continue
    out[key] = "ok" if hasattr(m, sym) else "symbol %r missing from %s" % (sym, mod)
json.dump(out, sys.stdout)
"""


def _probe_as_a_driver_would() -> dict[str, str]:
    """Resolve each site in a subprocess whose sys.path[0] is scripts/xfp."""
    if not SITES:
        return {}
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        input=json.dumps([[m, s] for _f, _l, m, s in SITES]),
        capture_output=True, text=True, cwd=str(DRIVERS),
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin",
             "HOME": str(Path.home()), "PYTHONIOENCODING": "utf-8"},
        timeout=300,
    )
    if proc.returncode != 0:
        pytest.fail(f"probe subprocess failed: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


RESULTS = _probe_as_a_driver_would()


def test_discovery_finds_the_known_sites():
    """If this collapses, the AST walk broke and the guard is vacuous."""
    assert len(SITES) >= 20, (
        f"only {len(SITES)} fail-soft `lib.*` imports discovered — expected "
        f"30-ish. The AST walk has probably stopped matching."
    )


@pytest.mark.parametrize(
    "file,lineno,module,symbol", SITES,
    ids=[f"{f}:{l}:{m}.{s}" for f, l, m, s in SITES],
)
def test_failsoft_lib_import_resolves_for_a_driver(file, lineno, module, symbol):
    verdict = RESULTS.get(f"{module}.{symbol}", "not probed")
    assert verdict == "ok", (
        f"{file}:{lineno} does `from {module} import {symbol}` inside a "
        f"fail-soft try, and it does NOT resolve on a driver's sys.path: "
        f"{verdict}\nThe handler swallows this, so the feature is silently "
        f"dead and nothing reports it (cf. the 2026-08-18 PL-staleness "
        f"checkpoint, which never ran for weeks)."
    )


def test_refresh_dashboards_never_uses_the_fully_qualified_spelling():
    """The one driver that never puts the repo root on sys.path.

    Every other driver that writes `scripts.xfp.lib.x` inserts the repo root
    first (under various names — ROOT, REPO, even '.'), so the spelling works
    there. refresh_dashboards inserts only SCRIPTS, so the same spelling is a
    guaranteed ModuleNotFoundError — swallowed, silent, and exactly the
    2026-08-18 regression.
    """
    src = (DRIVERS / "refresh_dashboards.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    offenders = [
        f"line {n.lineno}: from {n.module} import "
        f"{', '.join(a.name for a in n.names)}"
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module
        and n.module.startswith("scripts.")
    ]
    offenders += [
        f"line {n.lineno}: import {a.name}"
        for n in ast.walk(tree) if isinstance(n, ast.Import)
        for a in n.names if a.name.startswith("scripts.")
    ]
    assert not offenders, (
        "refresh_dashboards.py uses the `scripts.*` import spelling:\n  "
        + "\n  ".join(offenders)
        + "\n\nIt never adds the repo root to sys.path, so this raises "
          "ModuleNotFoundError at runtime. Inside a fail-soft try that is "
          "silent and the feature is dead. Use `lib.<module>` instead."
    )
