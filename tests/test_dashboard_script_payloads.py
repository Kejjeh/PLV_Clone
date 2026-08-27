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


def test_every_payload_variable_is_built_through_the_helper():
    """The point of the helper is that no site can quietly skip it."""
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    # every `*_json = <call>` assignment inside main()
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name) or not tgt.id.endswith("_json"):
            continue
        src = ast.unparse(node.value)
        if src.startswith(("'", '"')):
            continue                       # a literal default, nothing to escape
        if "_script_json" in src or "_script_safe" in src:
            continue
        offenders.append(f"line {node.lineno}: {tgt.id} = {src[:70]}")
    assert not offenders, (
        "payload(s) built without the <script>-safety helper:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse _script_json(obj) / _script_safe(raw). A bare json.dumps "
          "lets a free-text field close the <script> block and silently kill "
          "every payload after it.")


def test_all_payload_placeholders_share_one_script_block():
    """The premise: if they were separate blocks this would matter less."""
    tpl = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r"<script>\s*(window\.XFP_.*?)</script>", tpl, re.S)
    assert m, "the XFP payload <script> block is no longer recognisable"
    placeholders = re.findall(r"__[A-Z0-9_]+_JSON__", m.group(1))
    assert len(placeholders) >= 8, (
        f"expected the payloads to share one block; found {placeholders}")
