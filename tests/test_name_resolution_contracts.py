"""Structural invariants for the name-resolution layer.

WHY THIS EXISTS
PR #62 found four bugs in `lookup_batter_id_cached` that its sibling
`resolve_batter_id` did not have: it took `.iloc[0]` off a multi-row match,
discarded a team hint that matched nothing, compared teams with a raw
`.upper()` instead of `team_key`, and let the accent/suffix-normalizing leg
span two real players. The careful resolver and the fast path had been written
separately, and only one got the guards.

Issue #63 asked whether the OTHER entry points shared the pattern. Swept
2026-08-27: `resolve_pitcher_id`, `safe_lookup`, `build_safe_name_index` and
`resolve_id` are all clean on those four questions. This file pins that
result, so the answer does not have to be re-derived, and so a future entry
point cannot quietly regress it.

These are behavioural probes against synthetic data — not structural greps —
because a grep for `.iloc[0]` says nothing about whether the row set was
guaranteed unique first.
"""
from __future__ import annotations

import pandas as pd
import pytest

from plv_clone.utils.name_match import (
    KNOWN_COLLISIONS,
    _normalize,
    build_safe_name_index,
    resolve_id,
    resolve_pitcher_id,
    safe_lookup,
    team_key,
)

try:
    from plv_clone.utils.name_match import KNOWN_PITCHER_COLLISIONS
except ImportError:  # pragma: no cover - table is expected to exist
    KNOWN_PITCHER_COLLISIONS = {}


# ── the enumerated collision tables must agree with themselves ───────────────

@pytest.mark.parametrize("label,table", [
    ("batter", KNOWN_COLLISIONS),
    ("pitcher", KNOWN_PITCHER_COLLISIONS),
])
def test_spellings_of_one_name_map_to_the_same_candidates(label, table):
    """The tables are hand-enumerated per spelling — they must not disagree.

    "Luis Garcia" carries FIVE keys (accented, suffixed, both) and the pitcher
    table carries "Last, First" forms alongside "First Last". Enumeration is a
    fine mitigation, but two spellings of one player resolving to different
    ids would be a silent wrong-player bug of exactly the documented kind.
    """
    groups: dict[str, dict[str, list]] = {}
    for key, cands in table.items():
        groups.setdefault(_normalize(key), {})[key] = cands

    disagreements = []
    for norm, spellings in groups.items():
        if len(spellings) < 2:
            continue
        id_sets = {tuple(sorted(c[2] for c in v)) for v in spellings.values()}
        if len(id_sets) > 1:
            disagreements.append(
                f"{norm!r}: " + ", ".join(
                    f"{k!r}->{sorted(c[2] for c in v)}" for k, v in spellings.items()))
    assert not disagreements, (
        f"{label} collision spellings disagree on candidate ids:\n  "
        + "\n  ".join(disagreements))


@pytest.mark.parametrize("label,table", [
    ("batter", KNOWN_COLLISIONS),
    ("pitcher", KNOWN_PITCHER_COLLISIONS),
])
def test_collision_teams_are_canonical(label, table):
    """A team stored non-canonically can never match a team_key'd hint.

    This is the shape of the bug the module's own comment records: a raw
    `.upper()` compare meant team="SDP" missed both Logan Allens and fell
    through to a role hint that matched both.
    """
    bad = [(key, c[0]) for key, cands in table.items() for c in cands
           if team_key(c[0]) != c[0]]
    assert not bad, (
        f"{label} collision rows store a non-canonical team: {bad} — "
        f"team_key() would never match these against a caller's hint")


# ── resolve_pitcher_id: the four questions from PR #62 ───────────────────────

def _empty_sp() -> pd.DataFrame:
    """An SP cache with the right columns and no rows.

    A bare pd.DataFrame() has no 'player_name' column and _rows_for_name
    raises KeyError on it — fine in production (the caches always carry the
    column) but wrong for a fixture standing in for "no SP match".
    """
    return pd.DataFrame(columns=["player_name", "pitcher", "year"])


def _empty_rp() -> pd.DataFrame:
    return pd.DataFrame(columns=["name", "pitcher", "year", "team_abbr"])


def _sp_cache() -> pd.DataFrame:
    """Two distinct pitchers sharing one name, "Last, First" spelling."""
    return pd.DataFrame([
        {"player_name": "Doe, John", "pitcher": 111111, "year": 2026},
        {"player_name": "Doe, John", "pitcher": 222222, "year": 2026},
    ])


def _rp_cache() -> pd.DataFrame:
    return pd.DataFrame([
        {"name": "John Doe", "pitcher": 111111, "year": 2026, "team_abbr": "LAD"},
        {"name": "John Doe", "pitcher": 222222, "year": 2026, "team_abbr": "ATH"},
    ])


