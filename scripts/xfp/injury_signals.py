"""injury_signals.py — ESPN injury status integration for league-wide audit.

Pulls injury details for rostered players and classifies whether an injury
overlaps with a detected slump window.

Standalone and testable: run `python scripts/xfp/injury_signals.py` to print
a league-wide injury summary.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


# ── injury_class mapping ──────────────────────────────────────────────────────

# Maps ESPN injuryStatus strings (and status_code abbreviations) to our
# standardized injury_class values.
_STATUS_TO_CLASS = {
    # ESPN injuryStatus field values
    "ACTIVE":         "NONE",
    "":               "NONE",
    "DAY_TO_DAY":     "DTD",
    "QUESTIONABLE":   "DTD",
    "DOUBTFUL":       "DTD",
    "OUT":            "IL15",        # generic OUT — refined by detail if available
    "SUSPENSION":     "OUT_INDEFINITE",
    "INJURED_RESERVE": "IL60",
    "FIFTEEN_DAY_DL":  "IL15",
    "TEN_DAY_DL":      "IL10",
    "SIXTY_DAY_DL":    "IL60",
    "NON_ROSTER":     "NONE",
}

_CODE_TO_CLASS = {
    "DTD": "DTD",
    "Q":   "DTD",
    "D":   "DTD",
    "O":   "IL15",
    "IR":  "IL60",
    "15":  "IL15",
    "10":  "IL10",
    "60":  "IL60",
}

_INJURED_CLASSES = {"DTD", "IL10", "IL15", "IL60", "OUT_INDEFINITE"}


def _resolve_injury_class(injury_status: str, status_code: str | None) -> str:
    """Resolve injury_class from ESPN status string and/or status code."""
    cls = _STATUS_TO_CLASS.get((injury_status or "").upper().replace(" ", "_"), None)
    if cls is not None:
        return cls
    if status_code:
        return _CODE_TO_CLASS.get(status_code.upper(), "NONE")
    return "NONE"


# ── batch_injury_status ───────────────────────────────────────────────────────

def batch_injury_status(player_ids: list[int]) -> dict[int, dict]:
    """Pull ESPN injury status for a list of ESPN player_ids.

    First checks the roster DataFrame columns (injured, injury_status) that
    are already available from get_all_teams().  For players flagged as
    injured, fetches detailed injury data from the ESPN public athlete
    endpoint to get injury type, side, return date, etc.

    Args:
        player_ids: list of ESPN player IDs (playerId from espn-api).

    Returns:
        dict keyed by player_id. Each value has:
            injury_class, injury_status_raw, injury_type, injury_side,
            return_date, days_until_return, short_comment, status_code.
    """
    from plv_clone.league_state import LeagueState
    get_injury_details = LeagueState().injury_details

    result: dict[int, dict] = {}

    # Seed all with NONE defaults
    for pid in player_ids:
        result[pid] = {
            "injury_class": "NONE",
            "injury_status_raw": "",
            "injury_type": None,
            "injury_side": None,
            "return_date": None,
            "days_until_return": None,
            "short_comment": None,
            "status_code": None,
        }

    # Fetch detailed info for all players (the ESPN public endpoint is fast
    # and does not require auth; only hit it once per player_id)
    if not player_ids:
        return result

    detail_df = get_injury_details(player_ids)
    if detail_df.empty or "player_id" not in detail_df.columns:
        return result

    for _, row in detail_df.iterrows():
        pid = int(row["player_id"])
        if pid not in result:
            continue

        def _cell(v) -> str:
            """Coerce a DataFrame cell to str, treating NaN/None as ''."""
            import math
            if v is None:
                return ""
            if isinstance(v, float) and math.isnan(v):
                return ""
            return str(v)

        sc = _cell(row.get("status_code"))
        inj_status = _cell(row.get("injury_type"))
        cls = _resolve_injury_class(inj_status, sc)
        short_val = _cell(row.get("short_comment"))
        detail_val = _cell(row.get("injury_detail"))
        # Only upgrade to DTD if there is a meaningful, non-empty injury signal
        if cls == "NONE" and (sc.strip() or short_val.strip() or detail_val.strip()):
            cls = "DTD"

        import math as _math
        return_date_raw = row.get("return_date")
        if isinstance(return_date_raw, float) and _math.isnan(return_date_raw):
            return_date_raw = None
        days_out_raw = row.get("days_until_return")
        days_out: int | None = None
        if days_out_raw is not None:
            try:
                candidate = int(days_out_raw)
                days_out = candidate
            except (ValueError, TypeError):
                pass

        inj_type_clean = _cell(row.get("injury_detail")) or _cell(row.get("injury_type")) or None
        inj_side_clean = _cell(row.get("injury_side")) or None
        short_clean = short_val or None

        result[pid] = {
            "injury_class": cls,
            "injury_status_raw": inj_status,
            "injury_type": inj_type_clean,
            "injury_side": inj_side_clean,
            "return_date": str(return_date_raw) if return_date_raw else None,
            "days_until_return": days_out,
            "short_comment": short_clean,
            "status_code": sc or None,
        }

    return result


def enrich_from_roster_df(
    player_ids: list[int],
    roster_df: pd.DataFrame,
    injury_lu: dict[int, dict],
) -> dict[int, dict]:
    """Backfill injury_class from the roster DataFrame's injured/injury_status
    columns for any player_id that still shows NONE in injury_lu.

    Mutates injury_lu in-place and returns it.
    """
    if roster_df.empty or "player_id" not in roster_df.columns:
        return injury_lu

    for _, row in roster_df.iterrows():
        pid_raw = row.get("player_id")
        if pid_raw is None:
            continue
        try:
            pid = int(pid_raw)
        except (ValueError, TypeError):
            continue
        if pid not in injury_lu:
            continue

        # Only override if currently NONE and roster says injured
        if injury_lu[pid]["injury_class"] == "NONE" and row.get("injured"):
            raw = (row.get("injury_status") or "").upper().replace(" ", "_")
            cls = _STATUS_TO_CLASS.get(raw, "DTD")  # default to DTD if unrecognized
            injury_lu[pid]["injury_class"] = cls
            injury_lu[pid]["injury_status_raw"] = raw

    return injury_lu


# ── classify_injury_impact ────────────────────────────────────────────────────

def classify_injury_impact(
    injury_status: dict,
    slump_start_date: str | None,
) -> dict:
    """Classify whether injury status overlaps with slump timing.

    Args:
        injury_status: one player's row from batch_injury_status().
        slump_start_date: ISO date string when slump started (from
            slump_trajectory_batch), or None.

    Returns dict with:
        injury_class, injury_overlap, injury_note, should_modify_verdict,
        return_date, days_until_return, short_comment.
    """
    cls = injury_status.get("injury_class", "NONE")
    short = injury_status.get("short_comment") or ""
    if not isinstance(short, str):
        short = ""
    inj_type = injury_status.get("injury_type") or ""
    if not isinstance(inj_type, str):
        inj_type = ""
    inj_side = injury_status.get("injury_side") or ""
    if not isinstance(inj_side, str):
        inj_side = ""
    return_date = injury_status.get("return_date")
    days_out = injury_status.get("days_until_return")

    # Build a human-readable injury description
    parts = []
    if cls != "NONE":
        parts.append(cls)
    if inj_type:
        s = inj_type
        if inj_side:
            s += f", {inj_side}"
        parts.append(f"({s})")
    elif short:
        parts.append(f"({short[:80]})")

    inj_desc = " ".join(parts) if parts else cls

    # No injury — fast path
    if cls == "NONE":
        return {
            "injury_class": "NONE",
            "injury_overlap": "NO_OVERLAP",
            "injury_note": "",
            "should_modify_verdict": False,
            "return_date": return_date,
            "days_until_return": days_out,
            "short_comment": short or None,
        }

    # Classify overlap with slump window
    if slump_start_date is None:
        overlap = "UNKNOWN"
        note = f"{inj_desc} — slump window unknown"
        modify = cls in ("IL10", "IL15", "IL60", "OUT_INDEFINITE")
    else:
        today = date.today()
        try:
            slump_dt = date.fromisoformat(slump_start_date)
        except (ValueError, TypeError):
            slump_dt = None

        if slump_dt is None:
            overlap = "UNKNOWN"
            note = f"{inj_desc} — slump start date unparseable"
            modify = cls in _INJURED_CLASSES
        else:
            # If injury is IL/OUT — classify as SLUMP_EXPLAINED if the slump
            # started within 45 days (i.e., injury could plausibly have caused it)
            days_since_slump = (today - slump_dt).days
            if cls in ("IL10", "IL15", "IL60", "OUT_INDEFINITE"):
                if days_since_slump <= 45:
                    overlap = "SLUMP_EXPLAINED"
                    note = (
                        f"{inj_desc} — overlaps slump start {slump_start_date}"
                    )
                    if return_date:
                        note += f"; exp. return {return_date}"
                    modify = True
                else:
                    overlap = "NO_OVERLAP"
                    note = (
                        f"{inj_desc} — injury predates slump by {days_since_slump}d"
                    )
                    modify = False
            elif cls == "DTD":
                # DTD: possible factor if slump started in last 30 days
                if days_since_slump <= 30:
                    overlap = "POSSIBLE_FACTOR"
                    note = f"{inj_desc} — DTD during slump window (started {slump_start_date})"
                    modify = True
                else:
                    overlap = "POSSIBLE_FACTOR"
                    note = f"{inj_desc} — active DTD note"
                    modify = False
            else:
                overlap = "POSSIBLE_FACTOR"
                note = f"{inj_desc}"
                modify = False

    return {
        "injury_class": cls,
        "injury_overlap": overlap,
        "injury_note": note,
        "should_modify_verdict": modify,
        "return_date": return_date,
        "days_until_return": days_out,
        "short_comment": short or None,
    }


# ── classify_all ─────────────────────────────────────────────────────────────

def classify_all(
    injury_lu: dict[int, dict],
    slump_start_by_pid: dict[int, str | None],
) -> dict[int, dict]:
    """Run classify_injury_impact for every player_id in injury_lu.

    Args:
        injury_lu: output of batch_injury_status().
        slump_start_by_pid: mapping player_id → slump_start_date (or None).

    Returns dict[player_id, impact_dict].
    """
    result = {}
    for pid, status in injury_lu.items():
        slump_start = slump_start_by_pid.get(pid)
        result[pid] = classify_injury_impact(status, slump_start)
    return result


# ── __main__ ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)

    print("Fetching all-team roster from ESPN...")
    from app.espn_connector import get_all_teams

    all_teams = get_all_teams()
    hitters = all_teams[~all_teams["position"].isin(["SP", "RP", "P"])].copy()

    pid_col_ok = "player_id" in hitters.columns
    if not pid_col_ok:
        print("ERROR: get_all_teams() does not return player_id column.")
        sys.exit(1)

    espn_pids = hitters["player_id"].dropna().astype(int).tolist()
    print(f"Pulling injury data for {len(espn_pids)} hitters...")

    injury_lu = batch_injury_status(espn_pids)

    # Backfill from roster df (injured / injury_status columns)
    injury_lu = enrich_from_roster_df(espn_pids, hitters, injury_lu)

    # No slump_start_date available in standalone mode
    classified = classify_all(injury_lu, {})

    # Summary
    n_any = sum(1 for v in classified.values() if v["injury_class"] != "NONE")
    n_dtd = sum(1 for v in classified.values() if v["injury_class"] == "DTD")
    n_il = sum(1 for v in classified.values() if v["injury_class"] in ("IL10", "IL15", "IL60", "OUT_INDEFINITE"))

    print(f"\n=== Injury summary ({len(espn_pids)} hitters) ===")
    print(f"  Any injury flag : {n_any}")
    print(f"  DTD             : {n_dtd}")
    print(f"  IL (10/15/60)   : {n_il}")

    if n_any:
        print("\nInjured players:")
        pid_to_name = dict(zip(
            hitters["player_id"].dropna().astype(int),
            hitters["player_name"],
        ))
        pid_to_team = dict(zip(
            hitters["player_id"].dropna().astype(int),
            hitters["team_name"],
        ))
        for pid, impact in sorted(classified.items(), key=lambda x: x[1]["injury_class"]):
            if impact["injury_class"] == "NONE":
                continue
            name = pid_to_name.get(pid, f"pid={pid}")
            team = pid_to_team.get(pid, "?")
            note = impact["injury_note"] or impact["injury_class"]
            ret = f" (return: {impact['return_date']})" if impact["return_date"] else ""
            print(f"  {name} [{team}] — {note}{ret}")
