"""Behavioral tests for mlb_stats pure merge + prediction logic.

HTTP-fetching wrapper (`fetch_week_probables`) is tested separately; the
pure prediction unit is what bug B (no-rotation-gap-fallback undercount)
regresses against.
"""
from __future__ import annotations

from datetime import date

from plv_clone.cap_math import WeekProbables
from plv_clone.mlb_stats import fetch_week_probables, predict_rotation_starts, resolve_mlbam


def test_predicts_next_start_at_gap_after_last_actual():
    """Last actual start + rotation gap lands on a team game in window -> one predicted start."""
    last_actual = date(2026, 5, 17)
    prior_start = date(2026, 5, 12)
    week_start = date(2026, 5, 22)
    week_end = date(2026, 5, 28)
    team_schedule = [
        (date(2026, 5, 22), "BAL"),
        (date(2026, 5, 23), "BAL"),
        (date(2026, 5, 24), "NYY"),
    ]

    result = predict_rotation_starts(
        gamelog_dates=[last_actual, prior_start],
        confirmed_dates=[],
        team_schedule=team_schedule,
        week_start=week_start,
        week_end=week_end,
    )

    assert result == [(date(2026, 5, 22), "BAL")]


def test_predicted_start_dedups_against_confirmed_date():
    """A predicted date that is already a confirmed start must not double-emit."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 17), date(2026, 5, 12)],
        confirmed_dates=[date(2026, 5, 22)],
        team_schedule=[(date(2026, 5, 22), "BAL")],
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
    )

    assert result == []


def test_gap_clamps_to_seven_when_prior_starts_far_apart():
    """A 10-day gap from extended rest must clamp to 7, not extrapolate the full gap."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 17), date(2026, 5, 7)],
        confirmed_dates=[],
        team_schedule=[
            (date(2026, 5, 24), "NYY"),
            (date(2026, 5, 27), "TBR"),
        ],
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
    )

    assert result == [(date(2026, 5, 24), "NYY")]


def test_gap_clamps_to_four_when_prior_starts_close():
    """A 3-day gap (rare back-to-back) must clamp to 4 minimum."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 20), date(2026, 5, 17)],
        confirmed_dates=[],
        team_schedule=[
            (date(2026, 5, 23), "NYY"),
            (date(2026, 5, 24), "NYY"),
        ],
        week_start=date(2026, 5, 22),
        week_end=date(2026, 5, 28),
    )

    assert result == [(date(2026, 5, 24), "NYY")]


# ---- HTTP-wrapper tests with injected transport ------------------------------

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
    def json(self):
        return self._payload
    @property
    def status_code(self):
        return 200


def _make_http_get(routes):
    """Build a fake http_get that dispatches by URL substring -> payload."""
    def _http_get(url, **kwargs):
        for needle, payload in routes.items():
            if needle in url:
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected URL: {url}")
    return _http_get


def test_resolve_mlbam_returns_name_to_pitcher_id_map():
    routes = {
        "names=Hunter%20Brown": {"people": [
            {"id": 686613, "primaryPosition": {"abbreviation": "P"}, "fullName": "Hunter Brown"},
        ]},
        "names=Bobby%20Witt": {"people": [
            {"id": 677951, "primaryPosition": {"abbreviation": "SS"}, "fullName": "Bobby Witt Jr."},
        ]},
    }

    result = resolve_mlbam(["Hunter Brown", "Bobby Witt"], http_get=_make_http_get(routes))

    # Hunter Brown is a P -> picks 686613. Bobby Witt is an SS -> still picks first match.
    assert result == {"Hunter Brown": 686613, "Bobby Witt": 677951}


def test_resolve_mlbam_omits_names_with_no_match():
    routes = {"names=Ghost%20Player": {"people": []}}

    result = resolve_mlbam(["Ghost Player"], http_get=_make_http_get(routes))

    assert result == {}


def test_fetch_week_probables_returns_confirmed_starts_matching_pitcher_ids():
    week_start = date(2026, 5, 22)
    week_end = date(2026, 5, 28)
    schedule_payload = {
        "dates": [{"games": [
            {
                "gameDate": "2026-05-24T19:00:00Z",
                "teams": {
                    "home": {"team": {"id": 117, "abbreviation": "HOU"},
                              "probablePitcher": {"id": 686613, "fullName": "Hunter Brown"}},
                    "away": {"team": {"id": 110, "abbreviation": "BAL"},
                              "probablePitcher": {"id": 999999, "fullName": "Not Tracked"}},
                },
            },
        ]}]
    }
    # Empty gamelog for our pitcher -> no rotation-gap predictions added.
    gamelog_payload = {"stats": [{"splits": []}]}

    routes = {
        "schedule?sportId=1": schedule_payload,
        "people/686613/stats": gamelog_payload,
    }

    result = fetch_week_probables(
        week_start=week_start, week_end=week_end,
        pitcher_ids=[686613],
        http_get=_make_http_get(routes),
    )

    assert isinstance(result, WeekProbables)
    assert result.starts == {(686613, date(2026, 5, 24)): "BAL"}


def test_fetch_week_probables_folds_rotation_gap_predictions_into_confirmed():
    """Bug B integration: pitcher confirmed Mon + 5-day gap gamelog -> predicted Sat too."""
    week_start = date(2026, 5, 18)
    week_end = date(2026, 5, 24)
    schedule_payload = {"dates": [{"games": [
        # Mon confirmed for our pitcher (HOU home vs BAL)
        {
            "gameDate": "2026-05-18T19:00:00Z",
            "teams": {
                "home": {"team": {"id": 117, "abbreviation": "HOU"},
                          "probablePitcher": {"id": 686613, "fullName": "Hunter Brown"}},
                "away": {"team": {"id": 110, "abbreviation": "BAL"}},
            },
        },
        # Sat HOU plays NYY — no probable listed; rotation-gap should fill
        {
            "gameDate": "2026-05-23T19:00:00Z",
            "teams": {
                "home": {"team": {"id": 117, "abbreviation": "HOU"}},
                "away": {"team": {"id": 147, "abbreviation": "NYY"}},
            },
        },
    ]}]}
    # Last two actual starts 5 days apart -> gap=5 -> next start = 5/18 + 5 = 5/23.
    gamelog_payload = {"stats": [{"splits": [
        {"date": "2026-05-18", "stat": {"gamesStarted": "1"}},
        {"date": "2026-05-13", "stat": {"gamesStarted": "1"}},
    ]}]}

    result = fetch_week_probables(
        week_start=week_start, week_end=week_end,
        pitcher_ids=[686613],
        http_get=_make_http_get({
            "schedule?sportId=1": schedule_payload,
            "people/686613/stats": gamelog_payload,
        }),
    )

    assert result.starts == {
        (686613, date(2026, 5, 18)): "BAL",   # confirmed
        (686613, date(2026, 5, 23)): "NYY",   # rotation-gap fill
    }


def test_anchor_advances_to_latest_confirmed_to_prevent_doublecount():
    """Gray bug: gamelog 5/18 + confirmed 5/24 -> anchor should be 5/24, predict 5/29 not 5/23."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 18), date(2026, 5, 13)],  # gap=5
        confirmed_dates=[date(2026, 5, 24)],                    # future confirmed
        team_schedule=[
            (date(2026, 5, 23), "BAL"),  # would falsely emit without anchor advance
            (date(2026, 5, 29), "BOS"),  # the true next start
        ],
        week_start=date(2026, 5, 18),
        week_end=date(2026, 5, 30),
    )

    # No 5/23 (anchor=5/24, so 5/23 is BEFORE the anchor and not a candidate).
    # 5/29 = anchor + gap = 5/24 + 5; matches BOS in team schedule.
    assert result == [(date(2026, 5, 29), "BOS")]


