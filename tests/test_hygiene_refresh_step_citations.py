"""Refresh-step citation drift guard (audit T50).

Spec: every refresh-step number cited in a source comment names a step the
driver actually runs. The 2026-07-19 renumber moved the decision-console
payload writer from 4.52 to 4.3, but comments in consumer modules kept
pointing at the retired number, so a reader chasing "step 4.52" finds nothing
in `refresh_dashboards.main()`.

The driver documents a renumber inline as ``'<new> (was <old>). <label>'``.
This guard honours that convention on BOTH sides: a `(was N)` parenthetical in
a consumer comment is a deliberate historical breadcrumb and is stripped
before the citation is resolved.

Live step numbers are read from the driver by AST -- the leading token of the
first string argument of each ``run(...)`` call -- not by regexing the driver's
source text (the anti-pattern flagged separately as backlog item 39/40). When
the driver grows a declarative step list, swap the `_live_step_numbers` body
for a read of that list; the assertions below stay as-is.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DRIVER = REPO_ROOT / "scripts" / "xfp" / "refresh_dashboards.py"

# Scope: the whole production tree. The first cut listed ONE file because the
# bare "step N" pattern drowned in false positives; requiring refresh context
# (see _REFRESH_CTX_RE) removed them, so the guard can now police every module
# that actually cites a refresh step instead of the one someone remembered.
_SKIP_PARTS = ("archive", "research", "_oneoff", "_attic", "_research")
CITING_MODULES = sorted(
    p for p in list((REPO_ROOT / "scripts" / "xfp").rglob("*.py"))
    + list((REPO_ROOT / "src").rglob("*.py"))
    if not any(part in _SKIP_PARTS for part in p.parts)
)

_STEP_TOKEN = r"\d+(?:\.\d+)*[a-z]?"
# A citation only counts when the text ALSO names the refresh driver.
# Without that context the pattern matches every standalone script's own
# internal numbering ("# Step 7 - Final verdict"), which is not drift at
# all: a repo-wide scan found 153 "step N" mentions of which only ~6 were
# real refresh citations. Precision is what lets the scope be repo-wide.
_CITATION_RE = re.compile(rf"step\s+({_STEP_TOKEN})", re.IGNORECASE)
_REFRESH_CTX_RE = re.compile(r"refresh", re.IGNORECASE)
_WAS_RE = re.compile(rf"\(\s*was\s+{_STEP_TOKEN}\s*\)", re.IGNORECASE)
_LEADING_RE = re.compile(rf"^\s*({_STEP_TOKEN})")


def _live_step_numbers(path: Path | None = None) -> set[str]:
    """Step numbers the driver actually runs, from its bare ``run(...)`` labels.

    BARE name only (``ast.Name``): ``subprocess.run('9.99 ...')`` is an
    attribute call and must never enter the live set — admitting it would let
    any command string starting with a digit masquerade as a live step and
    silently widen the set the drift check compares against.
    """
    tree = ast.parse((path or DRIVER).read_text(encoding="utf-8"))
    live: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "run":
            continue
        args = list(node.args) + [kw.value for kw in node.keywords]
        for arg in args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                match = _LEADING_RE.match(arg.value)
                if match:
                    live.add(match.group(1))
                break
    return live


def _cited_steps(path: Path) -> list[tuple[int, str, str]]:
    """(lineno, step_number, text) for every step cited in a COMMENT or a
    DOCSTRING.

    Docstrings are scanned too (review round 2026-08-01): the first cut
    tokenized only COMMENT tokens and was therefore blind to citations in
    module/class/function docstrings, which is where several real ones live —
    a drift guard that sees half the citations reads as coverage it does not
    have.
    """
    src = path.read_text(encoding="utf-8")
    found: list[tuple[int, str, str]] = []

    def _scan_block(lines: list[tuple[int, str]], label_prefix: str) -> None:
        """Apply the refresh-context test at BLOCK level, report per line.

        Per-LINE context was the review round's blocking find: a citation
        wrapped as "... (step 4.7 of
# refresh_dashboards.py)" splits the
        step and the word "refresh" across adjacent lines, so a line-scoped
        gate silently skipped the very citation the guard exists to police.
        A comment block / docstring is one utterance — context anywhere in it
        qualifies every citation in it.
        """
        cleaned = [(ln, _WAS_RE.sub("", text)) for ln, text in lines]
        if not any(_REFRESH_CTX_RE.search(t) for _ln, t in cleaned):
            return                      # a script's own step numbering
        for ln, text in cleaned:
            for match in _CITATION_RE.finditer(text):
                found.append((ln, match.group(1),
                              f"{label_prefix}{text.strip()[:80]}"))

    # contiguous COMMENT tokens form one block
    block: list[tuple[int, str]] = []
    last_ln = None
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            if last_ln is not None and tok.start[0] != last_ln + 1:
                _scan_block(block, "")
                block = []
            block.append((tok.start[0], tok.string))
            last_ln = tok.start[0]
    _scan_block(block, "")

    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node, clean=False)
        if not doc:
            continue
        lineno = getattr(node, "lineno", 1)
        _scan_block([(lineno + i, line) for i, line in
                     enumerate(doc.splitlines())], "docstring: ")
    return found


def test_driver_step_labels_are_discoverable() -> None:
    """Harness guard: an empty live set would make the drift check vacuous."""
    live = _live_step_numbers()
    assert len(live) >= 20, f"only {len(live)} step labels found in {DRIVER.name}"


def test_cited_refresh_step_numbers_resolve_to_a_live_driver_step() -> None:
    live = _live_step_numbers()
    stale = [
        f"{path.name}:{lineno} cites step {step} -> not a live driver step "
        f"({comment})"
        for path in CITING_MODULES
        for lineno, step, comment in _cited_steps(path)
        if step not in live
    ]
    assert not stale, "stale refresh-step citations:\n  " + "\n  ".join(stale)


FIXTURE_LINES = [
    '"""A module whose docstring cites a step.',
    '',
    'Written by refresh step 9.91 (a number that is not live).',
    '"""',
    '',
    '',
    'def go():',
    '    """Consumes what the refresh step 9.92 produced."""',
    '    return 1',
]


def test_the_guard_sees_step_citations_in_DOCSTRINGS_too(tmp_path):
    """Review round (2026-08-01): the scan tokenized only COMMENT tokens, so a
    stale step number written in a module/function DOCSTRING — where several
    real citations live — was structurally invisible. A guard that cannot see
    half the citations it polices is worse than none: it reads as coverage."""
    f = tmp_path / "mod_with_docstring_citation.py"
    f.write_text(chr(10).join(FIXTURE_LINES) + chr(10), encoding="utf-8")
    cited = {step for _ln, step, _txt in _cited_steps(f)}
    assert "9.91" in cited, "module-docstring citation must be seen"
    assert "9.92" in cited, "function-docstring citation must be seen"


def test_subprocess_run_string_is_not_mistaken_for_a_live_step(tmp_path):
    """`_live_step_numbers` matched ANY call named `run` — including
    `subprocess.run` — so a command string starting with a digit would be
    admitted as a live step number, silently widening the live set and
    weakening the drift check it feeds."""
    f = tmp_path / "driver_like.py"
    f.write_text(
        "import subprocess" + chr(10) +
        "def main():" + chr(10) +
        "    run('1.05 gf bridge', 'python x.py')" + chr(10) +
        "    subprocess.run('9.99 not a step', shell=True)" + chr(10),
        encoding="utf-8")
    live = _live_step_numbers(f)
    assert "1.05" in live
    assert "9.99" not in live, (
        "a subprocess.run command string must never enter the live step set")