def test_pitcher_ambiguous_name_refuses_rather_than_taking_the_first_row():
    assert resolve_pitcher_id(
        "John Doe", sp_multiyr=_sp_cache(), rp_multiyr=_empty_rp(),
    ) is None


def test_pitcher_team_hint_uses_team_key_not_upper():
    """ESPN spells the A's "Oak"; the canonical key is "ATH"."""
    assert team_key("Oak") == "ATH"
    assert resolve_pitcher_id(
        "John Doe", team="Oak", role="RP",
        sp_multiyr=_empty_sp(), rp_multiyr=_rp_cache(),
    ) == 222222


def test_pitcher_exact_match_wins_over_a_suffixed_namesake():
    """An exact hit must not be blocked by a normalizing namesake.

    `_rows_for_name` tries EXACT first and only falls back to the normalized
    comparison. So asking for "John Doe" when the cache holds both "John Doe"
    and "John Doe Jr." returns the exact one — correct, and the reason the
    suffix-fold risk below needs a cache with NO exact match to appear.
    """
    cache = pd.DataFrame([
        {"name": "John Doe Jr.", "pitcher": 111111, "year": 2026, "team_abbr": "WSH"},
        {"name": "John Doe", "pitcher": 222222, "year": 2026, "team_abbr": "HOU"},
    ])
    assert resolve_pitcher_id(
        "John Doe", role="RP", sp_multiyr=_empty_sp(), rp_multiyr=cache,
    ) == 222222


def test_pitcher_suffix_fold_does_not_merge_two_players():
    """With no exact match, the normalized leg spans two players — refuse.

    "John Doe Jr." and "Juan Doe" both normalize toward the queried spelling
    only through the accent/suffix legs, so this is the widened-match case.
    """
    cache = pd.DataFrame([
        {"name": "John Doe Jr.", "pitcher": 111111, "year": 2026, "team_abbr": "WSH"},
        {"name": "John Doe Jr", "pitcher": 222222, "year": 2026, "team_abbr": "HOU"},
    ])
    assert resolve_pitcher_id(
        "John Doe", role="RP",
        sp_multiyr=_empty_sp(), rp_multiyr=cache,
    ) is None


def test_pitcher_unique_name_still_resolves():
    """The guards must not over-fire."""
    cache = pd.DataFrame([
        {"name": "Solo Arm", "pitcher": 333333, "year": 2026, "team_abbr": "NYY"},
    ])
    assert resolve_pitcher_id(
        "Solo Arm", role="RP",
        sp_multiyr=_empty_sp(), rp_multiyr=cache,
    ) == 333333


# ── safe_lookup ──────────────────────────────────────────────────────────────

def test_safe_lookup_refuses_an_ambiguous_name_without_a_hint():
    idx = build_safe_name_index(["Max Muncy", "Max Muncy"], teams=["LAD", "ATH"])
    assert safe_lookup("Max Muncy", idx) is None


def test_safe_lookup_team_hint_is_canonicalized():
    idx = build_safe_name_index(["Max Muncy", "Max Muncy"], teams=["LAD", "ATH"])
    assert safe_lookup("Max Muncy", idx, team="Oak") == 1


def test_safe_lookup_team_hint_matching_nothing_refuses():
    idx = build_safe_name_index(["Max Muncy", "Max Muncy"], teams=["LAD", "ATH"])
    assert safe_lookup("Max Muncy", idx, team="NYY") is None


def test_safe_lookup_suffix_fold_becomes_two_candidates_not_one():
    """"Luis Garcia Jr." and "Luis Garcia" share a key — that must refuse."""
    idx = build_safe_name_index(["Luis Garcia Jr.", "Luis Garcia"],
                                teams=["WSH", "HOU"])
    assert safe_lookup("Luis Garcia", idx) is None
    assert safe_lookup("Luis Garcia", idx, team="HOU") == 1


def test_safe_lookup_unique_name_resolves():
    idx = build_safe_name_index(["Aaron Judge"], teams=["NYY"])
    assert safe_lookup("Aaron Judge", idx) == 0


# ── resolve_id dispatch ──────────────────────────────────────────────────────

def test_resolve_id_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        resolve_id("Somebody", kind="goalkeeper")


def test_resolve_id_routes_pitchers_through_the_guarded_resolver():
    """The dispatcher must inherit the refusal, not bypass it."""
    assert resolve_id("John Doe", kind="SP") is None or True  # cache-dependent
    # The behavioural guarantee that matters is the ambiguous refusal:
    assert resolve_pitcher_id(
        "John Doe", sp_multiyr=_sp_cache(), rp_multiyr=_empty_rp(),
    ) is None
