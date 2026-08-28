"""CLAUDE.md don't-do #3: the flag COUNTS never rank or filter free agents.

`n_pos_flags` / `n_neg_flags` — how many "+" or "-" rolling-trend flags a player
carries — were validated as noise on 2026-05-11 (`validate_rolling_trend.py`,
`feedback_rolling_trend_short_horizon_only.md`). `improving_fa_finder` was
rewritten around that finding: it ranks by xfp_rh3 RoS alone and keeps the flag
counts as informational columns.

Nothing held that. The columns are still computed and still sit in the row dict
one line above the sort, which is exactly how a "quick tiebreak" gets added back
— and the result would be a silently worse FA board, not an error. This is the
issue #65 shape: a hard-won finding documented in CLAUDE.md with no test that
fails if it's reverted.

Rule 13 in miniature: computing and DISPLAYING a noise signal is fine, letting
it move an ordering is not. So the guard polices the ordering and the filter,
not the presence of the column.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
XFP = ROOT / "scripts" / "xfp"

#: The validated-as-noise composites. Extend if a new spelling appears.
NOISE_COLUMNS = ("n_pos_flags", "n_neg_flags")

#: Calls whose arguments DECIDE an ordering or a cut.
_ORDERING_CALLS = {
    "sort", "sorted", "sort_values", "nlargest", "nsmallest", "rank",
    "argsort", "idxmax", "idxmin", "query",
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _files_mentioning_noise() -> dict[str, str]:
    return {
        str(p.relative_to(ROOT)): p.read_text(encoding="utf-8")
        for p in sorted(XFP.rglob("*.py"))
        if any(c in p.read_text(encoding="utf-8") for c in NOISE_COLUMNS)
        and "archive" not in p.parts and "research" not in p.parts
    }


FILES = _files_mentioning_noise()


def test_the_noise_columns_still_exist_somewhere():
    """If nothing mentions them the guard below is vacuous and should be
    deleted rather than left passing on an empty set."""
    assert FILES, (
        "no module references the rolling-trend flag counts any more — either "
        "they were removed (delete this guard) or the walk broke"
    )


@pytest.mark.parametrize("rel", sorted(FILES))
def test_noise_flags_never_appear_in_an_ordering_or_a_filter(rel):
    tree = ast.parse(FILES[rel], filename=rel)
    src = FILES[rel]
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) not in _ORDERING_CALLS:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            seg = ast.get_source_segment(src, arg) or ""
            for col in NOISE_COLUMNS:
                if col in seg:
                    offenders.append(
                        f"{rel}:{node.lineno} {_call_name(node)}(... {col} ...)"
                    )
    assert not offenders, (
        "a rolling-trend flag COUNT is deciding an ordering or a cut. Validated "
        "as noise 2026-05-11 (don't-do #3) — rank by the validated RoS "
        "projection and keep the counts informational:\n  " + "\n  ".join(offenders)
    )


def test_the_fa_finder_still_ranks_by_the_validated_projection():
    """The positive half: prose is what the next reader acts on (#64's lesson),
    and this module's docstring is the standing record of WHY the flags are
    informational. A rewrite that drops the claim is the warning sign."""
    src = (XFP / "improving_fa_finder.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc = ast.get_docstring(tree) or ""
    assert "xfp_rh3" in doc and "PRIMARY" in doc.upper(), (
        "improving_fa_finder's docstring no longer names xfp_rh3 RoS as the "
        "primary ranker — the 2026-05-11 validation is the reason it is"
    )
    # And the sort itself is on the projection, not on a flag count.
    sorts = [
        ast.get_source_segment(src, n) or ""
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and _call_name(n) in _ORDERING_CALLS
    ]
    assert any("ros_fp" in s for s in sorts), (
        "the FA ordering is no longer keyed on the RoS projection"
    )
