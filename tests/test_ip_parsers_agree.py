"""Every innings-pitched parser in the repo must agree on the notation.

WHY THIS EXISTS
MLB reports `inningsPitched` as partial-inning NOTATION, not a decimal:
"5.1" is 5 + 1/3 and "5.2" is 5 + 2/3. Reading it as a decimal under-counts
by up to 0.47 IP, which at 3.3 FP/IP is 1.54 FP on a start that averages ~12.

This repo has SIXTEEN independent IP parsers — one canonical `_parse_ip` in
plv_clone.fantasy.scoring plus fifteen hand-rolled copies across the drivers.
That is the same shape as the holds-multiplier incident (issue #69): one rule,
many private copies, and nothing forcing them to agree.

Two real disagreements were found on 2026-08-27:

  * `plv_clone.fantasy.scoring._parse_ip` short-circuited a NUMERIC input as
    `float(raw)`, so '5.2' gave 5.6667 while 5.2 gave 5.2. All twelve testable
    siblings coerce with str() first and read a numeric as notation — the
    canonical function was the odd one out.
  * `validate_sp_bootstrap_opp_factor._fp_from_stat` called bare
    `float(stat["inningsPitched"])`, mispricing every start it scored.

This test pins the shared contract. It discovers the parsers rather than
listing them, so a sixteenth copy is covered the day it is written.
"""
from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

#: (module, attribute) for every scalar IP parser. Modules that expose the
#: parser only as a nested function, or that take a pandas Series rather than a
#: scalar, are out of scope for a scalar contract test and are listed in
#: _KNOWN_NON_SCALAR so the census below stays honest about coverage.
#: CONSOLIDATED 2026-08-27 (issue #78): every parser below now delegates to
#: plv_clone.fantasy.scoring.parse_ip, so the four "nested, untestable" excuses
#: are gone — the delegation is the guarantee, and the sites are listed here to
#: keep that visible rather than assumed.
_DELEGATED_NESTED = {
    "plv_clone.models.xfp.rprs2.parse_ip",
    "build_relievers_multiyr.parse_ip",
    "monitor_drift.parse_ip",
    "build_milb_pitcher_counting.ip_to_float",
}
#: The ONE parser that is legitimately its own implementation: FanGraphs/BBRef
#: IP, Series-wise, where a non-.1/.2 fraction is a real aggregated decimal and
#: is TRUNCATED rather than raising. See its docstring.
_INTENTIONALLY_SEPARATE = {
    "build_rp_leverage_proxy._ip_to_float",
}
_KNOWN_NON_SCALAR = _DELEGATED_NESTED | _INTENTIONALLY_SEPARATE

_SCALAR_PARSERS = [
    ("plv_clone.fantasy.scoring", "_parse_ip"),
    ("refresh_boxscores", "_ip_to_float"),
    ("weekly_cap_check", "_ip_float"),
    ("build_sp_gamelog_panel", "ip_to_float"),
    ("augment_milb_stats", "ip_to_float"),
    ("build_sp_event_panel", "ip_to_float"),
    ("build_rp_event_panel", "ip_to_float"),
    ("pl_feature_correlation", "parse_ip"),
    ("lib.pitcher_role", "_ip_to_float"),
    ("lib.boom_bust", "_ip_to_float"),
    ("live_monitor", "_ip_to_float"),
]

#: The notation contract. Values are exact innings.
_CASES = {
    "0.0": 0.0,
    "5.0": 5.0,
    "5.1": 5 + 1 / 3,
    "5.2": 5 + 2 / 3,
    "0.1": 1 / 3,
    "0.2": 2 / 3,
    "7": 7.0,
}


def _load(mod_name: str, attr: str):
    try:
        return getattr(importlib.import_module(mod_name), attr)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"{mod_name}.{attr} not importable here: "
                    f"{type(exc).__name__}: {exc}")


@pytest.mark.parametrize("mod_name,attr", _SCALAR_PARSERS,
                         ids=[f"{m}.{a}" for m, a in _SCALAR_PARSERS])
@pytest.mark.parametrize("raw,expected", sorted(_CASES.items()))
def test_string_notation(mod_name, attr, raw, expected):
    fn = _load(mod_name, attr)
    assert fn(raw) == pytest.approx(expected, abs=1e-6), (
        f"{mod_name}.{attr}({raw!r}) misreads MLB partial-inning notation"
    )


@pytest.mark.parametrize("mod_name,attr", _SCALAR_PARSERS,
                         ids=[f"{m}.{a}" for m, a in _SCALAR_PARSERS])
