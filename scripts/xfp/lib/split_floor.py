"""split_floor — is a difference between two halves of a player's season real?

CONTEXT-ONLY (CLAUDE.md #13). This NEVER moves rh3/rp3/rprs2. It answers the
prior question: is the gap you are looking at even distinguishable from ordinary
within-season variation?

WHY THIS EXISTS
Measured 2026-08-26/27 on 26,954 SP split-points (1,331 pitcher-seasons,
2017-2026): the |K-BB%| difference between two halves of the SAME pitcher-season
has a p90 of ~10pp at 100 TBF per side. Most "he's a different pitcher since
X" observations are inside that band.

THE THREE THINGS THE STUDY ESTABLISHED

1. The floor is BINOMIAL. Express the gap in z units against the sampling SE and
   the p90 is ~1.83 at EVERY sample size (1.79-1.88 across 50-300+ TBF buckets)
   and at EVERY talent level (1.77-1.92 across K-BB% quintiles). Raw p90 rises
   with a pitcher's rate only because p(1-p) does. One constant covers everyone,
   so this is a formula, not a lookup table.

2. Real in-season movement is SMALL. Observed |z| mean is 0.889 against 0.798 for
   a pure half-normal — an over-dispersion factor of only **1.114x**. About 89%
   of what looks like a pitcher changing mid-season is sampling noise. The
   true-talent wander component is ~0.49x the sampling SE.

3. It differs by metric, and BB% moves least:
       k_pct       1.134   (true-talent SD 0.53x SE)
       k_minus_bb  1.114   (0.49x)
       bb_pct      1.053   (0.33x)  <- barely above pure noise
   An independent confirmation of "watch STUFF, not walks" and of
   stabilization.NEVER_STABILIZES listing pitcher bb_pct.

WHAT THIS MAY AND MAY NOT BE USED FOR
May: a screen. "Is this gap worth discussing at all."
May NOT: a number. Re-anchoring a projection on a split that clears this bar was
tested and FAILS — event-triggered + z>1.83 gained +0.168 on train (t=0.25) and
lost 1.462 on holdout (t=-2.16). See sp_regime_break_finding_2026-08-26.md.
Clearing the floor means the gap is real; it does NOT mean it predicts.
"""
from __future__ import annotations

import math
from typing import Literal

# TWO BARS, and using the wrong one is the single easiest way to fool yourself.
#
# Z_GIVEN — the split point was handed to you by an EVENT (IL stint, trade, role
#   change). One test, no search. Bar = p90 of |z| over single splits = 1.83.
#   Flat across sample size (1.79-1.88 over 50-300+ TBF) and across talent level
#   (1.77-1.92 across K-BB% quintiles), and it lands in the same place for
#   hitters (1.82) as for pitchers (1.83).
#
# Z_SEARCHED — you scanned the season for the biggest gap. That is ~100 tests,
#   and the max of 100 draws is not distributed like one draw. Measured on the
#   max-split statistic itself: SP p90 = 2.58 (1,326 seasons), hitters p90 = 2.79
#   (2,437 seasons).
#
# The cost of confusing them: 39% of pitcher-seasons and 50% of hitter-seasons
# clear the GIVEN bar at their best split BY CONSTRUCTION. The hitter max-split
# MEDIAN is 1.83 — exactly the single-split p90.
Z_GIVEN = 1.83
Z_SEARCHED_SP = 2.58
Z_SEARCHED_H = 2.79

# Back-compat alias; prefer the explicit names above.
Z_P90 = Z_GIVEN
# p50 and p99 for context when reporting how extreme a gap is.
Z_P50, Z_P99 = 0.75, 2.90

# Over-dispersion vs pure sampling noise, measured per metric.
# Pitchers vs hitters INVERT on walks, which is the most interpretable result
# of the whole study:
#     SP      k_pct 1.134 | k_minus_bb 1.114 | bb_pct 1.053  <- walks move least
#     Hitter  k_pct 1.104 | k_minus_bb 1.104 | bb_pct 1.139  <- walks move MOST
# The walk belongs to the batter. Pitcher command barely moves within a season
# (ratifying stabilization.NEVER_STABILIZES listing pitcher bb_pct, and CLAUDE.md
# gotcha #11's "watch STUFF, not walks"); hitter plate discipline genuinely does.
DISPERSION = {"k_pct": 1.134, "k_minus_bb": 1.114, "bb_pct": 1.053}
DISPERSION_HITTER = {"k_pct": 1.104, "k_minus_bb": 1.104, "bb_pct": 1.139}

Metric = Literal["k_pct", "k_minus_bb", "bb_pct"]


def _per_event_variance(metric: Metric, p_k: float, p_bb: float) -> float:
    """Variance of one plate appearance's contribution to the rate."""
    if metric == "k_pct":
        return p_k * (1 - p_k)
    if metric == "bb_pct":
        return p_bb * (1 - p_bb)
    # K-BB per PA takes values +1 (K), -1 (BB), 0 otherwise.
    return (p_k + p_bb) - (p_k - p_bb) ** 2


