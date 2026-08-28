"""season_snapshots — in-season archetype trajectory (OVERALL + main domains).

Surfaces a player's 2026 archetype snapshots OVER TIME on the triangulate card:
SP per-START (STUFF/MOVEMENT/CONTROL), hitter/RP per-WEEK (CONTACT/POWER/DISCIPLINE
| STUFF/CONTROL/BATTED_BALL). Reuses the dashboard's snapshot builders verbatim
(single source of truth, no rating drift), cached per process so the cost is paid
once. Context-only (CLAUDE.md #13) — trajectory never moves rh3/rp3.
"""
from __future__ import annotations

import functools
from plv_clone.league_config import SEASON_YEAR  # single source of truth for the season

# (domain column names, x-axis key) per bucket — match the dashboard snapshot rows
_DOMAINS = {
    "SP": (("STUFF", "MOVEMENT", "CONTROL"), "start_no"),
    "RP": (("STUFF", "CONTROL", "BATTED_BALL"), "date"),
    "H":  (("CONTACT", "POWER", "DISCIPLINE"), "date"),
}


def sample_trajectory(rows, n: int = 6):
    """Pick ~n evenly-spaced points from a time-ordered list, always keeping the
    first and last (the endpoints carry the start→now story). Pure + None-safe."""
    if not rows:
        return []
    if len(rows) <= n:
        return list(rows)
    step = (len(rows) - 1) / (n - 1)
    idx = sorted({round(i * step) for i in range(n)} | {0, len(rows) - 1})
    return [rows[i] for i in idx]


# Disk-cached (keyed on statcast_2026 signature): the cold build is tens of seconds and
# is paid on EVERY triangulate invocation incl. single-player cards; the warm pickle load
# is ~1-2s. In-process lru_cache still sits on top (built/loaded once per process).
@functools.lru_cache(maxsize=1)
def _sp_snaps():
    from build_player_profiles_dashboard import build_sp_start_snapshots
    from .disk_cache import disk_cached, STATCAST_2026
    return disk_cached("sp_snaps_2026",
                       lambda: build_sp_start_snapshots(years=(2026,)),
                       [STATCAST_2026], version=1)


@functools.lru_cache(maxsize=1)
def _h_snaps():
    from build_player_profiles_dashboard import build_hitter_snapshots
    from .disk_cache import disk_cached, STATCAST_2026
    return disk_cached("h_snaps_2026",
                       lambda: [r for r in build_hitter_snapshots() if r.get("year") == SEASON_YEAR],
                       [STATCAST_2026], version=1)


@functools.lru_cache(maxsize=1)
def _rp_snaps():
    from build_player_profiles_dashboard import build_rp_snapshots
    from .disk_cache import disk_cached, STATCAST_2026
    return disk_cached("rp_snaps_2026",
                       lambda: [r for r in build_rp_snapshots() if r.get("year") == SEASON_YEAR],
                       [STATCAST_2026], version=1)


def season_trajectory(player_id: int, bucket: str, n: int = 6) -> dict | None:
    """Return {domains, xkey, points:[{label, OVERALL, <domains>, archetype}]} for
    the player's 2026 in-season snapshots, sampled to ~n points. None if absent."""
    if bucket not in _DOMAINS:
        return None
    domains, xkey = _DOMAINS[bucket]
    src = {"SP": _sp_snaps, "RP": _rp_snaps, "H": _h_snaps}[bucket]()
    idk = "pitcher" if bucket in ("SP", "RP") else "batter"
    rows = sorted((r for r in src if r.get(idk) == player_id),
                  key=lambda r: r.get(xkey))
    if len(rows) < 2:
        return None
    pts = []
    for r in sample_trajectory(rows, n):
        label = f"#{int(r['start_no'])}" if xkey == "start_no" else str(r["date"])[5:]
        pts.append({"label": label, "OVERALL": r.get("OVERALL"),
                    **{d: r.get(d) for d in domains}, "archetype": r.get("archetype")})
    return {"domains": domains, "xkey": xkey, "points": pts}
