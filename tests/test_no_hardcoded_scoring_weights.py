"""Guard: league scoring weights live in ONE place, never inlined as literals.

Why this exists. On 2026-08-12 the BrownU holds weight was found wrong (2 vs
the live ESPN league's 3, statId 60). The fix took ~6 edits because the weight
was hardcoded across the repo, and one live site was still MISSED by the
cleanup sweep — bullpen_quality.py multiplied holds by 2 through a
`.fillna(0)` call, so every `hld * 2` regex slid right past it.

A league setting is data, not a literal. Route through
plv_clone.fantasy.scoring (LeagueScoring / pitcher_fp / DEFAULT), whose values
come from data/models/league_scoring.json.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Files allowed to carry a literal, WITH a reason.
ALLOWLIST = {
    # the owner itself + its data file loader
    "src/plv_clone/fantasy/scoring.py": "defines the canonical weights",
    # rprs2 declares the hold weight as a named module constant it also
    # publishes in its output metadata; it is a single declared value, not an
    # inlined literal in a formula.
    "src/plv_clone/models/xfp/rprs2.py": "named _HLD_WEIGHT constant, published in output meta",
    # dead/one-off trees kept out of the index; not imported by live paths
    "scripts/_oneoff/boom_bust_sampler.py": "one-off scratch, not a live path",
    "scripts/xfp/_attic/xfp_rprs1_pipeline.py": "attic, superseded by rprs2",
    # `saves*3 + holds` is a LEVERAGE heuristic (which reliever gets the ninth),
    # not BrownU fantasy scoring — it must NOT track the league's FP weights.
    "scripts/xfp/save_handcuffs.py": "leverage heuristic, not league FP scoring",
    # `g + 2*(sv+hld)` is a RELIEVER-SELECTION score (which arms enter the
    # sample), not FP; it must not track league weights either.
    "scripts/xfp/build_subseason_variance_bands.py": "line 164 is a sample-selection score, not FP",
    # dated research one-offs under scripts/research/: frozen analyses, not
    # live paths, and rerunning them under new weights would misdate them.
    "scripts/research/rp_decline_stuff_velo_2026-06-13.py": "dated frozen research artifact",
    "scripts/_oneoff/build_multiyr_fp_store.py": "one-off scratch, not a live path",
    "scripts/_oneoff/stuff_translation_gap_rp_study.py": "one-off scratch, not a live path",
    # dashboard tooltip TEXT that describes the formula to a reader; it is a
    # dict-value string (not an Expr docstring, so AST can't classify it) and
    # computes nothing. Keep its wording in sync by hand when weights change.
    "scripts/xfp/_player_profiles_template.py": "UI tooltip prose, computes nothing",
}

def _docstring_lines(src: str) -> set[int]:
    """Line numbers occupied by docstrings / bare string expressions.

    Prose that merely RESTATES the formula is not a drift risk the way an
    executable literal is. Detected via AST rather than by eyeballing quote
    characters, because these formulas live on CONTINUATION lines inside
    triple-quoted module docstrings — invisible to any startswith() check.
    Dict-key strings (`_f(g, 'holds')`) stay in scope: they are code.
    """
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            out.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return out

# A save/hold stat token, then anything that is NOT a line-comment start,
# then a bare numeric multiplier. Catches `hld * 2`, `hld_to.fillna(0) * 2`,
# `holds"] * 2` — the shapes a plain `hld\s*\*\s*2` sweep misses.
_PAT = re.compile(
    # token-then-multiplier:  hld * 2 | hld_to.fillna(0) * 2 | holds"] * 2
    r"(?:hld|holds|\bsv\b|saves)[^\n#]{0,40}?\*\s*(\d+(?:\.\d+)?)"
    # multiplier-then-token:  2 * hld | 2 * _f(g, 'holds')   <- the shape the
    # first version of this guard missed, hiding 4 live sites.
    r"|(\d+(?:\.\d+)?)\s*\*[^\n#]{0,40}?(?:hld|holds|\bsv\b|saves)",
    re.IGNORECASE)

_SEARCH_DIRS = ("scripts", "src", "app")


def _offenders() -> list[str]:
    hits = []
    for d in _SEARCH_DIRS:
        for py in (_ROOT / d).rglob("*.py"):
            rel = py.relative_to(_ROOT).as_posix()
            if rel in ALLOWLIST or "/archive/" in rel or "/_research/" in rel:
                continue
            try:
                src = py.read_text(encoding="utf-8")
            except Exception:
                continue
            doc_lines = _docstring_lines(src)
            for i, line in enumerate(src.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or i in doc_lines:
                    continue
                m = _PAT.search(line)
                if not m:
                    continue
                weight = m.group(1) or m.group(2)
                if weight in {"2", "3", "5", "2.0", "3.0", "5.0"}:
                    hits.append(f"{rel}:{i}: {stripped[:90]}")
    return hits


def test_no_live_code_hardcodes_save_or_hold_weights():
    found = _offenders()
    assert not found, (
        "League scoring weights are hardcoded in live code — these drift "
        "silently when the league setting changes (the 2026-08-12 holds 2->3 "
        "incident):\n  " + "\n  ".join(found) +
        "\n\nRoute through plv_clone.fantasy.scoring (pitcher_fp / DEFAULT.sv / "
        "DEFAULT.hd), or add the file to ALLOWLIST here WITH a reason."
    )
