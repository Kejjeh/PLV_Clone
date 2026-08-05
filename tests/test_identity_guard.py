"""Cross-source identity: does the mlbam you joined actually play where ESPN says?

Within-source duplicate detection is NOT enough, and this is the case that
proved it. A 0.1%-owned catcher named "Julio Rodriguez" is UNIQUE in the ESPN
free-agent pool, and the real Julio Rodríguez is UNIQUE in rh3 — so no
duplicate fires anywhere — yet joining them on a normalized name puts the real
J-Rod's #12 projection on a replacement-level catcher and floats him to the top
of a "best available" board. It surfaced three separate times on 2026-08-03/04
before a check existed that could see it.

The tell is never the name. It is that the joined mlbam plays for a club the
ESPN row does not claim.
"""
import json

import pandas as pd
import pytest

TO = pytest.importorskip("scripts.xfp.lib.team_override")


def _map(tmp_path, players):
    p = tmp_path / "current_teams.json"
    p.write_text(json.dumps({
        "as_of": "2026-08-04", "source": "test",
        "players": {str(k): {"abbr": v, "team": v, "name": f"P{k}", "pos": "C"}
                    for k, v in players.items()}}), encoding="utf-8")
    return TO.load_map(p)


def test_the_julio_rodriguez_phantom_is_caught(tmp_path):
    """The canonical case: ESPN row has NO major-league club, but the joined
    mlbam is an everyday star. Two unique names, one wrong join."""
    m = _map(tmp_path, {677594: "SEA"})
    df = pd.DataFrame({"player_name": ["Julio Rodriguez"], "batter": [677594],
                       "pro_team": ["FA"]})
    kept, dropped = TO.verify_identity(df, m, mlbam_col="batter",
                                       team_col="pro_team")
    assert len(kept) == 0 and len(dropped) == 1
    assert dropped.iloc[0]["identity_status"] == "NO_CLUB"


def test_a_mismatched_club_is_dropped(tmp_path):
    """ESPN says Boston, the mlbam plays in Seattle — not the same person."""
    m = _map(tmp_path, {677594: "SEA"})
    df = pd.DataFrame({"player_name": ["Someone"], "batter": [677594],
                       "pro_team": ["Bos"]})
    kept, dropped = TO.verify_identity(df, m, mlbam_col="batter",
                                       team_col="pro_team")
    assert len(kept) == 0
    assert dropped.iloc[0]["identity_status"] == "MISMATCH"


def test_agreeing_clubs_survive_including_espn_alias_spellings(tmp_path):
    """ESPN writes Ari/ChW/Oak/Wsh where the model writes AZ/CWS/ATH/WSH.
    Normalisation failures would drop the whole league as mismatches."""
    m = _map(tmp_path, {1: "AZ", 2: "CWS", 3: "ATH", 4: "WSH", 5: "SEA"})
    df = pd.DataFrame({"player_name": list("abcde"), "batter": [1, 2, 3, 4, 5],
                       "pro_team": ["Ari", "ChW", "Oak", "Wsh", "Sea"]})
    kept, dropped = TO.verify_identity(df, m, mlbam_col="batter",
                                       team_col="pro_team")
    assert len(kept) == 5 and len(dropped) == 0
    assert set(kept["identity_status"]) == {"VERIFIED"}


def test_a_player_on_no_40man_is_flagged_but_kept(tmp_path):
    """A minor-leaguer with a real ESPN row is UNVERIFIABLE, not a phantom.
    Dropping him would quietly shrink every board; the earlier ad-hoc version
    of this check did exactly that to five legitimate players."""
    m = _map(tmp_path, {677594: "SEA"})
    df = pd.DataFrame({"player_name": ["Some Prospect"], "batter": [999999],
                       "pro_team": ["Bal"]})
    kept, dropped = TO.verify_identity(df, m, mlbam_col="batter",
                                       team_col="pro_team")
    assert len(kept) == 1 and len(dropped) == 0
    assert kept.iloc[0]["identity_status"] == "UNVERIFIED"


def test_caller_may_widen_what_gets_dropped(tmp_path):
    m = _map(tmp_path, {677594: "SEA"})
    df = pd.DataFrame({"player_name": ["Some Prospect"], "batter": [999999],
                       "pro_team": ["Bal"]})
    kept, dropped = TO.verify_identity(df, m, mlbam_col="batter",
                                       team_col="pro_team",
                                       drop_statuses=("MISMATCH", "NO_CLUB",
                                                      "UNVERIFIED"))
    assert len(kept) == 0 and dropped.iloc[0]["identity_status"] == "UNVERIFIED"


def test_an_empty_map_drops_nobody(tmp_path):
    """No map must never mean no board. The guard is an improvement, not a
    dependency — same contract as apply_team_override."""
    m = TO.load_map(tmp_path / "missing.json")
    df = pd.DataFrame({"player_name": ["X"], "batter": [1], "pro_team": ["Bos"]})
    kept, dropped = TO.verify_identity(df, m, mlbam_col="batter",
                                       team_col="pro_team")
    assert len(kept) == 1 and len(dropped) == 0


def test_missing_columns_raise_rather_than_pass_everything(tmp_path):
    """A silent no-op guard is worse than none — it reads as 'checked, clean'."""
    m = _map(tmp_path, {1: "SEA"})
    df = pd.DataFrame({"player_name": ["X"], "mlbam": [1]})
    with pytest.raises(KeyError):
        TO.verify_identity(df, m, mlbam_col="batter", team_col="pro_team")
    with pytest.raises(KeyError):
        TO.verify_identity(df, m, mlbam_col="mlbam", team_col="pro_team")


def test_report_summarises_what_was_removed_and_why(tmp_path):
    m = _map(tmp_path, {1: "SEA", 2: "BOS"})
    df = pd.DataFrame({"player_name": ["ok", "phantom", "moved", "unknown"],
                       "batter": [1, 2, 2, 999], "pro_team": ["Sea", "FA", "NYY", "Bal"]})
    kept, dropped = TO.verify_identity(df, m, mlbam_col="batter",
                                       team_col="pro_team")
    line = TO.identity_report(kept, dropped)
    assert "NO_CLUB" in line and "MISMATCH" in line
    assert set(dropped["player_name"]) == {"phantom", "moved"}
