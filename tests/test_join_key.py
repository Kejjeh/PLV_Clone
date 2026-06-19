"""Tests for name_match.join_key — the order-independent dict join key."""
from plv_clone.utils.name_match import join_key


def test_order_independent():
    assert join_key("Kyle Schwarber") == join_key("Schwarber, Kyle")
    assert join_key("Kyle Schwarber") == "kyleschwarber"


def test_accent_stripping():
    assert join_key("José Ramírez") == join_key("Jose Ramirez")


def test_non_alpha_dropped():
    assert join_key("Ronald Acuña Jr.") == join_key("Acuna, Ronald Jr")


def test_non_string_safe():
    assert join_key(None) == ""
    assert join_key(12345) == ""   # digits aren't [a-z] tokens → empty key