def test_single_start_gamelog_uses_default_five_day_gap():
    """No IndexError when only one prior start exists; default gap=5."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 18)],
        confirmed_dates=[],
        team_schedule=[(date(2026, 5, 23), "NYY")],
        week_start=date(2026, 5, 18),
        week_end=date(2026, 5, 28),
    )

    assert result == [(date(2026, 5, 23), "NYY")]


def test_predict_returns_multiple_starts_when_window_wide():
    """Wide window + many team games -> emit up to n_predictions rotation slots.

    API default is n_predictions=2; this test asks for 3 explicitly to exercise
    the full pipeline. Production callers (sp-week-plan, matchup dashboard) keep
    the default 2 because BrownU scoring weeks rarely contain a third start.
    """
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 17), date(2026, 5, 12)],  # gap=5
        confirmed_dates=[],
        team_schedule=[
            (date(2026, 5, 22), "BAL"),
            (date(2026, 5, 27), "NYY"),
            (date(2026, 6, 1), "BOS"),  # third rotation slot
        ],
        week_start=date(2026, 5, 17),
        week_end=date(2026, 6, 5),
        n_predictions=3,
    )

    # 5/17 + 5 = 5/22 BAL; +5 = 5/27 NYY; +5 = 6/1 BOS.
    assert result == [
        (date(2026, 5, 22), "BAL"),
        (date(2026, 5, 27), "NYY"),
        (date(2026, 6, 1), "BOS"),
    ]


def test_predict_uses_one_day_tolerance_to_match_team_schedule():
    """Predicted 5/24 with team game on 5/23 (±1 day) -> matches."""
    result = predict_rotation_starts(
        gamelog_dates=[date(2026, 5, 19), date(2026, 5, 14)],  # gap=5
        confirmed_dates=[],
        team_schedule=[(date(2026, 5, 23), "BAL")],  # one day before predicted 5/24
        week_start=date(2026, 5, 19),
        week_end=date(2026, 5, 28),
    )

    assert result == [(date(2026, 5, 23), "BAL")]


def test_fetch_week_probables_resolves_team_via_people_endpoint_fallback():
    """McClanahan bug: pitcher with no confirmed in-window start still gets rotation-gap fill."""
    week_start = date(2026, 5, 22)
    week_end = date(2026, 5, 25)
    # Schedule has TB games but NO probable listed -> can't resolve team via schedule walk.
    schedule_payload = {"dates": [{"games": [
        {
            "gameDate": "2026-05-24T19:00:00Z",
            "teams": {
                "home": {"team": {"id": 139, "abbreviation": "TB"}},
                "away": {"team": {"id": 110, "abbreviation": "BAL"}},
            },
        },
    ]}]}
    # The /people fallback returns TB as currentTeam for McClanahan.
    people_payload = {"people": [{"id": 663556, "currentTeam": {"id": 139}}]}
    # Gamelog: last actual 5/19 -> gap=5 -> next=5/24 (matches TB home game).
    gamelog_payload = {"stats": [{"splits": [
        {"date": "2026-05-19", "stat": {"gamesStarted": "1"}},
        {"date": "2026-05-14", "stat": {"gamesStarted": "1"}},
    ]}]}

    result = fetch_week_probables(
        week_start=week_start, week_end=week_end,
        pitcher_ids=[663556],
        http_get=_make_http_get({
            "schedule?sportId=1": schedule_payload,
            "people/663556?hydrate": people_payload,
            "people/663556/stats": gamelog_payload,
        }),
    )

    assert result.starts == {(663556, date(2026, 5, 24)): "BAL"}
