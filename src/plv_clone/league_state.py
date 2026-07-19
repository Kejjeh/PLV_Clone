"""league_state — read-side league rules.

Owns the read-side surface for the BrownU league: my roster, all rosters,
free-agent pool, standings, and IL-slot arithmetic. Replaces
`app/espn_connector.py` as the *interface* callers reach for. Step 4 of
the architecture refactor (migrating consumers) is out of scope here —
`app/espn_connector.py` stays in place for now.

Structural negatives encoded in the class shape (load-bearing — see
`docs/adr/0004-league-state-omits-injured-players.md`):

  1. No ``injured_players()`` method. Callers who need the injury flag
     read ``my_roster()`` and filter ``injured==True`` themselves.
  2. No ``size=`` parameter on FA-querying methods. The default of 2000
     lives inside the method; callers cannot override.
  3. No public method returns unverified FAs. ``available_fa`` does the
     cross-team check internally — kills the Connelly Early bug class
     (`feedback_pl_rank_not_equal_fa_available.md`).
  4. ``il_slots()`` counts ``lineup_slot=='IL'`` — distinct from
     ``injured==True`` (`feedback_il_slot_vs_il_status.md`).

The class lazily authenticates against ESPN via `app/espn_connector`'s
existing `_get_league` so credentials, cookie-refresh hints, and the
``espn-api`` dependency keep one source of truth during the migration
window.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from plv_clone.cap_math import IL_SLOT_COUNT, RP_SLOT_CAP, SP_CAP  # noqa: F401  (CONTEXT.md)
from plv_clone.utils.name_match import fuzzy_match_name, merge_with_model

logger = logging.getLogger(__name__)

_HITTER_POSITIONS = frozenset({
    "C", "1B", "2B", "3B", "SS",
    "OF", "LF", "CF", "RF",
    "DH", "UT",
})
_PITCHER_POSITIONS = frozenset({"SP", "RP", "P"})

# ESPN baseball position-slot IDs (only used when filtering FAs by position).
_POS_SLOT_ID: dict[str, int] = {
    "C": 0, "1B": 2, "2B": 4, "3B": 5, "SS": 6,
    "OF": 7, "DH": 17, "SP": 14, "RP": 15, "P": 13,
}

_FA_POOL_SIZE: int = 2000
"""Unfiltered FA pool size. Internal — not a caller knob.

