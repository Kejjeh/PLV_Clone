"""boom_bust — realized boom/bust actuals lens (the variance side).

Model lenses (rh3/rp3/archetype/sustainability) describe expectation; this is what
actually happened — realized BrownU FP per game (H L21) / start (SP L8) /
appearance (RP L15), with boom%/bust%/std/trend. Context-only (CLAUDE.md #13):
variance context, never moves rh3/rp3/rprs2.

Source of per-game FP (two-tier, fast path first):
  1. The materialized boxscore accumulator (``boxscore_{pitchers,hitters}.parquet``,
     rebuilt daily by ``refresh_boxscores.py`` and grown idempotently per game_pk).
     A parquet slice is sub-millisecond, so batch/slate scans pay no network cost.
     The pitcher store carries a ``gs`` flag (1=start) so we filter starts vs relief
     exactly like the live gameLog path.
  2. Live MLB Stats API gameLog (the same source /boom-bust-history uses), cached
     per process — used ONLY when the player is absent from the boxscore store
     (cross-year IL stashes, a just-called-up rookie, or the parquet not built yet).
Set ``PLV_BOOMBUST_FORCE_LIVE=1`` to bypass the parquet (used by the byte-identity
verification harness to prove the two tiers agree).

Boom/bust thresholds (calibrated vs 2025 league p80/p20): SP boom>=20 / bust<5;
H boom>=10 / bust<2; RP boom>=6 / bust<0.
"""
from __future__ import annotations

import functools
import os
import statistics
from pathlib import Path

_K = {"strikeout", "strikeout_double_play"}

# plv_clone root: scripts/xfp/lib/boom_bust.py -> parents[3]
_ROOT = Path(__file__).resolve().parents[3]
_BOX_PITCHERS = _ROOT / "data" / "research" / "xfp_cache" / "boxscore_pitchers.parquet"
_BOX_HITTERS = _ROOT / "data" / "research" / "xfp_cache" / "boxscore_hitters.parquet"


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


# ---------------------------------------------------------------------------
# Tier 1 — materialized boxscore accumulator (fast path)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=2)
def _load_box(kind: str):
    """Load and cache the boxscore parquet ('P' pitchers / 'H' hitters). None if
    the store hasn't been built yet (callers fall back to the live API)."""
    import pandas as pd
    path = _BOX_PITCHERS if kind == "P" else _BOX_HITTERS
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _series_from_box(df, mlbam, bucket: str):
    """Pure: time-ordered per-game BrownU FP list for one player from a boxscore
    frame. SP -> started games (gs==1, SP formula); RP -> relief (gs==0, RP formula
    incl. SV/HLD); H -> all games. None if df is None/empty or the player has no
    qualifying rows. Arithmetic mirrors the live _sp_fp/_rp_fp/_h_fp exactly so the
    two tiers are byte-identical."""
    if df is None or len(df) == 0:
        return None
    sub = df[df["mlbam_id"] == int(mlbam)]
    if sub.empty:
        return None
    if bucket in ("SP", "RP"):
        if "gs" not in sub.columns:
            return None
        sub = sub[sub["gs"] == (1 if bucket == "SP" else 0)]
        if sub.empty:
            return None
        sub = sub.sort_values(["game_date", "game_pk"])
        ip = sub["ip"].astype(float)
        fp = (sub["so"] + ip * 3.3 - sub["h_allowed"] - 2 * sub["er"]
              - sub["bb_allowed"] - sub["hbp_allowed"])
        if bucket == "RP":
            fp = fp + 5 * sub["sv"] + 2 * sub["hld"]
        return [float(x) for x in fp.tolist()]
    # hitter
    sub = sub.sort_values(["game_date", "game_pk"])
    fp = (sub["r"] + sub["tb"] + sub["rbi"] + sub["bb"]
          + sub["hbp"] + sub["sb"] - sub["k"])
    return [float(x) for x in fp.tolist()]


# ---------------------------------------------------------------------------
# Tier 2 — live MLB Stats API gameLog (fallback)
# ---------------------------------------------------------------------------

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


