"""An SP start whose game is already FINAL leaves the remaining projection.

Defect (found 2026-09-18): the hitter/RP branch of ``project_player`` has
subtracted completed games since 2026-08-29, but the SP branch filtered its
starts by date only. Once a start finalised, its FP sat in the live WTD score
AND in the projection, and it occupied a cap slot in ESPN's banked count AND
in ``my_sp_events`` — so a genuine future start was zeroed by the cap.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_matchup_dashboard as BMD

NYY = 147
TODAY, END = date(2026, 9, 19), date(2026, 9, 27)


class _P:
    def __init__(self, name, pos, team="NYY", inj="ACTIVE"):
        self.name, self.position, self.proTeam, self.injuryStatus = name, pos, team, inj
        self.playerId = 1


def _games(*dates):
    return [{"date": d, "opp_team": "BOS", "is_home": True,
             "opp_probable_id": None, "opp_probable_name": None} for d in dates]


def _sp_env(monkeypatch):
    monkeypatch.setattr(BMD, "_resolve_pitcher_mlbam", lambda name, **kw: 555)
    monkeypatch.setattr(BMD, "detect_pitcher_role", lambda p, mlbam_id=None: "SP")


def _project(starts_by_pid, sched, completed):
    rp3_map = {BMD._norm("Ace Starter"): {"per_start": 12.0, "per_start_sched": 12.0, "sigma": 5.5}}
    return BMD.project_player(_P("Ace Starter", "SP"), sched, starts_by_pid,
                              {}, rp3_map, {}, {}, {"BOS": {"bat_index": 1.0}},
                              TODAY, END, completed_games=completed)


def test_final_start_today_is_not_re_projected(monkeypatch):
    _sp_env(monkeypatch)
    sched = {NYY: _games("2026-09-19", "2026-09-24")}
    starts = {555: [{"date": "2026-09-19", "opp_team": "BOS", "confirmed": True},
                    {"date": "2026-09-24", "opp_team": "BOS", "confirmed": True}]}
    before = _project(starts, sched, {})
    after = _project(starts, sched, {(NYY, "2026-09-19", 0): True})
    assert before["units"] == 2
    assert after["units"] == 1
    assert [b["date"] for b in after["breakdown"]] == ["2026-09-24"]
    assert after["fp"] < before["fp"]


def test_in_progress_start_is_kept(monkeypatch):
    """Only FINAL games are subtracted — an in-flight start stays projectable
    (its cap slot is not yet in ESPN's banked count)."""
    _sp_env(monkeypatch)
    sched = {NYY: _games("2026-09-19")}
    starts = {555: [{"date": "2026-09-19", "opp_team": "BOS", "confirmed": True}]}
    assert _project(starts, sched, {})["units"] == 1


def test_split_dh_game_two_start_survives_game_one_final():
    games = _games("2026-09-19", "2026-09-19")
    starts = [{"date": "2026-09-19"}]
    kept = BMD.drop_completed_starts(starts, games, NYY, {(NYY, "2026-09-19", 0): True})
    assert kept == starts
    gone = BMD.drop_completed_starts(starts, games, NYY,
                                     {(NYY, "2026-09-19", 0): True, (NYY, "2026-09-19", 1): True})
    assert gone == []