def test_a_numeric_is_notation_too(mod_name, attr):
    """5.2 the float means the same thing as '5.2' the string.

    A pandas/parquet round-trip turns the string into a float, and reading
    that as a decimal is the whole bug.
    """
    fn = _load(mod_name, attr)
    assert fn(5.2) == pytest.approx(5 + 2 / 3, abs=1e-6), (
        f"{mod_name}.{attr}(5.2) read a numeric as a DECIMAL — '5.2' and 5.2 "
        f"must agree"
    )


def test_the_census_is_complete():
    """Every `def *ip*` parser is either covered above or explicitly excused.

    Listing beats discovery here only because the parsers are named a dozen
    different ways; the assert keeps the list honest by failing when a new one
    appears.
    """
    import re

    pat = re.compile(r"^\s*def\s+(_?(?:parse_ip|ip_to_float|_ip_float|ip_float))\b")
    found = set()
    for path in list((ROOT / "scripts" / "xfp").rglob("*.py")) + \
            list((ROOT / "src").rglob("*.py")):
        # Work on the ROOT-relative POSIX path: the absolute str() breaks two
        # ways outside the container this was written in (2026-08-28) — the
        # repo DIRECTORY is itself named plv_clone, so parts.index() anchored
        # the module name at the repo root instead of src/plv_clone; and on
        # Windows the "/research/" substring never matches a backslashed path.
        rel = path.relative_to(ROOT)
        rel_posix = rel.as_posix()
        if any(p in rel_posix for p in ("_oneoff", "_attic", "_research",
                                        "/research/", "archive")):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            m = pat.match(line)
            if m:
                stem = path.stem
                if rel.parts[-2] == "lib":
                    stem = f"lib.{stem}"
                elif "plv_clone" in rel.parts:
                    idx = rel.parts.index("plv_clone")
                    stem = ".".join(rel.parts[idx:]).removesuffix(".py")
                found.add(f"{stem}.{m.group(1)}")

    covered = {f"{m}.{a}" for m, a in _SCALAR_PARSERS} | _KNOWN_NON_SCALAR
    uncovered = sorted(found - covered)
    assert not uncovered, (
        f"new IP parser(s) not covered by the notation contract: {uncovered}\n"
        f"Add to _SCALAR_PARSERS, or to _KNOWN_NON_SCALAR with a reason. "
        f"Sixteen private copies of one rule is how they drift apart."
    )


# ── consolidation (issue #78) ────────────────────────────────────────────────

def test_no_module_still_hand_rolls_the_notation_arithmetic():
    """One implementation, not sixteen.

    The `/3` partial-inning arithmetic should now appear in exactly ONE place:
    plv_clone.fantasy.scoring.parse_ip. A new copy is how PR #77's two bugs
    happened, so a fresh one fails here rather than waiting to drift.
    """
    import re as _re

    pat = _re.compile(r"(int\(\s*fra?c?\s*\)|int\(\s*f\s*\)|int\(\s*outs[^)]*\))\s*/\s*3"
                      r"|1\s*/\s*3\s+if\s+frac")
    offenders = []
    for path in list((ROOT / "scripts" / "xfp").rglob("*.py")) + \
            list((ROOT / "src").rglob("*.py")):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if any(sd in rel for sd in ("_oneoff", "_attic", "_research",
                                    "research/", "archive")):
            continue
        if rel == "src/plv_clone/fantasy/scoring.py":
            continue                      # the one canonical home
        if rel == "scripts/xfp/build_rp_leverage_proxy.py":
            continue                      # documented FG/BBRef variant
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if pat.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()[:70]}")
    assert not offenders, (
        "hand-rolled partial-inning arithmetic outside the canonical parser:\n  "
        + "\n  ".join(offenders)
        + "\n\nImport `from plv_clone.fantasy.scoring import parse_ip` instead. "
          "Pass default=0.0 (or np.nan) to keep a fail-soft contract.")


def test_the_canonical_parser_supports_both_failure_contracts():
    """Consolidation must not convert a silent zero into an exception.

    The copies did not agree on failure: most swallowed anything unparseable
    and returned 0.0, one returned NaN for pandas. Each delegating site passes
    the default it already had, so `default` has to work.
    """
    from plv_clone.fantasy.scoring import parse_ip as _p

    with pytest.raises(ValueError):
        _p("5.5")
    assert _p("5.5", default=0.0) == 0.0
    assert _p("junk", default=-1.0) == -1.0
    assert _p("5.2", default=0.0) == pytest.approx(5 + 2 / 3)