def _ip_to_float(ip_str) -> float:
    """'6.2' → 6.667 (MLB 'outs' notation: .1 = 1/3 IP). The naive float('6.2')
    reads ⅔ of an inning as 0.2 and undercounts IP*3.3 by up to ~1.5 FP/start —
    the boxscore accumulator converts correctly, so the live fallback must too or
    the two tiers disagree on every fractional-IP outing."""
    try:
        whole, frac = str(ip_str).split(".")
        return int(whole) + int(frac) / 3
    except Exception:
        try:
            return float(ip_str)
        except Exception:
            return 0.0


def _is_phantom(s, ip: float) -> bool:
    """A 0-out appearance that faced 0 batters is a phantom (e.g. entered and a
    runner was caught stealing before a pitch) — 0 FP and not a real game. The
    boxscore builder skips these; the live path must too, or the two tiers disagree
    on the window. Only skip when battersFaced is present AND 0 (absent => keep)."""
    if ip != 0:
        return False
    bf = s.get("battersFaced")
    return bf is not None and int(bf) == 0


def _sp_fp(s) -> float | None:
    if int(s.get("gamesStarted", 0)) < 1:
        return None
    ip = _ip_to_float(s.get("inningsPitched", 0) or 0)
    if _is_phantom(s, ip):
        return None
    return (int(s.get("strikeOuts", 0)) + ip * 3.3 - int(s.get("hits", 0))
            - 2 * int(s.get("earnedRuns", 0)) - int(s.get("baseOnBalls", 0))
            - int(s.get("hitBatsmen", 0)))


def _rp_fp(s) -> float | None:
    if int(s.get("gamesStarted", 0)) >= 1 or int(s.get("gamesPitched", 0)) < 1:
        return None
    ip = _ip_to_float(s.get("inningsPitched", 0) or 0)
    if _is_phantom(s, ip):
        return None
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


def _live_series(mlbam, bucket: str, season: int = 2026):
    """Live-API per-game FP list for one player (fallback tier)."""
    group = "hitting" if bucket == "H" else "pitching"
    fpf = {"SP": _sp_fp, "RP": _rp_fp, "H": _h_fp}[bucket]
    fp = [fpf(s) for s in _gamelog(int(mlbam), group, season)]
    return [x for x in fp if x is not None]


# ---------------------------------------------------------------------------
# Dispatcher — parquet first, live fallback
# ---------------------------------------------------------------------------

def _fp_series(mlbam, bucket: str, season: int = 2026):
    """Per-game FP list: materialized boxscore slice if present, else live API.
    season != 2026 (cross-year stash fallback) always uses the live API since the
    boxscore store is current-season only. PLV_BOOMBUST_FORCE_LIVE=1 forces live.

    Each per-game FP is rounded to 1 decimal — its true grain. BrownU FP is integer
    counting stats plus IP*3.3, and IP*3.3 == total_outs*1.1 is exact to 0.1, so the
    box (which stores IP rounded to 4 dp) and the live API (full precision) only ever
    differ by float dust; rounding to the real grain makes the two tiers agree exactly
    even at boom/bust thresholds."""
    s = None
    if season == 2026 and os.environ.get("PLV_BOOMBUST_FORCE_LIVE") != "1":
        kind = "H" if bucket == "H" else "P"
        s = _series_from_box(_load_box(kind), mlbam, bucket)
    if not s:
        s = _live_series(mlbam, bucket, season)
    return [round(x, 1) for x in s]


def sp_boom_bust(mlbam, n: int = 8, season: int = 2026) -> dict | None:
    fp = _fp_series(mlbam, "SP", season)[-n:]
    return boom_bust_summary(fp, boom_thr=20, bust_thr=5)


def rp_boom_bust(mlbam, n: int = 15, season: int = 2026) -> dict | None:
    fp = _fp_series(mlbam, "RP", season)[-n:]
    return boom_bust_summary(fp, boom_thr=6, bust_thr=0)


def hitter_boom_bust(mlbam, n: int = 21, season: int = 2026) -> dict | None:
    fp = _fp_series(mlbam, "H", season)[-n:]
    return boom_bust_summary(fp, boom_thr=10, bust_thr=2)
