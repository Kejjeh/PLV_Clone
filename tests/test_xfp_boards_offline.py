"""Offline tests for build_xfp_boards injection seams (Phase 0, decision console).

Proves build_sp_board / build_hitter_board run fully offline when handed
roster / fas / injury_details (the fetch_board_inputs contract), never touch
ESPN on the injected path, and keep their row schemas stable.

Fixtures follow the fake-object style of tests/test_period_meta.py.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_xfp_boards as B


# ── fakes ────────────────────────────────────────────────────────────────────
class _FakePlayer:
    """Mirrors every attr the boards getattr() off an ESPN FA object."""

    def __init__(self, name, playerId, position, eligibleSlots, proTeam="NYM",
                 injured=False, injuryStatus="ACTIVE", percent_owned=1.2):
        self.name = name
        self.playerId = playerId
        self.position = position
        self.eligibleSlots = eligibleSlots
        self.proTeam = proTeam
        self.injured = injured
        self.injuryStatus = injuryStatus
        self.percent_owned = percent_owned


class _NoNetwork:
    """Stands in for LeagueState — any instantiation means a network fetch
    was attempted on a fully-injected call, which is a test failure."""

    def __init__(self, *a, **k):
        raise AssertionError("network fetch attempted: LeagueState() instantiated "
                             "despite fully-injected board inputs")


def _roster_df(rows):
    cols = ["player_name", "player_id", "position", "pro_team", "eligible_slots",
            "lineup_slot", "injured", "injury_status", "return_date"]
    return pd.DataFrame(rows, columns=cols)


SP_COLS = ["owner", "name", "team", "own", "per_start", "stuff", "src", "vol",
           "inj", "ret", "xfp_ros", "xfp_po"]
HIT_COLS = ["owner", "name", "team", "own", "slots", "per_game", "rank", "signal",
            "etfr", "src", "vol", "inj", "ret", "xfp_ros", "xfp_po", "buckets"]


# ── model-layer seams (no CSV / no Stuff+ fit / no rp3 load) ─────────────────
@pytest.fixture()
def sp_model_seams(monkeypatch):
    """Stub the SP projection tiers: Stuff+ fit and rp3 read become in-memory."""

    class _Mdl:
        def predict(self, X):
            return [14.0] * len(X)

    class _Sc:
        def transform(self, X):
            return X

    d = pd.DataFrame({
        "player_name_fg": ["Ace Starter", "Fringe Arm"],
        "stuff_plus": [110.0, 95.0],
        "feat": [1.0, 1.0],
    })
    monkeypatch.setattr(B.ss, "fit_model", lambda: (_Mdl(), _Sc(), None))
    monkeypatch.setattr(B.ss, "load_2026", lambda: d)
    monkeypatch.setattr(B.ss, "FEATS", ["feat"])

    rp3 = pd.DataFrame({
        "player_name": ["Driven, Data", "Stash, Marcel"],
        "pitcher": [111, 222],
        "xfp_rp3_per_start": [12.0, 9.0],
        "data_quality_tag": ["data_driven_2026", "marcel_il"],
    })
    monkeypatch.setattr(B.PROJECTIONS, "rp3", lambda: rp3)
    monkeypatch.setattr(B, "_SP_VOL_MAPS", [])   # no volume model in tests
    return d


@pytest.fixture()
def hitter_model_seams(monkeypatch):
    """Pre-seed the lazy rh3 globals so _load_rh3() early-returns (offline)."""
    rh3 = pd.DataFrame({
        "player_name": ["Good Hitter", "Deep Cut"],
        "batter": [1001, 1002],
        "xfp_rh3_per_game": [4.2, 2.1],
        "xfp_rh3_per_pa": [1.2, 0.6],
        "rank": [5, 250],
        "signal": ["hold", "fade"],
        "expected_total_fp_remaining": [300.0, 90.0],
    })
    monkeypatch.setattr(B, "_RH3", rh3)
    monkeypatch.setattr(B, "_RH3_BY_ID", rh3.set_index("batter"))
    full = {B.norm(r["player_name"]): r for _, r in rh3.iterrows()}
    monkeypatch.setattr(B, "_FULL", full)
    monkeypatch.setattr(B, "_AMBIG_NAMES", set())
    monkeypatch.setattr(B, "_MULTIYR", pd.DataFrame(
        {"player_name": [], "batter": [], "team": []}))
    monkeypatch.setattr(B, "_HIT_VOL", {})
    # id resolution: exact fake mapping, no multiyr lookup
    monkeypatch.setattr(
        B, "resolve_batter_id",
        lambda name, team=None, position=None, multiyr=None:
            {"good hitter": 1001, "deep cut": 1002}.get(B.norm(name)))
    return rh3


# ── SP board ─────────────────────────────────────────────────────────────────
def test_sp_board_offline_schema_and_no_network(sp_model_seams, monkeypatch):
    monkeypatch.setattr(B, "LeagueState", _NoNetwork)
    roster = _roster_df([
        ("Ace Starter", 1, "SP", "PHI", ["SP"], "SP", False, "ACTIVE", None),
    ])
    fas = [
        _FakePlayer("Data Driven", 201, "SP", ["SP"]),
        _FakePlayer("Marcel Stash", 202, "SP", ["SP"], injured=True,
                    injuryStatus="SIXTY_DAY_DL"),
        _FakePlayer("Good Hitter", 301, "OF", ["OF", "UTIL"]),   # non-SP: filtered
    ]
    df = B.build_sp_board(roster=roster, fas=fas, injury_details={})
    assert list(df.columns) == SP_COLS
    assert set(df["owner"]) == {"MINE", "FA"}
    assert "Good Hitter" not in set(df["name"])
    mine = df[df["owner"] == "MINE"].iloc[0]
    assert mine["name"] == "Ace Starter" and mine["src"].startswith("Stuff+")
    mar = df[df["name"] == "Marcel Stash"].iloc[0]
    assert mar["src"].startswith("talent_prior")   # LOW-CONF tier preserved


def test_sp_board_injected_return_date_reflected(sp_model_seams, monkeypatch):
    monkeypatch.setattr(B, "LeagueState", _NoNetwork)
    ret = date.today() + timedelta(days=40)
    fas = [_FakePlayer("Marcel Stash", 202, "SP", ["SP"], injured=True,
                       injuryStatus="SIXTY_DAY_DL")]
    df = B.build_sp_board(roster=_roster_df([]), fas=fas,
                          injury_details={202: ret})
    row = df[df["name"] == "Marcel Stash"].iloc[0]
    assert row["ret"] == ret          # explicit date beats the HEUR fallback


# ── hitter board ─────────────────────────────────────────────────────────────
def test_hitter_board_offline_schema_buckets_and_no_network(hitter_model_seams,
                                                            monkeypatch):
    monkeypatch.setattr(B, "LeagueState", _NoNetwork)
    roster = _roster_df([
        ("Good Hitter", 2, "OF", "NYY", ["OF", "UTIL"], "OF", False, "ACTIVE", None),
    ])
    fas = [
        _FakePlayer("Deep Cut", 301, "2B", ["2B", "UTIL"]),
        _FakePlayer("Some Pitcher", 401, "SP", ["SP"]),    # non-hitter: filtered
    ]
    df = B.build_hitter_board(roster=roster, fas=fas, injury_details={})
    assert list(df.columns) == HIT_COLS
    assert "Some Pitcher" not in set(df["name"])
    gh = df[df["name"] == "Good Hitter"].iloc[0]
    assert gh["owner"] == "MINE" and gh["buckets"] >= {"OF", "UTIL"}
    dc = df[df["name"] == "Deep Cut"].iloc[0]
    assert dc["owner"] == "FA" and "2B/SS" in dc["buckets"]
    # per_game came from the seeded rh3, availability-scaled into totals
    assert gh["per_game"] == 4.2 and gh["xfp_ros"] > 0


def test_no_arg_calls_still_fetch(monkeypatch, sp_model_seams):
    """Backward compat: the no-arg path still constructs LeagueState (we assert
    it TRIES to — the _NoNetwork sentinel raising proves the code path)."""
    monkeypatch.setattr(B, "LeagueState", _NoNetwork)
    with pytest.raises(AssertionError, match="network fetch attempted"):
        B.build_sp_board()
