"""`league_config.SEASON_YEAR` must actually be the rollover switch it claims.

WHY THIS EXISTS
SEASON_YEAR is declared "bump at rollover". It had exactly ONE importer
(run_decision_trend) while 125 sites hardcoded 2026 independently, and
`lib/expected_stats.CURRENT_SEASON` declared itself canonical too. Bumping
SEASON_YEAR on 2027-01-01 would have changed essentially nothing, and the
decision-path lenses — boom/bust, pitcher role, trend, rating arc — would
have gone on reading the 2026 season all year while reporting success.

The repo had already diagnosed this exact class once: `refresh_dashboards.
season_year()` exists because three driver commands hardcoded 2026, "redundant
today and wrong on 2027-01-01". That fix covered three commands; the library
layer kept the literals.

So the invariant here is narrow and absolute rather than a soft ratchet: no
function in `scripts/xfp/lib` may DEFAULT a season parameter to a year
literal. A default is the dangerous form — the caller who omits the argument
silently gets a pinned season, and on an lru_cached function that pinning is
also cached. Bare year literals elsewhere in a body (era boundaries, validated
panel years, cutoff dates) are legitimate history and are not policed here.

(Added 2026-08-27.)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "scripts" / "xfp" / "lib"

#: Parameter names that mean "which season" — a year literal defaulted into one
#: of these is the bug. Extend if a new spelling appears.
_SEASON_PARAMS = {"season", "year", "cur", "base", "yr", "season_year"}


def _season_defaults() -> list[str]:
    offenders = []
    for path in sorted(LIB.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args
            pairs = list(zip(args.args[-len(args.defaults):], args.defaults)) \
                if args.defaults else []
            pairs += list(zip(args.kwonlyargs, args.kw_defaults))
            for arg, default in pairs:
                if arg.arg not in _SEASON_PARAMS or default is None:
                    continue
                if (isinstance(default, ast.Constant)
                        and isinstance(default.value, int)
                        and not isinstance(default.value, bool)
                        and 2000 < default.value < 2100):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} "
                        f"{node.name}({arg.arg}={default.value})"
                    )
    return offenders


def test_no_lib_function_defaults_a_hardcoded_season() -> None:
    offenders = _season_defaults()
    assert not offenders, (
        "season parameter(s) defaulted to a year literal in scripts/xfp/lib — "
        "use `from plv_clone.league_config import SEASON_YEAR` so a rollover is "
        "one bump, not a search:\n  " + "\n  ".join(offenders)
    )


def test_expected_stats_current_season_is_an_alias_not_a_rival() -> None:
    """Two independent 'current season' constants is one too many."""
    from plv_clone.league_config import SEASON_YEAR
    import importlib
    mod = importlib.import_module("scripts.xfp.lib.expected_stats")
    assert mod.CURRENT_SEASON == SEASON_YEAR, (
        f"expected_stats.CURRENT_SEASON={mod.CURRENT_SEASON} has drifted from "
        f"league_config.SEASON_YEAR={SEASON_YEAR}"
    )


def _season_defaults_live() -> dict[str, int]:
    """{qualified name: current default} for every season param in the lenses."""
    import importlib
    import inspect

    out = {}
    for name in ("trend_signal", "boom_bust", "pitcher_role", "rating_arc"):
        mod = importlib.reload(importlib.import_module(f"scripts.xfp.lib.{name}"))
        for fn_name, fn in vars(mod).items():
            if not callable(fn) or fn_name.startswith("__"):
                continue
            try:
                sig = inspect.signature(fn)
            except (ValueError, TypeError):
                continue
            for pname, param in sig.parameters.items():
                if pname not in _SEASON_PARAMS:
                    continue
                d = param.default
                if isinstance(d, int) and not isinstance(d, bool) and 2000 < d < 2100:
                    out[f"{name}.{fn_name}({pname})"] = d
    return out


def test_bumping_season_year_moves_the_decision_path() -> None:
    """The contract SEASON_YEAR advertises: one bump moves the lenses.

    Every season default must shift by exactly the bump — including `base`,
    which trails the current season by one and so moves 2025 -> 2026 rather
    than to the new SEASON_YEAR. Comparing each default against its OWN
    pre-bump value is what makes that distinction correctly; asserting
    "> original" instead would call a correctly-trailing `base` stuck.

    This is what was NOT true before 2026-08-27: the defaults were literals
    and a bump moved none of them.
    """
    import importlib

    import plv_clone.league_config as lc

    original = lc.SEASON_YEAR
    before = _season_defaults_live()
    assert before, "no season defaults found at all — did the modules import?"

    try:
        lc.SEASON_YEAR = original + 1
        after = _season_defaults_live()
    finally:
        lc.SEASON_YEAR = original
        for name in ("trend_signal", "boom_bust", "pitcher_role", "rating_arc"):
            importlib.reload(importlib.import_module(f"scripts.xfp.lib.{name}"))

    assert set(before) == set(after)
    stuck = [f"{k}: {before[k]} -> {after[k]}" for k in before
             if after[k] != before[k] + 1]
    assert not stuck, (
        "these season defaults did NOT follow the SEASON_YEAR bump:\n  "
        + "\n  ".join(stuck)
    )
