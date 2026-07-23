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


# ── Slotless-row degrade (caught live 2026-07-20) ────────────────────────────
# get_all_teams() rows carry NO eligible_slots column (gotcha #3). The old
# final branch returned the bare ESPN position tag for such rows — a slotless
# Detmers (ESPN 'RP', 20-of-20 starts, in rp3) came back 'RP', bypassing the
# rp3-membership escalation. These lock the fixed behavior.

def test_slotless_rp_tag_in_rp3_escalates_to_starts():
    """Slotless row + ESPN RP tag + name in rp3 -> decide on real starts (SP)."""
    from plv_clone.utils.name_match import safe_name_key
    row = {'player_name': 'Reid Detmers', 'position': 'RP', 'pro_team': 'LAA'}
    role = detect_pitcher_role(
        row, mlbam_id=672282,
        gs_lookup=lambda pid, season: 'SP',        # 20/20 starts
        rp3_keys=frozenset({safe_name_key('Detmers, Reid')}),
    )
    assert role == 'SP'


def test_slotless_rp_tag_not_in_rp3_stays_rp_no_api():
    """Slotless true reliever: RP tag + not in rp3 -> 'RP', zero API calls."""
    def _boom(pid, season):
        raise AssertionError('gs_lookup must not be called for a true RP')
    row = {'player_name': 'Jhoan Duran', 'position': 'RP', 'pro_team': 'PHI'}
    role = detect_pitcher_role(row, gs_lookup=_boom, rp3_keys=frozenset())
    assert role == 'RP'


def test_slotless_sp_tag_short_circuits():
    """Slotless SP tag -> 'SP' directly (mislabel risk runs RP->SP only)."""
    row = {'player_name': 'Hunter Greene', 'position': 'SP', 'pro_team': 'CIN'}
    def _boom(pid, season):
        raise AssertionError('no API call expected for an SP tag')
    assert detect_pitcher_role(row, gs_lookup=_boom, rp3_keys=frozenset()) == 'SP'
