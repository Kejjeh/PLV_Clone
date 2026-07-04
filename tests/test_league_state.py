"""Behavioral tests for plv_clone.league_state.LeagueState.

Each test names a structural invariant from ADR-0004 or the related
feedback memory files:

  * ``il_slots()`` counts ``lineup_slot=='IL'`` and NOT ``injured==True``
    (`feedback_il_slot_vs_il_status.md`).
  * No ``injured_players`` accessor exists — the absence is the
    enforcement mechanism (ADR-0004).
  * ``available_fa`` has no ``size=`` parameter — the size lives inside
    the method (`feedback_fa_pool_size_cap.md`).
  * ``available_fa`` filters out cross-team-rostered players internally
    (`feedback_pl_rank_not_equal_fa_available.md`).
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pytest

from plv_clone.league_state import LeagueState


# ── Fakes ────────────────────────────────────────────────────────────────

@dataclass
class _FakePlayer:
    name: str
    playerId: int = 1
    position: str = ""
    proTeam: str = ""
    eligibleSlots: list[str] = field(default_factory=list)
    lineupSlot: str = "BE"  # nonempty default so the schema sentinel passes
    injured: bool = False
    injuryStatus: str = ""
    percent_owned: float = 0.0


@dataclass
class _FakeTeam:
    team_id: int
    team_name: str
    owner: str
    roster: list[_FakePlayer]
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: float = 0.0
    points_against: float = 0.0


class _FakeLeague:
    """Minimal stand-in for espn_api.baseball.League."""

    def __init__(self, teams: list[_FakeTeam], free_agents: list[_FakePlayer]):
        self.teams = teams
        self._fas = free_agents
        self.free_agents_size_arg: int | None = None
        self.free_agents_call_count: int = 0

    def free_agents(self, size: int = 50, **_: Any) -> list[_FakePlayer]:
        self.free_agents_size_arg = size
        self.free_agents_call_count += 1
        return list(self._fas)


@pytest.fixture(autouse=True)
def _clean_ttl_cache():
    """Isolate the per-process TTL cache between tests (id() reuse guard)."""
    from plv_clone.league_state import clear_ttl_cache

    clear_ttl_cache()
    yield
    clear_ttl_cache()


# ── Tests ────────────────────────────────────────────────────────────────

def test_il_slots_counts_lineup_slot_not_injured_flag():
    """The load-bearing distinction from ADR-0004 and CONTEXT.md.

    Roster has TWO injured players:
      - Player A: ``lineup_slot=='IL'`` and ``injured==True``
      - Player B: ``lineup_slot=='OF'`` and ``injured==True`` (the
        Langford pattern: hurt but still in the starting slot)

    ``il_slots()`` must return 1, not 2. Counting ``injured==True`` is
    the bug.
    """
    roster = pd.DataFrame([
        {"player_name": "A", "lineup_slot": "IL", "injured": True},
        {"player_name": "B", "lineup_slot": "OF", "injured": True},
        {"player_name": "C", "lineup_slot": "1B", "injured": False},
    ])

    state = LeagueState(league=object())  # league handle unused in this path
    assert state.il_slots(roster) == 1


def test_il_slots_free_uses_il_slot_count_constant():
    roster = pd.DataFrame([
        {"player_name": "A", "lineup_slot": "IL", "injured": True},
        {"player_name": "B", "lineup_slot": "IL", "injured": True},
    ])
    state = LeagueState(league=object())
    # IL_SLOT_COUNT==3, 2 used → 1 free
    assert state.il_slots_free(roster) == 1


def test_league_state_has_no_injured_players_attribute():
    """ADR-0004 — the absence is the enforcement.

    Future contributors who add ``injured_players()`` back as a small
    helper will trip this regression.
    """
    state = LeagueState(league=object())
    assert not hasattr(state, "injured_players"), (
        "LeagueState must NOT expose injured_players — see ADR-0004. "
        "Callers who need the injury flag read my_roster() and filter "
        "injured==True themselves."
    )


def test_available_fa_signature_has_no_size_parameter():
    """`feedback_fa_pool_size_cap.md` — size=2000 lives inside the method.

    A ``size=`` parameter on the public API invites the silent-truncation
    bug. The default is internal and not a caller knob.
    """
    sig = inspect.signature(LeagueState.available_fa)
    assert "size" not in sig.parameters, (
        "LeagueState.available_fa must NOT accept size= — the default "
        "of 2000 is an internal invariant, not a caller knob. See "
        "feedback_fa_pool_size_cap.md."
    )


def test_available_fa_pulls_full_pool_internally():
    """Even without size= in the signature, the method must pull 2000."""
    fa = _FakePlayer(name="Free Agent X", position="OF")
    team = _FakeTeam(team_id=1, team_name="My Ligers", owner="josh", roster=[])
    league = _FakeLeague(teams=[team], free_agents=[fa])

    state = LeagueState(league=league)
    state.available_fa()

    assert league.free_agents_size_arg == 2000, (
        "available_fa() must pull the unfiltered size=2000 pool — per-"
        "position size=N calls silently truncate low-owned candidates."
    )


def test_available_fa_drops_cross_team_rostered_players():
    """`feedback_pl_rank_not_equal_fa_available.md` — the Connelly Early bug.

    ESPN's FA endpoint can lag and surface "available" players who are
    actually rostered. ``available_fa()`` must filter them out
    internally — the cross-team check is not a caller obligation.
    """
    # Connelly Early appears in the FA pool…
    fa_pool = [
        _FakePlayer(name="Connelly Early", position="SP"),
        _FakePlayer(name="True FA", position="SP"),
    ]
    # …but is also on another team's roster.
    other_team = _FakeTeam(
        team_id=2,
        team_name="Frendy's Fantastic Team",
        owner="frendy",
        roster=[_FakePlayer(name="Connelly Early", position="SP")],
    )
    my_team = _FakeTeam(
        team_id=1, team_name="New York Ligers", owner="josh", roster=[]
    )
    league = _FakeLeague(teams=[my_team, other_team], free_agents=fa_pool)

    state = LeagueState(league=league)
    fa_df = state.available_fa()

    names = set(fa_df["player_name"].tolist())
    assert "Connelly Early" not in names, (
        "available_fa() must drop players who are rostered on another "
        "team — that's the Connelly Early bug class."
    )
    assert "True FA" in names


def test_available_fa_position_filter_works():
    fa_pool = [
        _FakePlayer(name="Outfielder", position="OF"),
        _FakePlayer(name="Pitcher", position="SP"),
    ]
    my_team = _FakeTeam(
        team_id=1, team_name="New York Ligers", owner="josh", roster=[]
    )
    league = _FakeLeague(teams=[my_team], free_agents=fa_pool)

    state = LeagueState(league=league)
    sps = state.available_fa(position="SP")

    assert sps["player_name"].tolist() == ["Pitcher"]


def test_my_roster_exposes_injured_flag_for_caller_filtering():
    """Per ADR-0004 — callers who need injury status read my_roster()
    and filter themselves. This test just confirms the column exists."""
    injured_player = _FakePlayer(
        name="Hurt Hitter",
        position="OF",
        lineupSlot="OF",
        injured=True,
        injuryStatus="DAY_TO_DAY",
    )
    healthy_player = _FakePlayer(
        name="Healthy Hitter",
        position="1B",
        lineupSlot="1B",
        injured=False,
    )
    my_team = _FakeTeam(
        team_id=1,
        team_name="New York Ligers",
        owner="josh",
        roster=[injured_player, healthy_player],
    )
    league = _FakeLeague(teams=[my_team], free_agents=[])

    state = LeagueState(league=league)
    roster = state.my_roster()

    assert "injured" in roster.columns
    # Caller-side filter, as documented:
    injured_subset = roster[roster["injured"]]
    assert injured_subset["player_name"].tolist() == ["Hurt Hitter"]


def test_available_fa_meaningful_drops_zero_pa_callup():
    """A veteran (3000 career PA) is kept; a zero-PA callup is dropped."""
    multiyr = pd.DataFrame([
        {"player_name": "Veteran Vet", "batter": 1, "year": 2024, "pa": 600},
        {"player_name": "Veteran Vet", "batter": 1, "year": 2025, "pa": 650},
        {"player_name": "Veteran Vet", "batter": 1, "year": 2026, "pa": 50},
        {"player_name": "Zero Callup", "batter": 2, "year": 2026, "pa": 3},
    ])

    fa_pool = [
        _FakePlayer(name="Veteran Vet", position="OF"),
        _FakePlayer(name="Zero Callup", position="OF"),
    ]
    my_team = _FakeTeam(
        team_id=1, team_name="New York Ligers", owner="josh", roster=[]
    )
    league = _FakeLeague(teams=[my_team], free_agents=fa_pool)
    state = LeagueState(league=league)

    df, summary = state.available_fa_meaningful(
        min_2026_pa=100, min_career_pa=300, multiyr=multiyr,
    )

    assert summary["input_n"] == 2
    assert summary["kept"] == 1
    assert summary["dropped_no_pa"] == 1
    assert summary["dropped_unresolved"] == 0
    assert df["player_name"].tolist() == ["Veteran Vet"]


def test_available_fa_meaningful_filters_fewer_than_unfiltered():
    """Filtered count <= unfiltered, and dropped_no_pa is non-zero when
    the pool has zero-PA names."""
    multiyr = pd.DataFrame([
        {"player_name": "Veteran", "batter": 1, "year": 2025, "pa": 500},
        {"player_name": "Veteran", "batter": 1, "year": 2026, "pa": 200},
        {"player_name": "Fringe", "batter": 2, "year": 2026, "pa": 5},
        {"player_name": "Other", "batter": 3, "year": 2026, "pa": 2},
    ])
    fa_pool = [
        _FakePlayer(name="Veteran", position="OF"),
        _FakePlayer(name="Fringe", position="OF"),
        _FakePlayer(name="Other", position="OF"),
    ]
    my_team = _FakeTeam(
        team_id=1, team_name="New York Ligers", owner="josh", roster=[]
    )
    league = _FakeLeague(teams=[my_team], free_agents=fa_pool)
    state = LeagueState(league=league)

    base = state.available_fa()
    df, summary = state.available_fa_meaningful(multiyr=multiyr)

    assert len(df) < len(base)
    assert summary["dropped_no_pa"] > 0


def test_available_fa_meaningful_sp_drops_callup_starter():
    """An SP with 30 career starts is kept; a 1-start callup is dropped."""
    multiyr = pd.DataFrame([
        {"player_name": "Vet SP", "year": 2024, "gs": 30},
        {"player_name": "Vet SP", "year": 2026, "gs": 1},
        {"player_name": "AAA Callup", "year": 2026, "gs": 1},
    ])
    fa_pool = [
        _FakePlayer(name="Vet SP", position="SP"),
        _FakePlayer(name="AAA Callup", position="SP"),
    ]
    my_team = _FakeTeam(
        team_id=1, team_name="New York Ligers", owner="josh", roster=[]
    )
    league = _FakeLeague(teams=[my_team], free_agents=fa_pool)
    state = LeagueState(league=league)

    df, summary = state.available_fa_meaningful_sp(
        min_2026_starts=2, min_career_starts=10, multiyr=multiyr,
    )

    assert summary["kept"] == 1
    assert summary["dropped_no_pa"] == 1
    assert df["player_name"].tolist() == ["Vet SP"]


def test_imports_at_advertised_paths():
    """The two public import paths CONTEXT.md and the task spec promise."""
    from plv_clone.league_state import LeagueState as LS  # noqa: F401
    from plv_clone.utils.name_match import (  # noqa: F401
        fuzzy_match_name,
        merge_with_model,
    )


def test_constants_exposed_for_callers():
    """CONTEXT.md says league_state imports cap_math constants."""
    from plv_clone.league_state import IL_SLOT_COUNT, RP_SLOT_CAP, SP_CAP

    assert SP_CAP == 10
    assert RP_SLOT_CAP == 4
    assert IL_SLOT_COUNT == 3


# ── TTL cache (2026-07-04 audit) ─────────────────────────────────────────

def _one_team_league(fa_names=("FA One",)):
    my_team = _FakeTeam(
        team_id=1,
        team_name="New York Ligers",
        owner="josh",
        roster=[_FakePlayer(name="Rostered Guy", playerId=7, position="OF")],
    )
    fas = [_FakePlayer(name=n, position="SP") for n in fa_names]
    return _FakeLeague(teams=[my_team], free_agents=fas)


def test_ttl_cache_dedups_fa_pool_pull():
    """Two available_fa() calls within TTL → ONE league.free_agents() hit,
    even across different position filters (the run_roster_audit pattern)."""
    league = _one_team_league()
    state = LeagueState(league=league)

    a = state.available_fa()
    b = state.available_fa(position="SP")

    assert league.free_agents_call_count == 1
    assert not a.empty and not b.empty


def test_ttl_cache_expiry_refetches(monkeypatch):
    """An entry older than the TTL is a miss → second roundtrip."""
    import plv_clone.league_state as ls

    league = _one_team_league()
    state = LeagueState(league=league)
    state.available_fa()

    # Age every cache entry past the TTL.
    for k, (ts, val) in list(ls._TTL_CACHE.items()):
        ls._TTL_CACHE[k] = (ts - ls.CACHE_TTL_SECONDS - 1, val)

    state.available_fa()
    assert league.free_agents_call_count == 2


def test_fresh_param_bypasses_cache():
    league = _one_team_league()
    state = LeagueState(league=league)
    state.available_fa()
    state.available_fa(fresh=True)
    assert league.free_agents_call_count == 2


def test_ttl_cache_returns_defensive_copy():
    """Mutating a returned frame must not poison later cache hits."""
    league = _one_team_league()
    state = LeagueState(league=league)
    first = state.all_teams()
    first["player_name"] = "MUTATED"
    second = state.all_teams()
    assert second["player_name"].tolist() == ["Rostered Guy"]


# ── all_teams schema superset (2026-07-04 audit) ─────────────────────────

def test_all_teams_is_schema_superset_of_espn_connector():
    """all_teams() must carry every column app.espn_connector.get_all_teams()
    returns, so importers can migrate without column surprises."""
    espn_connector_cols = {
        "team_name", "owner", "team_id", "player_name", "player_id",
        "position", "pro_team", "lineup_slot", "injured", "injury_status",
    }
    league = _one_team_league()
    state = LeagueState(league=league)
    df = state.all_teams()
    missing = espn_connector_cols - set(df.columns)
    assert not missing, f"all_teams() missing columns: {missing}"
    row = df.iloc[0]
    assert row["player_id"] == 7
    assert row["lineup_slot"] == "BE"
    assert row["injured"] is False or row["injured"] == False  # noqa: E712
    assert row["injury_status"] == ""


# ── espn-api schema-drift sentinel (2026-07-04 audit) ────────────────────

def test_sentinel_trips_on_all_empty_lineup_slots():
    my_team = _FakeTeam(
        team_id=1, team_name="New York Ligers", owner="josh",
        roster=[
            _FakePlayer(name="A", playerId=1, lineupSlot=""),
            _FakePlayer(name="B", playerId=2, lineupSlot=""),
        ],
    )
    state = LeagueState(league=_FakeLeague(teams=[my_team], free_agents=[]))
    with pytest.raises(RuntimeError, match="espn-api schema drift"):
        state.all_teams()


def test_sentinel_trips_on_null_player_ids():
    roster = [
        _FakePlayer(name=f"P{i}", playerId=None, lineupSlot="BE")
        for i in range(9)
    ] + [_FakePlayer(name="OK", playerId=5, lineupSlot="BE")]
    my_team = _FakeTeam(
        team_id=1, team_name="New York Ligers", owner="josh", roster=roster,
    )
    state = LeagueState(league=_FakeLeague(teams=[my_team], free_agents=[]))
    with pytest.raises(RuntimeError, match="espn-api schema drift"):
        state.my_roster()


def test_sentinel_passes_on_healthy_schema():
    league = _one_team_league()
    state = LeagueState(league=league)
    assert not state.all_teams().empty
    assert not state.my_roster().empty


# ── name_match utility tests ─────────────────────────────────────────────

def test_fuzzy_match_name_handles_accents():
    from plv_clone.utils.name_match import fuzzy_match_name

    model_names = ["Jose Soriano", "Ivan Herrera", "Luis Garcia Jr."]
    assert fuzzy_match_name("José Soriano", model_names) == "Jose Soriano"
    assert fuzzy_match_name("Iván Herrera", model_names) == "Ivan Herrera"


def test_fuzzy_match_name_returns_none_below_cutoff():
    from plv_clone.utils.name_match import fuzzy_match_name

    assert fuzzy_match_name("Totally Random", ["Aaron Judge"], cutoff=0.9) is None


def test_merge_with_model_fuzzy_joins_on_player_name():
    from plv_clone.utils.name_match import merge_with_model

    espn = pd.DataFrame([
        {"player_name": "José Soriano", "position": "SP"},
        {"player_name": "Aaron Judge", "position": "OF"},
    ])
    model = pd.DataFrame([
        {"player_name": "Jose Soriano", "xfp_rp3_per_start": 12.5},
        {"player_name": "Aaron Judge", "xfp_rp3_per_start": 7.0},
    ])

    merged = merge_with_model(espn, model)
    # The merge produces a `model_name` column with the matched name and
    # the joined projection column. Verify both rows joined.
    by_match = dict(zip(merged["model_name"], merged["xfp_rp3_per_start"]))
    assert by_match["Jose Soriano"] == pytest.approx(12.5)
    assert by_match["Aaron Judge"] == pytest.approx(7.0)
