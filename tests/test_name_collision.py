"""Regression tests for same-last-name player collisions in skill lookups.

Canonical case (2026-06-26): a diagnostic matched pitchers by last-name substring
("Warren") and conflated Will Warren (mlbam 701542, NYY, STARTER) with Austin
Warren (mlbam 681810, NY Mets, RELIEVER), so Austin's relief games corrupted Will's
profile. The fix removed last-name `str.contains` from skill engines in favor of
normalized full-name / mlbam-keyed lookups (resolve_pitcher_id / resolve_batter_id).

These tests lock in:
  1. the fix PATTERN (normalized full-name match does not cross-leak), and
  2. the canonical resolver distinguishes the two Warrens, and
  3. the boom-bust engine filters by mlbam, never by name.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

# The collision-safe normalizer the fixed skill engines use (full name,
# accent-stripped, "Last, First" flipped, apostrophes/periods/hyphens collapsed).
# This file used to carry its OWN copy of the body — which is exactly the
# duplication the tests below exist to prevent, and exactly how Ryan O'Hearn's
# curly apostrophe got mis-keyed on 2026-07-28. The test that locks the fix must
# exercise the shipped function, not a look-alike.
from plv_clone.utils.name_match import safe_name_key as _nm  # noqa: E402


def test_lastname_substring_was_the_bug():
    """Documents the OLD bug: a surname substring matches BOTH Warrens."""
    df = pd.DataFrame({"player_name": ["Warren, Will", "Warren, Austin", "Garcia, Luis"]})
    leaked = df[df["player_name"].str.lower().str.contains("warren", na=False)]
    assert len(leaked) == 2  # the cross-person leak we removed


def test_fullname_match_does_not_cross_leak():
    """The FIX: normalized full-name match resolves to exactly one Warren."""
    df = pd.DataFrame({"player_name": ["Warren, Will", "Warren, Austin"],
                       "pitcher": [701542, 681810]})
    m = df[df["player_name"].apply(_nm) == _nm("Will Warren")]
    assert len(m) == 1
    assert int(m.iloc[0]["pitcher"]) == 701542
    m2 = df[df["player_name"].apply(_nm) == _nm("Austin Warren")]
    assert int(m2.iloc[0]["pitcher"]) == 681810


def test_resolve_pitcher_id_distinguishes_warrens():
    """The canonical resolver (the recommended path) keeps the Warrens separate."""
    from plv_clone.utils.name_match import resolve_pitcher_id
    cache = ROOT / "data" / "research" / "xfp_cache"
    spm_p, rpm_p = cache / "sp_multiyr.csv", cache / "relievers_multiyr_2018_2026.csv"
    if not (spm_p.exists() and rpm_p.exists()):
        pytest.skip("multiyr frames unavailable")
    spm, rpm = pd.read_csv(spm_p), pd.read_csv(rpm_p)
    assert resolve_pitcher_id("Will Warren", team="NYY", role="SP",
                              sp_multiyr=spm, rp_multiyr=rpm) == 701542
    assert resolve_pitcher_id("Austin Warren", team="NYM", role="RP",
                              sp_multiyr=spm, rp_multiyr=rpm) == 681810


def test_resolver_accent_and_suffix_forces_2026_07_20():
    """2026-07-20 QA regression: accent/suffix spellings that live-failed.

    - "Eury Perez" (unaccented) missed the SP cache's "Pérez, Eury" row via
      the accent-SENSITIVE exact match → KNOWN_PITCHER_COLLISIONS force.
    - "Luis Garcia Jr." (unaccented Jr.) fell through the collision gate
      (only the accented key existed) → unaccented KNOWN_COLLISIONS keys.
    These hit the collision tables before any cache read, so no fixtures.
    """
    from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
    # Eury Pérez, MIA SP — both hinted forms and the hintless single-
    # candidate force resolve to 691587 (NOT the retired OF 516811).
    assert resolve_pitcher_id("Eury Perez", team="MIA") == 691587
    assert resolve_pitcher_id("Perez, Eury", role="SP") == 691587
    assert resolve_pitcher_id("Eury Perez") == 691587       # hintless force
    assert resolve_pitcher_id("Eury Perez", team="NYY") is None  # wrong hint refuses
    # Jose Soriano keeps working, now also hintless (single-candidate force).
    assert resolve_pitcher_id("Jose Soriano", team="LAA") == 667755
    assert resolve_pitcher_id("Jose Soriano") == 667755
    # Luis García Jr., WSH 2B — accented and unaccented, with team hint.
    assert resolve_batter_id("Luis Garcia Jr.", team="WSH") == 671277
    assert resolve_batter_id("Luis Garcia Jr", team="WSH") == 671277
    assert resolve_batter_id("Luis García Jr.", team="WSH") == 671277
    # Multi-candidate Garcias still refuse to guess without a hint.
    assert resolve_batter_id("Luis Garcia Jr.") is None
    # Multi-candidate collisions (Muncy) still refuse hintless too — the
    # single-candidate fallthrough must not weaken the Muncy guard.
    assert resolve_batter_id("Max Muncy") is None
    assert resolve_batter_id("Max Muncy", team="LAD") == 571970


def test_collision_gate_team_hint_is_canonical_and_authoritative_2026_07_29():
    """2026-07-29 live regression: the FA replacement-pool board surfaced the
    Oakland Max Muncy carrying the LAD Muncy's projection.

    ``resolve_batter_id("Max Muncy", team="Oak", position="3B")`` returned
    571970 (LAD, rh3 #60, 1.97 FP/g, 62.0 RoS) instead of 691777 (ATH, rh3
    #436, 1.27 FP/g, signal=drop) — so a drop-signal bat ranked 4th of ~490
    candidates as an "upgrade". Two independent faults:

      1. the gate compared raw ``.upper()`` team strings, so ESPN's "Oak"
         matched neither "LAD" nor "ATH" (``team_key`` aliases OAK→ATH);
      2. it then FELL THROUGH to the position hint, where "3B" matched the
         LAD entry — the silent guess the docstring promises never happens.
    """
    from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id

    # (1) ESPN's live team spelling now resolves, with or without a position.
    assert resolve_batter_id("Max Muncy", team="Oak") == 691777
    assert resolve_batter_id("Max Muncy", team="Oak", position="3B") == 691777
    assert resolve_batter_id("Max Muncy", team="OAK", position="C") == 691777
    assert resolve_batter_id("Max Muncy", team="ATH") == 691777
    # The LAD side is unaffected, and a position hint can't override team.
    assert resolve_batter_id("Max Muncy", team="LAD") == 571970
    assert resolve_batter_id("Max Muncy", team="LAD", position="SS") == 571970

    # (2) A team hint that matches NO candidate refuses — it must not fall
    # through to position and hand back an arbitrary player.
    assert resolve_batter_id("Max Muncy", team="NYY", position="3B") is None
    assert resolve_batter_id("Max Muncy", team="NYY") is None

    # (3) Both Muncys are listed at 3B now, so position alone is ambiguous
    # and must refuse rather than pick the first match.
    assert resolve_batter_id("Max Muncy", position="3B") is None
    assert resolve_batter_id("Max Muncy") is None
    # A position unique to one of them still resolves.
    assert resolve_batter_id("Max Muncy", position="DH") == 571970

    # (4) Same fault existed pitcher-side: "SDP" missed both Logan Allens on
    # the raw compare, then role="SP" matched BOTH and returned the CLE id.
    assert resolve_pitcher_id("Logan Allen", team="SDP") == 663531
    assert resolve_pitcher_id("Logan Allen", team="SD") == 663531
    assert resolve_pitcher_id("Logan Allen", team="CLE") == 671106
    assert resolve_pitcher_id("Logan Allen", role="SP") is None   # ambiguous
    assert resolve_pitcher_id("Logan Allen", team="NYY", role="SP") is None
    assert resolve_pitcher_id("Logan Allen") is None


def test_accented_pitcher_cache_spelling_still_resolves():
    """The accented spelling resolves via the cache path (the force entries
    must not shadow it)."""
    from plv_clone.utils.name_match import resolve_pitcher_id
    cache = ROOT / "data" / "research" / "xfp_cache"
    spm_p = cache / "sp_multiyr_2015_2025.csv"
    rpm_p = cache / "relievers_multiyr_2018_2026.csv"
    if not (spm_p.exists() and rpm_p.exists()):
        pytest.skip("multiyr frames unavailable")
    spm, rpm = pd.read_csv(spm_p), pd.read_csv(rpm_p)
    assert resolve_pitcher_id("Eury Pérez", team="MIA",
                              sp_multiyr=spm, rp_multiyr=rpm) == 691587


def test_fa_join_does_not_inherit_star_row_by_surname_similarity():
    """2026-07-19 regression: the roster-audit FA board joined the FA pool onto
    projections with fuzzy_match_name (difflib 0.78), so FA prospect 'Hayden
    Alvarez' inherited Yordan Alvarez's rh3 rank-#2 row and 'Bryce Mayer'
    (not in rp3 at all) inherited Bryce Miller's. safe_lookup must return
    None for near-miss names instead of a distance-based guess."""
    from plv_clone.utils.name_match import (
        build_safe_name_index, safe_lookup, fuzzy_match_name)
    model = pd.DataFrame({
        "player_name": ["Yordan Alvarez", "Bryce Miller", "Luis Garcia"],
        "rank": [2, 12, 40]})
    # Document the OLD bug: fuzzy really did cross-match these.
    assert fuzzy_match_name("Hayden Alvarez", model["player_name"].tolist()) == "Yordan Alvarez"
    assert fuzzy_match_name("Bryce Mayer", model["player_name"].tolist()) == "Bryce Miller"
    # The FIX: no inheritance, ever.
    idx = build_safe_name_index(model["player_name"])
    assert safe_lookup("Hayden Alvarez", idx) is None
    assert safe_lookup("Bryce Mayer", idx) is None
    assert safe_lookup("Luis Guanipa", idx) is None
    # Exact names still resolve across format drift: 'Last, First', accents,
    # punctuation.
    assert safe_lookup("Alvarez, Yordan", idx) == 0
    assert safe_lookup("Yordan Álvarez", idx) == 0


def test_safe_lookup_same_name_collision_needs_team():
    """Both Max Muncys appear in rh3 as the identical string — the join must
    refuse to guess without a team hint and resolve with one (incl. ESPN vs
    Statcast team-code aliases)."""
    from plv_clone.utils.name_match import build_safe_name_index, safe_lookup
    model = pd.DataFrame({"player_name": ["Max Muncy", "Max Muncy"],
                          "team": ["LAD", "ATH"]})
    idx = build_safe_name_index(model["player_name"], model["team"])
    assert safe_lookup("Max Muncy", idx) is None          # refuse to guess
    assert safe_lookup("Max Muncy", idx, team="LAD") == 0
    assert safe_lookup("Max Muncy", idx, team="ATH") == 1
    assert safe_lookup("Max Muncy", idx, team="Oak") == 1  # OAK → ATH alias


def test_roster_audit_join_is_not_fuzzy():
    """Lock the wiring: run_roster_audit's projection/FA joins go through the
    collision-safe exact join, never fuzzy_match_name."""
    src = (ROOT / "scripts" / "xfp" / "run_roster_audit.py").read_text(encoding="utf-8")
    assert "fuzzy_match_name" not in src
    assert "safe_lookup" in src and "build_safe_name_index" in src


def test_boom_bust_engine_keys_by_mlbam():
    """The /boom-bust-history engine must filter the boxscore store by mlbam id,
    never by player_name — so a same-name player can never leak into a profile."""
    src = (ROOT / "scripts" / "xfp" / "lib" / "boom_bust.py").read_text(encoding="utf-8")
    assert 'df["mlbam_id"] == int(mlbam)' in src
    assert "people/{mlbam}" in src or "people/" in src
    # and it must NOT filter the box by player_name substring
    assert "player_name'].str.contains" not in src
    assert 'player_name"].str.contains' not in src


# ── Mid-season trades + accent drift starved the live scoreboard (2026-08-07) ──
# live_monitor could not resolve José Soriano or Luis García Jr. and SKIPPED
# both. A skipped player scores 0 and silently vanishes from the daily total,
# which then reads as authoritative — the printed Ligers total was understated
# by ~8 FP. Three distinct faults, locked below.

def test_unaccented_espn_spelling_resolves_via_cache_2026_08_07():
    """Fault 1: the resolvers promised accent normalization in their docstrings
    but compared raw strings. ESPN sends ascii "Jose Soriano"; the SP cache
    holds "Soriano, José"; the `==` compare missed and returned None."""
    from plv_clone.utils.name_match import resolve_pitcher_id, resolve_batter_id

    for spelling in ("Jose Soriano", "José Soriano", "Soriano, Jose",
                     "Soriano, José"):
        assert resolve_pitcher_id(spelling, team="TOR", role="SP") == 667755, spelling
    # Hitter side shares the lookup; the accented cache spelling still resolves
    # from the unaccented ESPN one.
    assert resolve_batter_id("Jose Ramirez", team="CLE") == \
        resolve_batter_id("José Ramírez", team="CLE")


def test_traded_pitcher_resolves_on_new_team_2026_08_07():
    """Fault 2a. Team is authoritative, so a candidate list pinned to last
    year's team matches ZERO on the live hint and returns None — which reads
    downstream as "no such player". Soriano moved LAA->TOR and vanished from
    the live score.

    Fixed by listing BOTH teams for the same id, NOT by short-circuiting
    single-candidate entries past the team gate: that would resolve a wrong
    hint too, breaking the refuse-on-wrong-hint contract asserted in
    ``test_resolver_accent_and_suffix_forces_2026_07_20`` (line 80). The
    guard below locks that distinction in."""
    from plv_clone.utils.name_match import resolve_pitcher_id

    assert resolve_pitcher_id("Jose Soriano", team="TOR", role="SP") == 667755
    assert resolve_pitcher_id("Jose Soriano", team="LAA", role="SP") == 667755
    assert resolve_pitcher_id("Soriano, Jose", team="TOR") == 667755
    assert resolve_pitcher_id("Jose Soriano") == 667755          # hintless force
    # A team he has never played for still REFUSES — adding the trade row must
    # not turn the team gate into a no-op for single-candidate entries.
    assert resolve_pitcher_id("Jose Soriano", team="NYY") is None
    assert resolve_pitcher_id("Eury Perez", team="NYY") is None


def test_traded_collision_member_resolves_on_new_team_2026_08_07():
    """Fault 2b. Luis García Jr. (671277) is a MULTI-candidate name, so the
    single-id shortcut above cannot apply and team stays authoritative. He moved
    WSH->NYY, so the live team hint matched no candidate. Both teams must map to
    the same id; the other Garcías are unaffected."""
    from plv_clone.utils.name_match import resolve_batter_id

    for spelling in ("Luis Garcia Jr.", "Luis García Jr.", "Luis Garcia Jr"):
        assert resolve_batter_id(spelling, team="NYY") == 671277, spelling
        assert resolve_batter_id(spelling, team="WSH") == 671277, spelling
    assert resolve_batter_id("Luis Garcia", team="HOU") == 677651
    assert resolve_batter_id("Luis Garcia", team="PHI") == 472610


def test_trade_fix_does_not_weaken_the_refuse_to_guess_contract():
    """The guards that matter most. Widening name matching and short-circuiting
    single-candidate entries must NOT reintroduce a silent mispick: every name
    below has >1 distinct id, so team stays authoritative and an unmatched or
    absent hint must still refuse."""
    from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id

    # Muncy — the canonical mispick. Unchanged in both directions.
    assert resolve_batter_id("Max Muncy", team="Oak", position="3B") == 691777
    assert resolve_batter_id("Max Muncy", team="LAD") == 571970
    assert resolve_batter_id("Max Muncy", team="NYY", position="3B") is None
    assert resolve_batter_id("Max Muncy") is None
    # García is multi-candidate: hintless must still refuse despite the new row.
    assert resolve_batter_id("Luis Garcia") is None
    assert resolve_batter_id("Luis Garcia Jr.") is None
    assert resolve_batter_id("Luis Garcia Jr.", team="SEA") is None
    # Warrens differ on FIRST name, so suffix/accent folding must not merge them.
    assert resolve_pitcher_id("Will Warren", team="NYY", role="SP") == 701542
    assert resolve_pitcher_id("Austin Warren", team="NYM", role="RP") == 681810
    # Logan Allen stays ambiguous on role alone.
    assert resolve_pitcher_id("Logan Allen", role="SP") is None


def test_suffix_folding_cannot_return_an_arbitrary_player():
    """_normalize folds ' Jr.', so the normalized leg WIDENS the match set and
    could span two real players the collision table doesn't list. The ambiguity
    guard must refuse rather than take .iloc[0] — the exact silent-wrong-player
    failure this module exists to prevent."""
    import pandas as _pd
    from plv_clone.utils.name_match import resolve_batter_id

    multiyr = _pd.DataFrame({
        "player_name": ["Sammy Sosa Jr.", "Sammy Sosa II"],
        "batter": [900001, 900002],
        "team": ["CHC", "BAL"],
        "year": [2026, 2026],
    })
    # No EXACT row for the query, so the normalized leg runs and folds both
    # suffixes to "sammy sosa" — two distinct ids, no usable hint -> refuse.
    assert resolve_batter_id("Sammy Sosa", multiyr=multiyr) is None
    # A team hint that isolates one row still resolves.
    assert resolve_batter_id("Sammy Sosa", team="BAL", multiyr=multiyr) == 900002
    assert resolve_batter_id("Sammy Sosa", team="CHC", multiyr=multiyr) == 900001
    # An EXACT match is unambiguous and must NOT be widened by folding: exact
    # is tried first precisely so a real full-name hit never competes with a
    # suffix-folded near-miss.
    assert resolve_batter_id("Sammy Sosa II", multiyr=multiyr) == 900002


def test_live_monitor_surfaces_unresolved_players():
    """Fault 3: an unresolved player scores 0 and disappears, so the total reads
    'he did nothing' instead of 'we cannot see him'. The module must expose the
    gap list the dashboard reprints beside the scoreboard."""
    import live_monitor

    assert hasattr(live_monitor, "UNRESOLVED"), \
        "live_monitor must track unresolved roster entries"
    assert isinstance(live_monitor.UNRESOLVED, list)
