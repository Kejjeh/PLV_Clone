"""The FA leak filter must match on identity, not on a name string.

WHY THIS EXISTS
`LeagueState.available_fa` cross-references the FA pool against every team's
roster and drops anyone already rostered. That filter exists *because* ESPN's
free-agent endpoint is unreliable — it lags and surfaces players another team
already grabbed (the Connelly Early case; the Julio Rodriguez leak of
2026-06-04, which `build_fa_snapshot` and `build_triangulate_universe` both
carry their own warnings about).

It compared `player_name` strings. The two ESPN endpoints do not always agree
on a spelling: ascii "Jose Soriano" in one, "José Soriano" in the other — the
same drift that made `live_monitor` drop him from the live scoreboard entirely
on 2026-08-07, and the reason `name_match` carries RESOLUTION-FORCE entries
for him and Eury Pérez.

So a leak filter whose whole job is to compensate for an unreliable upstream
was itself relying on that upstream being consistent. `all_teams()` has always
carried `player_id`; the FA side did not capture it. Now it does, and the id
leg runs first. (Added 2026-08-27.)
"""
from __future__ import annotations

import pandas as pd
import pytest

from plv_clone.league_state import LeagueState


class _FakePlayer:
    def __init__(self, name, pid, position="SP", team="LAA"):
        self.name = name
        self.playerId = pid
        self.position = position
        self.proTeam = team
        self.percent_owned = 12.3
        self.injured = False
        self.injuryStatus = "ACTIVE"


class _FakeLeague:
    def __init__(self, fas):
        self._fas = fas

    def free_agents(self, size=None, **kw):
        return self._fas


@pytest.fixture
def state(monkeypatch):
    """A LeagueState whose league + all_teams are injected."""
    ls = LeagueState()
    fas = [
        _FakePlayer("Jose Soriano", 667755),      # ascii on the FA endpoint
        _FakePlayer("Genuine FA", 999999),
        _FakePlayer("Renamed Guy", 555555),
    ]
    monkeypatch.setattr(ls, "_get_league", lambda: _FakeLeague(fas))
    rostered = pd.DataFrame([
        # accented on the roster endpoint — same player, different spelling
        {"player_name": "José Soriano", "player_id": 667755},
        # id missing upstream; only the name leg can catch this one
        {"player_name": "Renamed Guy", "player_id": None},
    ])
    monkeypatch.setattr(ls, "all_teams", lambda **kw: rostered)
    # defeat the per-process raw-pool memo between tests
    monkeypatch.setattr("plv_clone.league_state._cache_get", lambda *a, **k: None)
    monkeypatch.setattr("plv_clone.league_state._cache_put", lambda *a, **k: None)
    return ls


def test_accent_drift_does_not_leak_a_rostered_player(state):
    """The headline case: same id, two spellings."""
    fa = state.available_fa()
    assert "Jose Soriano" not in set(fa["player_name"]), (
        "a rostered player leaked into the FA pool because the two ESPN "
        "endpoints spelled him differently"
    )


def test_the_name_leg_still_runs_when_an_id_is_missing(state):
    """Both legs must run — an id can be absent on either side."""
    fa = state.available_fa()
    assert "Renamed Guy" not in set(fa["player_name"])


def test_a_genuine_free_agent_survives(state):
    """The filter must not over-fire and empty the pool."""
    fa = state.available_fa()
    assert "Genuine FA" in set(fa["player_name"])


def test_player_id_is_exposed_on_the_fa_frame(state):
    """Downstream callers get identity, not just a name."""
    fa = state.available_fa()
    assert "player_id" in fa.columns
    assert int(fa.loc[fa["player_name"] == "Genuine FA", "player_id"].iloc[0]) == 999999


def test_schema_is_still_a_superset_of_the_legacy_frame(state):
    """available_fa documents itself as a superset — keep that true."""
    fa = state.available_fa()
    legacy = {"player_name", "position", "pro_team", "percent_owned",
              "injured", "injury_status"}
    assert legacy <= set(fa.columns)


def test_duplicate_ids_disable_the_id_leg_rather_than_emptying_the_pool(monkeypatch):
    """An id column with repeats is not an identity column.

    A shared sentinel id would make the id filter match every free agent and
    return an EMPTY pool — "no free agents available" — which is a far worse
    failure than the leak this filter guards against. Both sides are checked
    for uniqueness; duplicates fall back to the name leg.
    """
    ls = LeagueState()
    fas = [
        _FakePlayer("Rostered Guy", 1),
        _FakePlayer("Genuine FA", 1),     # same sentinel id — not identifying
    ]
    monkeypatch.setattr(ls, "_get_league", lambda: _FakeLeague(fas))
    monkeypatch.setattr(ls, "all_teams", lambda **kw: pd.DataFrame(
        [{"player_name": "Rostered Guy", "player_id": 1}]))
    monkeypatch.setattr("plv_clone.league_state._cache_get", lambda *a, **k: None)
    monkeypatch.setattr("plv_clone.league_state._cache_put", lambda *a, **k: None)

    names = set(ls.available_fa()["player_name"])
    assert "Genuine FA" in names, "a shared sentinel id emptied the FA pool"
    assert "Rostered Guy" not in names, "the name leg must still drop him"
