"""Tests for capture_upcoming_starts — the upcoming-SP-slate snapshot.

Locks the three things a capture can silently get wrong: dropping a TBD side,
sorting a slate by string clock ("10:10PM" before "7:40PM"), and annotating by
name instead of MLBAM id. Injected schedule rows — no network.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "capture_upcoming_starts", _ROOT / "scripts" / "xfp" / "capture_upcoming_starts.py")
cus = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cus)

from plv_clone.mlb_stats import _et_clock, get_schedule  # noqa: E402


def _game(pk, day, et_utc, home, away, home_p=None, away_p=None, game_type="R"):
    return {
        "date": day, "game_pk": pk, "game_type": game_type, "game_state": "Preview",
        "venue_name": f"{home} Park", "game_datetime_utc": et_utc,
        "first_pitch_et": _et_clock(et_utc),
        "home_abbr": home, "away_abbr": away,
        "home_probable_id": home_p[0] if home_p else None,
        "home_probable_name": home_p[1] if home_p else None,
        "away_probable_id": away_p[0] if away_p else None,
        "away_probable_name": away_p[1] if away_p else None,
    }


GAMES = [
    _game(1, "2026-07-29", "2026-07-30T02:10:00Z", "LAD", "SEA",
          home_p=(1, "Eric Lauer"), away_p=(2, "Luis Castillo")),          # 10:10PM ET
    _game(2, "2026-07-29", "2026-07-29T16:10:00Z", "MIA", "PHI",
          home_p=None, away_p=(3, "Jesus Luzardo")),                       # 12:10PM, MIA TBD
    _game(3, "2026-07-29", "2026-07-29T23:40:00Z", "CHW", "NYY",
          home_p=(4, "Davis Martin"), away_p=(5, "Cam Schlittler")),       # 7:40PM ET
]


def test_tbd_side_is_captured_not_dropped():
    rows = cus.build_rows(GAMES, captured_at="T", rp3={})
    assert len(rows) == 6  # 3 games x 2 sides — the TBD side included
    tbd = [r for r in rows if r["pitcher_name"] == "-"]
    assert len(tbd) == 1
    assert tbd[0]["team"] == "MIA" and tbd[0]["pitcher_id"] == ""


def test_slate_is_sorted_by_real_clock_not_string():
    rows = cus.build_rows(GAMES, captured_at="T", rp3={})
    assert [r["first_pitch_et"] for r in rows] == [
        "12:10PM", "12:10PM", "7:40PM", "7:40PM", "10:10PM", "10:10PM"]


def test_park_is_home_team_and_vs_at_orientation():
    rows = cus.build_rows(GAMES, captured_at="T", rp3={})
    schlittler = next(r for r in rows if r["pitcher_name"] == "Cam Schlittler")
    assert schlittler["home_away"] == "away"
    assert schlittler["team"] == "NYY" and schlittler["opp"] == "CWS"
    assert schlittler["park"] == "CWS"  # park = HOME team, matching get_probables


def test_rp3_annotation_joins_on_mlbam_id_only():
    rp3 = {5: {"rank": "40", "per_start": "13.55", "dq": "data_driven_full"},
           99: {"rank": "1", "per_start": "19.66", "dq": "data_driven_full"}}
    rows = cus.build_rows(GAMES, captured_at="T", rp3=rp3)
    hit = next(r for r in rows if r["pitcher_id"] == 5)
    assert (hit["rp3_rank"], hit["rp3_per_start"], hit["dq"]) == (
        "40", "13.55", "data_driven_full")
    # every other side is unannotated — no fuzzy/name fallback may fill them in
    assert all(r["rp3_rank"] == "" for r in rows if r["pitcher_id"] != 5)


def test_non_regular_season_games_excluded():
    spring = _game(9, "2026-07-29", "2026-07-29T17:05:00Z", "TB", "BOS",
                   home_p=(7, "Spring Arm"), game_type="S")
    rows = cus.build_rows(GAMES + [spring], captured_at="T", rp3={})
    assert all(r["game_pk"] != 9 for r in rows)


def test_md_reports_confirmed_observed_and_tbd_counts():
    rows = cus.build_rows(GAMES, captured_at="T", rp3={})
    md = cus.render_md(rows, start="2026-07-29", end="2026-07-29", captured_at="T")
    assert ("5 probables confirmed by the MLB Stats API across 3 games; "
            "0 filled from the observed overlay; 1 side(s) still TBD") in md
    assert "| @ CWS |" in md and "| vs SEA |" in md


# ── observed overlay: app-projected sides the MLB feed has not confirmed ──────

_MIA_PITCHERS = [
    {"id": 660853, "full_name": "Edward Cabrera"},
    {"id": 663554, "full_name": "Eury Perez"},
    {"id": 999001, "full_name": "Elias Perez"},  # same surname + initial as above
]


def _roster(team_abbr):
    return _MIA_PITCHERS if team_abbr == "MIA" else []


def _observed(name):
    return {("2026-07-29", "MIA"): {
        "observed_name": name, "source": "scoreboard_app_screenshot"}}


def test_observed_fills_blank_side_and_is_tagged_not_confirmed():
    rows = cus.build_rows(GAMES, captured_at="T", rp3={},
                          observed=_observed("E. Cabrera"), roster_fetch=_roster)
    mia = next(r for r in rows if r["team"] == "MIA" and r["home_away"] == "home")
    assert mia["pitcher_name"] == "Edward Cabrera" and mia["pitcher_id"] == 660853
    assert mia["source"] == "observed"  # never "mlb_api"
    assert mia["observed_source"] == "scoreboard_app_screenshot"


def test_observed_never_overrides_a_confirmed_probable():
    obs = {("2026-07-29", "CWS"): {"observed_name": "Someone Else", "source": "app"}}
    rows = cus.build_rows(GAMES, captured_at="T", rp3={}, observed=obs,
                          roster_fetch=_roster)
    cws = next(r for r in rows if r["team"] == "CWS")
    assert cws["pitcher_name"] == "Davis Martin" and cws["source"] == "mlb_api"


def test_ambiguous_observed_name_is_captured_unresolved_not_guessed():
    rows = cus.build_rows(GAMES, captured_at="T", rp3={},
                          observed=_observed("E. Perez"), roster_fetch=_roster)
    mia = next(r for r in rows if r["team"] == "MIA" and r["home_away"] == "home")
    assert mia["pitcher_name"] == "E. Perez"  # verbatim, no id invented
    assert mia["pitcher_id"] == "" and mia["rp3_rank"] == ""


def test_surname_only_match_is_refused_when_team_has_two():
    assert cus.resolve_observed_name("Perez", "MIA", roster_fetch=_roster) == (
        None, "Perez")


def test_observed_row_gets_rp3_annotation_via_resolved_id():
    rp3 = {660853: {"rank": "77", "per_start": "11.11", "dq": "data_driven_full"}}
    rows = cus.build_rows(GAMES, captured_at="T", rp3=rp3,
                          observed=_observed("E. Cabrera"), roster_fetch=_roster)
    mia = next(r for r in rows if r["team"] == "MIA" and r["home_away"] == "home")
    assert mia["rp3_rank"] == "77" and mia["dq"] == "data_driven_full"


def test_overlay_file_keys_on_api_abbrs_and_skips_dashes(tmp_path):
    p = tmp_path / "observed.csv"
    p.write_text("date,team,observed_name,source,observed_at,note\n"
                 "2026-07-29,CHW,D. Martin,app,x,\n"      # app abbr -> CWS
                 "2026-07-29,ARI,B. Pfaadt,app,x,\n"      # app abbr -> AZ
                 "2026-07-29,MIA,-,app,x,\n",             # explicit TBD: not an entry
                 encoding="utf-8")
    obs = cus.load_observed(p)
    assert set(obs) == {("2026-07-29", "CWS"), ("2026-07-29", "AZ")}


def test_missing_overlay_file_is_not_an_error():
    assert cus.load_observed(Path("/nonexistent/observed.csv")) == {}


def test_the_shipped_overlay_parses_and_targets_only_blank_sides():
    """The committed 2026-07-27 overlay must stay loadable and honestly tagged."""
    shipped = cus.OBSERVED_CSV
    if not shipped.exists():
        return
    obs = cus.load_observed(shipped)
    assert obs, "shipped overlay parsed to nothing"
    assert all(len(k) == 2 and k[0].count("-") == 2 for k in obs)
    assert all(r.get("source") and r.get("observed_at") for r in obs.values())


# ── the owner's new first_pitch_et field (additive to get_schedule) ───────────

def test_et_clock_converts_utc_to_et_wall_clock():
    assert _et_clock("2026-07-27T23:40:00Z") == "7:40PM"   # EDT = UTC-4
    assert _et_clock("2026-07-27T18:35:00Z") == "2:35PM"
    assert _et_clock("2026-07-30T02:10:00Z") == "10:10PM"  # rolls back a day
    assert _et_clock("2026-07-27T16:00:00Z") == "12:00PM"  # noon, not 0:00PM
    assert _et_clock(None) is None and _et_clock("garbage") is None


def test_get_schedule_carries_first_pitch_et():
    class _Resp:
        def __init__(self, p):
            self._p = p

        def json(self):
            return self._p

    def http(url, **_):
        if "/teams" in url:
            return _Resp({"teams": []})
        return _Resp({"dates": [{"date": "2026-07-27", "games": [{
            "gamePk": 822868, "gameType": "R", "gameDate": "2026-07-27T18:35:00Z",
            "status": {"abstractGameState": "Preview"},
            "venue": {"name": "Globe Life Field"},
            "teams": {"home": {"team": {"id": 1, "abbreviation": "TEX"}},
                      "away": {"team": {"id": 2, "abbreviation": "SEA"}}}}]}]})

    row = get_schedule("2026-07-27", "2026-07-27", http_get=http, use_cache=False)[0]
    assert row["game_datetime_utc"] == "2026-07-27T18:35:00Z"
    assert row["first_pitch_et"] == "2:35PM"
