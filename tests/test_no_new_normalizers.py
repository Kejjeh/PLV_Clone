"""Guard: no NEW hand-rolled player-name normalizer may be added.

WHY THIS FILE EXISTS
--------------------
An audit on 2026-07-29 counted 127 files / 134 local definitions of
``_norm`` / ``_nm`` / ``name_norm`` / ``ascii_strip``-style helpers. They had
drifted apart, and the drift shipped two real incidents:

  * **Ryan O'Hearn (2026-07-28).** A local ``_nm()`` did not collapse a curly
    apostrophe (U+2019) against a straight one (U+0027). The Pitcher List cache
    writes curly, the rh3 output writes straight — so he matched *nothing*,
    including the roster scan, and an opponent-rostered player was printed on a
    board as a **FREE AGENT**.
  * **Will / Austin Warren (2026-06-26).** A surname-substring lookup pulled a
    reliever's game log into a starter's profile.

Both failures are SILENT: a normalizer that disagrees with its dict partner
returns "no match", which every caller renders as an empty cell or a zero.
Nothing raises. There is no test a wrong normalizer fails except this one.

THE OWNER
---------
``src/plv_clone/utils/name_match.py``. Two keys, NOT interchangeable:

  ``safe_name_key(name)`` -> ``"kyle schwarber"``
      Order-PRESERVING, space-separated. The drop-in replacement for the classic
      scripts-layer body (NFKD -> ascii -> lower -> strip non-``[a-z ]`` ->
      collapse whitespace). Use this unless you know you need the other one; it
      is also the only choice when the key is later split on spaces (a
      ``(last, first-initial)`` fallback needs the separator).

  ``join_key(name)`` -> ``"kyleschwarber"``
      Sorted alphabetic tokens, NO separator, therefore order-INDEPENDENT
      ("Fried, Max" == "Max Fried"). Only for dicts whose partner also uses it.

Mixing them misses 100% of rows, silently. For every call site, determine which
variant the dict's PARTNER uses and match it.

WHAT TO DO INSTEAD OF ADDING A DEF
----------------------------------
    from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402

That is the established idiom across ``scripts/xfp/`` — an import alias, so
existing call sites are untouched and there is no second definition to drift.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Trees to police. Tier D (research / one-off / attic) is deliberately excluded:
# it is dead-or-frozen code kept out of the CodeGraph index on purpose.
SCANNED_DIRS = ("src", "scripts/xfp")
EXCLUDED_DIR_NAMES = frozenset({
    "research", "_research", "_oneoff", "_attic", "archive",
    "__pycache__", ".venv", "node_modules",
})

# The owner itself is allowed to define normalizers — that is its whole job.
OWNER = "src/plv_clone/utils/name_match.py"

# ── Two detectors, ORed ──────────────────────────────────────────────────────
#
# (A) BROAD NAME + HAND-ROLLED BODY. Any function whose name mentions
#     norm/nm/ascii/strip_accents AND whose body performs its own unicode or
#     regex text munging. This is the classic shape (NFKD -> ascii -> lower ->
#     strip non-[a-z ]) and it is what all 134 duplicates looked like. The body
#     condition is what keeps statistical `_norm_cdf` / `crps_lognormal_*` and
#     dict-driven position/team normalizers out of the net.
#
# (B) EXACT NAME + DOESN'T REACH THE OWNER. A tight list of identifiers that can
#     only mean "player-name key". These are flagged even with a trivial body,
#     because the WEAKEST variant is the most dangerous: a bare `.strip().lower()`
#     is exactly what keyed PL ranks in run_positional_board.load_pl_ranks while
#     the lookup side stripped accents and punctuation — so every accented /
#     apostrophe / "C.J." name silently had no PL rank (found and fixed
#     2026-07-30 by this sweep).
_NAME_HINTS = ("norm", "_nm", "ascii", "strip_accents")

_EXACT_NAME_FNS = frozenset({
    "nm", "norm", "normalize",
    "name_norm", "norm_name", "normalize_name", "normalize_model_name",
    "norm_sp_name", "norm_audit",
    "ascii", "ascii_lower", "ascii_strip", "strip_accents",
})

# The owner's functions. A def matching (B) must reach one of these.
_OWNER_FUNCS = frozenset({
    "safe_name_key", "join_key", "_normalize", "team_key",
    "safe_lookup", "build_safe_name_index",
    "resolve_batter_id", "resolve_pitcher_id", "resolve_id",
    "lookup_batter_id_cached", "canonical_pitcher_spelling",
})

_HANDROLL_CALLS = frozenset({
    "normalize",          # unicodedata.normalize
    "combining",          # unicodedata.combining
    "category",           # unicodedata.category
    "encode",             # .encode('ascii', 'ignore')
})
_HANDROLL_RE_FUNCS = frozenset({"sub", "findall"})   # re.sub / re.findall

# ── Allowlist ────────────────────────────────────────────────────────────────
# Each entry is "<repo-relative-path>::<function name>" and MUST carry a reason.
# Adding an entry is a deliberate, reviewed act — not a way around the guard.
ALLOWLIST: dict[str, str] = {
    # NOT a join key. Builds filesystem-safe decision_ids ("Max Muncy" ->
    # "max_muncy", underscore-joined). safe_name_key returns "max muncy", so
    # routing this would change EVERY decision_id and orphan the existing
    # decision records on disk.
    "src/plv_clone/decisions/logger.py::_norm_name": "decision_id slug, not a join key",

    # Name-adjacent but with a load-bearing contract the owner does not provide.
    # `_normalize` here STRIPS SUFFIXES (jr/sr/ii/iii) because Baseball Reference
    # attaches them and FanGraphs may not; the suffix strip is what makes the
    # bref<->fg IL merge land. Migrating needs an output byte-diff of that merge
    # first (see the docstring in the file).
    "scripts/xfp/pull_bref_rp_ir.py::_norm_name": "suffix-stripping bref<->fg merge contract",

    # ALIAS-KEY GENERATORS, not join keys. These populate a dict with BOTH the
    # raw spelling and an accent-folded spelling, and the lookup side passes a
    # RAW ESPN name. Normalizing only the stored keys would break the exact
    # matches; fixing them properly means normalizing both sides at once.
    "scripts/xfp/sp_career_form_batch.py::_normalize": "raw+ascii alias-key generator",
    "scripts/xfp/league_wide_full_audit.py::_ascii": "raw+ascii alias-key generator",

    # A spelling-VARIANT generator feeding retries of `lookup_batter_id_cached`
    # (which IS the canonical resolver). It never keys a dict of its own.
    "scripts/xfp/league_wide_career_form.py::_strip_accents": "retry-variant generator, not a key",

    # Frozen one-off analysis over a hardcoded 2026 add list, whose matching is a
    # SequenceMatcher fuzzy ratio against `player.lower()`. Changing the
    # normalizer changes the fuzzy scores, and there is no production consumer to
    # justify the risk.
    "scripts/xfp/missed_breakout_scan.py::normalize_model_name": "frozen one-off, fuzzy-ratio matched",
}


def _iter_py_files():
    for d in SCANNED_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            rel = p.relative_to(ROOT).as_posix()
            if set(rel.split("/")) & EXCLUDED_DIR_NAMES:
                continue
            yield p, rel


def _looks_like_name_fn(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in _NAME_HINTS)


def _is_exact_name_fn(name: str) -> bool:
    return name.lower().strip("_") in _EXACT_NAME_FNS


def _body_hand_rolls_text(node: ast.AST) -> bool:
    """True if the function body performs its own unicode/regex text munging."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if isinstance(f, ast.Attribute):
            if f.attr in _HANDROLL_CALLS:
                return True
            if f.attr in _HANDROLL_RE_FUNCS and isinstance(f.value, ast.Name) and f.value.id == "re":
                return True
        elif isinstance(f, ast.Name) and f.id in _HANDROLL_CALLS:
            return True
    return False