def split_floor(k1: float, bb1: float, n1: float,
                k2: float, bb2: float, n2: float,
                metric: Metric = "k_minus_bb") -> dict:
    """Is the difference between two segments outside ordinary variation?

    k/bb are COUNTS, n is the denominator (TBF for pitchers, PA for hitters).
    Returns gap, sampling SE, z, the p90 threshold in rate units, and a verdict.
    """
    if n1 <= 0 or n2 <= 0:
        raise ValueError("split_floor: both segments need a positive denominator")
    p_k = (k1 + k2) / (n1 + n2)
    p_bb = (bb1 + bb2) / (n1 + n2)
    v = _per_event_variance(metric, p_k, p_bb)
    se = math.sqrt(v * (1.0 / n1 + 1.0 / n2)) if v > 0 else float("nan")

    def rate(k, bb, n):
        if metric == "k_pct":
            return k / n
        if metric == "bb_pct":
            return bb / n
        return (k - bb) / n

    gap = abs(rate(k2, bb2, n2) - rate(k1, bb1, n1))
    z = gap / se if se and se == se and se > 0 else float("nan")
    thresh = Z_GIVEN * se
    if z != z:
        verdict = "UNMEASURABLE"
    elif z > Z_P99:
        verdict = "FAR OUTSIDE (top 1%)"
    elif z > Z_P90:
        verdict = "EXCEEDS FLOOR (top 10%)"
    elif z > Z_P50:
        verdict = "within noise (above median)"
    else:
        verdict = "WITHIN NOISE"
    return dict(metric=metric, gap=gap, se=se, z=z, threshold=thresh,
                verdict=verdict, n_small=min(n1, n2))


def floor_for(n1: float, n2: float, p_k: float, p_bb: float,
              metric: Metric = "k_minus_bb", *, searched: bool = False,
              side: str = "SP") -> float:
    """The rate-unit gap a split must exceed for this player and sample.

    Pass ``searched=True`` when YOU picked the split point by looking for the
    biggest gap; the bar roughly doubles in false-positive terms.
    """
    v = _per_event_variance(metric, p_k, p_bb)
    if searched:
        bar = Z_SEARCHED_H if side == "H" else Z_SEARCHED_SP
    else:
        bar = Z_GIVEN
    return bar * math.sqrt(v * (1.0 / n1 + 1.0 / n2))


# ── FP/start splits (calibrated 2026-08-28) ──────────────────────────────────
# The decision layer increasingly screens RESULTS gaps in FP-per-start terms
# (forward distribution cards, the new-leaf boards, the calibration study's
# Gate 1), and until 2026-08-28 every such screen improvised a NAIVE Welch z —
# with no dispersion calibration at all. Measured on the same panel discipline
# as the K-BB floor (1,175 pitcher-seasons 2018-2026, >=12 GS; every split
# with >=4 starts per side = 21,242 splits; iid null = per-season start-order
# shuffle with identical split geometry, seed 20260828):
#
#     var(z_obs) / var(z_shuffle) = 1.180 overall — and it GROWS with window
#     size (min-side 4-5: 1.121 · 6-9: 1.165 · 10+: 1.259), i.e. real
#     within-season temporal structure accumulates; a naive Welch z is too
#     lenient exactly when the windows look most trustworthy.
#
# Searched-split honesty, FP edition: the per-season MAX naive z has
# p50 = 1.86 — the median season's best split "clears" the given bar by
# construction — and p90 = 3.17 naive (~2.92 after dispersion), hence
# Z_SEARCHED_FP below. Full memo: fp_split_floor_calibration_2026-08-28.md.
DISPERSION_FP_SP = {(4, 5): 1.121, (6, 9): 1.165, (10, None): 1.259}
DISPERSION_FP_SP_OVERALL = 1.180
Z_SEARCHED_FP = 2.92


def _fp_dispersion(min_side: int) -> float:
    for (lo, hi), ratio in DISPERSION_FP_SP.items():
        if min_side >= lo and (hi is None or min_side <= hi):
            return ratio
    return DISPERSION_FP_SP_OVERALL


def split_floor_fp(pre_fps, post_fps) -> dict:
    """Is an FP-per-start gap between two windows outside ordinary variation?

    Same contract as :func:`split_floor` — (gap, se, z, threshold, verdict,
    n_small) — but on per-start FP arrays, with the Welch SE inflated by the
    empirically measured within-season over-dispersion for the window size.
    Judge the returned z at Z_GIVEN for an event-supplied split and at
    Z_SEARCHED_FP for a split you went looking for.

    Both sides need >=4 starts (below the calibration's own admissibility);
    fewer returns verdict UNMEASURABLE rather than a falsely precise z.
    """
    import numpy as _np

    a = _np.asarray(pre_fps, dtype=float)
    b = _np.asarray(post_fps, dtype=float)
    n1, n2 = len(a), len(b)
    if min(n1, n2) < 4:
        return dict(metric="fp_per_start", gap=float("nan"), se=float("nan"),
                    z=float("nan"), threshold=float("nan"),
                    verdict="UNMEASURABLE", n_small=min(n1, n2))
    naive_se = math.sqrt(a.var(ddof=1) / n1 + b.var(ddof=1) / n2)
    se = naive_se * math.sqrt(_fp_dispersion(min(n1, n2)))
    gap = abs(float(b.mean()) - float(a.mean()))
    z = gap / se if se > 0 else float("nan")
    if z != z:
        verdict = "UNMEASURABLE"
    elif z > Z_P99:
        verdict = "FAR OUTSIDE (top 1%)"
    elif z > Z_P90:
        verdict = "EXCEEDS FLOOR (top 10%)"
    elif z > Z_P50:
        verdict = "within noise (above median)"
    else:
        verdict = "WITHIN NOISE"
    return dict(metric="fp_per_start", gap=gap, se=se, z=z,
                threshold=Z_GIVEN * se, verdict=verdict, n_small=min(n1, n2))
