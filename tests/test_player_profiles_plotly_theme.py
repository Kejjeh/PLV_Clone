"""Plotly charts must theme with the page, not stay hardcoded-dark (issue #7 item 2).

`_player_profiles_template.py`'s 5 Plotly.react() call sites hardcoded
paper_bgcolor/plot_bgcolor/gridcolor/font-color as literal dark hex, so in
light mode (dashboard_chrome's data-theme toggle) the surrounding page themed
correctly but every chart stayed a dark card. Since the toggle mutates
document.documentElement's data-theme attribute in place (no page reload —
see dashboard_chrome.theme_boot_js), a correct fix must (a) resolve chart
colors from the page's live CSS custom properties, not literal hex, and
(b) re-apply those colors to already-rendered charts when the toggle fires,
not just at first paint.

Tests assert on the template module's JS string — the build embeds it
verbatim, so string presence here == behavior present in the built page
(same convention as test_player_profiles_readability.py).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

import _player_profiles_template as T

JS = T.JS

# The 5 known chart-producing functions from the issue #7 writeup.
_CHART_FUNCS = [
    "renderQuadrant",
    "renderStackedArchDist",
    "renderSnapshotTrajectory",
    "renderSnapshotTrajectoryYoY",
    "renderSparkline",
]

_HARDCODED_DARK_HEX = ("#211e1a", "#1a1815", "#34302a", "#f5f1ea")


def _plotly_react_blocks():
    """Every `Plotly.react(divId, traces, { ... }` layout-object literal,
    isolated by brace-depth so nested {} (xaxis, legend, font, ...) don't
    truncate the match."""
    blocks = []
    for m in re.finditer(r"Plotly\.react\([^,]+,\s*[A-Za-z_]\w*,\s*\{", JS):
        start = m.end() - 1  # index of the opening '{'
        depth = 0
        i = start
        while i < len(JS):
            if JS[i] == "{":
                depth += 1
            elif JS[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        blocks.append(JS[start : i + 1])
    return blocks


def test_theme_helper_reads_live_css_custom_properties():
    """A shared helper must resolve chart colors from computed CSS vars
    (getComputedStyle), not hardcode them — this is what makes the fix work
    for BOTH themes instead of just picking a different fixed hex."""
    assert re.search(r"function _plotlyChartTheme\s*\(", JS), (
        "expected a shared _plotlyChartTheme() helper"
    )
    helper_start = JS.index("function _plotlyChartTheme")
    helper_body = JS[helper_start : helper_start + 600]
    assert "getComputedStyle" in helper_body
    assert "--bg" in helper_body and "--panel" in helper_body
    assert "--text" in helper_body and "--border" in helper_body


def test_no_chart_layout_hardcodes_dark_canvas_colors():
    """None of the 5 Plotly.react() layout objects may contain a literal
    dark hex for paper_bgcolor/plot_bgcolor/gridcolor/zerolinecolor/font
    color — those must all be resolved via the theme helper at render time."""
    blocks = _plotly_react_blocks()
    assert len(blocks) >= 5, f"expected >=5 Plotly.react() layout blocks, found {len(blocks)}"
    for i, block in enumerate(blocks):
        for hexval in _HARDCODED_DARK_HEX:
            assert hexval not in block, (
                f"Plotly.react() block #{i} still hardcodes {hexval} — "
                f"chart will not theme in light mode:\n{block[:200]}..."
            )


def test_every_chart_function_uses_the_theme_helper():
    for fn in _CHART_FUNCS:
        m = re.search(rf"function {fn}\(", JS)
        assert m, f"{fn} not found in JS"
        # scan forward to the function's matching closing brace
        start = JS.index("{", m.end())
        depth, i = 0, start
        while i < len(JS):
            if JS[i] == "{":
                depth += 1
            elif JS[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = JS[start : i + 1]
        assert "_plotlyChartTheme(" in body, f"{fn} does not call the theme helper"


def test_theme_toggle_relayouts_existing_charts():
    """The toggle mutates data-theme in place without reloading the page, so
    a chart already on screen needs to be re-colored live, not just at next
    render. Must wrap/hook the toggle to re-apply theme colors to any
    already-rendered Plotly div."""
    assert "__xfpToggleTheme" in JS, "must hook the existing theme toggle"
    assert "Plotly.relayout" in JS, "must re-color already-rendered charts on toggle"
