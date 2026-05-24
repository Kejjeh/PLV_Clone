"""Adapter for MLB Stats API + pure rotation-gap prediction.

See ADR-0002. The MLB Stats API fetch is the I/O wrapper around pure
functions that work on already-normalized data, so the bug-B
no-rotation-gap-fallback regression test can be written against
literals.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote

from plv_clone.cap_math import WeekProbables

_STATSAPI = "https://statsapi.mlb.com/api/v1"


def predict_rotation_starts(
    *,
    gamelog_dates: list[date],
    confirmed_dates: list[date],
    team_schedule: list[tuple[date, str]],
    week_start: date,
    week_end: date,
    anchor: date | None = None,
    n_predictions: int = 3,
) -> list[tuple[date, str]]:
    """Predict up to ``n_predictions`` rotation-gap starts in [week_start, week_end].

    Anchor (the date forward from which we count gaps) defaults to the later
    of (a) the latest actual gamelog start and (b) the latest confirmed start
    in the window. ESPN-confirmed future starts MUST advance the anchor or
    we double-emit a start the cap has already counted.

    ±1 day tolerance on both dedup (predicted date is "close enough" to a
    confirmed date) and team-schedule matching (predicted date can land on
    an adjacent team game).
    """
    if not gamelog_dates:
        return []
    last_actual = gamelog_dates[0]
    if len(gamelog_dates) >= 2:
        gap = max(4, min(7, (last_actual - gamelog_dates[1]).days))
    else:
        gap = 5  # single-start gamelog: default to 5-day rotation
    if anchor is None:
        anchor = max([last_actual] + list(confirmed_dates)) if confirmed_dates else last_actual
    sched = {d: opp for d, opp in team_schedule}
    out: list[tuple[date, str]] = []
    next_date = anchor
    for _ in range(n_predictions):
        next_date = next_date + timedelta(days=gap)
        if next_date > week_end:
            break
        # ±1 day dedup against confirmed
        if any(abs((next_date - cd).days) <= 1 for cd in confirmed_dates):
            continue
        # ±1 day tolerance for matching team schedule
        match: tuple[date, str] | None = None
        for offset in (0, 1, -1):
            cand = next_date + timedelta(days=offset)
            if week_start <= cand <= week_end and cand in sched:
                match = (cand, sched[cand])
                break
        if match is not None:
            out.append(match)
    return out


def _default_http_get(url: str, **_: Any):
    import requests
    return requests.get(url, timeout=15)


def resolve_mlbam(
    names: Iterable[str],
    *,
    http_get: Callable[..., Any] = _default_http_get,
) -> dict[str, int]:
    """Map names -> MLBAM IDs via the people-search endpoint.

    Names with no API match are omitted from the result. When multiple people
    match a name, prefers position='P' (the pitcher use case); falls back to
    the first match otherwise.
    """
    out: dict[str, int] = {}
    for name in names:
        url = f"{_STATSAPI}/people/search?names={quote(name)}"
        try:
            data = http_get(url).json()
        except Exception:
            continue
        people = data.get("people") or []
        if not people:
            continue
        pid: int | None = None
        for p in people[:5]:
            if (p.get("primaryPosition") or {}).get("abbreviation") == "P":
                pid = p.get("id")
                break
        if pid is None:
            pid = people[0].get("id")
        if pid is not None:
            out[name] = int(pid)
    return out


def fetch_week_probables(
    *,
    week_start: date,
    week_end: date,
    pitcher_ids: Iterable[int],
    http_get: Callable[..., Any] = _default_http_get,
) -> WeekProbables:
    """Confirmed probables + rotation-gap predictions, restricted to ``pitcher_ids``.

    Bug B's fix: a pitcher with no confirmed late-week probable still gets a
    prediction folded in via :func:`predict_rotation_starts` so downstream
    cap math doesn't undercount.
    """
    pitcher_set = {int(p) for p in pitcher_ids}
    sched_url = (
        f"{_STATSAPI}/schedule?sportId=1"
        f"&startDate={week_start.isoformat()}&endDate={week_end.isoformat()}"
        f"&hydrate=probablePitcher,team"
    )
    try:
        sched = http_get(sched_url).json()
    except Exception:
        sched = {"dates": []}

    confirmed: dict[tuple[int, date], str] = {}
    # pitcher_id -> list of (date, opp) for ALL their team's games in window
    team_schedule_by_pid: dict[int, list[tuple[date, str]]] = {p: [] for p in pitcher_set}
    confirmed_dates_by_pid: dict[int, list[date]] = {p: [] for p in pitcher_set}

    for date_block in sched.get("dates", []):
        for game in date_block.get("games", []):
            game_date = datetime.fromisoformat(
                game["gameDate"].replace("Z", "+00:00")
            ).date()
            if not (week_start <= game_date <= week_end):
                continue
            home = game.get("teams", {}).get("home", {}) or {}
            away = game.get("teams", {}).get("away", {}) or {}
            for self_side, opp_side in ((home, away), (away, home)):
                probable = self_side.get("probablePitcher") or {}
                pid = probable.get("id")
                if pid is None:
                    continue
                opp_team = (opp_side.get("team") or {}).get("abbreviation", "?").upper()
                if int(pid) in pitcher_set:
                    confirmed[(int(pid), game_date)] = opp_team
                    confirmed_dates_by_pid.setdefault(int(pid), []).append(game_date)
                # Also record team_schedule for each rostered pitcher whose
                # team is playing today (need team_id resolution below).

    # For rotation-gap prediction, each rostered pitcher needs (a) their
    # gamelog for prior actual starts and (b) their team's schedule in window.
    # We resolve (b) via a per-pitcher /people/{id}/stats?stats=statsSingleSeason
    # call would give current team — but the simpler path is: from the
    # schedule we already pulled, find any game where this pitcher is the
    # probable (gives us their team_id), then re-walk for that team's games.
    pid_team_id: dict[int, int] = {}
    for date_block in sched.get("dates", []):
        for game in date_block.get("games", []):
            for side_key in ("home", "away"):
                side = game.get("teams", {}).get(side_key, {}) or {}
                probable = side.get("probablePitcher") or {}
                pid = probable.get("id")
                if pid and int(pid) in pitcher_set:
                    pid_team_id[int(pid)] = (side.get("team") or {}).get("id")

    # Fallback: pitchers with no confirmed in-window start aren't resolved by
    # the schedule walk above (McClanahan case — Sunday probable not yet
    # posted). Hit /people/{id}?hydrate=currentTeam to pull their team_id.
    for pid in pitcher_set - pid_team_id.keys():
        try:
            person = http_get(
                f"{_STATSAPI}/people/{pid}?hydrate=currentTeam"
            ).json()
        except Exception:
            continue
        people = person.get("people") or []
        if not people:
            continue
        current_team = people[0].get("currentTeam") or {}
        tid = current_team.get("id")
        if tid is not None:
            pid_team_id[pid] = int(tid)

    # Build team-schedule lists for any pitcher we found a team for.
    for date_block in sched.get("dates", []):
        for game in date_block.get("games", []):
            game_date = datetime.fromisoformat(
                game["gameDate"].replace("Z", "+00:00")
            ).date()
            if not (week_start <= game_date <= week_end):
                continue
            home_team_id = ((game.get("teams", {}).get("home") or {}).get("team") or {}).get("id")
            away_team_id = ((game.get("teams", {}).get("away") or {}).get("team") or {}).get("id")
            home_abbr = ((game.get("teams", {}).get("home") or {}).get("team") or {}).get("abbreviation", "?").upper()
            away_abbr = ((game.get("teams", {}).get("away") or {}).get("team") or {}).get("abbreviation", "?").upper()
            for pid, tid in pid_team_id.items():
                if tid == home_team_id:
                    team_schedule_by_pid.setdefault(pid, []).append((game_date, away_abbr))
                elif tid == away_team_id:
                    team_schedule_by_pid.setdefault(pid, []).append((game_date, home_abbr))

    # Rotation-gap fill per pitcher.
    for pid in pitcher_set:
        log_url = (
            f"{_STATSAPI}/people/{pid}/stats?stats=gameLog&group=pitching"
            f"&season={week_start.year}"
        )
        try:
            log = http_get(log_url).json()
        except Exception:
            continue
        splits = ((log.get("stats") or [{}])[0]).get("splits") or []
        starts = [s for s in splits if int((s.get("stat") or {}).get("gamesStarted", "0")) > 0]
        if not starts:
            continue
        starts.sort(key=lambda s: s["date"], reverse=True)
        gamelog_dates = [datetime.fromisoformat(s["date"]).date() for s in starts]
        predicted = predict_rotation_starts(
            gamelog_dates=gamelog_dates,
            confirmed_dates=confirmed_dates_by_pid.get(pid, []),
            team_schedule=team_schedule_by_pid.get(pid, []),
            week_start=week_start, week_end=week_end,
        )
        for game_date, opp in predicted:
            confirmed.setdefault((pid, game_date), opp)

    return WeekProbables(starts=confirmed)
