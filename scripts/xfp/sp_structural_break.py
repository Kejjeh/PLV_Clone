"""sp_structural_break — a PROPERLY TESTED structural break, not the noisiest split.

WHAT WAS WRONG IN v1
--------------------
v1 split on FP/start and took the largest mean separation with no null
distribution. FP/start has a within-pitcher SD near 9, so the largest split of
any season is almost always noise: v1 "found a break" in 80% of pitcher-seasons
and its adjustment lost to simply using the season mean (holdout MAE +0.33).

WHAT v2 DOES DIFFERENTLY — four changes, each targeting one defect
-----------------------------------------------------------------
1. TEST A STABILIZING RATE, NOT A NOISY COMPOSITE.
   The break is tested on K% (K/TBF), not FP. SP K% is the rate this repo has
   actually measured as readable in-window (stabilization.SP_MINS -> 100 TBF).
   FP/start bundles K, IP, H, ER, BB and sequencing luck; a shift in it is
   mostly BABIP. A shift in K% is a shift in the pitcher.

2. GATE BOTH SEGMENTS AT THE STABILIZATION MINIMUM.
   A candidate split is only considered when BOTH sides carry >= 100 TBF, so
   each side's K% is a readable number rather than a rumour. This is the
   trimming rule, and it comes from the module, not from taste.

3. CALIBRATE FOR THE SEARCH WITH A PERMUTATION NULL.
   Statistic is sup|z| of a two-proportion test over all admissible splits.
   Because the split point is CHOSEN, its null distribution is not standard
   normal. Start order is exchangeable under "no break", so we shuffle the
   (k, tbf) pairs B times, recompute sup|z| each time, and take the empirical
   p-value. This is exactly calibrated to the search that produced it — the
   thing v1 had no answer for.

4. CONTROL FALSE DISCOVERIES ACROSS PITCHERS.
   Testing ~1300 pitcher-seasons at p<0.05 would hand back ~65 fake breaks.
   Benjamini-Hochberg FDR across all seasons tested, matching the protocol
   already used by the in-season delta grid.

An ABSENCE (>=25-day gap) is an event, not a search: its split point is given
rather than chosen, so it is reported separately and does not pay the search
penalty. It is still required to show a real K% shift.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from plv_clone import stabilization as stab  # noqa: E402

MIN_TBF_SIDE, _UNIT = stab.minimum("k_pct", "SP")   # 100 TBF — not hand-picked
GAP_DAYS = 25
B_PERM = 400
FDR_Q = 0.10


def sup_z(k: np.ndarray, tbf: np.ndarray, min_tbf: int = MIN_TBF_SIDE):
    """sup|two-proportion z| over splits where BOTH sides clear min_tbf.

    Returns (sup_stat, split_index) or (nan, None) when no split is admissible.
    """
    ck, ct = np.cumsum(k), np.cumsum(tbf)
    K, T = ck[-1], ct[-1]
    i = np.arange(1, len(k))
    t1, t2 = ct[:-1], T - ct[:-1]
    ok = (t1 >= min_tbf) & (t2 >= min_tbf)
    if not ok.any():
        return np.nan, None
    k1, k2 = ck[:-1], K - ck[:-1]
    p = K / T
    with np.errstate(divide="ignore", invalid="ignore"):
        se = np.sqrt(p * (1 - p) * (1.0 / t1 + 1.0 / t2))
        z = np.abs(k1 / t1 - k2 / t2) / se
    z = np.where(ok & np.isfinite(z), z, -np.inf)
    j = int(np.argmax(z))
    return float(z[j]), int(i[j])


def perm_pvalue(k, tbf, observed, rng, B=B_PERM, min_tbf=MIN_TBF_SIDE):
    """Empirical p-value for sup|z| under exchangeable start order."""
    if not np.isfinite(observed):
        return np.nan
    n = len(k)
    ge = 0
    idx = np.arange(n)
    for _ in range(B):
        rng.shuffle(idx)
        s, _ = sup_z(k[idx], tbf[idx], min_tbf)
        if np.isfinite(s) and s >= observed:
            ge += 1
    return (ge + 1) / (B + 1)


def bh_fdr(pvals, q=FDR_Q):
    """Benjamini-Hochberg. Returns a boolean mask of rejections."""
    p = np.asarray(pvals, float)
    ok = np.isfinite(p)
    out = np.zeros(len(p), bool)
    idx = np.where(ok)[0]
    if len(idx) == 0:
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        out[order[: kmax + 1]] = True
    return out


def absence_split(dates, tbf, min_tbf: int = MIN_TBF_SIDE):
    """Largest >=GAP_DAYS gap whose two sides both clear min_tbf. Event, not search."""
    ct = np.cumsum(tbf)
    T = ct[-1]
    best, bestg = None, 0
    for i in range(1, len(dates)):
        g = (dates[i] - dates[i - 1]).days
        if g >= GAP_DAYS and ct[i - 1] >= min_tbf and (T - ct[i - 1]) >= min_tbf:
            if g > bestg:
                best, bestg = i, g
    return best, bestg


def parse_date(s):
    return dt.date(*map(int, s.split("-")))


def perm_pvalue_fast(k, tbf, observed, rng, B, min_tbf=MIN_TBF_SIDE):
    """Vectorised permutation p-value.

    RESOLUTION FLOOR (the bug this exists to fix): an empirical p-value from B
    permutations cannot go below 1/(B+1). BH-FDR over M tests needs the smallest
    p to clear q/M. With B=400 and M=1339 the floor is 0.0025 while the bar is
    7.5e-5, so NO test can ever be rejected regardless of the data. Always check
    1/(B+1) < q/M before believing a null result from a permutation test.
    """
    if not np.isfinite(observed):
        return np.nan
    n = len(k)
    ge = 0
    CH = 2000
    done = 0
    while done < B:
        b = min(CH, B - done)
        idx = np.argsort(rng.random((b, n)), axis=1)
        kk, tt = k[idx], tbf[idx]
        ck, ct = np.cumsum(kk, axis=1), np.cumsum(tt, axis=1)
        K = ck[:, -1:], 
        Ktot, Ttot = ck[:, -1:], ct[:, -1:]
        t1, t2 = ct[:, :-1], Ttot - ct[:, :-1]
        k1, k2 = ck[:, :-1], Ktot - ck[:, :-1]
        p = Ktot / Ttot
        with np.errstate(divide="ignore", invalid="ignore"):
            se = np.sqrt(p * (1 - p) * (1.0 / t1 + 1.0 / t2))
            z = np.abs(k1 / t1 - k2 / t2) / se
        okm = (t1 >= min_tbf) & (t2 >= min_tbf) & np.isfinite(z)
        z = np.where(okm, z, -np.inf)
        ge += int((z.max(axis=1) >= observed).sum())
        done += b
    return (ge + 1) / (B + 1)
