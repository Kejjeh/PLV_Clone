"""A traded player must not keep his old club in the projection outputs.

The 2026 deadline left **85 players** carrying stale teams across rh3 and the
volume models. José Soriano read LAA in xfp_sp_volume_projections.csv while
pitching for Toronto — and team is what park factors, schedule joins, opponent
context and bullpen lenses all key on, so a stale code is silently wrong
everywhere downstream rather than obviously wrong in one place.

The models cannot fix this themselves: they derive team from historical
Statcast, which is by construction where the player USED to be.
"""
import json

import pandas as pd
import pytest

TO = pytest.importorskip("scripts.xfp.lib.team_override")


def _map_file(tmp_path, players, as_of="2026-08-03"):
    p = tmp_path / "current_teams.json"
    p.write_text(json.dumps({
        "as_of": as_of, "source": "test",
        "players": {str(k): {"abbr": v, "team": v, "name": f"P{k}", "pos": "P"}
                    for k, v in players.items()},
    }), encoding="utf-8")
    return p


def test_a_traded_player_gets_his_new_club(tmp_path):
    """Soriano, in miniature."""
    m = TO.load_map(_map_file(tmp_path, {667755: "TOR"}))
    df = pd.DataFrame({"mlbam": [667755], "team": ["LAA"]})
    out, n, unknown = TO.apply_team_override(df, m, mlbam_col="mlbam")
    assert out.loc[0, "team"] == "TOR"
    assert n == 1 and unknown == 0


def test_a_player_absent_from_the_map_keeps_his_team(tmp_path):
    """A 40-man pull does not contain every projected player — minor-leaguers,
    released veterans, the 60-day IL. Absence is not evidence he was traded,
    and blanking his team would break park lookups that work today."""
    m = TO.load_map(_map_file(tmp_path, {667755: "TOR"}))
    df = pd.DataFrame({"mlbam": [111111], "team": ["BOS"]})
    out, n, unknown = TO.apply_team_override(df, m, mlbam_col="mlbam")
    assert out.loc[0, "team"] == "BOS"
    assert n == 0 and unknown == 1


def test_a_code_outside_the_model_vocabulary_is_refused(tmp_path):
    """Writing a code the park table cannot resolve is worse than staleness:
    stale gives the wrong park, unknown gives none at all."""
    m = TO.load_map(_map_file(tmp_path, {667755: "XXX"}))
    assert 667755 not in m.teams, "an unresolvable code must not enter the map"


def test_applying_twice_changes_nothing_the_second_time(tmp_path):
    m = TO.load_map(_map_file(tmp_path, {667755: "TOR"}))
    df = pd.DataFrame({"mlbam": [667755], "team": ["LAA"]})
    once, n1, _ = TO.apply_team_override(df, m, mlbam_col="mlbam")
    _, n2, _ = TO.apply_team_override(once, m, mlbam_col="mlbam")
    assert n1 == 1 and n2 == 0, "override must be idempotent"


def test_rows_already_correct_are_not_counted_as_changes(tmp_path):
    m = TO.load_map(_map_file(tmp_path, {1: "TOR", 2: "BOS"}))
    df = pd.DataFrame({"mlbam": [1, 2], "team": ["TOR", "BOS"]})
    _, n, _ = TO.apply_team_override(df, m, mlbam_col="mlbam")
    assert n == 0


def test_staleness_is_reported_in_days(tmp_path):
    import datetime
    m = TO.load_map(_map_file(tmp_path, {1: "TOR"}, as_of="2026-08-01"))
    assert m.staleness_days(datetime.date(2026, 8, 4)) == 3


def test_a_stale_map_still_applies_but_says_so(tmp_path):
    """Half-fresh beats not-at-all: a week-old map still fixes deadline trades.
    It must not silently pass as current, though."""
    import datetime
    m = TO.load_map(_map_file(tmp_path, {1: "TOR"}, as_of="2026-07-01"))
    assert m.is_stale(datetime.date(2026, 8, 4)) is True
    df = pd.DataFrame({"mlbam": [1], "team": ["LAA"]})
    out, n, _ = TO.apply_team_override(df, m, mlbam_col="mlbam")
    assert out.loc[0, "team"] == "TOR" and n == 1


def test_a_missing_map_file_is_a_no_op_not_a_crash(tmp_path):
    """The override is an improvement, never a dependency. A fresh clone with
    no map must still run every board."""
    m = TO.load_map(tmp_path / "does_not_exist.json")
    df = pd.DataFrame({"mlbam": [1], "team": ["LAA"]})
    out, n, _ = TO.apply_team_override(df, m, mlbam_col="mlbam")
    assert out.loc[0, "team"] == "LAA" and n == 0
    assert m.empty is True


def test_missing_mlbam_column_raises_rather_than_silently_doing_nothing(tmp_path):
    """A renamed id column would make this a silent no-op forever — exactly
    how the SP volume side sat dead for weeks matching 0 of 29 names."""
    m = TO.load_map(_map_file(tmp_path, {1: "TOR"}))
    df = pd.DataFrame({"batter_id": [1], "team": ["LAA"]})
    with pytest.raises(KeyError):
        TO.apply_team_override(df, m, mlbam_col="mlbam")


def test_model_vocabulary_is_exactly_the_thirty_clubs():
    assert len(TO.MODEL_TEAM_CODES) == 30
    for c in ("ATH", "AZ", "CWS", "WSH", "SD", "SF", "TB", "KC"):
        assert c in TO.MODEL_TEAM_CODES
