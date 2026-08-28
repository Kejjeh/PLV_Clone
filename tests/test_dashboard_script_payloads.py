"""No dashboard payload may close the <script> block it lives in.

WHY THIS FILE EXISTS
build_index_dashboard writes TEN payloads into ONE <script> element:

    <script>
    window.XFP_META = __META_JSON__;
    ...
    window.XFP_DECISION = __DECISION_JSON__;
    </script>

A free-text field containing "</script>" closes that element early, so every
assignment AFTER it never runs. The React app reads undefined and the page
renders blank or half-built — with nothing in the build log to say why.

The guard existed on exactly ONE payload, `decision_json`, carrying a comment
that named the risk precisely: "escape </ so free-text fields can't close the
<script> block". The other nine did not have it — including `weekly_json`,
which is read VERBATIM off disk. (Found 2026-08-27; same partial-fix shape as
issue #69.)

Escaping "</" as "<\\/" is lossless — "\\/" is a valid JSON escape for "/" —
so both JSON.parse and a JS literal recover the original text exactly.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
sys.path.insert(0, str(ROOT / "src"))

bid = pytest.importorskip("build_index_dashboard")
TEMPLATE = ROOT / "scripts" / "xfp" / "lib" / "index_dashboard_template.py"
BUILDER = ROOT / "scripts" / "xfp" / "build_index_dashboard.py"

_HOSTILE = "writeup</script><b>pwned</b>"


def test_the_helper_neutralises_a_script_close():
    out = bid._script_json([{"note": _HOSTILE}])
    assert "</script>" not in out
    assert "<\\/script>" in out


def test_the_escape_is_lossless():
    """The text must survive intact — a guard that mangles data is a new bug."""
    out = bid._script_json([{"note": _HOSTILE}])
    back = json.loads(out)
    assert back[0]["note"] == _HOSTILE


def test_the_raw_string_guard_handles_a_file_read_verbatim():
    """weekly_json comes straight off disk and never passes through dumps."""
    out = bid._script_safe('{"a":"</script>"}')
    assert "</script>" not in out
    assert json.loads(out.replace("<\\/", "</"))["a"] == "</script>"


def test_a_hostile_payload_no_longer_closes_the_block_early():
    """The consequence, reproduced: later assignments must still be reached."""
    payload = bid._script_json([{"note": _HOSTILE}])
    block = (f"<script>\nwindow.XFP_ADVISORY = {payload};\n"
             f"window.XFP_WEEKLY = {{}};\n</script>")
    assert block.index("</script>") > block.index("window.XFP_WEEKLY"), (
        "the script element closes before the later payloads are assigned")


def _builders() -> list[Path]:
    """Every module that writes a <script> element AND serializes JSON."""
    out = []
    for path in sorted((ROOT / "scripts" / "xfp").rglob("*.py")):
        if any(sd in str(path) for sd in
               ("_oneoff", "_attic", "_research", "/research/", "archive")):
            continue
        src = path.read_text(encoding="utf-8")
        if "<script" in src and "json.dumps" in src:
            out.append(path)
    return out


BUILDERS = _builders()


def test_the_builder_census_is_not_empty():
    """If discovery breaks, every assertion below passes vacuously."""
    assert len(BUILDERS) >= 3, (
        f"only {len(BUILDERS)} HTML builders discovered — expected 4-5. "
        f"The walk has probably stopped matching.")


@pytest.mark.parametrize("path", BUILDERS, ids=[p.name for p in BUILDERS])
def test_no_builder_embeds_unguarded_json_in_a_script(path):
    """A bare json.dumps interpolated into a <script> can close it early.

    Generalised from build_index_dashboard to EVERY builder (issue #84):
    scoping the check to one file is the same mistake as scoping the guard to
    one payload. A json.dumps whose result is written to a .json/.js FILE is
    fine — there is no closing tag to hit — so only interpolation into a
    <script> context is flagged.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    # names bound to a bare json.dumps(...) result
    bare: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        call = ast.unparse(node.value)
        if "json.dumps" not in call:
            continue
        if "script_json" in call or "script_safe" in call or "replace(" in call:
            continue
        bare[tgt.id] = node.lineno

    # ...that are then interpolated near a <script> tag
    offenders = []
    for name, lineno in bare.items():
        for m in re.finditer(r"<script[^>]*>[^\n]*\{" + re.escape(name) + r"\}", src):
            offenders.append(f"{path.name}:{lineno} {name} -> {m.group(0)[:70]}")
        # f-string on a later line: same variable inside a script-tag line
        for i, line in enumerate(src.splitlines(), 1):
            if "<script" in line and "{" + name + "}" in line:
                offenders.append(f"{path.name}:{i} {name} in {line.strip()[:70]}")

    assert not offenders, (
        "JSON embedded into a <script> without the </ guard:\n  "
        + "\n  ".join(sorted(set(offenders)))
        + "\n\nUse lib.dashboard_chrome.script_json / script_safe. A free-text "
          "field containing '</script>' closes the element and silently kills "
          "every statement after it.")


def test_all_payload_placeholders_share_one_script_block():
    """The premise: if they were separate blocks this would matter less."""
    tpl = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r"<script>\s*(window\.XFP_.*?)</script>", tpl, re.S)
    assert m, "the XFP payload <script> block is no longer recognisable"
    placeholders = re.findall(r"__[A-Z0-9_]+_JSON__", m.group(1))
    assert len(placeholders) >= 8, (
        f"expected the payloads to share one block; found {placeholders}")
