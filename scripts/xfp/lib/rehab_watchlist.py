"""rehab_watchlist — auto-discovered team IL players merged with a maintained
FA rehab watchlist, into one master list. See test file for the WHY.
"""
from __future__ import annotations

REAL_IL_STATES = frozenset({"TEN_DAY_DL", "FIFTEEN_DAY_DL", "SIXTY_DAY_DL"})


def discover_il_players(roster_rows, my_team_name):
    return [
        r for r in roster_rows
        if r.get("team_name") == my_team_name and r.get("injury_status") in REAL_IL_STATES
    ]


def build_rehab_master_list(il_players, fa_watchlist):
    master = []
    for p in il_players:
        master.append({**p, "source": "mine"})
    for p in fa_watchlist:
        master.append({**p, "source": "fa_watchlist"})
    return master


def needs_playing_time_mode(status):
    return status == "activated"