def _reaches_owner(node: ast.AST) -> bool:
    """True if the function body calls one of the owner's functions.

    This is what lets the sanctioned shapes pass: a thin wrapper that flips a
    "Last, First" spelling and then delegates, or a helper that resolves an
    mlbam id. The sanctioned shape for a *pure* rename is an import alias
    (``from ... import safe_name_key as _norm``), which leaves no def at all and
    so is never inspected here.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if isinstance(f, ast.Attribute) and f.attr in _OWNER_FUNCS:
            return True
        if isinstance(f, ast.Name) and f.id in _OWNER_FUNCS:
            return True
    return False


def _find_handrolled_normalizers():
    """Return [(rel_path, fn_name, lineno), ...] for every offending definition."""
    found = []
    for path, rel in _iter_py_files():
        if rel == OWNER:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - not our files
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            hand_rolled = (_looks_like_name_fn(node.name)
                           and _body_hand_rolls_text(node))
            weak_local = (_is_exact_name_fn(node.name)
                          and not _reaches_owner(node))
            if hand_rolled or weak_local:
                found.append((rel, node.name, node.lineno))
    return found


def test_no_new_handrolled_name_normalizer():
    """Every hand-rolled name normalizer must be allowlisted with a reason.

    If this fails on code you just wrote, the fix is almost never to add an
    allowlist entry. It is:

        from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402

    Then make sure the OTHER side of the join uses the same function. Pick
    ``join_key`` instead only if the dict you are reading was built with
    ``join_key`` — they are not interchangeable and mixing them silently matches
    nothing (see this module's docstring).
    """
    offenders = [
        (rel, fn, lineno)
        for rel, fn, lineno in _find_handrolled_normalizers()
        if f"{rel}::{fn}" not in ALLOWLIST
    ]
    if offenders:
        listing = "\n".join(f"  {rel}:{lineno}  def {fn}(...)" for rel, fn, lineno in offenders)
        pytest.fail(
            "New hand-rolled player-name normalizer(s) found:\n"
            f"{listing}\n\n"
            "Do NOT add a local copy — 127 of them drifted apart and printed an\n"
            "opponent-rostered player (Ryan O'Hearn) as a FREE AGENT on 2026-07-28,\n"
            "because one copy did not collapse a curly apostrophe.\n\n"
            "Replace the def with an import alias so call sites stay untouched:\n"
            "    from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402\n\n"
            "  safe_name_key -> 'kyle schwarber'  order-PRESERVING, space-separated.\n"
            "                   Use this by default, and ALWAYS when the key is later\n"
            "                   split on spaces (a (last, first-initial) fallback).\n"
            "  join_key      -> 'kyleschwarber'   sorted tokens, no separator, order-\n"
            "                   INDEPENDENT. Only when the partner dict also uses it.\n\n"
            "They are NOT interchangeable: reading a safe_name_key-built dict with\n"
            "join_key misses every row and raises nothing.\n\n"
            f"If the function genuinely is not a name join key, add it to ALLOWLIST in\n{__file__}\n"
            "WITH a reason."
        )


def test_allowlist_has_no_stale_entries():
    """An allowlist entry whose function no longer exists must be deleted.

    Otherwise the allowlist silently grows into a place where a real offender can
    hide behind a path that used to be legitimate.
    """
    live = {f"{rel}::{fn}" for rel, fn, _ in _find_handrolled_normalizers()}
    stale = sorted(set(ALLOWLIST) - live)
    assert not stale, (
        "ALLOWLIST entries no longer match a hand-rolled normalizer (the function was "
        "migrated, renamed, or deleted). Remove them so the allowlist stays honest:\n  "
        + "\n  ".join(stale)
    )


def test_owner_exposes_both_keys_and_they_differ():
    """The two canonical keys must both exist and must NOT be interchangeable.

    This is the trap the guard's failure message warns about; if the two ever
    converge, that message becomes wrong and the mixing hazard silently changes.
    """
    from plv_clone.utils.name_match import join_key, safe_name_key

    assert safe_name_key("Kyle Schwarber") == "kyle schwarber"
    assert join_key("Kyle Schwarber") == "kyleschwarber"
    # Order-independence is join_key's defining property, and safe_name_key must
    # NOT have it (it preserves token order after the "Last, First" rewrite).
    assert join_key("Fried, Max") == join_key("Max Fried") == "friedmax"
    assert safe_name_key("Fried, Max") == safe_name_key("Max Fried") == "max fried"
    assert safe_name_key("Kyle Schwarber") != join_key("Kyle Schwarber")


def test_owner_collapses_the_ohearn_apostrophe_and_the_cj_period():
    """The two drift classes that caused the incidents, locked at the owner."""
    from plv_clone.utils.name_match import safe_name_key

    assert safe_name_key("Ryan O’Hearn") == safe_name_key("Ryan O'Hearn") == "ryan ohearn"
    assert safe_name_key("C.J. Abrams") == safe_name_key("CJ Abrams") == "cj abrams"
    assert safe_name_key("Ha-Seong Kim") == safe_name_key("Ha Seong Kim") == "ha seong kim"
    assert safe_name_key("José Ramírez") == safe_name_key("Jose Ramirez") == "jose ramirez"


# ── latent risk introduced BY this codemod (2026-07-29) ──────────────────────

def test_suffix_stripping_does_not_merge_two_real_players():
    """safe_name_key strips Jr./Sr./II/III/IV; the local _norm bodies it replaced
    did NOT. So "Luis Garcia Jr." and "Luis Garcia" now share a key.

    That is only safe while no production file carries both. It holds today
    (measured: 472/355/347 names -> the same number of keys, zero merges), but it
    is a latent MERGE — two players collapsing into one row — not a conservative
    miss. This test fails the moment it starts to bite, which is the point.
    """
    import pandas as pd
    from plv_clone.utils.name_match import safe_name_key
    root = Path(__file__).resolve().parent.parent
    specs = [("data/outputs/xfp_rh3_projections.csv", "player_name"),
             ("data/outputs/xfp_rp3_projections.csv", "player_name"),
             ("data/outputs/xfp_rprs2_projections.csv", "name_api")]
    merged_report = []
    for rel, col in specs:
        p = root / rel
        if not p.exists():
            continue
        d = pd.read_csv(p)
        if col not in d.columns:
            continue
        buckets = {}
        for n in (str(x) for x in d[col].dropna().unique()):
            buckets.setdefault(safe_name_key(n), []).append(n)
        for k, v in buckets.items():
            if len(v) > 1:
                merged_report.append(f"{rel}: {k!r} <- {v}")
    sep = chr(10) + "  "
    assert not merged_report, (
        "safe_name_key now merges distinct players in a production file. Those "
        "call sites need an mlbam join or a KNOWN_COLLISIONS guard:" + sep
        + sep.join(merged_report))


def test_the_suffix_difference_is_real_and_documented():
    """Pin the behaviour so the risk above is not mistaken for paranoia."""
    from plv_clone.utils.name_match import safe_name_key
    assert safe_name_key("Luis Garcia Jr.") == safe_name_key("Luis Garcia")
    assert safe_name_key("Michael Harris II") == safe_name_key("Michael Harris")
