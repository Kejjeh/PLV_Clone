"""CLAUDE.md gotcha #6: `fetch_schedules_by_team(team_ids, start, end)` is a
cross-module contract, and nothing held it.

The note says "`sp_bench_mc.py` imports it from `build_matchup_dashboard`; keep
in sync if that module refactors." A refactor of the owner's signature would
break the consumers at RUNTIME, in the weekly refresh, with no test catching it
first — and the note undercounts: FIVE modules depend on this function, not one.
That undercount is why this guard DISCOVERS the consumers instead of naming
them. A guard that enumerated `sp_bench_mc` alone would have reproduced the
same blind spot the note has (issue #65, issue #69's partial-fix shape).

Cheap and structural, per the #64 pattern: the owner exists, its parameters are
the three the contract names, and every consumer calls it with three arguments.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
XFP = ROOT / "scripts" / "xfp"

OWNER_MODULE = "build_matchup_dashboard"
FUNC = "fetch_schedules_by_team"
#: The contract CLAUDE.md states, in order.
EXPECTED_PARAMS = ("team_ids", "start_date", "end_date")


def _owner_signature() -> list[str]:
    """The owner's parameter names, read from source (no heavy import)."""
    tree = ast.parse((XFP / f"{OWNER_MODULE}.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == FUNC:
            return [a.arg for a in node.args.args]
    raise AssertionError(f"{OWNER_MODULE}.{FUNC} not found — the owner moved")


def _consumers() -> dict[str, ast.Module]:
    """Every module under scripts/xfp that imports FUNC, found by walking."""
    out = {}
    for path in sorted(XFP.rglob("*.py")):
        if path.stem == OWNER_MODULE:
            continue
        src = path.read_text(encoding="utf-8")
        if FUNC not in src:
            continue
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                a.name == FUNC for a in node.names
            ):
                out[str(path.relative_to(ROOT))] = tree
                break
    return out


CONSUMERS = _consumers()


def test_the_owner_still_defines_the_contract():
    assert tuple(_owner_signature()) == EXPECTED_PARAMS, (
        f"{OWNER_MODULE}.{FUNC} signature changed to {_owner_signature()}. "
        f"{len(CONSUMERS)} module(s) call it positionally — update them in the "
        f"same commit: {sorted(CONSUMERS)}"
    )


def test_the_contract_has_more_than_one_consumer():
    """A sanity check on the discovery itself: if this drops to zero the walk
    broke, and every assertion below would pass vacuously."""
    assert len(CONSUMERS) >= 2, f"discovery found only {sorted(CONSUMERS)}"
    assert CALLERS, "no consumer calls it directly — the call-site check is vacuous"


def _direct_calls(tree) -> list[ast.Call]:
    return [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == FUNC
    ]


#: Consumers that call it directly. A module that only re-exports it (currently
#: run_matchup_leverage) has no call site to check and is covered by the
#: signature test above — parametrizing over it would only add a skip, and a
#: skipped test is one that can silently not run.
CALLERS = {rel: t for rel, t in CONSUMERS.items() if _direct_calls(t)}


@pytest.mark.parametrize("rel", sorted(CALLERS))
def test_every_consumer_calls_it_with_three_arguments(rel):
    for call in _direct_calls(CALLERS[rel]):
        n_args = len(call.args) + len(call.keywords)
        assert n_args == len(EXPECTED_PARAMS), (
            f"{rel}:{call.lineno} calls {FUNC} with {n_args} argument(s); the "
            f"contract is {EXPECTED_PARAMS}"
        )
        for kw in call.keywords:
            assert kw.arg in EXPECTED_PARAMS, (
                f"{rel}:{call.lineno} passes {kw.arg}=, not in {EXPECTED_PARAMS}"
            )


def test_the_live_import_resolves_to_the_owner():
    """Source agreement isn't enough — the import has to actually work. This is
    the failure the note is really about: a refactor that moves the function
    leaves every consumer's `from build_matchup_dashboard import ...` raising
    ImportError on the next refresh run."""
    bmd = pytest.importorskip("scripts.xfp.build_matchup_dashboard")
    fn = getattr(bmd, FUNC, None)
    assert callable(fn), f"{FUNC} is no longer importable from {OWNER_MODULE}"
    assert tuple(inspect.signature(fn).parameters) == EXPECTED_PARAMS
