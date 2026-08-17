"""
espn_connector.py — ESPN Fantasy Baseball API integration for plv_clone dashboard.

Uses the espn-api library (pip install espn-api) with cookie-based auth
for private league access.

League: BrownU and Friends
League ID: 24080
Year: 2026
"""

from __future__ import annotations

import difflib
import logging
from functools import lru_cache
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── ESPN auth (moved to plv_clone.espn; re-exported here for back-compat) ──────
# Auth + the raw League factory now live in the package (plv_clone/espn.py) so
# league_state and scripts depend on one home. Re-exported here so this module's
# existing importers and the higher-level helpers below are unaffected. The
# re-exported `_get_league` is the same lru_cached object (cache_clear() works).
from plv_clone.espn import (  # noqa: F401
    _get_league,
    _AUTH_ERROR_HINTS,
    LEAGUE_ID,
    YEAR,
    SWID,
    ESPN_S2,
)


# ── Player name normalisation ─────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """Lowercase, strip accents naively, remove suffixes, normalize
    'Last, First' → 'First Last' for fuzzy matching."""
    import unicodedata
    if not isinstance(name, str):
        return ""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    # Normalize "Last, First" → "First Last" (common in projection CSVs)
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            name = f"{parts[1]} {parts[0]}"
    for suffix in [" jr.", " jr", " ii", " iii", " iv", " sr.", " sr"]:
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name.lower().strip()


def fuzzy_match_name(
    espn_name: str,
    model_names: list[str],
    cutoff: float = 0.78,
) -> Optional[str]:
    """Return best fuzzy match from model_names for an ESPN player name."""
    norm_espn = _normalize(espn_name)
    norm_model = {_normalize(n): n for n in model_names}
    matches = difflib.get_close_matches(
        norm_espn, list(norm_model.keys()), n=1, cutoff=cutoff
    )
    if matches:
        return norm_model[matches[0]]
    return None


def merge_with_model(
    espn_df: pd.DataFrame,
    model_df: pd.DataFrame,
    model_name_col: str = "player_name",
    cutoff: float = 0.78,
) -> pd.DataFrame:
    """
    Left-join ESPN player list onto model_df by fuzzy name matching.
    Adds a `model_name` column showing the matched name (or NaN if no match).
    """
    model_names = model_df[model_name_col].tolist()
    espn_df = espn_df.copy()
    espn_df["model_name"] = espn_df["player_name"].apply(
        lambda n: fuzzy_match_name(n, model_names, cutoff=cutoff)
    )
    matched = espn_df.dropna(subset=["model_name"])
    merged = matched.merge(
        model_df,
        left_on="model_name",
        right_on=model_name_col,
        how="left",
        suffixes=("_espn", ""),
    )
    return merged


# ── Core API fetchers ─────────────────────────────────────────────────────────

def get_my_roster() -> pd.DataFrame:
    """
    Return DataFrame of players on YOUR team (BrownU and Friends, team owned by Josh).

    Columns: player_name, position, pro_team, eligible_slots, lineup_slot,
             on_team_name
    """
    league = _get_league()
    # Find your team — owner name or team name match
    my_team = None
    for team in league.teams:
        owner = getattr(team, "owner", "") or ""
        tname = getattr(team, "team_name", "") or ""
        if "ligers" in tname.lower() or "new york ligers" in tname.lower() or "josh" in owner.lower():
            my_team = team
            break

    if my_team is None:
        logger.warning("Could not identify your team — using team_id=1")
        my_team = league.teams[0]

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
            "on_team_name": my_team.team_name,
        })
    return pd.DataFrame(rows)


def get_injury_details(player_ids: list[int]) -> pd.DataFrame:
    """
    Fetch structured injury details (type, side, expected return date, blurb)
    from ESPN's public athlete endpoint for a list of player IDs.

    No auth needed — uses site.web.api.espn.com which is public.

    Returns DataFrame with: player_id, injury_type, injury_detail, injury_side,
                            return_date (date), days_until_return, status_code,
                            short_comment, long_comment.
    Players with no current injury are returned with NaN injury fields.
    """
    import requests
    from datetime import date, datetime

    rows = []
    for pid in player_ids:
        if pid is None:
            continue
        url = f"https://site.web.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{pid}"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception as e:
            logger.warning(f"injury fetch failed for {pid}: {e}")
            continue

        athlete = data.get("athlete", {}) or {}
        injuries = athlete.get("injuries", []) or []
        if not injuries:
            rows.append({"player_id": pid})
            continue

        # Take the most recent injury (first in list per ESPN ordering)
        inj = injuries[0]
        details = inj.get("details", {}) or {}
        return_iso = details.get("returnDate") or inj.get("returnDate")
        return_dt = None
        days_out = None
        if return_iso:
            try:
                return_dt = datetime.fromisoformat(return_iso.replace("Z", "+00:00")).date()
                days_out = (return_dt - date.today()).days
            except Exception:
                pass

        rows.append({
            "player_id": pid,
            "injury_type": details.get("type") or inj.get("type", {}).get("description", ""),
            "injury_detail": details.get("detail", ""),
            "injury_side": details.get("side", ""),
            "return_date": return_dt,
            "days_until_return": days_out,
            "status_code": (inj.get("type", {}) or {}).get("abbreviation", ""),
            "short_comment": inj.get("shortComment", ""),
            "long_comment": inj.get("longComment", ""),
        })

    return pd.DataFrame(rows)


def get_my_roster_with_injuries() -> pd.DataFrame:
    """Convenience: get_my_roster + injury details merged on player_id."""
    roster = get_my_roster()
    if roster.empty:
        return roster
    injured = roster[roster["injured"]]
    if injured.empty:
        return roster
    inj_df = get_injury_details(injured["player_id"].dropna().astype(int).tolist())
    if inj_df.empty:
        return roster
    return roster.merge(inj_df, on="player_id", how="left")


def get_all_teams() -> pd.DataFrame:
    """
    Return DataFrame of all teams and their rosters.

    Columns: team_name, owner, team_id, player_name, player_id, position,
             pro_team, lineup_slot, injured, injury_status
    """
    league = _get_league()
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
    return pd.DataFrame(rows)


def get_free_agents(
    position: Optional[str] = None,
    size: int = 200,
) -> pd.DataFrame:
    """
    Return DataFrame of free agents available in your league.

    Args:
        position: ESPN position string, e.g. "SP", "RP", "C", "1B", "OF".
                  None = all positions.
        size: max number of free agents to return.

    Columns: player_name, position, pro_team, percent_owned
    """
    league = _get_league()

    # ESPN position IDs for baseball
    _pos_map = {
        "C": 0, "1B": 2, "2B": 4, "3B": 5, "SS": 6,
        "OF": 7, "DH": 17, "SP": 14, "RP": 15, "P": 13,
    }

    kwargs: dict = {"size": size}
    if position and position.upper() in _pos_map:
        kwargs["position_id"] = _pos_map[position.upper()]

    try:
        fas = league.free_agents(**kwargs)
    except TypeError:
        # Older espn-api versions don't support position_id
        fas = league.free_agents(size=size)

    rows = []
    for player in fas:
        pos = getattr(player, "position", "")
        # Filter manually if position_id not supported
        if position and pos != position.upper():
            continue
        rows.append({
            "player_name": player.name,
            "position": pos,
            "pro_team": getattr(player, "proTeam", ""),
            "percent_owned": getattr(player, "percent_owned", 0.0),
        })
    return pd.DataFrame(rows)


def get_league_standings() -> pd.DataFrame:
    """
    Return current standings / win-loss record for all teams.

    Columns: team_name, owner, wins, losses, ties, points_for, points_against
    """
    league = _get_league()
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


# ── Convenience: available players cross-referenced with model ────────────────

def get_available_targets(
    model_hitters: pd.DataFrame,
    model_pitchers: pd.DataFrame,
    size: int = 2000,
    min_signal_rank: int = 0,
) -> dict[str, pd.DataFrame]:
    """
    Return {hitters: DataFrame, pitchers: DataFrame} of available free agents
    merged with plv_clone model data, sorted by signal tier.

    Args:
        model_hitters: master_hitter_2026 DataFrame (must have player_name, signal, proc_plus_positional)
        model_pitchers: pitcher_fantasy_2026 DataFrame (must have player_name, signal, plv_blended)
        size: max free agents to fetch from ESPN
        min_signal_rank: 0=all, 1=Pass+, 2=Watchlist+, 3=StrongAdd+, 4=TopTarget only
    """
    _signal_order = {"Top Target": 4, "Strong Add": 3, "Watchlist": 2, "Pass": 1, "Too Small": 0}
    _tier_floor = {0: "", 1: "Pass", 2: "Watchlist", 3: "Strong Add", 4: "Top Target"}
    floor_label = _tier_floor.get(min_signal_rank, "")

    fa_df = get_free_agents(size=size)
    if fa_df.empty:
        return {"hitters": pd.DataFrame(), "pitchers": pd.DataFrame()}

    # Split by position type
    pitcher_positions = {"SP", "RP", "P"}
    fa_hitters = fa_df[~fa_df["position"].isin(pitcher_positions)].copy()
    fa_pitchers = fa_df[fa_df["position"].isin(pitcher_positions)].copy()

    def _merge_and_sort(fa: pd.DataFrame, model: pd.DataFrame, sort_col: str) -> pd.DataFrame:
        merged = merge_with_model(fa, model, model_name_col="player_name")
        if merged.empty:
            return merged
        if "signal" in merged.columns:
            merged["_signal_rank"] = merged["signal"].map(_signal_order).fillna(0)
            if floor_label:
                merged = merged[merged["_signal_rank"] >= _signal_order.get(floor_label, 0)]
            merged = merged.sort_values(["_signal_rank", sort_col], ascending=[False, False])
            merged = merged.drop(columns=["_signal_rank"])
        return merged.reset_index(drop=True)

    hit_col = "proc_plus_positional" if "proc_plus_positional" in model_hitters.columns else "process_plus"
    pit_col = "plv_blended" if "plv_blended" in model_pitchers.columns else "plv"

    return {
        "hitters": _merge_and_sort(fa_hitters, model_hitters, hit_col),
        "pitchers": _merge_and_sort(fa_pitchers, model_pitchers, pit_col),
    }


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing ESPN connector...")

    try:
        roster = get_my_roster()
        print(f"\n✓ My roster ({len(roster)} players):")
        print(roster[["player_name", "position", "pro_team"]].to_string(index=False))
    except Exception as e:
        print(f"✗ Roster fetch failed: {e}")

    try:
        fa = get_free_agents(size=10)
        print(f"\n✓ Sample free agents ({len(fa)} shown):")
        print(fa.to_string(index=False))
    except Exception as e:
        print(f"✗ Free agent fetch failed: {e}")

    try:
        standings = get_league_standings()
        print("\n✓ Standings:")
        print(standings[["team_name", "wins", "losses", "points_for"]].to_string(index=False))
    except Exception as e:
        print(f"✗ Standings fetch failed: {e}")
