"""Tests for lib/dashboard_chrome.py — the ONE top-nav owner (item 8).

Pins the canonical page set (so xfp_board can't silently drop off a nav again)
and the topnav() contract every builder depends on.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for p in (_ROOT / "scripts" / "xfp", _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib import dashboard_chrome as dc


def test_canonical_pages_include_all_six():
    keys = [k for k, _, _ in dc.PAGES]
    assert keys == ["index", "matchup", "live", "xfp_board", "player_profiles", "triangulate"]
    # the drift bug that motivated the owner: xfp_board must be present
    assert "xfp_board" in dc.PAGE_KEYS


def test_topnav_marks_current_without_href():
    nav = dc.topnav("index")
    assert '<a class="current">XFP</a>' in nav
    assert 'href="index.html"' not in nav  # current page has no href
    # every OTHER page is a link
    assert 'href="xfp_board.html"' in nav
    assert 'href="matchup.html"' in nav


def test_topnav_every_page_key_renders():
    for key, _, _ in dc.PAGES:
        nav = dc.topnav(key)
        assert nav.startswith('<nav class="topnav">') and nav.endswith("</nav>")
        assert nav.count('class="current"') == 1


def test_topnav_unknown_key_raises():
    import pytest
    with pytest.raises(ValueError):
        dc.topnav("nope")
