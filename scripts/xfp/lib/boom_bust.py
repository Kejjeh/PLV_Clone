"""boom_bust — realized boom/bust actuals lens (the variance side).

Model lenses (rh3/rp3/archetype/sustainability) describe expectation; this is what
actually happened — realized BrownU FP per game (H L21) / start (SP L8) /
appearance (RP L15), with boom%/bust%/std/trend. Pulls the live MLB Stats API
gameLog (current + full FP incl SV/HLD — the same source /boom-bust-history uses),
cached per process so repeated calls in one run don't refetch. Context-only
(CLAUDE.md #13): variance context, never moves rh3/rp3/rprs2.

Boom/bust thresholds (calibrated vs 2025 league p80/p20): SP boom>=20 / bust<5;
H boom>=10 / bust<2; RP boom>=6 / bust<0.
"""
from __future__ import annotations

import functools
import statistics

_K = {"strikeout", "strikeout_double_play"}


def boom_bust_summary(fp_values, *, boom_thr, bust_thr) -> dict | None:
    """Pure: mean/std/min/max/boom%/bust%/trend over realized FP values."""
    v = [x for x in fp_values if x is not None]
    if not v:
        return None
    n = len(v)
    std = statistics.stdev(v) if n > 1 else 0.0
    l3 = v[-3:]
    l3_mean = sum(l3) / len(l3)
    full_mean = sum(v) / n
    trend = "UP" if l3_mean > full_mean + 1 else "DOWN" if l3_mean < full_mean - 1 else "FLAT"
    return {
        "n": n,
        "mean": round(full_mean, 1),
        "std": round(std, 1),
        "min": round(min(v), 1),
        "max": round(max(v), 1),
        "boom_pct": round(sum(1 for x in v if x >= boom_thr) / n * 100),
        "bust_pct": round(sum(1 for x in v if x < bust_thr) / n * 100),
        "l3_mean": round(l3_mean, 1),
        "trend": trend,
        "last": [round(x, 1) for x in v[-8:]],
    }


@functools.lru_cache(maxsize=512)
def _gamelog(mlbam: int, group: str, season: int = 2026):
    """Raw per-game stat splits from the live MLB Stats API (cached)."""
    import requests
    url = (f"https://statsapi.mlb.com/api/v1/people/{mlbam}/stats"
           f"?stats=gameLog&season={season}&group={group}")
    try:
        j = requests.get(url, timeout=15).json()
    except Exception:
        return ()
    out = []
    for sp in j.get("stats", []):
        for g in sp.get("splits", []):
            out.append(g.get("stat", {}))
    return tuple(out)


def _sp_fp(s) -> float | None:
    if int(s.get("gamesStarted", 0)) < 1:
        return None
    ip = float(s.get("inningsPitched", 0) or 0)
    return (int(s.get("strikeOuts", 0)) + ip * 3.3 - int(s.get("hits", 0))
            - 2 * int(s.get("earnedRuns", 0)) - int(s.get("baseOnBalls", 0))
            - int(s.get("hitBatsmen", 0)))


def _rp_fp(s) -> float | None:
    if int(s.get("gamesStarted", 0)) >= 1 or int(s.get("gamesPitched", 0)) < 1:
        return None
    ip = float(s.get("inningsPitched", 0) or 0)
    return (int(s.get("strikeOuts", 0)) + ip * 3.3 - int(s.get("hits", 0))
            - 2 * int(s.get("earnedRuns", 0)) - int(s.get("baseOnBalls", 0))
            - int(s.get("hitBatsmen", 0)) + 5 * int(s.get("saves", 0))
            + 2 * int(s.get("holds", 0)))


def _h_fp(s) -> float | None:
    if int(s.get("plateAppearances", 0)) < 1:
        return None
    tb = int(s.get("totalBases", 0))
    return (int(s.get("runs", 0)) + tb + int(s.get("rbi", 0)) + int(s.get("baseOnBalls", 0))
            + int(s.get("hitByPitch", 0)) + int(s.get("stolenBases", 0)) - int(s.get("strikeOuts", 0)))


def sp_boom_bust(mlbam, n: int = 8) -> dict | None:
    fp = [_sp_fp(s) for s in _gamelog(int(mlbam), "pitching")]
    fp = [x for x in fp if x is not None][-n:]
    return boom_bust_summary(fp, boom_thr=20, bust_thr=5)


def rp_boom_bust(mlbam, n: int = 15) -> dict | None:
    fp = [_rp_fp(s) for s in _gamelog(int(mlbam), "pitching")]
    fp = [x for x in fp if x is not None][-n:]
    return boom_bust_summary(fp, boom_thr=6, bust_thr=0)


def hitter_boom_bust(mlbam, n: int = 21) -> dict | None:
    fp = [_h_fp(s) for s in _gamelog(int(mlbam), "hitting")]
    fp = [x for x in fp if x is not None][-n:]
    return boom_bust_summary(fp, boom_thr=10, bust_thr=2)
