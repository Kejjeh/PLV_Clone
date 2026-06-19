"""Tests for the position-agnostic Rule-9 lift scoring primitive.

This is the pure math that the validation harness (and the many bespoke
validate_*.py scripts) re-derive: given per-year and overall cross-year r for a
baseline vs baseline+candidate, compute the lift, per-year sign consistency, and
holdout lift. Pure over the cross_year_eval OUTPUTS — no data, no model.
"""
import pytest

from scripts.xfp.lib.rule9 import rule9_lift


def test_rule9_lift_basic():
    py_base = {2023: {'r': 0.50}, 2024: {'r': 0.55}, 2025: {'r': 0.60}}
    py_full = {2023: {'r': 0.52}, 2024: {'r': 0.54}, 2025: {'r': 0.63}}
    out = rule9_lift(py_base, py_full, r_base=0.55, r_full=0.57)
    assert out['lift'] == pytest.approx(0.02)
    assert out['per_year_lift'] == {2023: 0.02, 2024: -0.01, 2025: 0.03}
    assert out['sign_match_years'] == 2          # 2023 and 2025 are positive
    assert out['n_total_years'] == 3
    # holdout default (2024, 2025): mean(0.54,0.63) - mean(0.55,0.60) = 0.01
    assert out['holdout_lift'] == pytest.approx(0.01)


def test_rule9_lift_only_overlapping_years_count():
    # a year present in full but not baseline must be ignored
    py_base = {2024: {'r': 0.40}}
    py_full = {2024: {'r': 0.45}, 2025: {'r': 0.99}}
    out = rule9_lift(py_base, py_full, r_base=0.40, r_full=0.45)
    assert out['n_total_years'] == 1
    assert out['sign_match_years'] == 1
    assert out['per_year_lift'] == {2024: 0.05}


def test_rule9_lift_holdout_none_when_absent():
    py_base = {2021: {'r': 0.3}, 2022: {'r': 0.3}}
    py_full = {2021: {'r': 0.4}, 2022: {'r': 0.4}}
    out = rule9_lift(py_base, py_full, r_base=0.3, r_full=0.4,
                     holdout_years=(2024, 2025))
    assert out['holdout_lift'] is None        # holdout years absent
