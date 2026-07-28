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
    n_predictions: int = 2,
    with_meta: bool = False,
) -> list[tuple[date, str]] | list[tuple[date, str, dict]]:
    """Predict up to ``n_predictions`` rotation-gap starts in [week_start, week_end].

    ``with_meta`` appends a ``{"slide", "gap"}`` dict to each tuple. Callers that
    aggregate ACROSS pitchers need it to break team-game collisions: this
    function is pure and per-pitcher, so it cannot know another pitcher was
    already predicted into the same team-game (#10).

    Anchor (the date forward from which we count gaps) defaults to the later
    of (a) the latest actual gamelog start and (b) the latest confirmed start
    in the window. ESPN-confirmed future starts MUST advance the anchor or
    we double-emit a start the cap has already counted.

    Gap is derived from the MINIMUM of the last three inter-start intervals so
    that off-days or travel days don't inflate the estimate (e.g. Valdez
    May 18→24 = 6d, but typical gap is 5d — the min of recent intervals).

    ±1 day tolerance for team-schedule matching (predicted date can land on an
    adjacent team game). After a ±1 slide the loop anchor advances from the
    *matched* date, not the pre-slide date — this prevents double-predictions
    (the original bug that gave Rodon two false starts: May 26 slid to May 27,
    then May 26+5=May 31 fired a second prediction).
    """
    if not gamelog_dates:
        return []
    last_actual = gamelog_dates[0]
    # Use the MINIMUM of up to 3 recent inter-start gaps (clamped 4–7).
    # Minimum is more conservative: off-days inflate the last gap but the
    # pitcher's underlying rotation cadence is the shorter intervals.
    if len(gamelog_dates) >= 2:
        intervals = [(gamelog_dates[i] - gamelog_dates[i + 1]).days
                     for i in range(min(5, len(gamelog_dates) - 1))]
        # Intervals > 7d are not rotation cadence — they are IL stints, the
        # All-Star break, or a skipped turn. Drop them, then take the MEDIAN of
        # what remains. Taking min() over a raw 3-window let a single ASG or
        # IL-inflated log poison the estimate downward: Henderson's last three
        # were [5, 8, 48] -> min 5, but his true cadence is 6, which put him a
        # day early and manufactured a start inside the period (#10).
        clean = [g for g in intervals if 4 <= g <= 7]
        if clean:
            gap = max(4, min(7, sorted(clean)[len(clean) // 2]))
        else:
            gap = max(4, min(7, min(intervals)))
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
            if with_meta:
                out.append((match[0], match[1],
                            {"slide": abs((match[0] - next_date).days), "gap": gap}))
            else:
                out.append(match)
            # Advance the anchor to the MATCHED date (not the pre-slide
            # next_date) so the next iteration doesn't re-fire from the
            # wrong base and produce a double-prediction.
            next_date = match[0]
    return out


def _default_http_get(url: str, **_: Any):
    """3-attempt exponential backoff (pattern from refresh_boxscores). One MLB
    blip must not poison a process-lifetime cache (audit 2026-07-04)."""
    import time as _time
    import requests
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001 — retried, then re-raised
            last = e
            if attempt < 2:
                _time.sleep(1.5 ** attempt)
    raise last


# ── Probable-pitcher slate (OWNER — audit 2026-07-04) ─────────────────────────
# The raw "every probable in a date window" fetch was re-implemented in 8+
# modules (build_matchup_dashboard, extra_lenses, stream_the_stack,
# weekly_schedule, lineup_optimizer, build_pitcher_schedule, the two
# hitter_boom_stack builders, run_streamer_board) — and was rebuilt ad-hoc 4x
# in one session. This is the single owner; callers must not re-implement the
# schedule?hydrate=probablePitcher dance. Distinct from fetch_week_probables
# (roster-scoped cap math with rotation-gap predictions).

_TEAM_ABBR_CACHE: dict[int, str] = {}
_PROBABLES_CACHE: dict[tuple[str, str], list[dict]] = {}


def _team_abbr_map(http_get: Callable[..., Any] = _default_http_get) -> dict[int, str]:
    if not _TEAM_ABBR_CACHE:
        try:
            j = http_get(f"{_STATSAPI}/teams?sportId=1").json()
            for t in j.get("teams", []):
                _TEAM_ABBR_CACHE[int(t["id"])] = t.get("abbreviation", "?")
        except Exception:
            pass
    return _TEAM_ABBR_CACHE


def get_probables(
    start_date: date | str,
    end_date: date | str,
    *,
    http_get: Callable[..., Any] = _default_http_get,
    use_cache: bool = True,
) -> list[dict]:
    """Every probable-pitcher slot in [start_date, end_date], one dict per
    (game, side):

        {date, pitcher_id, pitcher_name, team_abbr, opp_abbr, park_abbr,
         game_pk, game_state}   # game_state: Preview/Live/Final

    park_abbr is the HOME team (feed straight into extra_lenses.park_fp_adj).
    Cached per (start, end) within the process; pass use_cache=False to force.
    """
    s = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
    e = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
    key = (s, e)
    if use_cache and key in _PROBABLES_CACHE:
        return _PROBABLES_CACHE[key]
    abbr = _team_abbr_map(http_get)
    url = (f"{_STATSAPI}/schedule?sportId=1&startDate={s}&endDate={e}"
           f"&hydrate=probablePitcher,team")
    fetched_ok = True
    try:
        sched = http_get(url).json()
    except Exception as exc:  # fail-soft, but LOUD and UNCACHED
        import sys as _sys
        print(f"WARN get_probables({s}..{e}): fetch failed after retries — {exc}; "
              "returning empty slate (NOT cached)", file=_sys.stderr)
        sched = {"dates": []}
        fetched_ok = False
    out: list[dict] = []
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {}).get("team", {}) or {}
            away = teams.get("away", {}).get("team", {}) or {}
            hab = home.get("abbreviation") or abbr.get(int(home.get("id", -1)), "?")
            aab = away.get("abbreviation") or abbr.get(int(away.get("id", -1)), "?")
            state = g.get("status", {}).get("abstractGameState", "")
            for side, own_ab, opp_ab in (("home", hab, aab), ("away", aab, hab)):
                pp = teams.get(side, {}).get("probablePitcher", {}) or {}
                if not pp.get("id"):
                    continue
                out.append({
                    "date": d.get("date"),
                    "pitcher_id": int(pp["id"]),
                    "pitcher_name": pp.get("fullName", ""),
                    "team_abbr": own_ab,
                    "opp_abbr": opp_ab,
                    "park_abbr": hab,
                    "game_pk": g.get("gamePk"),
                    "game_state": state,
                })
    if use_cache and fetched_ok:
        # cache only SUCCESSFUL fetches — an API blip must not become a
        # process-lifetime empty slate indistinguishable from an off-day
        _PROBABLES_CACHE[key] = out
    return out


_SCHEDULE_CACHE: dict[tuple[str, str], list[dict]] = {}


def get_schedule(
    start_date: date | str,
    end_date: date | str,
    *,
    http_get: Callable[..., Any] = _default_http_get,
    use_cache: bool = True,
) -> list[dict]:
    """Every scheduled game in [start_date, end_date] — INCLUDING games with no
    posted probable pitcher — one dict per game:

        {date, game_pk, game_type, game_state, venue_name,
         home_id, away_id, home_abbr, away_abbr,
         home_probable_id, home_probable_name,
         away_probable_id, away_probable_name}

    Companion to :func:`get_probables` (which emits one row per *probable* and
    skips games/sides with no probable). This is the owner for the "all games,
    incl. no-probable, with venue/team names" fetch that weekly_schedule,
    build_pitcher_schedule, extra_lenses._upcoming_schedule and the two
    hitter_boom_stack builders each re-implemented. game_type is the raw MLB
    code ('R' regular, 'F'/'D'/'L'/'W' postseason, 'S' spring) — callers filter.
    Cached per (start, end) within the process; only successful fetches cache.
    """
    s = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
    e = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
    key = (s, e)
    if use_cache and key in _SCHEDULE_CACHE:
        return _SCHEDULE_CACHE[key]
    abbr = _team_abbr_map(http_get)
    url = (f"{_STATSAPI}/schedule?sportId=1&startDate={s}&endDate={e}"
           f"&hydrate=probablePitcher,team,venue")
    fetched_ok = True
    try:
        sched = http_get(url).json()
    except Exception as exc:  # fail-soft, but LOUD and UNCACHED
        import sys as _sys
        print(f"WARN get_schedule({s}..{e}): fetch failed after retries — {exc}; "
              "returning empty schedule (NOT cached)", file=_sys.stderr)
        sched = {"dates": []}
        fetched_ok = False
    out: list[dict] = []
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {}) or {}
            away = teams.get("away", {}) or {}
            home_t = home.get("team", {}) or {}
            away_t = away.get("team", {}) or {}
            home_id = home_t.get("id")
            away_id = away_t.get("id")
            hab = home_t.get("abbreviation") or abbr.get(int(home_id) if home_id else -1, "?")
            aab = away_t.get("abbreviation") or abbr.get(int(away_id) if away_id else -1, "?")
            hp = home.get("probablePitcher") or {}
            ap = away.get("probablePitcher") or {}
            out.append({
                "date": d.get("date"),
                "game_pk": g.get("gamePk"),
                "game_type": g.get("gameType"),
                "game_state": g.get("status", {}).get("abstractGameState", ""),
                "venue_name": (g.get("venue") or {}).get("name"),
                "home_id": int(home_id) if home_id else None,
                "away_id": int(away_id) if away_id else None,
                "home_abbr": hab,
                "away_abbr": aab,
                "home_probable_id": int(hp["id"]) if hp.get("id") else None,
                "home_probable_name": hp.get("fullName"),
                "away_probable_id": int(ap["id"]) if ap.get("id") else None,
                "away_probable_name": ap.get("fullName"),
            })
    if use_cache and fetched_ok:
        _SCHEDULE_CACHE[key] = out
    return out


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
    # Keys that came directly from MLB's confirmed probable list (not rotation-gap)
    mlb_confirmed_keys: set[tuple[int, date]] = set()
    # pitcher_id -> list of (date, opp) for ALL their team's games in window
    team_schedule_by_pid: dict[int, list[tuple[date, str]]] = {p: [] for p in pitcher_set}
    confirmed_dates_by_pid: dict[int, list[date]] = {p: [] for p in pitcher_set}

    for date_block in sched.get("dates", []):
        for game in date_block.get("games", []):
            # BLOCK date = actual ET game day. game["gameDate"] is a UTC
            # instant, which rolls to tomorrow for evening-ET first pitches and
            # pushes a period's final-day starts out of the cap window (#10).
            game_date = date.fromisoformat(date_block["date"])
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
                    mlb_confirmed_keys.add((int(pid), game_date))
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
            # BLOCK date = actual ET game day. game["gameDate"] is a UTC
            # instant, which rolls to tomorrow for evening-ET first pitches and
            # pushes a period's final-day starts out of the cap window (#10).
            game_date = date.fromisoformat(date_block["date"])
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

    # Rotation-gap fill per pitcher. Predictions are COLLECTED first, then
    # resolved to at most one per team-game below — predict_rotation_starts is
    # pure and per-pitcher, so nothing inside it can see that another pitcher
    # was already predicted into the same game (#10).
    pred_rows: list[dict] = []
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
            with_meta=True,
        )
        for game_date, opp, meta in predicted:
            pred_rows.append({"pid": pid, "date": game_date, "opp": opp,
                              "tid": pid_team_id.get(pid),
                              "slide": meta["slide"], "gap": meta["gap"]})

    # One starter per team-game. A team-date already held by an MLB-confirmed
    # probable is closed to predictions; among competing predictions the
    # least-speculative wins — no +/-1 slide first, then the shorter inferred
    # rotation gap, then pitcher id purely so the result is deterministic.
    taken: set[tuple[int, date]] = {
        (pid_team_id[p], d) for (p, d) in mlb_confirmed_keys if p in pid_team_id
    }
    for r in sorted(pred_rows, key=lambda r: (r["slide"], r["gap"], r["pid"])):
        key = (r["tid"], r["date"])
        if r["tid"] is not None:
            if key in taken:
                continue
            taken.add(key)
        confirmed.setdefault((r["pid"], r["date"]), r["opp"])

    return WeekProbables(starts=confirmed, confirmed_keys=frozenset(mlb_confirmed_keys))
