"""Every inline copy of the SP FP formula must have the canonical shape.

WHY THIS EXISTS
BrownU SP FP is `K + IP*3.3 - H - 2*ER - BB - HBP`. That formula is written
out inline in TWENTY places across the drivers, in addition to the canonical
`plv_clone.fantasy.scoring.pitcher_fp`. One rule, twenty private copies, and
nothing forcing them to agree — the same shape as the sixteen IP parsers
(PR #77), the holds multiplier, and `SEASON_YEAR` (PR #58).

Unlike the IP sweep, this one found NO arithmetic bug: all twenty copies carry
the right terms, signs, and the 2x on earned runs. So this guard is
preventive rather than a fix, and worth having precisely because the IP sweep
DID find two bugs in twelve copies — the shape is identical, so the exposure
is real even though today's census is clean.

It checks structure, not values: a sign flip, a dropped term, or a lost `2 *`
on earned runs would each silently reprice every pitcher a script touches.
(Added 2026-08-27.)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = ("_oneoff", "_attic", "_research", "/research/", "archive")

#: stat key -> (required sign, required multiplier or None for 1)
_CANON = {
    "K":   (+1, None),
    "IP":  (+1, 3.3),
    "H":   (-1, None),
    "ER":  (-1, 2),
    "BB":  (-1, None),
    "HBP": (-1, None),
}

#: Sites that deliberately substitute runs (R) for earned runs (ER) because
#: their source is Statcast pitch-by-pitch, which exposes runs_on_play and not
#: ER. Each carries a comment saying so. Listed here so the substitution stays
#: a DECISION rather than drifting into an unnoticed default.
_R_FOR_ER_PROXIES = {
    "scripts/xfp/lib/recform_hot.py",
    "scripts/xfp/build_recform_hot_retroactive.py",
    "scripts/xfp/playoff_peak_pitchers.py",
    "scripts/xfp/per_start_predictor_battle.py",
}


#: Whole-token aliases per canonical term. Matched against the identifier-ish
#: tokens of a summand, NOT as substrings — "per_start" contains "er" and
#: "merged" contains "er", which is exactly how a substring classifier
#: mislabels a term and then passes.
_ALIASES = {
    "K":   {"k", "so", "strikeouts", "k_to", "actual_k", "strikeout"},
    "H":   {"h", "hits", "h_to", "actual_h", "h_allowed"},
    "ER":  {"er", "earnedruns", "er_to", "actual_er",
            # the documented Statcast R-for-ER proxy
            "r", "runs", "runs_allowed"},
    "BB":  {"bb", "baseonballs", "bb_to", "actual_bb", "bb_allowed", "walks"},
    "HBP": {"hbp", "hitbypitch", "hitbatsmen", "hbp_to", "actual_hbp",
            "hbp_allowed"},
}


def _tokens(expr: str) -> set[str]:
    """Identifier-ish tokens, lowercased, from string literals and names."""
    return {t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", expr)}


def _classify(expr: str) -> str | None:
    """Which canonical term does this summand represent?"""
    if "3.3" in expr:
        return "IP"
    toks = _tokens(expr)
    # Longest/most specific aliases win, so "hbp_allowed" is not read as "bb".
    best, best_len = None, 0
    for term, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in toks and len(alias) > best_len:
                best, best_len = term, len(alias)
    return best


def _summands(node: ast.BinOp) -> list[tuple[int, ast.expr]]:
    out: list[tuple[int, ast.expr]] = []

    def walk(n, sign):
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub)):
            walk(n.left, sign)
            walk(n.right, sign * (1 if isinstance(n.op, ast.Add) else -1))
        else:
            out.append((sign, n))

    walk(node, 1)
    return out


def _multiplier(node: ast.expr) -> float | None:
    """The literal constant a term is multiplied by, if any."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        for side in (node.left, node.right):
            if isinstance(side, ast.Constant) and isinstance(side.value, (int, float)):
                return float(side.value)
    return None


def _fp_expressions() -> list[tuple[str, int, ast.BinOp]]:
    found = []
    for path in sorted(ROOT.joinpath("scripts", "xfp").rglob("*.py")):
        if any(sd in str(path) for sd in SKIP_DIRS):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        seen_lines = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            try:
                src = ast.unparse(node)
            except Exception:  # noqa: BLE001
                continue
            if "3.3" not in src:
                continue
            terms = _summands(node)
            if len(terms) != 6:      # the full six-term formula only
                continue
            if node.lineno in seen_lines:
                continue
            seen_lines.add(node.lineno)
            found.append((str(path.relative_to(ROOT)).replace("\\", "/"),
                          node.lineno, node))
    return found


EXPRESSIONS = _fp_expressions()


def test_the_census_is_not_empty():
    """If the walk stops matching, every assertion below passes vacuously."""
    assert len(EXPRESSIONS) >= 10, (
        f"only {len(EXPRESSIONS)} six-term SP-FP expressions found — expected "
        f"~14. The AST walk has probably stopped matching."
    )


@pytest.mark.parametrize(
    "relpath,lineno,node", EXPRESSIONS,
    ids=[f"{f}:{l}" for f, l, _ in EXPRESSIONS],
)
def test_inline_sp_fp_matches_the_canonical_shape(relpath, lineno, node):
    got: dict[str, tuple[int, float | None]] = {}
    unknown = []
    for sign, term in _summands(node):
        expr = ast.unparse(term)
        which = _classify(expr)
        if which is None:
            unknown.append(expr)
            continue
        got[which] = (sign, _multiplier(term))

    assert not unknown, (
        f"{relpath}:{lineno} has term(s) this test cannot classify: {unknown}. "
        f"Either the formula changed or the classifier needs extending — do "
        f"not leave it unclassified, that is how a wrong term hides."
    )
    missing = sorted(set(_CANON) - set(got))
    assert not missing, f"{relpath}:{lineno} is missing term(s) {missing}"

    for key, (want_sign, want_mult) in _CANON.items():
        sign, mult = got[key]
        assert sign == want_sign, (
            f"{relpath}:{lineno} term {key} has sign {sign:+d}, expected "
            f"{want_sign:+d} — a sign flip reprices every pitcher this touches"
        )
        if want_mult is not None:
            assert mult == want_mult, (
                f"{relpath}:{lineno} term {key} has multiplier {mult}, "
                f"expected {want_mult}"
            )


def test_r_for_er_substitutions_stay_documented():
    """A proxy is a decision; an undocumented one reads as a mistake."""
    offenders = []
    for relpath in sorted(_R_FOR_ER_PROXIES):
        src = (ROOT / relpath).read_text(encoding="utf-8").lower()
        if "proxy" not in src and "approximate" not in src:
            offenders.append(relpath)
    assert not offenders, (
        f"{offenders} substitute runs for earned runs with no comment saying "
        f"so. Statcast exposes runs_on_play, not ER, which is a legitimate "
        f"reason — but it must be stated, or the next reader either 'fixes' "
        f"it or trusts the number as canonical FP."
    )
