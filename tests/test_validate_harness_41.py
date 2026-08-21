"""Issue #41 — the role-lag validation harness must keep selection and
holdout disjoint, and use the tested Rule 9 helper."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'scripts' / 'xfp' / 'validate_role_lag_missing.py').read_text(encoding='utf-8')


def test_selection_years_exclude_the_holdout():
    """The winning cell must be picked WITHOUT 2024/2025 in the signal —
    otherwise the reported holdout gain is optimistically biased."""
    assert 'SEL_YEARS' in SRC
    assert 'y not in HOLDOUT_YEARS' in SRC


def test_holdout_reported_for_all_variants_not_just_the_winner():
    assert SRC.count('holdout_r(variant(') >= 1 or "for name in ['A', 'B', 'C']" in SRC.split('strict holdout')[1]


def test_uses_lib_rule9_not_inline_arithmetic():
    assert 'rule9_lift' in SRC
