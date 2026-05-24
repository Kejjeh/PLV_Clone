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
    check_feats_validated,
    load_registry,
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
        production_targets=("rh3",),
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
    assert sig.production_targets == ("rh3",)


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


def _write_run(directory: Path, name: str, target: str, verdict: str | None) -> None:
    body = ["---", f"signal: {name}", "formula: a - b",
            f"production_target: {target}", "expected_sign: +", "date: 2026-05-16"]
    if verdict is not None:
        body.append(f"verdict: {verdict}")
    body.append("---\n")
    (directory / f"{name}_2026-05-16.md").write_text("\n".join(body), encoding="utf-8")


def test_load_registry_skips_readme_and_indexes_by_signal_name(tmp_path):
    (tmp_path / "README.md").write_text("# index\n", encoding="utf-8")
    _write_run(tmp_path, "feat_a", "rh3", "PASS")
    _write_run(tmp_path, "feat_b", "rp3", "REJECTED")

    registry = load_registry(tmp_path)

    assert set(registry) == {"feat_a", "feat_b"}
    assert registry["feat_a"].production_targets == ("rh3",)
    assert registry["feat_b"].verdict == "REJECTED"


def test_check_feats_validated_warns_on_missing_and_mismatched(tmp_path):
    _write_run(tmp_path, "valid_feat", "rh3", "PASS")
    _write_run(tmp_path, "wrong_target", "rp3", "PASS")
    _write_run(tmp_path, "not_passed", "rh3", "MARGINAL")
    registry = load_registry(tmp_path)

    with pytest.warns(UserWarning, match="rh3: 3 FEATS entries unvalidated"):
        gaps = check_feats_validated(
            ["valid_feat", "wrong_target", "not_passed", "missing_entirely"],
            target="rh3",
            registry=registry,
        )

    assert len(gaps) == 3
    assert any("wrong_target" in g and "'rp3'" in g for g in gaps)
    assert any("not_passed" in g and "MARGINAL" in g for g in gaps)
    assert any("missing_entirely" in g for g in gaps)


def test_check_feats_validated_returns_empty_when_all_pass(tmp_path):
    _write_run(tmp_path, "a", "rh3", "PASS")
    _write_run(tmp_path, "b", "rh3", "PASS")
    registry = load_registry(tmp_path)

    gaps = check_feats_validated(["a", "b"], target="rh3", registry=registry)

    assert gaps == []


def test_check_feats_validated_strict_raises(tmp_path):
    registry = load_registry(tmp_path)  # empty dir

    with pytest.raises(AssertionError, match="unvalidated"):
        check_feats_validated(["unknown_feat"], target="rh3", registry=registry, strict=True)


def test_parse_frontmatter_accepts_comma_separated_targets():
    """Shared features (e.g. k_pct_to_sh used by rh3 + rp3) carry a comma-separated production_target."""
    text = """\
---
signal: k_pct_to_sh
formula: k/pa season-to-date, denom-shrunk
production_target: rh3, rp3
expected_sign: -
date: 2026-05-23
verdict: PASS
---
"""

    sig = parse_frontmatter(text, path=Path("k_pct_to_sh_2026-05-23.md"))

    assert sig.production_targets == ("rh3", "rp3")


def test_check_feats_validated_accepts_signal_registered_for_either_target(tmp_path):
    """A signal with production_targets=(rh3, rp3) clears the check for either target."""
    _write_run(tmp_path, "shared", "rh3, rp3", "PASS")
    registry = load_registry(tmp_path)

    assert check_feats_validated(["shared"], target="rh3", registry=registry) == []
    assert check_feats_validated(["shared"], target="rp3", registry=registry) == []
    # But not for a third target
    with pytest.warns(UserWarning):
        gaps = check_feats_validated(["shared"], target="rprs2", registry=registry)
    assert any("rprs2" in g for g in gaps)
