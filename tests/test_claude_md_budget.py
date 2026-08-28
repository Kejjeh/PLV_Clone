"""CLAUDE.md is auto-loaded into every session; keep it from drifting again.

It opened with "keep tight; ~200 lines max" and had reached **635** — 3.2x its
own stated budget, by slow drift rather than one bad commit (issue #46). The
stated escape hatch, "detail belongs in memory files", pointed at
`C:\\Users\\Joshua\\.claude\\projects\\...` — a Windows path unreachable from the
Linux containers these sessions run in, so the repo was the only durable place
to put anything and everything landed inline.

`docs/memory/` is the reachable target. The detail moved there VERBATIM; the
headline stayed in CLAUDE.md, so each rule still fires from the auto-loaded
file and the evidence is one hop away.

WHY THE CEILING IS 320 AND NOT 200
200 was aspirational and never met. The file must carry 15 numbered gotchas and
18 numbered don't-dos — 33 rules that each have to fire on their own — plus the
league constants, the scoring formulas and the model table. Compressed to one
line per rule that is ~110 lines before anything else. A ceiling the file
cannot meet is a ceiling that gets ignored, which is how it reached 635. 320 is
the post-extraction size (317) plus a little headroom, and it RATCHETS: the way
to add a rule is one line here and the full text in docs/memory/.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = ROOT / "CLAUDE.md"
MEMORY = ROOT / "docs" / "memory"

#: Hard ceiling. Lower it when the file shrinks; raising it needs a reason in
#: the same commit, and "I added a rule inline" is not one.
MAX_LINES = 320


def _text() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def test_claude_md_stays_under_the_ceiling():
    n = len(_text().splitlines())
    assert n <= MAX_LINES, (
        f"CLAUDE.md is {n} lines, over the {MAX_LINES}-line ceiling. It is "
        f"auto-loaded into every session. Put the detail in docs/memory/ and "
        f"leave a one-line headline here."
    )


def test_the_ceiling_is_actually_binding():
    """A ceiling far above the file is not a ratchet. If this fails the file
    shrank a lot — lower MAX_LINES rather than leaving the slack."""
    n = len(_text().splitlines())
    assert n >= MAX_LINES - 60, (
        f"CLAUDE.md is {n} lines against a {MAX_LINES} ceiling — {MAX_LINES - n} "
        f"lines of slack. Lower MAX_LINES so the ratchet keeps working."
    )


def test_the_memory_dir_exists_and_is_reachable():
    """The whole point of issue #46: the escape hatch has to be a path these
    sessions can actually read."""
    assert MEMORY.is_dir(), "docs/memory/ is gone — the detail has nowhere to live"
    assert list(MEMORY.glob("*.md")), "docs/memory/ is empty"


@pytest.mark.parametrize(
    "name",
    ["gotchas.md", "dont_do.md", "pwin_layer.md", "skills_cheatsheet.md",
     "league_rules.md", "validated_models.md", "codegraph.md"],
)
def test_each_extracted_file_still_exists(name):
    """CLAUDE.md points at these by name. A dead pointer is worse than the
    inline text it replaced — the reader gets the headline and no evidence."""
    path = MEMORY / name
    assert path.exists(), f"docs/memory/{name} is referenced by CLAUDE.md but missing"
    assert path.stat().st_size > 200, f"docs/memory/{name} looks emptied out"


def test_every_docs_memory_pointer_in_claude_md_resolves():
    """Catches the reverse drift: a renamed memory file leaving a stale link."""
    broken = [
        ref for ref in set(re.findall(r"docs/memory/([A-Za-z0-9_]+\.md)", _text()))
        if not (MEMORY / ref).exists()
    ]
    assert not broken, f"CLAUDE.md links to missing memory files: {sorted(broken)}"


def test_no_numbered_rule_was_lost_in_the_extraction():
    """The compression must not silently drop a rule. Numbering is load-bearing
    — memos and skill docs cite "gotcha #12" and "don't-do #10" by number — so
    both lists have to stay contiguous from 1, in CLAUDE.md AND in the memory
    file that holds their full text.
    """
    text = _text()

    def _numbers(block: str) -> list[int]:
        return sorted({int(m) for m in re.findall(r"^(\d+)\. ", block, flags=re.M)})

    for heading, memory_file, expected_n in (
        ("## Fast-path gotchas", "gotchas.md", 15),
        ("## Don't do these", "dont_do.md", 18),
    ):
        start = text.index(heading)
        end = text.index("\n## ", start + 1)
        headline_nums = _numbers(text[start:end])
        assert headline_nums == list(range(1, expected_n + 1)), (
            f"{heading} in CLAUDE.md lists {headline_nums}, not 1..{expected_n} — "
            f"a rule was dropped or renumbered. Retire in place, never renumber."
        )
        full_nums = _numbers((MEMORY / memory_file).read_text(encoding="utf-8"))
        assert set(headline_nums) <= set(full_nums), (
            f"these rules have a headline in CLAUDE.md but no full text in "
            f"docs/memory/{memory_file}: {sorted(set(headline_nums) - set(full_nums))}"
        )


def test_claude_md_does_not_send_the_reader_to_the_unreachable_windows_path():
    """The header used to name a `C:\\Users\\...` memory dir as THE place detail
    belongs. It is unreachable from these containers, so the instruction could
    not be followed and everything accumulated inline instead. The path may
    still be MENTIONED — it exists on Josh's host — but not as the destination
    for new detail."""
    text = _text()
    if "C:\\Users" not in text:
        return
    windows_lines = [l for l in text.splitlines() if "C:\\Users" in l]
    context = "\n".join(windows_lines)
    assert "docs/memory" in text, "no reachable memory target is offered at all"
    assert "NOT reachable" in text or "not reachable" in text, (
        "CLAUDE.md names the Windows memory path without saying it is "
        f"unreachable from these sessions:\n{context}"
    )
