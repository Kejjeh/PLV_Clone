"""The RP roster merge in build_index_dashboard.py must use the ID-first
join (rp_by_id), matching the SP/hitter merges — issue #24.

find_xfp_record()'s ID-first behavior is already covered by
test_index_dashboard_roster_labels.py (using synthetic SP-shaped data).
This is a narrower regression test for the specific wiring bug: rp_by_id
was built but never passed to the RP call site, so it silently fell
through to the collision-prone name-key path (rp_by_key is last-write-
wins on a bare (last, first) key) that the SP/hitter merges avoid two
lines above it.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCE_PATH = ROOT / "scripts" / "xfp" / "build_index_dashboard.py"


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_rp_merge_call_site_passes_mlbam_and_by_id():
    """The RP find_xfp_record() call must pass mlbam=/by_id= exactly like
    the SP call two lines above it — the fix for issue #24."""
    src = _source()
    m = re.search(r"rp_rec\s*=.*?find_xfp_record\(", src, re.DOTALL)
    assert m, "rp_rec = find_xfp_record(...) call site not found"
    start = m.end()
    depth, i = 1, start
    while i < len(src) and depth:
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
        i += 1
    call_args = src[start : i - 1]
    assert "mlbam=" in call_args, (
        f"RP find_xfp_record() call is missing mlbam= — falls through to the "
        f"collision-prone name-key path. Call args: {call_args!r}"
    )
    assert "by_id=" in call_args or "rp_by_id" in call_args, (
        f"RP find_xfp_record() call is missing by_id=rp_by_id — the id-index "
        f"is built but never used. Call args: {call_args!r}"
    )


def test_rp_by_id_index_is_actually_referenced_somewhere():
    """rp_by_id must be used at least once beyond its own definition line —
    guards against the exact 'built but dead' pattern this issue was."""
    src = _source()
    assert src.count("rp_by_id") >= 2, (
        "rp_by_id is defined but not referenced anywhere else in the file"
    )
