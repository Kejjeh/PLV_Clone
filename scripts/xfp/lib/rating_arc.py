"""rating_arc — in-season archetype-rating arc (OWNER of arc computation).

The 2026-07-04 rating-validation study established which pillar carries each
role's forward-FP signal: SP STUFF (forward r=.57 year-over-year, .48 in-season
— the only rating that out-predicts the raw FP level) and hitter CONTACT
(r=.47/.29). This module computes each player's IN-SEASON arc on those pillars:
latest snapshot vs the snapshot ~lookback days earlier, tagged RISER/FLAT/FALLER.

Rule 13: arcs are DISPLAY/CONTEXT only — they never move rh3/rp3/rprs2. The
validated-rejected finding on within-season *FP* trajectory (gotcha #11) is
about FP-level recency; this is a PROCESS-stat arc (SwStr/velo/contact quality),
the early-warning family that bat-speed/velo trending already validated. Any
promotion to a ranker requires /validate-feature.

Consumers: run_rating_arc.py (the /rating-arc skill board) and
run_fa_monitor.py signal O (FA rating-arc risers). Both import from HERE —
never re-derive arcs (SKILL_REGISTRY ownership rule).

Data provenance note: SP snapshots are START-ANCHORED, computed directly from
statcast_{year}.parquet with PRIOR-year baselines — they are same-day current
and unaffected by the sp_multiyr staleness bug (which only froze the ratings
MASTER). Hitter snapshots are weekly from the rolling cache.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys

_XFP = Path(__file__).resolve().parents[1]
if str(_XFP) not in sys.path:
    sys.path.insert(0, str(_XFP))

# The load-bearing pillar per role (2026-07-04 validation).
KEY_PILLAR = {"sp": "STUFF", "hitter": "CONTACT"}
ID_KEY = {"sp": "pitcher", "hitter": "batter"}
PILLARS = {
    "sp": ["OVERALL", "STUFF", "MOVEMENT", "CONTROL"],
    "hitter": ["OVERALL", "CONTACT", "POWER", "DISCIPLINE", "SB"],
}
ARC_RISE = 5    # rating points on the key pillar (~0.5 SD) => RISER
ARC_FALL = -5   # => FALLER


def compute_arcs(snapshots: list[dict], role: str,
                 lookback_days: int = 28, min_gap_days: int = 14) -> list[dict]:
    """Pure arc computation over snapshot rows (testable, no I/O).

    snapshots: rows with ID_KEY[role], 'player_name', 'date' (YYYY-MM-DD) and
    the role's pillar columns. For each player: latest snapshot vs the snapshot
    CLOSEST to (latest_date - lookback_days); players whose earliest usable
    snapshot is under min_gap_days old are skipped (no meaningful arc yet).
    """
    idk = ID_KEY[role]
    key = KEY_PILLAR[role]
    pillars = [p for p in PILLARS[role]]
    by_player: dict[int, list[dict]] = {}
    for s in snapshots:
        if s.get(idk) is None or s.get("date") is None:
            continue
        by_player.setdefault(int(s[idk]), []).append(s)

    out = []
    for pid, rows in by_player.items():
        rows.sort(key=lambda r: r["date"])
        latest = rows[-1]
        latest_dt = datetime.fromisoformat(str(latest["date"]))
        target = latest_dt - timedelta(days=lookback_days)
        past = [r for r in rows[:-1]
                if (latest_dt - datetime.fromisoformat(str(r["date"]))).days >= min_gap_days]
        if not past:
            continue
        anchor = min(past, key=lambda r: abs(
            (datetime.fromisoformat(str(r["date"])) - target).days))
        gap = (latest_dt - datetime.fromisoformat(str(anchor["date"]))).days

        rec = {idk: pid, "player_name": latest.get("player_name"),
               "date_now": str(latest["date"]), "date_then": str(anchor["date"]),
               "gap_days": gap}
        ok = True
        for p in pillars:
            v_now, v_then = latest.get(p), anchor.get(p)
            if p == key and (v_now is None or v_then is None):
                ok = False
                break
            rec[f"{p.lower()}_now"] = v_now
            rec[f"{p.lower()}_then"] = v_then
            rec[f"d_{p.lower()}"] = (None if (v_now is None or v_then is None)
                                     else int(v_now) - int(v_then))
        if not ok:
            continue
        dk = rec[f"d_{key.lower()}"]
        rec["key_pillar"] = key
        rec["key_delta"] = dk
        rec["arc"] = "RISER" if dk >= ARC_RISE else ("FALLER" if dk <= ARC_FALL else "FLAT")
        out.append(rec)
    out.sort(key=lambda r: -(r["key_delta"] or 0))
    return out


def rating_arcs(role: str, year: int = 2026, lookback_days: int = 28):
    """Production loader: build in-season snapshots via the dashboard builder
    functions (the established reuse seam — lib/season_snapshots does the same)
    and return arcs as a DataFrame."""
    import pandas as pd
    import build_player_profiles_dashboard as B
    if role == "sp":
        snaps = B.build_sp_start_snapshots(years=(year,), window=10, min_starts=3)
    elif role == "hitter":
        snaps = [s for s in B.build_hitter_snapshots() if int(s.get("year", 0)) == year]
    else:
        raise ValueError(f"role must be 'sp' or 'hitter', got {role!r}")
    arcs = compute_arcs(snaps, role, lookback_days=lookback_days)
    return pd.DataFrame(arcs)
