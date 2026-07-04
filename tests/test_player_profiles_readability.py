"""Readability contract for the player-profiles dashboard all-players tables.

Driven by the 2026-07-04 feedback session: 22-26 columns squeezed into 100%
viewport width (table-layout: fixed) clipped the header labels ("STUFF SL",
"PITCH ARCH" cut mid-word), domain ratings rendered as cryptic single letters
(S/M/C, C/P/D), and 20-80 ratings were bare numbers with no visual anchor.

The contract this locks in:
  1. Core/Full column views — Core (default) shows only decision columns at
     comfortable widths; Full shows everything but SCROLLS horizontally
     (min-width) instead of clipping headers.
  2. 20-80 rating chips — rating cells render in color-banded chips
     (ratingClass -> .rchip.r20..r80) so a 74 reads as elite at a glance.
  3. Full-word header labels (labelFull) for the domain ratings.
  4. Sticky header row.

Tests assert on the template module's JS/CSS strings — the build embeds them
verbatim, so string presence here == feature present in the built page.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

import _player_profiles_template as T

CSS = T.HEAD
JS = T.JS


# ── 1. Core/Full column views ────────────────────────────────────────────────

def test_column_defs_carry_core_flags():
    """Each main table needs a curated core subset (the decision columns)."""
    # the three domain ratings + OVERALL + archetype must be core in all tables
    for key in ("OVERALL", "archetype", "player_name"):
        assert re.search(rf"key:\s*'{key}'[^}}]*core:\s*true", JS), f"{key} not core-flagged"
    # context-only columns must NOT be core (they belong to the Full view)
    for key in ("boundary_tier", "data_tier", "rank_in_year"):
        assert not re.search(rf"key:\s*'{key}'[^}}]*core:\s*true", JS), f"{key} wrongly core"


def test_colview_state_and_toggle_exist():
    assert "colView" in JS, "per-role column-view state missing"
    assert "colview" in JS.lower() and "Core" in JS and "All columns" in JS, \
        "Core / All-columns toggle UI missing"


def test_full_view_scrolls_instead_of_clipping():
    assert ".table-scroll.cols-full" in CSS, "full-view scroll wrapper CSS missing"
    assert re.search(r"table\.alltable\.cols-full\s*\{[^}]*min-width", CSS), \
        "full view needs min-width so headers never clip"


# ── 2. 20-80 rating chips ────────────────────────────────────────────────────

def test_rating_class_function_bands_20_to_80():
    assert "function ratingClass(" in JS
    assert "RATING_CHIP_KEYS" in JS


def test_rchip_css_bands_present():
    for band in ("r80", "r70", "r60", "r50", "r40", "r30", "r20"):
        assert f".rchip.{band}" in CSS, f"missing rating chip band .{band}"


# ── 3. Full-word domain labels ───────────────────────────────────────────────

def test_domain_columns_have_full_word_labels():
    for key, word in (("STUFF", "Stuff"), ("MOVEMENT", "Move"), ("CONTROL", "Ctrl"),
                      ("CONTACT", "Contact"), ("POWER", "Power"), ("DISCIPLINE", "Disc")):
        assert re.search(rf"key:\s*'{key}'[^}}]*labelFull:\s*'{word}'", JS), \
            f"{key} lacks labelFull '{word}'"


# ── 4. Sticky header ─────────────────────────────────────────────────────────

def test_sticky_table_header():
    assert re.search(r"table\.alltable thead th\s*\{[^}]*position:\s*sticky", CSS), \
        "alltable header row must be sticky"
