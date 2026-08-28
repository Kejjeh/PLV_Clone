"""Every tracked .py file must parse on the declared minimum Python.

WHY THIS EXISTS
`pyproject.toml` declares `requires-python = ">=3.11"`, but three files had
crept in using PEP 701 nested same-quote f-strings — `f"...{d["key"]}..."` —
which only parse on 3.12+. On 3.11 those files could not be imported or run
at all, and nothing caught it because no test imported them. It surfaced
only indirectly, as an `ast.parse` crash inside an unrelated hygiene test.

A syntax floor is exactly the kind of thing a cheap repo-wide guard should
hold, so this walks every tracked source file and parses it. On 3.12+ the
interpreter accepts PEP 701 happily, so the check additionally rejects the
specific construct by scanning f-strings for a nested same-quote subscript
that older interpreters reject. (Added 2026-08-27.)
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# `f'...{x["k"]}...'` is fine (different quotes). `f"...{x["k"]}..."` is PEP 701.
# Match an f-string opener, then a replacement field `{...` whose expression
# reaches a `[` + same-quote — the nested-subscript shape PEP 701 legalized.
# Two guards, both from false positives found 2026-08-28 on Python 3.13 (the
# container ran 3.11 where this test skips, so the regex had never executed):
#   * the lookbehind: an identifier's trailing f (`stuff":r["`), a format spec
#     (`:.0f}`), and `df['` all read as f-string openers without it;
#   * the `\{` requirement: a literal `[` at the end of the string body
#     (`f"const {tbl} = ["`) is the string's own closing quote after `[`,
#     not a nested quote.
_PEP701 = re.compile(
    r"""(?<![\w"'])f(?P<q>["'])(?:[^"'\\\n]|\\.)*?\{[^"'{}\n]*\[\s*(?P=q)""",
)


def _declared_floor() -> tuple[int, int]:
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())
    spec = cfg["project"]["requires-python"]
    m = re.search(r"(\d+)\.(\d+)", spec)
    assert m, f"could not parse requires-python={spec!r}"
    return int(m.group(1)), int(m.group(2))


def _tracked_py_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [ROOT / p for p in out]


def test_every_tracked_file_parses_on_the_declared_floor() -> None:
    files = _tracked_py_files()
    assert files, "git ls-files returned no .py files — is this a git checkout?"

    bad = []
    for path in files:
        try:
            src = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        try:
            ast.parse(src, filename=str(path))
        except SyntaxError as exc:
            bad.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")

    assert not bad, (
        f"{len(bad)} file(s) do not parse on this interpreter "
        f"(Python {sys.version_info.major}.{sys.version_info.minor}):\n  "
        + "\n  ".join(bad)
    )


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="on <3.12 the parse test above already rejects PEP 701",
)
def test_no_pep701_nested_same_quote_fstrings() -> None:
    """On 3.12+ the parser accepts PEP 701, so scan for it explicitly."""
    floor = _declared_floor()
    if floor >= (3, 12):
        pytest.skip(f"requires-python floor is {floor} — PEP 701 is allowed")

    bad = []
    for path in _tracked_py_files():
        if path.name == Path(__file__).name:
            continue  # this file documents the pattern in comments
        try:
            src = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(src.splitlines(), 1):
            if _PEP701.search(line):
                bad.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

    assert not bad, (
        f"PEP 701 nested same-quote f-string(s) found, but requires-python is "
        f">={floor[0]}.{floor[1]} — these will not parse on the declared floor.\n"
        "Hoist the value into a local, or use the other quote style:\n  "
        + "\n  ".join(bad)
    )
