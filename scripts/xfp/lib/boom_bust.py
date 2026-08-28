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

Boom/bust thresholds (RECALIBRATED 2026-06-28 to empirical p~78/p~22, then
confirmed across all 12 Statcast years on 656k real per-game FP): SP boom>=17 /
bust<5; H boom>=5 / bust<0; RP boom>=6 / bust<0. The old H 10/2 fired a useless
3%/57%; old SP 20 missed top-quartile starts (a 17.7 didn't count). These are the
DISPLAY lens; the boom_stack forward tables intentionally use their own (stricter,
separately-validated) thresholds. See boom_bust_cutoff_recalibration_2026-06-28.md.
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

# The BrownU scoring formula has ONE owner (audit 2026-07-03). Proven identical to the
# old inline formula (parity 0.000000, test_scoring_parity.py) — this migration is a no-op.
from plv_clone.fantasy.scoring import pitcher_fp, hitter_fp
from plv_clone.league_config import SEASON_YEAR  # single source of truth for the season
from plv_clone.fantasy.scoring import parse_ip as _canon_parse_ip  # noqa: E402


#: Below this many events a boom/bust RATE is not a usable discriminator.
#: An 8-start window can only express rates in eighths, and its 95% interval
#: spans most of the unit line — see ``RATE_MIN_N`` usage in ``rate_is_usable``.
RATE_MIN_N = 12


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion, as PERCENTAGES.

    Wilson rather than normal-approximation because these samples are small and
    the rates sit near 0 — the normal interval goes negative there and implies
    a precision that does not exist.
    """
    if n <= 0:
        return (0.0, 100.0)
    p = successes / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (round(max(0.0, centre - half) * 100, 1),
            round(min(1.0, centre + half) * 100, 1))


def rate_is_usable(n: int) -> bool:
    """Is an observed rate over ``n`` events precise enough to RANK on?"""
    return n >= RATE_MIN_N


def boom_bust_summary(fp_values, *, boom_thr, bust_thr) -> dict | None:
    """Pure: mean/std/min/max/boom%/bust%/trend over realized FP values.

    Every rate ships with its denominator and a 95% Wilson interval, and with
    ``rate_precise`` saying whether it is usable for ranking. A bare percentage
    reads as far more certain than a handful of games can support: on
    2026-08-07 an 8% bust rate was quoted as "the lowest on the slate" and used
    to pick a streamer, when it was ONE bust in twelve starts — CI [1%, 35%],
    overlapping the alternative's [9%, 40%] almost entirely. The two arms were
    not distinguishable and the number said nothing about that. Consumers that
    sort or filter on boom/bust MUST gate on ``rate_precise``.
    """
    v = [x for x in fp_values if x is not None]
    if not v:
        return None
    n = len(v)
    std = statistics.stdev(v) if n > 1 else 0.0
    l3 = v[-3:]
    l3_mean = sum(l3) / len(l3)
    full_mean = sum(v) / n
    trend = "UP" if l3_mean > full_mean + 1 else "DOWN" if l3_mean < full_mean - 1 else "FLAT"
    n_boom = sum(1 for x in v if x >= boom_thr)
    n_bust = sum(1 for x in v if x < bust_thr)
    return {
        "n": n,
        "mean": round(full_mean, 1),
        "std": round(std, 1),
        "min": round(min(v), 1),
        "max": round(max(v), 1),
        "boom_pct": round(n_boom / n * 100),
        "bust_pct": round(n_bust / n * 100),
        "boom_n": n_boom,
        "bust_n": n_bust,
        "boom_ci": wilson_ci(n_boom, n),
        "bust_ci": wilson_ci(n_bust, n),
        "rate_precise": rate_is_usable(n),
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
        # pitcher_fp is element-wise over Series; SV/HLD default 0 for SP.
        if bucket == "RP":
            fp = pitcher_fp(k=sub["so"], ip=ip, h=sub["h_allowed"], er=sub["er"],
                            bb=sub["bb_allowed"], hbp=sub["hbp_allowed"],
                            sv=sub["sv"], hld=sub["hld"])
        else:
            fp = pitcher_fp(k=sub["so"], ip=ip, h=sub["h_allowed"], er=sub["er"],
                            bb=sub["bb_allowed"], hbp=sub["hbp_allowed"])
        return [float(x) for x in fp.tolist()]
    # hitter
    sub = sub.sort_values(["game_date", "game_pk"])
    fp = hitter_fp(r=sub["r"], tb=sub["tb"], rbi=sub["rbi"], bb=sub["bb"],
                   hbp=sub["hbp"], sb=sub["sb"], k=sub["k"])
    return [float(x) for x in fp.tolist()]


# ---------------------------------------------------------------------------
# Tier 2 — live MLB Stats API gameLog (fallback)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=512)
def _gamelog(mlbam: int, group: str, season: int = SEASON_YEAR):
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
    # Delegates to the ONE canonical parser (issue #78).
    return _canon_parse_ip(ip_str, default=0.0)


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
    return pitcher_fp(k=int(s.get("strikeOuts", 0)), ip=ip, h=int(s.get("hits", 0)),
                      er=int(s.get("earnedRuns", 0)), bb=int(s.get("baseOnBalls", 0)),
                      hbp=int(s.get("hitBatsmen", 0)))


def _rp_fp(s) -> float | None:
    if int(s.get("gamesStarted", 0)) >= 1 or int(s.get("gamesPitched", 0)) < 1:
        return None
    ip = _ip_to_float(s.get("inningsPitched", 0) or 0)
    if _is_phantom(s, ip):
        return None
    return pitcher_fp(k=int(s.get("strikeOuts", 0)), ip=ip, h=int(s.get("hits", 0)),
                      er=int(s.get("earnedRuns", 0)), bb=int(s.get("baseOnBalls", 0)),
                      hbp=int(s.get("hitBatsmen", 0)), sv=int(s.get("saves", 0)),
                      hld=int(s.get("holds", 0)))


def _h_fp(s) -> float | None:
    if int(s.get("plateAppearances", 0)) < 1:
        return None
    return hitter_fp(r=int(s.get("runs", 0)), tb=int(s.get("totalBases", 0)),
                     rbi=int(s.get("rbi", 0)), bb=int(s.get("baseOnBalls", 0)),
                     hbp=int(s.get("hitByPitch", 0)), sb=int(s.get("stolenBases", 0)),
                     k=int(s.get("strikeOuts", 0)))


def _live_series(mlbam, bucket: str, season: int = SEASON_YEAR):
    """Live-API per-game FP list for one player (fallback tier)."""
    group = "hitting" if bucket == "H" else "pitching"
    fpf = {"SP": _sp_fp, "RP": _rp_fp, "H": _h_fp}[bucket]
    fp = [fpf(s) for s in _gamelog(int(mlbam), group, season)]
    return [x for x in fp if x is not None]


# ---------------------------------------------------------------------------
# Dispatcher — parquet first, live fallback
# ---------------------------------------------------------------------------

def _fp_series(mlbam, bucket: str, season: int = SEASON_YEAR):
    """Per-game FP list: materialized boxscore slice if present, else live API.
    season != SEASON_YEAR (cross-year stash fallback) always uses the live API since the
    boxscore store is current-season only. PLV_BOOMBUST_FORCE_LIVE=1 forces live.

    Each per-game FP is rounded to 1 decimal — its true grain. BrownU FP is integer
    counting stats plus IP*3.3, and IP*3.3 == total_outs*1.1 is exact to 0.1, so the
    box (which stores IP rounded to 4 dp) and the live API (full precision) only ever
    differ by float dust; rounding to the real grain makes the two tiers agree exactly
    even at boom/bust thresholds."""
    s = None
    if season == SEASON_YEAR and os.environ.get("PLV_BOOMBUST_FORCE_LIVE") != "1":
        kind = "H" if bucket == "H" else "P"
        s = _series_from_box(_load_box(kind), mlbam, bucket)
    if not s:
        s = _live_series(mlbam, bucket, season)
    return [round(x, 1) for x in s]


# Display cutoffs recalibrated 2026-06-28 to the empirical per-game/per-start FP
# distribution (boom_bust_cutoff_recalibration_2026-06-28.md). These are the
# DISPLAY/context lens (CLAUDE.md #13) — they label realized boom/bust RATES and
# never move a projection. They are intentionally INDEPENDENT of the boom_stack
# forward-expectation tables, which use their own (stricter, validated) thresholds:
#   - SP boom_stack: P(FP>=20) "monster start" / bust P(FP<0); 33k-start derived.
#   - hitter boom_stack: fp_proxy >= 80th pct (~top-20%); 245k-game derived.
# The hitter display boom (fp>=5 ~ top-17%) now SHARES the boom_stack top-quintile
# philosophy (old fp>=10 was a top-3% mismatch). The SP display boom (fp>=17 ~ top
# quartile, so a 17.7 start counts) is looser than the boom_stack 20 by design —
# the display already differed on bust (5 vs 0), so the two lenses are separate tools.
# Named constants so callers stop re-typing the magic numbers (audit 2026-07-03:
# build_sp_pl_board hardcoded 17/5 inline, hitter-slate-grid doc still said the
# pre-recalibration 20). Import these — never re-type. (recalibrated 2026-06-28.)

# ── forward (shrunk) boom/bust estimates ─────────────────────────────────────
# An observed boom rate over a short window is mostly sampling noise. Measured
# 2026-08-27 on 1,331 SP-seasons (validate_boom_window.py): regressing the NEXT
# 8 starts' boom rate on the window's boom rate gives a slope well under 1, and
# 1 - slope is the fraction of any observed gap that does not survive.
#
#   window   slope   shrinkage   forward r
#     L3     0.179      82%        0.253
#     L5     0.261      74%        0.304
#     L8     0.353      65%        0.347     <- the /boom-bust-history default
#     L12    0.431      57%        0.371
#     L20    0.575      42%        0.411
#
# Consequence for the display: the skill's own canonical contrast — a "37% boom
# hot streak" against "0% boom cap-fodder" — is a 37.5pp gap on screen and a
# 13.2pp gap going forward (0/8 -> 19.7%, 3/8 -> 33.0%). Raw rates invite
# reading 0/8 as "never booms" when the forward truth is about one in five.
#
# Rule 13: this is a DISPLAY calibration. It never moves rh3/rp3/rprs2, and it
# does not change any existing boom_bust output — callers must opt in.
#   HITTER, window in GAMES (measured on 2,469 hitter-seasons, boom = FP >= 5):
#     L7  0.105 -> 89%   L14 0.192 -> 81%   L21 0.267 -> 73%  <- the H default
#     L28 0.330 -> 67%   L40 0.414 -> 59%   L60 0.520 -> 48%
#
# NOTE THE ASYMMETRY: hitter L21 is 73% noise while SP L8 is 65% — MORE
# observations carrying LESS signal. The mechanism is between-player spread, and
# both windows per side agree on it: the implied true between-player SD of boom
# rate is ~12pp for pitchers and only ~5pp for hitters. Hitters are simply more
# alike in how often they boom, so a longer window still resolves less.
BOOM_SHRINK_SLOPE = {3: 0.179, 5: 0.261, 8: 0.353, 12: 0.431, 20: 0.575}
BOOM_SHRINK_SLOPE_H = {7: 0.105, 14: 0.192, 21: 0.267, 28: 0.330,
                       40: 0.414, 60: 0.520}
# RP measured 2026-08-27 on 54,561 relief appearances / 1,282 RP-seasons
# (rp_event_panel_2017_2026.csv, boom >= 6 FP incl. 5*SV + 3*HLD). RPs sit
# BETWEEN the two: an L15 relief read retains 57% of its signal, more than a
# hitter's L21 (25%) and more than an SP's L8 (35%). Save/hold leverage is a
# durable role property, so relievers separate more than hitters do.
BOOM_SHRINK_SLOPE_RP = {5: 0.336, 10: 0.491, 15: 0.568, 20: 0.586, 30: 0.601}
SP_BOOM_BASE = 0.305   # league SP boom rate on the same panel
H_BOOM_BASE = 0.207    # league hitter boom rate on the same panel
RP_BOOM_BASE = 0.266   # league RP boom rate on the same panel


def forward_rate(observed_rate: float, window: int, side: str = "SP",
                 base: float | None = None) -> float:
    """Shrink an observed short-window boom/bust rate toward the base rate.

    ``observed_rate`` is a fraction (3/8 -> 0.375), ``window`` the number of
    units it came from (STARTS for SP, GAMES for a hitter, APPEARANCES for an
    RP), ``side`` one of "SP" / "H" / "RP". Interpolates the slope for an
    unlisted window and clamps to the measured range rather than extrapolating
    off the end.

    Returns the forward estimate: ``base + slope * (observed - base)``.

    >>> round(forward_rate(3/8, 8, "SP"), 3)
    0.33
    >>> round(forward_rate(0.0, 21, "H"), 3)
    0.152
    >>> round(forward_rate(6/15, 15, "RP"), 3)
    0.342
    """
    if observed_rate is None or window is None or window <= 0:
        return float("nan")
    table = {"H": BOOM_SHRINK_SLOPE_H,
             "RP": BOOM_SHRINK_SLOPE_RP}.get(side, BOOM_SHRINK_SLOPE)
    if base is None:
        base = {"H": H_BOOM_BASE,
                "RP": RP_BOOM_BASE}.get(side, SP_BOOM_BASE)
    ws = sorted(table)
    if window in table:
        slope = table[window]
    elif window <= ws[0]:
        slope = table[ws[0]]
    elif window >= ws[-1]:
        slope = table[ws[-1]]
    else:
        lo = max(w for w in ws if w < window)
        hi = min(w for w in ws if w > window)
        f = (window - lo) / (hi - lo)
        slope = table[lo] + f * (table[hi] - table[lo])
    return base + slope * (observed_rate - base)

SP_BOOM, SP_BUST = 17, 5     # per-start FP: ~top-quartile / replacement floor
RP_BOOM, RP_BUST = 6, 0      # per-appearance FP
H_BOOM, H_BUST = 5, 0        # per-game FP: ~top-quintile / negative day


def sp_boom_bust(mlbam, n: int = 8, season: int = SEASON_YEAR) -> dict | None:
    fp = _fp_series(mlbam, "SP", season)[-n:]
    return boom_bust_summary(fp, boom_thr=SP_BOOM, bust_thr=SP_BUST)


def rp_boom_bust(mlbam, n: int = 15, season: int = SEASON_YEAR) -> dict | None:
    fp = _fp_series(mlbam, "RP", season)[-n:]
    return boom_bust_summary(fp, boom_thr=RP_BOOM, bust_thr=RP_BUST)


def hitter_boom_bust(mlbam, n: int = 21, season: int = SEASON_YEAR) -> dict | None:
    fp = _fp_series(mlbam, "H", season)[-n:]
    return boom_bust_summary(fp, boom_thr=H_BOOM, bust_thr=H_BUST)
