"""Legality must not depend on what KIND of iterable the roster is.

WHY THIS EXISTS
`_counts` walks the roster twice — once to filter out IL'd players, once for
the total. Its signature said `Iterable[dict]`, so a caller was entitled to
pass a generator, and the second walk then saw an exhausted iterator and
reported `total: 0`.

`total: 0` does not fail loudly. It silently SATISFIES the roster-size check
in `check_swap` (`0 > 29` is False), so an oversized roster is declared legal
and the optimizer is free to recommend an add that cannot be made. Every
caller today passes a list, so this was latent — but a legality module is the
last place a silent pass belongs.

The tests below pin the consequence (an oversized roster stays illegal
whatever the iterable) rather than just the mechanic. (Added 2026-08-27.)
"""
from __future__ import annotations

import pytest

roster_rules = pytest.importorskip("scripts.xfp.lib.roster_rules")

_counts = roster_rules._counts
check_swap = roster_rules.check_swap
ROSTER_TOTAL = roster_rules.ROSTER_TOTAL


def _player(bucket: str, name: str, *, on_il: bool = False) -> dict:
    return {
        "name": name, "mlbam": abs(hash(name)) % 10**6, "bucket": bucket,
        "espn_pos": {"H": "OF", "SP": "SP", "RP": "RP"}[bucket],
        "eligible": {"OF"} if bucket == "H" else set(),
        "on_il": on_il, "injury_status": "",
    }


def _full_roster() -> list[dict]:
    """A legal 29-man roster: 13 H + 5 SP + 4 RP + 4 bench H + 3 IL."""
    r = [_player("H", f"h{i}") for i in range(13)]
    r += [_player("SP", f"sp{i}") for i in range(5)]
    r += [_player("RP", f"rp{i}") for i in range(4)]
    r += [_player("H", f"bench{i}") for i in range(4)]
    r += [_player("SP", f"il{i}", on_il=True) for i in range(3)]
    assert len(r) == ROSTER_TOTAL
    return r


def test_counts_total_is_the_same_for_a_list_and_a_generator():
    roster = _full_roster()
    assert _counts(roster)["total"] == _counts(p for p in roster)["total"]


def test_counts_total_is_not_zero_for_a_generator():
    """The specific regression: an exhausted iterator reported total 0."""
    roster = _full_roster()
    assert _counts(p for p in roster)["total"] == ROSTER_TOTAL


def test_every_count_field_survives_a_generator():
    roster = _full_roster()
    assert _counts(roster) == _counts(p for p in roster)


def test_oversized_roster_is_illegal_when_adding_without_dropping():
    """The consequence the silent zero was hiding."""
    roster = _full_roster()
    problems = check_swap(roster, add=_player("H", "newguy"), drop=None)
    assert any(str(ROSTER_TOTAL) in p for p in problems), (
        f"a 30th player must be rejected on roster size; got {problems!r}"
    )


def test_swap_at_full_roster_stays_legal():
    """The size check must not over-fire: one in, one out is fine at 29."""
    roster = _full_roster()
    problems = check_swap(
        roster, add=_player("H", "newguy"), drop=roster[17]  # a bench-ish hitter
    )
    assert not any("players" in p and str(ROSTER_TOTAL) in p for p in problems), (
        f"an even swap at a full roster must not trip the size rule; got {problems!r}"
    )


def test_all_exports_are_importable():
    """__all__ must not promise a name the module does not define.

    RP_CAP, lineup_capacity_problem and same_player were public but absent from
    __all__ — same_player even carries a comment calling itself a public alias
    while a star-import could not reach it.
    """
    import importlib

    mod = importlib.import_module("scripts.xfp.lib.roster_rules")
    missing = [n for n in mod.__all__ if not hasattr(mod, n)]
    assert not missing, f"__all__ names not defined in the module: {missing}"

    public = {
        n for n in vars(mod)
        if not n.startswith("_")
        and n not in ("annotations", "Iterable", "Mapping", "Optional")
    }
    unexported = sorted(public - set(mod.__all__))
    assert not unexported, (
        f"public name(s) missing from __all__: {unexported}"
    )
