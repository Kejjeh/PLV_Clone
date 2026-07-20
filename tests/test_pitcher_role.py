"""Tests for pitcher_role.detect_pitcher_role.

The load-bearing case: a dual-eligible pitcher (SP and RP both in
eligible_slots) whose ESPN .position tag is stale ('RP') but who is actually
starting (Detmers 2026). The module must own resolution and decide on real
gamesStarted WITHOUT the caller passing an id — i.e. detect_pitcher_role(player)
with no mlbam_id must NOT return the stale 'RP' tag.

The gamesStarted source and the name->id resolver are injected so the
dual-eligible path is exercised offline (no MLB Stats API, no CSV).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "xfp"))

from lib.pitcher_role import detect_pitcher_role


class _Player:
    def __init__(self, name, position, eligibleSlots, proTeam=None):
        self.name = name
        self.position = position
        self.eligibleSlots = eligibleSlots
        self.proTeam = proTeam


def test_sp_only_eligible_short_circuits():
    assert detect_pitcher_role(_Player("Ace", "SP", ["SP"])) == "SP"


def test_rp_only_eligible_short_circuits():
    assert detect_pitcher_role(_Player("Closer", "RP", ["RP"])) == "RP"


def test_rp_only_but_in_rp3_escalates_to_gamesstarted():
    """The Jax regression (2026-07). Post-trade, ESPN kept Griffin Jax
    RP-only-eligible for weeks while he made real starts for TB — the RP-only
    branch returned 'RP' without ever consulting gamesStarted, so cap math
    ignored his starts. When the name appears in the rp3 SP-model output
    (= the pipeline has real starts for him), the role must be decided on
    gamesStarted exactly like the dual-eligible path."""
    from plv_clone.utils.name_match import safe_name_key

    jax = _Player("Griffin Jax", "RP", ["P", "RP", "BE", "IL"], proTeam="TB")
    role = detect_pitcher_role(
        jax,
        rp3_keys={safe_name_key("Jax, Griffin")},        # rp3 spelling variant
        id_resolver=lambda name, team: 643377,
        gs_lookup=lambda pid, season: "SP",              # 15 GS / 26 G -> SP
    )
    assert role == "SP"


def test_rp_only_true_reliever_never_touches_resolver():
    """A genuine reliever (not in rp3) must short-circuit to 'RP' with zero
    resolution/API cost — the escalation only fires on rp3 membership."""
    def _boom(*a, **k):
        raise AssertionError("resolver must not be called for a true reliever")

    closer = _Player("Jhoan Duran", "RP", ["P", "RP", "BE", "IL"], proTeam="PHI")
    role = detect_pitcher_role(
        closer, rp3_keys=frozenset(), id_resolver=_boom, gs_lookup=_boom)
    assert role == "RP"


def test_rp_only_in_rp3_but_unresolvable_stays_rp():
    """If the escalation fires but the id can't be resolved, fall back to the
    conservative 'RP' (the slots' own claim), not the position tag."""
    from plv_clone.utils.name_match import safe_name_key

    ghost = _Player("Griffin Jax", "RP", ["P", "RP"], proTeam="TB")
    role = detect_pitcher_role(
        ghost,
        rp3_keys={safe_name_key("Griffin Jax")},
        id_resolver=lambda name, team: None,
    )
    assert role == "RP"


def test_dual_eligible_resolves_to_sp_without_caller_passing_id():
    """The regression. ESPN says position='RP', but dual-eligible + 15 GS = SP.
    No mlbam_id passed — the module must resolve it itself, not use the tag."""
    detmers = _Player("Reid Detmers", "RP", ["SP", "RP"], proTeam="LAA")
    role = detect_pitcher_role(
        detmers,
        id_resolver=lambda name, team: 672282,      # offline: name -> id
        gs_lookup=lambda pid, season: "SP",         # offline: 15 GS -> SP
    )
    assert role == "SP"


def test_dual_eligible_with_explicit_id_still_works():
    detmers = _Player("Reid Detmers", "RP", ["SP", "RP"])
    role = detect_pitcher_role(
        detmers, mlbam_id=672282, gs_lookup=lambda pid, season: "SP"
    )
    assert role == "SP"


def test_dual_eligible_unresolvable_falls_back_to_position_tag():
    """When resolution is exhausted, the ESPN tag is the documented last resort."""
    nobody = _Player("Rookie Nobody", "RP", ["SP", "RP"])
    role = detect_pitcher_role(nobody, id_resolver=lambda name, team: None)
    assert role == "RP"


def test_df_row_input_dual_eligible():
    """Works on a dict/Series row, not just ESPN player objects."""
    row = {"player_name": "Reid Detmers", "position": "RP",
           "eligible_slots": ["SP", "RP"], "pro_team": "LAA"}
    role = detect_pitcher_role(
        row,
        id_resolver=lambda name, team: 672282,
        gs_lookup=lambda pid, season: "SP",
    )
    assert role == "SP"


def test_pandas_series_row_reads_player_name_not_index():
    """Regression (Detmers, 2026-07-03): a pandas Series' ``.name`` attribute is
    its INDEX label (often an int), NOT the player's name. The prior _name_of did
    ``getattr(row, 'name')`` and then ``.strip()``, so a df row with a non-zero
    index crashed with ``'int' object has no attribute 'strip'`` on the dual-
    eligible path — and callers fell back to the stale ESPN position='RP' tag.
    A real pandas Series (not a dict) must read the 'player_name' column, resolve,
    and return 'SP'. This is exactly how the forced-drop planner calls it."""
    import pandas as pd

    df = pd.DataFrame(
        [{"player_name": "Reid Detmers", "position": "RP",
          "eligible_slots": ["P", "RP", "BE", "IL", "SP"], "pro_team": "LAA"}],
        index=[14],  # Series.name == 14 (int) — the trap
    )
    row = df.iloc[0]
    role = detect_pitcher_role(
        row,
        gs_lookup=lambda mid, season: "SP",
        id_resolver=lambda name, team: 12345 if name == "Reid Detmers" else None,
    )
    assert role == "SP"
