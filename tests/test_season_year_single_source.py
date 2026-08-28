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


# ─────────────────────────────────────────────────────────────────────────────
# Issue #59 — the ratchet follows the work into src/plv_clone.
#
# PR #58 held scripts/xfp/lib at zero season DEFAULTS. The package carried a
# second, different shape of the same bug: a current-season FILTER written as a
# literal comparison — `multiyr[multiyr["year"] == 2026]` in league_state at
# three sites, plus `prior_only['year'] = 2026` in rp3. Those fail worse than a
# stale default: after rollover the filter matches NOTHING, so every FA reads as
# a zero-PA fringe callup and the pool silently empties. Nobody sees a year.
#
# So this covers both shapes across src/plv_clone. Bare year literals elsewhere
# (cache filenames like hitters_multiyr_2015_2026.csv, column names like
# fp_actual_2026 that are downstream schema, era boundaries, dated study
# cutoffs) are legitimate history and stay unpoliced — the check is scoped to
# a `year` KEY being compared or assigned, which is unambiguously
# "which season is this".
SRC = ROOT / "src" / "plv_clone"

#: Subscript/attribute keys that mean "the season column".
_YEAR_KEYS = {"year", "season", "game_year"}


def _is_year_literal(node) -> bool:
    return (isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
            and 2000 < node.value < 2100)


def _names_the_year_column(node) -> bool:
    """True for `df["year"]`, `row.year`, `sub.get("year", -1)`."""
    if isinstance(node, ast.Subscript) and _is_year_literal_key(node.slice):
        return True
    if isinstance(node, ast.Attribute) and node.attr in _YEAR_KEYS:
        return True
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and node.args
            and _is_year_literal_key(node.args[0])):
        return True
    return False


def _is_year_literal_key(node) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value in _YEAR_KEYS)


def _year_column_literals() -> list[str]:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # df[df["year"] == 2026]
            if isinstance(node, ast.Compare) and _names_the_year_column(node.left):
                for op, cmp in zip(node.ops, node.comparators):
                    # `!=` is an EXCLUSION, not a current-season filter — the
                    # only one in the package is `year != 2020`, the COVID
                    # season dropped from every training frame. That is
                    # legitimate history and must never follow a rollover.
                    if isinstance(op, ast.Eq) and _is_year_literal(cmp):
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} "
                            f"year column compared to {cmp.value}")
            # df["year"] = 2026
            if isinstance(node, ast.Assign) and _is_year_literal(node.value):
                for tgt in node.targets:
                    if _names_the_year_column(tgt):
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} "
                            f"year column assigned {node.value.value}")
    return offenders


def test_no_current_season_filter_in_src_uses_a_year_literal() -> None:
    offenders = _year_column_literals()
    assert not offenders, (
        "a 'which season' filter in src/plv_clone is pinned to a year literal. "
        "After rollover it matches nothing and the caller sees an empty result, "
        "not an error. Import `league_config.SEASON_YEAR`:\n  "
        + "\n  ".join(offenders)
    )


def _src_season_defaults() -> list[str]:
    """The scripts/xfp/lib default check, applied to the package."""
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args
            pairs = list(zip(args.args[-len(args.defaults):], args.defaults)) \
                if args.defaults else []
            pairs += list(zip(args.kwonlyargs, args.kw_defaults))
            for arg, default in pairs:
                if arg.arg in _SEASON_PARAMS and _is_year_literal(default):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} "
                        f"{node.name}({arg.arg}={default.value})")
    return offenders


def test_no_src_function_defaults_a_hardcoded_season() -> None:
    offenders = _src_season_defaults()
    assert not offenders, (
        "season parameter(s) defaulted to a year literal in src/plv_clone — "
        "use `from plv_clone.league_config import SEASON_YEAR`:\n  "
        + "\n  ".join(offenders)
    )


def test_espn_year_default_follows_season_year() -> None:
    """ESPN_YEAR stays env-overridable for a historical pull, but its DEFAULT
    must be the one bumpable literal rather than a second one (issue #59)."""
    import importlib
    import os

    import plv_clone.league_config as lc

    original = lc.SEASON_YEAR
    saved = os.environ.pop("ESPN_YEAR", None)
    # espn.py re-runs its best-effort load_dotenv on every reload, and a local
    # `.env` legitimately defines ESPN_YEAR — so popping the var alone is not
    # enough: the reload puts it straight back and the DEFAULT path never runs
    # (caught 2026-08-28 on the first machine with a real .env; the container
    # this test was written in had none). Neutralize dotenv for the reload.
    try:
        import dotenv
        orig_load = dotenv.load_dotenv
        dotenv.load_dotenv = lambda *a, **k: False
    except ImportError:
        dotenv, orig_load = None, None
    try:
        lc.SEASON_YEAR = original + 1
        espn = importlib.reload(importlib.import_module("plv_clone.espn"))
        assert espn.YEAR == original + 1, (
            f"espn.YEAR={espn.YEAR} did not follow the SEASON_YEAR bump"
        )
        os.environ["ESPN_YEAR"] = "2019"
        espn = importlib.reload(importlib.import_module("plv_clone.espn"))
        assert espn.YEAR == 2019, "ESPN_YEAR must still override for a historical pull"
    finally:
        if dotenv is not None:
            dotenv.load_dotenv = orig_load
        os.environ.pop("ESPN_YEAR", None)
        if saved is not None:
            os.environ["ESPN_YEAR"] = saved
        lc.SEASON_YEAR = original
        importlib.reload(importlib.import_module("plv_clone.espn"))