ESPN's per-position filter returns at most ``size`` candidates ranked by
ownership %, so low-owned high-FP candidates get silently dropped if a
smaller cap is used. See `feedback_fa_pool_size_cap.md`.
"""

# ── Per-process TTL cache (2026-07-04 audit: 4→1 ESPN roundtrips) ────────
#
# Keyed by (frame_name, id(league)) so injected test doubles never share
# entries with the real league (or with each other). Values are
# (monotonic_timestamp, DataFrame). Callers get a defensive .copy() so
# cached frames can't be mutated in place.

CACHE_TTL_SECONDS: float = 300.0
_TTL_CACHE: dict[tuple[str, int], tuple[float, pd.DataFrame]] = {}


def _cache_get(key: tuple[str, int]) -> pd.DataFrame | None:
    hit = _TTL_CACHE.get(key)
    if hit is None:
        return None
    ts, val = hit
    if time.monotonic() - ts > CACHE_TTL_SECONDS:
        _TTL_CACHE.pop(key, None)
        return None
    return val.copy()


def _cache_put(key: tuple[str, int], val: pd.DataFrame) -> None:
    _TTL_CACHE[key] = (time.monotonic(), val.copy())


def clear_ttl_cache() -> None:
    """Drop every cached frame (tests / force-refresh flows)."""
    _TTL_CACHE.clear()


def _schema_sentinel(df: pd.DataFrame) -> None:
    """espn-api schema-drift tripwire (audit 2026-07-04, quick win #9).

    After a roster walk, if NO player carries a nonempty ``lineup_slot``
    OR >10% of players have a null ``player_id``, the installed espn-api
    version has almost certainly renamed/moved the underlying attributes
    (``lineupSlot`` / ``playerId``) — every downstream IL-slot count and
    injury join would silently degrade. Fail loud instead.
    """
    if df.empty:
        return
    slots = df.get("lineup_slot")
    any_slot = bool(
        slots is not None and slots.astype(str).str.strip().ne("").any()
    )
    ids = df.get("player_id")
    null_id_frac = float(ids.isna().mean()) if ids is not None else 1.0
    if (not any_slot) or null_id_frac > 0.10:
        raise RuntimeError(
            "espn-api schema drift: roster walk returned "
            f"{'no nonempty lineup_slot values' if not any_slot else ''}"
            f"{' and ' if (not any_slot) and null_id_frac > 0.10 else ''}"
            f"{f'{null_id_frac:.0%} null player_id' if null_id_frac > 0.10 else ''}"
            " — check the installed espn-api version against the "
            "'espn-api>=0.35,<0.47' pin in pyproject.toml."
        )


class LeagueState:
    """Read-side facade over the BrownU ESPN league.

    Construct with no arguments to use the credentials in the environment
    (``ESPN_LEAGUE_ID`` / ``ESPN_SWID`` / ``ESPN_S2`` / ``ESPN_YEAR``).
    Pass ``league`` (an ``espn_api.baseball.League`` or test double) to
    inject a pre-authenticated client — used for unit tests so we never
    touch the real ESPN endpoints in CI.

    Pass ``my_team_hints`` to override the heuristic that identifies the
    user's team (default looks for "ligers" / "josh").
    """

    DEFAULT_TEAM_HINTS: tuple[str, ...] = ("ligers", "new york ligers", "josh")

    def __init__(
        self,
        league: object | None = None,
        *,
        my_team_hints: tuple[str, ...] | None = None,
    ) -> None:
        self._league = league
        self._team_hints = tuple(
            h.lower() for h in (my_team_hints or self.DEFAULT_TEAM_HINTS)
        )

    # ── Internal: lazy league handle ─────────────────────────────────────

    def _get_league(self) -> object:
        if self._league is None:
            from plv_clone.espn import _get_league as _factory
            self._league = _factory()
        return self._league

    def _find_my_team(self):
        league = self._get_league()
        for team in league.teams:
            owner = (getattr(team, "owner", "") or "").lower()
            tname = (getattr(team, "team_name", "") or "").lower()
            if any(h in tname for h in self._team_hints) or any(
                h in owner for h in self._team_hints
            ):
                return team
        logger.warning("Could not identify your team — defaulting to first team")
        return league.teams[0]

    # ── Rosters ──────────────────────────────────────────────────────────

    def my_roster(self, *, fresh: bool = False) -> pd.DataFrame:
        """DataFrame of players on the user's team.

        Columns: ``player_name``, ``player_id``, ``position``, ``pro_team``,
        ``eligible_slots``, ``lineup_slot``, ``injured``, ``injury_status``,
        ``on_team_name``.

        Callers who want only the injured subset filter ``injured==True``
        themselves. There is NO ``injured_players()`` convenience — see
        ADR-0004 for why the absence is the enforcement mechanism.

        Results are cached per-process for ``CACHE_TTL_SECONDS``; pass
        ``fresh=True`` to bypass and refresh the cache.
        """
        key = ("my_roster", id(self._get_league()))
        if not fresh:
            cached = _cache_get(key)
            if cached is not None:
                return cached
        my_team = self._find_my_team()
        rows = []
        for player in my_team.roster:
            rows.append({
                "player_name": player.name,
                "player_id": getattr(player, "playerId", None),
                "position": getattr(player, "position", ""),
                "pro_team": getattr(player, "proTeam", ""),
                "eligible_slots": getattr(player, "eligibleSlots", []),
                "lineup_slot": getattr(player, "lineupSlot", ""),
                "injured": bool(getattr(player, "injured", False)),
                "injury_status": getattr(player, "injuryStatus", "") or "",
                "on_team_name": getattr(my_team, "team_name", ""),
            })
        df = pd.DataFrame(rows)
        _schema_sentinel(df)
        _cache_put(key, df)
        return df

    def my_roster_with_injuries(self) -> pd.DataFrame:
        """``my_roster()`` + ESPN injury details merged on ``player_id``.

        Only fetches details for players where ``injured==True``; healthy
        rows come back with NaN injury fields after the left-join.
        """
        roster = self.my_roster()
        if roster.empty:
            return roster
        injured = roster[roster["injured"]]
        if injured.empty:
            return roster
        ids = injured["player_id"].dropna().astype(int).tolist()
        inj_df = self.injury_details(ids)
        if inj_df.empty:
            return roster
        return roster.merge(inj_df, on="player_id", how="left")

    def all_teams(self, *, fresh: bool = False) -> pd.DataFrame:
        """DataFrame of every team + roster across the league.

        Columns: ``team_name``, ``owner``, ``team_id``, ``player_name``,
        ``player_id``, ``position``, ``pro_team``, ``lineup_slot``,
        ``injured``, ``injury_status`` — a schema SUPERSET of
        ``app.espn_connector.get_all_teams()`` so importers can migrate
        without column-availability surprises (audit 2026-07-04). Used
        internally by ``available_fa`` to verify that ESPN's free-agent
        endpoint hasn't lagged.

        Results are cached per-process for ``CACHE_TTL_SECONDS``; pass
        ``fresh=True`` to bypass and refresh the cache.
        """
        league = self._get_league()
        key = ("all_teams", id(league))
        if not fresh:
            cached = _cache_get(key)
            if cached is not None:
                return cached
        rows = []
        for team in league.teams:
            for player in team.roster:
                rows.append({
                    "team_name": team.team_name,
                    "owner": getattr(team, "owner", ""),
                    "team_id": team.team_id,
                    "player_name": player.name,
                    "player_id": getattr(player, "playerId", None),
                    "position": getattr(player, "position", ""),
                    "pro_team": getattr(player, "proTeam", ""),
                    "lineup_slot": getattr(player, "lineupSlot", ""),
                    "injured": bool(getattr(player, "injured", False)),
                    "injury_status": getattr(player, "injuryStatus", "") or "",
                })
        df = pd.DataFrame(rows)
        _schema_sentinel(df)
        _cache_put(key, df)
        return df

    # ── IL accounting (slot, not status) ────────────────────────────────

    def il_slots(self, roster: pd.DataFrame | None = None) -> int:
        """Count roster positions where ``lineup_slot=='IL'``.

        Distinct from the ``injured`` flag: a player can be ``injured``
        while in their starting slot (Langford OF) or on the bench
        (Helsley BE), and counting ``injured==True`` as occupying an IL
        slot produces wrong free-capacity numbers. Pass an existing
        roster DataFrame to avoid a second API hit; omit to fetch fresh.
        """
        if roster is None:
            roster = self.my_roster()
        if roster.empty or "lineup_slot" not in roster.columns:
            return 0
        return int((roster["lineup_slot"] == "IL").sum())

    def il_slots_free(self, roster: pd.DataFrame | None = None) -> int:
        """Remaining IL-slot capacity (``IL_SLOT_COUNT`` minus used)."""
        return max(0, IL_SLOT_COUNT - self.il_slots(roster))

    # ── Free agents (size baked in, cross-team verified) ────────────────

    def available_fa(
        self, position: Optional[str] = None, *, fresh: bool = False
    ) -> pd.DataFrame:
        """Free agents *actually* available in the BrownU league.

        Pulls the unfiltered FA pool (``size=2000`` — internal default,
        not a caller knob) and then cross-references against every
        team's roster, dropping any name that appears as rostered. The
        cross-team filter is internal because skipping it caused the
        Connelly Early bug (recommending a stash that was already
        rostered elsewhere). See
        `feedback_pl_rank_not_equal_fa_available.md`.

        Args:
            position: Optional ESPN position string ("SP", "RP", "OF",
                etc.) to filter the unfiltered pool down to. ``None``
                returns all positions.

        The raw size=2000 pull is cached per-process for
        ``CACHE_TTL_SECONDS`` (position filtering and cross-team
        verification always run on top of the cached raw pool). Pass
        ``fresh=True`` to bypass and refresh the cache.

        Returns:
            DataFrame with columns ``player_name``, ``position``,
            ``pro_team``, ``percent_owned``, ``injured``, ``injury_status``
            (a schema superset of the legacy get_free_agents DataFrame).
        """
        league = self._get_league()
        key = ("fa_pool_raw", id(league))
        raw_df = None if fresh else _cache_get(key)

        if raw_df is None:
            # Always pull the full size=2000 pool. Position is applied as a
            # manual post-filter — never via per-position size=N calls,
            # because those silently truncate (feedback_fa_pool_size_cap.md).
            try:
                fas = league.free_agents(size=_FA_POOL_SIZE)
            except TypeError:
                # Old espn-api shim: drop the kwarg form
                fas = league.free_agents(_FA_POOL_SIZE)

            rows = []
            for player in fas:
                rows.append({
                    "player_name": player.name,
                    "position": getattr(player, "position", "") or "",
                    "pro_team": getattr(player, "proTeam", ""),
                    "percent_owned": getattr(player, "percent_owned", 0.0),
                    # injured/injury_status (item 11, 2026-07-04): additive columns
                    # so available_fa is a schema SUPERSET of the old get_free_agents
                    # DataFrame — unblocks migrating the boards that read `injured`.
                    "injured": bool(getattr(player, "injured", False)),
                    "injury_status": getattr(player, "injuryStatus", "") or "",
                })
            raw_df = pd.DataFrame(rows)
            _cache_put(key, raw_df)

        wanted_pos = position.upper() if position else None
        fa_df = raw_df
        if wanted_pos is not None and not fa_df.empty:
            fa_df = fa_df[fa_df["position"] == wanted_pos].reset_index(drop=True)
        if fa_df.empty:
            return fa_df

        # Cross-team verification — drop any name that's actually rostered.
        # Without this, ESPN's FA endpoint can lag and surface "available"
        # players that another team already grabbed.
        rostered = self.all_teams(fresh=fresh)
        if not rostered.empty and "player_name" in rostered.columns:
            rostered_names = set(rostered["player_name"].dropna().tolist())
            fa_df = fa_df[~fa_df["player_name"].isin(rostered_names)].reset_index(
                drop=True
            )

        return fa_df

    # ── Meaningful-batter / meaningful-SP filters ───────────────────────

    _HITTERS_MULTIYR_PATH: str = (
        "data/research/xfp_cache/hitters_multiyr_2015_2026.csv"
    )
    _SP_MULTIYR_PATH: str = "data/research/xfp_cache/sp_multiyr_2015_2025.csv"

    def available_fa_meaningful(
        self,
        min_2026_pa: int = 100,
        min_career_pa: int = 300,
        position: Optional[str] = None,
        *,
        multiyr: pd.DataFrame | None = None,
        multiyr_path: str | None = None,
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        """``available_fa`` filtered to meaningful hitters.

        Drops zero-PA callups / retired / fringe names that bloat sweep
        skills (~6x speedup on the FA hitter pool). A player is kept if
        EITHER:

          * ≥ ``min_2026_pa`` PA in the 2026 season (active this year), OR
          * ≥ ``min_career_pa`` total career PA across all years (an
            established veteran whose 2026 sample is just small so far).

        Players whose names can't be resolved against the hitters multiyr
        cache (after `resolve_batter_id` fallback) are DROPPED — they're
        almost always non-hitter pitchers, retired players, or names
        that won't join any model output anyway.

        Returns:
            ``(df_filtered, summary)`` where ``summary`` is a dict with
            ``input_n``, ``kept``, ``dropped_no_pa``, ``dropped_unresolved``.
        """
        fa = self.available_fa(position=position)
        input_n = int(len(fa))
        if fa.empty:
            return fa, {
                "input_n": 0, "kept": 0,
                "dropped_no_pa": 0, "dropped_unresolved": 0,
            }

        if multiyr is None:
            path = multiyr_path or self._HITTERS_MULTIYR_PATH
            multiyr = pd.read_csv(path)

        # Per-batter aggregates: career PA total + 2026 PA.
        career_pa = (
            multiyr.groupby("player_name")["pa"].sum().to_dict()
            if "pa" in multiyr.columns else {}
        )
        cur_pa: dict[str, int] = {}
        if "year" in multiyr.columns and "pa" in multiyr.columns:
            cur = multiyr[multiyr["year"] == 2026]
            cur_pa = cur.groupby("player_name")["pa"].sum().to_dict()

        kept_rows = []
        dropped_no_pa = 0
        dropped_unresolved = 0
        for _, row in fa.iterrows():
            name = row["player_name"]
            if name in career_pa or name in cur_pa:
                c = float(career_pa.get(name, 0))
                y = float(cur_pa.get(name, 0))
                if y >= min_2026_pa or c >= min_career_pa:
                    kept_rows.append(row)
                else:
                    dropped_no_pa += 1
            else:
                # Try the disambiguating resolver as a fallback for names
                # the raw groupby missed (accents, suffix differences).
                try:
                    from plv_clone.utils.name_match import resolve_batter_id

                    bid = resolve_batter_id(
                        name,
                        team=row.get("pro_team"),
                        position=row.get("position"),
                        multiyr=multiyr,
                    )
                except Exception:
                    bid = None
                if bid is None:
                    dropped_unresolved += 1
                    continue
                sub = multiyr[multiyr["batter"] == bid] if "batter" in multiyr.columns else None
                if sub is None or sub.empty:
                    dropped_unresolved += 1
                    continue
                c = float(sub["pa"].sum()) if "pa" in sub.columns else 0.0
                y = float(
                    sub[sub.get("year", -1) == 2026]["pa"].sum()
                ) if "pa" in sub.columns and "year" in sub.columns else 0.0
                if y >= min_2026_pa or c >= min_career_pa:
                    kept_rows.append(row)
                else:
                    dropped_no_pa += 1

        kept_df = pd.DataFrame(kept_rows).reset_index(drop=True)
        summary = {
            "input_n": input_n,
            "kept": int(len(kept_df)),
            "dropped_no_pa": int(dropped_no_pa),
            "dropped_unresolved": int(dropped_unresolved),
        }
        return kept_df, summary

    def available_fa_meaningful_sp(
        self,
        min_2026_starts: int = 2,
        min_career_starts: int = 10,
        position: str = "SP",
        *,
        multiyr: pd.DataFrame | None = None,
        multiyr_path: str | None = None,
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        """SP analogue of :meth:`available_fa_meaningful`.

        A pitcher is kept if EITHER:

          * ≥ ``min_2026_starts`` game starts in 2026, OR
          * ≥ ``min_career_starts`` total career starts.

        Uses the SP multiyr cache (``gs`` column for starts). Names that
        don't appear in the cache are dropped as unresolved.
        """
        fa = self.available_fa(position=position)
        input_n = int(len(fa))
        if fa.empty:
            return fa, {
                "input_n": 0, "kept": 0,
                "dropped_no_pa": 0, "dropped_unresolved": 0,
            }

        if multiyr is None:
            path = multiyr_path or self._SP_MULTIYR_PATH
            multiyr = pd.read_csv(path)

        starts_col = "gs" if "gs" in multiyr.columns else None
        career_gs = (
            multiyr.groupby("player_name")[starts_col].sum().to_dict()
            if starts_col else {}
        )
        cur_gs: dict[str, float] = {}
        if "year" in multiyr.columns and starts_col:
            cur = multiyr[multiyr["year"] == 2026]
            cur_gs = cur.groupby("player_name")[starts_col].sum().to_dict()

        kept_rows = []
        dropped_no_pa = 0
        dropped_unresolved = 0
        for _, row in fa.iterrows():
            name = row["player_name"]
            if name not in career_gs and name not in cur_gs:
                dropped_unresolved += 1
                continue
            c = float(career_gs.get(name, 0))
            y = float(cur_gs.get(name, 0))
            if y >= min_2026_starts or c >= min_career_starts:
                kept_rows.append(row)
            else:
                dropped_no_pa += 1

        kept_df = pd.DataFrame(kept_rows).reset_index(drop=True)
        summary = {
            "input_n": input_n,
            "kept": int(len(kept_df)),
            "dropped_no_pa": int(dropped_no_pa),
            "dropped_unresolved": int(dropped_unresolved),
        }
        return kept_df, summary

    # ── Standings ────────────────────────────────────────────────────────

    def standings(self) -> pd.DataFrame:
        """Current win/loss + points record for every team."""
        league = self._get_league()
        rows = []
        for team in league.teams:
            rows.append({
                "team_name": team.team_name,
                "owner": getattr(team, "owner", ""),
                "team_id": team.team_id,
                "wins": getattr(team, "wins", 0),
                "losses": getattr(team, "losses", 0),
                "ties": getattr(team, "ties", 0),
                "points_for": getattr(team, "points_for", 0.0),
                "points_against": getattr(team, "points_against", 0.0),
            })
        df = pd.DataFrame(rows)
        if not df.empty and "wins" in df.columns:
            df = df.sort_values("wins", ascending=False).reset_index(drop=True)
        return df

    # ── Injury details (ESPN public athlete endpoint) ───────────────────

    def injury_details(self, player_ids: list[int]) -> pd.DataFrame:
        """Fetch structured injury info for a list of ESPN player IDs.

        Uses ESPN's public athlete endpoint (no auth required). Players
        with no current injury record come back with NaN fields.

        Snapshot read-through (audit 2026-07-19 F3): when PLV_ESPN_SNAPSHOT=1
        (set only by the refresh_dashboards driver), per-player records are
        served from a short-TTL accumulating JSON cache so the ~4 refresh
        steps that each sweep the injured subset (~30-80 HTTP GETs apiece)
        share one fetch per player per run. days_until_return is recomputed
        from the cached return_date at read time. Fail-open: any cache
        problem falls through to the live fetch. Interactive use (env var
        unset) is unaffected.
        """
        import json as _json
        import os as _os
        import time as _time
        import requests
        from datetime import date, datetime

        _snap_on = _os.environ.get("PLV_ESPN_SNAPSHOT") == "1"
        _ttl_s = float(_os.environ.get("PLV_ESPN_SNAPSHOT_TTL_MIN", "180")) * 60
        _snap_path = (Path(__file__).resolve().parents[2]
                      / "data" / "research" / "espn_snapshot" / "injury_details.json")
        _snap: dict = {}
        if _snap_on:
            try:
                if _snap_path.exists():
                    _snap = _json.loads(_snap_path.read_text(encoding="utf-8"))
            except Exception:
                _snap = {}

        def _row_from_snap(entry):
            row = dict(entry["row"])
            rd = row.get("return_date")
            if rd:
                try:
                    rdt = datetime.fromisoformat(rd).date()
                    row["return_date"] = rdt
                    row["days_until_return"] = (rdt - date.today()).days
                except Exception:
                    row["return_date"] = None
            return row

        _fetched_any = False
        rows = []
        for pid in player_ids:
            if pid is None:
                continue
            if _snap_on:
                entry = _snap.get(str(pid))
                if entry and (_time.time() - float(entry.get("ts", 0))) < _ttl_s:
                    rows.append(_row_from_snap(entry))
                    continue
            url = (
                "https://site.web.api.espn.com/apis/common/v3/sports/baseball/mlb/"
                f"athletes/{pid}"
            )
            try:
                r = requests.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                data = r.json()
            except Exception as e:
                logger.warning("injury fetch failed for %s: %s", pid, e)
                continue

            athlete = data.get("athlete", {}) or {}
            injuries = athlete.get("injuries", []) or []
            if not injuries:
                rows.append({"player_id": pid})
                if _snap_on:
                    _snap[str(pid)] = {"ts": _time.time(), "row": {"player_id": pid}}
                    _fetched_any = True
                continue

            inj = injuries[0]
            details = inj.get("details", {}) or {}
            return_iso = details.get("returnDate") or inj.get("returnDate")
            return_dt = None
            days_out = None
            if return_iso:
                try:
                    return_dt = datetime.fromisoformat(
                        return_iso.replace("Z", "+00:00")
                    ).date()
                    days_out = (return_dt - date.today()).days
                except Exception:
                    pass

            row = {
                "player_id": pid,
                "injury_type": details.get("type")
                or inj.get("type", {}).get("description", ""),
                "injury_detail": details.get("detail", ""),
                "injury_side": details.get("side", ""),
                "return_date": return_dt,
                "days_until_return": days_out,
                "status_code": (inj.get("type", {}) or {}).get("abbreviation", ""),
                "short_comment": inj.get("shortComment", ""),
                "long_comment": inj.get("longComment", ""),
            }
            rows.append(row)
            if _snap_on:
                srow = dict(row)
                srow["return_date"] = return_dt.isoformat() if return_dt else None
                _snap[str(pid)] = {"ts": _time.time(), "row": srow}
                _fetched_any = True

        if _snap_on and _fetched_any:
            try:
                _snap_path.parent.mkdir(parents=True, exist_ok=True)
                _snap_path.write_text(_json.dumps(_snap), encoding="utf-8")
            except Exception:
                pass

        return pd.DataFrame(rows)


_DEFAULT_STATE: LeagueState | None = None


def default_state() -> LeagueState:
    """Shared per-process ``LeagueState`` for script call-sites.

    Scripts migrating off ``app.espn_connector`` should use this instead
    of constructing ad-hoc instances, so the TTL cache and the lazily
    authenticated league handle are shared across every call-site in the
    process.
    """
    global _DEFAULT_STATE
    if _DEFAULT_STATE is None:
        _DEFAULT_STATE = LeagueState()
    return _DEFAULT_STATE


__all__ = [
    "LeagueState",
    "default_state",
    "clear_ttl_cache",
    "CACHE_TTL_SECONDS",
    "fuzzy_match_name",
    "merge_with_model",
    "IL_SLOT_COUNT",
    "RP_SLOT_CAP",
    "SP_CAP",
]
