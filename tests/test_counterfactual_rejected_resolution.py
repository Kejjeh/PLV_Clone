"""Issue #54, step 2: a counterfactual with no `rejected_mlbam` was unpairable
forever, and looked exactly like one still waiting for its settlement window.

`_settle_counterfactual_one` guarded the rejected-side lookup with `if rej_id:`
and skipped silently when it was absent. The pair could then never close — but
nothing distinguished "permanently unpairable" from "not ripe yet", so the
ledger's 0-pairs number carried no diagnosis.

Measured on disk 2026-08-28: of 3,101 decision records only **10** carry a
counterfactual at all, and 3 of those 10 lack `rejected_mlbam` while 2 of the
3 carry a resolvable name. So name resolution recovers a real slice, and the
3,091 records with no counterfactual are a separate (workflow) problem —
see the issue.

Resolution goes through the collision-safe resolvers on purpose: a wrong
rejected leg grades the DECISION wrong, not merely a number (don't-do #10).
"""
from __future__ import annotations

import pytest

settle = pytest.importorskip("scripts.xfp.settle_decisions")

_rejected_mlbam = settle._rejected_mlbam


def test_an_explicit_id_is_used_as_is():
    assert _rejected_mlbam({"rejected_mlbam": 12345, "rejected_name": "x"}) == 12345


def test_a_name_only_counterfactual_resolves_through_the_bucket_resolver(monkeypatch):
    import plv_clone.utils.name_match as nm

    monkeypatch.setattr(nm, "resolve_batter_id", lambda name, **kw: 111)
    monkeypatch.setattr(nm, "resolve_pitcher_id", lambda name, **kw: 222)

    assert _rejected_mlbam({"rejected_name": "A Hitter", "rejected_bucket": "H"}) == 111
    assert _rejected_mlbam({"rejected_name": "An Arm", "rejected_bucket": "SP"}) == 222
    assert _rejected_mlbam({"rejected_name": "A Closer", "rejected_bucket": "RP"}) == 222


def test_the_pitcher_role_is_passed_through(monkeypatch):
    """A bucket that isn't used is a resolver that can pick the wrong table."""
    import plv_clone.utils.name_match as nm

    seen = {}

    def _fake(name, **kw):
        seen.update(kw)
        return 999

    monkeypatch.setattr(nm, "resolve_pitcher_id", _fake)
    assert _rejected_mlbam({"rejected_name": "X", "rejected_bucket": "RP"}) == 999
    assert seen.get("role") == "RP"


def test_an_unknown_bucket_falls_back_across_both_tables(monkeypatch):
    import plv_clone.utils.name_match as nm

    monkeypatch.setattr(nm, "resolve_batter_id", lambda name, **kw: None)
    monkeypatch.setattr(nm, "resolve_pitcher_id", lambda name, **kw: 777)
    assert _rejected_mlbam({"rejected_name": "Someone"}) == 777


def test_an_unresolvable_name_returns_none_rather_than_a_guess(monkeypatch):
    """None settles the pair UNSETTLEABLE, which is the honest outcome. The one
    thing this must never do is return a same-name player's id."""
    import plv_clone.utils.name_match as nm

    monkeypatch.setattr(nm, "resolve_batter_id", lambda name, **kw: None)
    monkeypatch.setattr(nm, "resolve_pitcher_id", lambda name, **kw: None)
    assert _rejected_mlbam({"rejected_name": "Nobody", "rejected_bucket": "H"}) is None


def test_an_ambiguous_name_is_refused_not_guessed(monkeypatch):
    """The collision-safe resolvers RAISE on ambiguity rather than picking. That
    must surface as None here, never as an exception escaping into settlement
    and never as a silently chosen candidate."""
    import plv_clone.utils.name_match as nm

    def _ambiguous(name, **kw):
        raise ValueError(f"ambiguous name {name!r}")

    monkeypatch.setattr(nm, "resolve_batter_id", _ambiguous)
    monkeypatch.setattr(nm, "resolve_pitcher_id", _ambiguous)
    assert _rejected_mlbam({"rejected_name": "Max Muncy", "rejected_bucket": "H"}) is None


def test_no_name_and_no_id_is_none():
    assert _rejected_mlbam({}) is None
    assert _rejected_mlbam({"rejected_bucket": "H"}) is None
