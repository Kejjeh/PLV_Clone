"""Tests for mlb_stats.get_probables — the probable-pitcher slate OWNER.

The raw schedule?hydrate=probablePitcher fetch was re-implemented in 8+
modules (audit 2026-07-04); this locks the owner's contract so callers can
migrate onto it. Injected http_get — no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from plv_clone.mlb_stats import get_probables, get_schedule


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _fake_http(url, **_):
    if "/teams" in url:
        return _Resp({"teams": [
            {"id": 1, "abbreviation": "SEA"}, {"id": 2, "abbreviation": "TOR"}]})
    return _Resp({"dates": [{
        "date": "2026-07-05",
        "games": [{
            "gamePk": 777,
            "status": {"abstractGameState": "Preview"},
            "teams": {
                "home": {"team": {"id": 1, "abbreviation": "SEA"},
                         "probablePitcher": {"id": 622491, "fullName": "Luis Castillo"}},
                "away": {"team": {"id": 2, "abbreviation": "TOR"},
                         "probablePitcher": {"id": 111, "fullName": "Visiting Arm"}},
            },
        }],
    }]})


def test_one_row_per_probable_with_park_as_home():
    rows = get_probables("2026-07-05", "2026-07-05", http_get=_fake_http, use_cache=False)
    assert len(rows) == 2
    home = next(r for r in rows if r["pitcher_id"] == 622491)
    away = next(r for r in rows if r["pitcher_id"] == 111)
    assert home["park_abbr"] == away["park_abbr"] == "SEA"  # park = HOME team
    assert home["opp_abbr"] == "TOR" and away["opp_abbr"] == "SEA"
    assert home["game_state"] == "Preview" and home["date"] == "2026-07-05"


def test_missing_probable_side_is_skipped():
    def http(url, **_):
        if "/teams" in url:
            return _Resp({"teams": []})
        return _Resp({"dates": [{"date": "2026-07-05", "games": [{
            "gamePk": 1, "status": {"abstractGameState": "Final"},
            "teams": {"home": {"team": {"id": 1, "abbreviation": "SEA"}},
                      "away": {"team": {"id": 2, "abbreviation": "TOR"},
                               "probablePitcher": {"id": 9, "fullName": "X"}}}}]}]})
    rows = get_probables("2026-07-05", "2026-07-05", http_get=http, use_cache=False)
    assert [r["pitcher_id"] for r in rows] == [9]


def test_cache_hit_same_window():
    calls = {"n": 0}

    def http(url, **_):
        calls["n"] += 1
        return _fake_http(url)

    get_probables("2026-07-06", "2026-07-06", http_get=http)
    n_first = calls["n"]
    get_probables("2026-07-06", "2026-07-06", http_get=http)
    assert calls["n"] == n_first  # second call served from cache


def test_api_failure_degrades_to_empty():
    def boom(url, **_):
        raise RuntimeError("down")
    assert get_probables("2026-07-07", "2026-07-07", http_get=boom, use_cache=False) == []


# ── get_schedule (item 9): ALL games incl. no-probable, venue/team names ──────

def _sched_http(url, **_):
    if "/teams" in url:
        return _Resp({"teams": []})
    return _Resp({"dates": [{
        "date": "2026-07-05",
        "games": [
            {  # has probables both sides
                "gamePk": 777, "gameType": "R",
                "status": {"abstractGameState": "Preview"},
                "venue": {"name": "T-Mobile Park"},
                "teams": {
                    "home": {"team": {"id": 1, "abbreviation": "SEA"},
                             "probablePitcher": {"id": 622491, "fullName": "Luis Castillo"}},
                    "away": {"team": {"id": 2, "abbreviation": "TOR"},
                             "probablePitcher": {"id": 111, "fullName": "Visiting Arm"}},
                },
            },
            {  # NO probables — must STILL appear in get_schedule
                "gamePk": 888, "gameType": "R",
                "status": {"abstractGameState": "Preview"},
                "venue": {"name": "Rogers Centre"},
                "teams": {
                    "home": {"team": {"id": 2, "abbreviation": "TOR"}},
                    "away": {"team": {"id": 1, "abbreviation": "SEA"}},
                },
            },
        ],
    }]})


def test_get_schedule_includes_no_probable_games():
    rows = get_schedule("2026-07-05", "2026-07-05", http_get=_sched_http, use_cache=False)
    pks = sorted(r["game_pk"] for r in rows)
    assert pks == [777, 888]  # the no-probable game is present
    g = next(r for r in rows if r["game_pk"] == 888)
    assert g["home_abbr"] == "TOR" and g["away_abbr"] == "SEA"
    assert g["venue_name"] == "Rogers Centre"
    assert g["home_probable_id"] is None and g["away_probable_id"] is None


def test_get_schedule_carries_probables_and_venue():
    rows = get_schedule("2026-07-05", "2026-07-05", http_get=_sched_http, use_cache=False)
    g = next(r for r in rows if r["game_pk"] == 777)
    assert g["venue_name"] == "T-Mobile Park"
    assert g["home_abbr"] == "SEA" and g["away_abbr"] == "TOR"
    assert g["home_probable_id"] == 622491 and g["home_probable_name"] == "Luis Castillo"
    assert g["away_probable_id"] == 111
    assert g["game_type"] == "R" and g["game_state"] == "Preview"


def test_get_schedule_api_failure_empty_uncached():
    def boom(url, **_):
        raise RuntimeError("down")
    assert get_schedule("2026-07-09", "2026-07-09", http_get=boom, use_cache=False) == []
