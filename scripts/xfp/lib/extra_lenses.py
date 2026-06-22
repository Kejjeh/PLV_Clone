"""extra_lenses — four validated context lenses folded into triangulate.

All are CONTEXT-ONLY (CLAUDE.md #13): they never move the rh3/rp3/rprs2 headline or
the verdict. They add conviction / conflict color:

  • stuff_lens(name)      SP — FanGraphs Stuff+ level + the Stuff+-anchored RoS
                          fp/start projection + breakout gap (elite stuff, lagging
                          results = buy-low). Validated 2026-06-06.
  • floor_lens(name)      SP — per-start bust probability (P(fp<5)) + SAFE/MODERATE/
                          RISKY tier, driven by K-BB% (not stuff). Validated 2026-06-06.
  • trend_lens(mlbam,role) physical getting-better/worse: bat speed + attack-angle
                          (hitters) / FB velo (pitchers), 2026 vs prior-yr baseline.
  • shadow_lens(name)     SP process grade (20-80) for arms with no rp3/archetype
                          (rookies / thin post-callup) — fills the unranked gap.

Every accessor is defensive (returns None on any failure) and cached so a batch
run pays each underlying model fit once.
"""
from __future__ import annotations

import functools
import unicodedata


def _norm(s) -> str:
    if not isinstance(s, str):
        return ""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


# --------------------------------------------------------------------------
# Stuff+ and SP-floor share the FanGraphs 2026 SP frame (one fit, cached)
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _stuff_frame():
    """Build the Stuff+ board once; index by normalized FG name.
    Returns {norm_name: row_dict} or {} on failure."""
    try:
        import sys, os
        _xfp = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if _xfp not in sys.path:
            sys.path.insert(0, _xfp)
        from sp_stuff_model import build as _build
        d, _ = _build()
    except Exception:
        return {}
    out = {}
    for _, r in d.iterrows():
        k = _norm(r.get("player_name_fg"))
        if k:
            out.setdefault(k, r.to_dict())
    return out


def stuff_lens(name: str) -> dict | None:
    """SP Stuff+ level + Stuff+-anchored RoS fp/start projection + breakout gap."""
    row = _stuff_frame().get(_norm(name))
    if not row:
        return None
    try:
        return {
            "stuff_plus": round(float(row["stuff_plus"]), 1),
            "proj_ros_fp": round(float(row["proj_ros_fp"]), 2),
            "breakout_gap": round(float(row["breakout_gap"])),
            "stuff_pctl": round(float(row["stuff_pctl"])),
        }
    except (KeyError, TypeError, ValueError):
        return None


def floor_lens(name: str) -> dict | None:
    """SP per-start bust probability + SAFE/MODERATE/RISKY tier from current K-BB%.
    Uses league-neutral lineup/rest (player-level read, not a specific matchup)."""
    row = _stuff_frame().get(_norm(name))
    if not row:
        return None
    try:
        import sys, os
        _xfp = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if _xfp not in sys.path:
            sys.path.insert(0, _xfp)
        from sp_floor_model import floor_for
        k = float(row["k_pct"]); bb = float(row["bb_pct"])
        # FG rates are percentages (e.g. 24.5) -> fractions
        if k > 1:
            k /= 100.0
        if bb > 1:
            bb /= 100.0
        probs, tiers = floor_for(k, bb)
        return {"bust_prob": round(float(probs[0]) * 100), "tier": tiers[0]}
    except Exception:
        return None


# --------------------------------------------------------------------------
# Physical trend (bat speed / attack angle — H; FB velo — P)
# --------------------------------------------------------------------------

def trend_lens(mlbam, role: str) -> dict | None:
    """Physical getting-better/worse tag for a resolved MLBAM id. Context-only."""
    try:
        from lib.trend_signal import trend_for_mlbam
        tag, row = trend_for_mlbam(int(mlbam), role)
    except Exception:
        return None
    if not tag:
        return None
    return {"tag": tag}


# --------------------------------------------------------------------------
# Shadow scout (process grade for unranked SPs)
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=512)
def shadow_lens(name: str) -> dict | None:
    """20-80 process grade for an SP with no rp3/archetype. None when the player
    has no usable 2026 MLB sample (verdict NO_MLB_DATA)."""
    try:
        from lib.shadow_scout import shadow_scout
        res = shadow_scout([name])
    except Exception:
        return None
    if not res:
        return None
    r = res[0]
    if r.get("verdict") in (None, "NO_MLB_DATA"):
        return None
    return {
        "avg_grade": r.get("avg_grade"),
        "verdict": r.get("verdict"),
        "grades": r.get("grades"),
    }
