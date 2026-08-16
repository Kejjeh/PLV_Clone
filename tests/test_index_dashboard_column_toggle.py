"""Index dashboard column show/hide — issue #7 item 1.

Every other static dashboard already has column_toggle_js (scan the rendered
<table data-cols> DOM, hide by header-label fingerprint, persist to
localStorage['xfp_cols::{page}::{tableId}']). index.html's ~23-column SP
table is a React/Babel single-file app though — there's no persistent DOM for
a vanilla-JS scanner to fingerprint against, so this needs a React-side
useHiddenCols hook instead. Contract carried over from the vanilla version:
same localStorage key SHAPE, lock the first columns (rank/name) from being
hideable, hide by SortTh's existing `col` prop (a much better identity key
than the vanilla version's label-text fingerprint, since it's already stable
and unique per column).

Tests assert on the rendered template string — same convention as
test_index_dashboard_template.py / test_player_profiles_*.py.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PY = ROOT / "scripts" / "xfp" / "lib" / "index_dashboard_template.py"

# The SP projections table's 21 hideable columns (everything except the ★
# favorites column, rank, name — locked — and the FG icon column, neither of
# which is a SortTh / carries a `col` prop today).
_HIDEABLE_COLS = [
    "rosTotalFp", "rosReplDeltaTotal", "signal", "xfpRoS", "xfpRoSSched",
    "recencyGap", "gsToDate", "xfpV12", "replDelta", "xfpV11", "il60Lag1",
    "fpTotal", "delta", "stuffXfp", "ipPremium", "ipTrend", "kPct",
    "swstrPct", "gs", "fpActual", "roster",
]
_LOCKED_COLS = ["rank", "name"]


def _load_template_module():
    spec = importlib.util.spec_from_file_location(
        "_index_dashboard_template_under_test_coltoggle", TEMPLATE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _html():
    return _load_template_module().render_app()


def test_use_hidden_cols_hook_exists_and_is_localstorage_backed():
    html = _html()
    assert re.search(r"function useHiddenCols\s*\(", html), (
        "expected a useHiddenCols React hook"
    )
    start = html.index("function useHiddenCols")
    body = html[start : start + 1200]
    assert "localStorage" in body, "hidden-cols state must persist across reloads"
    # same key SHAPE as the vanilla column_toggle_js contract:
    # xfp_cols::{page}::{tableId}
    assert "xfp_cols::" in body, (
        "must reuse the xfp_cols:: localStorage key namespace from the "
        "vanilla column_toggle_js contract, not invent a new one"
    )


def test_sort_th_carries_a_data_col_identity_for_hiding():
    """SortTh already has a `col` prop as a stable per-column key (better
    than the vanilla scanner's label-text fingerprint) — it must expose that
    as a DOM attribute so the hide mechanism can target it."""
    html = _html()
    m = re.search(r"function SortTh\([^)]*\)\s*\{", html)
    assert m, "SortTh not found"
    start = m.end() - 1  # the function body's opening brace
    depth, i = 0, start
    while i < len(html):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = html[start : i + 1]
    assert re.search(r"data-col=\{\s*col\s*\}", body), (
        "SortTh must render data-col={col} so hidden columns can be targeted"
    )


def test_every_hideable_body_cell_carries_matching_data_col():
    """Header and body must agree on the same identity key per column, or
    hiding a header without hiding its data cell (or vice versa) leaves a
    misaligned table."""
    html = _html()
    for col in _HIDEABLE_COLS:
        assert re.search(rf"data-col=['\"]{col}['\"]", html), (
            f"no data-col='{col}' found on a body cell — header/body would "
            f"desync when this column is hidden"
        )


def test_locked_columns_are_never_hideable():
    """rank/name must not be toggleable — mirrors the vanilla
    column_toggle_js's data-col-lock (first N columns locked)."""
    html = _html()
    m = re.search(r"useHiddenCols\(\s*['\"]projections['\"]\s*,\s*\[([^\]]*)\]", html)
    assert m, "expected useHiddenCols('projections', [...locked cols...]) call site"
    locked_arg = m.group(1)
    for col in _LOCKED_COLS:
        assert f"'{col}'" in locked_arg or f'"{col}"' in locked_arg, (
            f"{col} must be in the locked-columns list passed to useHiddenCols"
        )


def test_column_picker_ui_exists_for_every_hideable_column():
    """A user-facing control must exist to toggle each hideable column —
    otherwise the hook has no way to be driven."""
    html = _html()
    assert re.search(r"function ColumnPicker\(", html), "expected a ColumnPicker component"
    picker_start = html.index("function ColumnPicker")
    picker_body = html[picker_start : picker_start + 4000]
    for col in _HIDEABLE_COLS:
        assert f"'{col}'" in picker_body or f'"{col}"' in picker_body, (
            f"ColumnPicker has no entry for hideable column '{col}'"
        )


def test_hiding_is_driven_by_a_display_none_rule_keyed_on_data_col():
    """The actual hide mechanism: a generated CSS/style rule targeting
    [data-col="X"] for each currently-hidden column."""
    html = _html()
    assert re.search(r"data-col=.\$\{[^}]+\}.\s*\{\s*display\s*:\s*none", html) or \
           re.search(r"display:\s*none", html) and "hiddenCols" in html, (
        "expected a display:none rule driven by hiddenCols state"
    )
