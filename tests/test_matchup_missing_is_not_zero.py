"""A rostered player with NO projection row must be labelled, not zeroed.

Defect (found 2026-09-18): ``project_player`` returned the same
``{'fp': 0.0, 'units': 0, 'badges': []}`` for a hitter absent from rh3 (or an
RP absent from rprs2) as for a 60-day-IL player. The SP branch alone said
``≈ est``. Missing and zero now differ by a badge, and NaN CSV cells no longer
slip through ``or 0`` into the projection maps.
"""
from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_matchup_dashboard as BMD

TODAY, END = date(2026, 9, 19), date(2026, 9, 27)
SCHED = {147: [{"date": "2026-09-20", "opp_team": "BOS", "is_home": True,
                "opp_probable_id": None, "opp_probable_name": None}]}


class _P:
    def __init__(self, name, pos, team="NYY", inj="ACTIVE"):
        self.name, self.position, self.proTeam, self.injuryStatus = name, pos, team, inj
        self.playerId = 1


def test_hitter_missing_from_rh3_is_badged():
    out = BMD.project_player(_P("Rookie Bat", "OF"), SCHED, {}, {}, {}, {}, {},
                             {"BOS": {"pit_index": 1.0}}, TODAY, END)
    assert out["fp"] == 0.0
    assert "⚠ no proj" in out["badges"]


def test_hitter_present_in_rh3_is_not_badged():
    rh3 = {BMD._norm("Known Bat"): {"per_game": 2.5}}
    out = BMD.project_player(_P("Known Bat", "OF"), SCHED, {}, rh3, {}, {}, {},
                             {"BOS": {"pit_index": 1.0}}, TODAY, END)
    assert out["fp"] > 0 and "⚠ no proj" not in out["badges"]


def test_il_hitter_is_zero_without_the_missing_badge():
    rh3 = {BMD._norm("Hurt Bat"): {"per_game": 2.5}}
    out = BMD.project_player(_P("Hurt Bat", "OF", inj="SIXTY_DAY_DL"), SCHED, {},
                             rh3, {}, {}, {}, {}, TODAY, END)
    assert out["fp"] == 0.0 and "⚠ no proj" not in out["badges"]


def test_rp_missing_from_rprs2_is_badged(monkeypatch):
    monkeypatch.setattr(BMD, "_resolve_pitcher_mlbam", lambda name, **kw: 77)
    monkeypatch.setattr(BMD, "detect_pitcher_role", lambda p, mlbam_id=None: "RP")
    out = BMD.project_player(_P("Unknown Arm", "RP"), SCHED, {}, {}, {}, {}, {},
                             {}, TODAY, END)
    assert out["fp"] == 0.0 and "⚠ no proj" in out["badges"]


def test_num_or_treats_nan_as_missing():
    assert BMD._num_or(float("nan")) == 0
    assert BMD._num_or(None) == 0
    assert BMD._num_or(float("nan"), None) is None
    assert BMD._num_or(3.5) == 3.5
    assert BMD._num_or(pd.NA) == 0
    assert not math.isnan(BMD._num_or(float("nan")))
