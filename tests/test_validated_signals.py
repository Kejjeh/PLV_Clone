"""Behavioral tests for the validated-signals frontmatter parser.

Per ADR-0003: validation_runs/*.md is the source-of-truth for what
features may appear in any production FEATS list. The parser must be
tolerant of the existing schema and reject incomplete records.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from plv_clone.models.xfp.validated_signals import (
    ValidatedSignal,
    parse_frontmatter,
)


MINIMAL = """\
---
signal: xwoba_gap_to
formula: xwoba_on_contact_to - (woba_v_sum_to / woba_d_sum_to)
production_target: rh3
expected_sign: +
date: 2026-05-16
---
"""


def test_parse_frontmatter_extracts_minimal_record():
    sig = parse_frontmatter(MINIMAL, path=Path("xwoba_gap_to_2026-05-16.md"))

    assert sig == ValidatedSignal(
        name="xwoba_gap_to",
        formula="xwoba_on_contact_to - (woba_v_sum_to / woba_d_sum_to)",
        production_target="rh3",
        expected_sign="+",
        validation_date=date(2026, 5, 16),
        validation_run_path=Path("xwoba_gap_to_2026-05-16.md"),
        verdict=None,
    )


def test_parse_frontmatter_ignores_unrecognized_fields():
    """The existing schema has many fields (theory, framing, purpose, ...) — parser must tolerate them."""
    text = """\
---
signal: bat_speed_delta
formula: bat_speed(T-1) - bat_speed(T-2)
production_target: rh3
expected_sign: +
date: 2026-05-16
theory: Sustained mechanical change predicts FP gain
framing: full-year
holdout_years: [2026]
training_years: [2025]
purpose: Test whether the +20 FP effect generalizes
---

### Body text follows — must be ignored
"""

    sig = parse_frontmatter(text, path=Path("bat_speed_delta_2026-05-16.md"))

    assert sig.name == "bat_speed_delta"
    assert sig.production_target == "rh3"


def test_parse_frontmatter_accepts_verdict_when_present():
    text = """\
---
signal: foo
formula: x - y
production_target: rh3
expected_sign: -
date: 2026-05-16
verdict: PASS
---
"""

    sig = parse_frontmatter(text, path=Path("foo.md"))

    assert sig.verdict == "PASS"


def test_parse_frontmatter_raises_when_required_field_missing():
    text = """\
---
signal: foo
formula: x - y
production_target: rh3
---
"""

    with pytest.raises(ValueError, match="expected_sign"):
        parse_frontmatter(text, path=Path("foo.md"))


def test_parse_frontmatter_raises_when_no_frontmatter_block():
    with pytest.raises(ValueError, match="frontmatter"):
        parse_frontmatter("just a markdown file\nno frontmatter\n", path=Path("foo.md"))
