"""backtest_sp_regime — does the regime re-anchor actually beat the season-to-date level?

STRICTLY NO LOOKAHEAD. At each as-of point t the break is detected using ONLY
starts 1..t. Prior-year aggregates are legitimately known at t. The outcome is
starts t+1..N and is never touched by the estimator.

Compared estimators, both available at t:
  BASE  mean FP/start over starts 1..t          (the season-to-date level; this is
                                                 rp3's dominant term and the thing
                                                 the method claims to beat)
  ADJ   regime re-anchor when a CORROBORATED break exists in 1..t, else BASE

Reported separately for ABSENCE (objective >=25d gap, no search) and SEARCHED
(changepoint scan) breaks, because they carry different evidential weight and
the live board leans on both.

Pseudo-replication killed the earlier stuff_regime_delta result, so every
headline is reported BOTH pooled and at one-row-per-pitcher-season.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import statistics as st
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANEL = os.path.join(ROOT, "data/research/xfp_cache/sp_gamelogs_2017_2026.csv")

GAP_DAYS = 25
MIN_SIDE_ABSENCE = 4
MIN_SIDE_SEARCH = 6
K_TOL = 0.05
W_PRIOR = 5.0
MIN_REMAIN = 5
MIN_ASOF = 10

TRAIN = [2017, 2018, 2019, 2021, 2022, 2023]
HOLD = [2024, 2025]


def d(s):
    return dt.date(*map(int, s.split("-")))


def agg(rows):
    n = len(rows)
    fp = sum(r["fp"] for r in rows) / n
    tbf = sum(r["tbf"] for r in rows)
    k = sum(r["k"] for r in rows)
    return n, fp, (k / tbf if tbf else None)


def detect(hist):
    """Break detection on hist ONLY (starts 1..t). Returns (idx, kind) or None."""
    best = None
    for i in range(1, len(hist)):
        g = (d(hist[i]["game_date"]) - d(hist[i - 1]["game_date"])).days
        if g >= GAP_DAYS and i >= MIN_SIDE_ABSENCE and len(hist) - i >= MIN_SIDE_ABSENCE:
            if best is None or g > best[2]:
                best = (i, "ABSENCE", g)
    if best:
        return best[0], best[1]
    bi, bsep = None, 0.0
    for i in range(MIN_SIDE_SEARCH, len(hist) - MIN_SIDE_SEARCH + 1):
        a = sum(r["fp"] for r in hist[:i]) / i
        b = sum(r["fp"] for r in hist[i:]) / (len(hist) - i)
        if abs(a - b) > bsep:
            bi, bsep = i, abs(a - b)
    return (bi, "SEARCHED") if bi else None


def main() -> int:
    by = defaultdict(list)
    with open(PANEL) as fh:
        for r in csv.DictReader(fh):
            by[(int(r["pitcher"]), int(r["year"]))].append(
                {"game_date": r["game_date"], "fp": float(r["fp"]),
                 "k": float(r["k"]), "tbf": float(r["tbf"])})
    for kk in by:
        by[kk].sort(key=lambda r: r["game_date"])

    rows = []
    for (pid, yr), gl in by.items():
        if len(gl) < MIN_ASOF + MIN_REMAIN:
            continue
        pr = by.get((pid, yr - 1))
        if pr and len(pr) >= 5:
            _, fp_prior, k_prior = agg(pr)
        else:
            fp_prior = k_prior = None
        for t in range(MIN_ASOF, len(gl) - MIN_REMAIN + 1):
            hist, fut = gl[:t], gl[t:]
            _, base, _ = agg(hist)
            _, actual, _ = agg(fut)
            kind, adj = "NONE", base
            hit = detect(hist)
            if hit and k_prior is not None:
                i, kd = hit
                n_post, fp_post, k_post = agg(hist[i:])
                if k_post is not None and abs(k_post - k_prior) <= K_TOL:
                    adj = (n_post * fp_post + W_PRIOR * fp_prior) / (n_post + W_PRIOR)
                    kind = kd
            rows.append({"pid": pid, "year": yr, "t": t, "kind": kind,
                         "base": base, "adj": adj, "actual": actual})

    def report(rs, label):
        if len(rs) < 20:
            print(f"  {label:<26} n={len(rs)} (too few)")
            return
        mb = st.mean(abs(r["base"] - r["actual"]) for r in rs)
        ma = st.mean(abs(r["adj"] - r["actual"]) for r in rs)
        # correlation with outcome
        def corr(key):
            xs = [r[key] for r in rs]; ys = [r["actual"] for r in rs]
            mx, my = st.mean(xs), st.mean(ys)
            num = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
            den = (sum((a-mx)**2 for a in xs) * sum((b-my)**2 for b in ys)) ** .5
            return num/den if den else float("nan")
        wins = sum(1 for r in rs if abs(r["adj"]-r["actual"]) < abs(r["base"]-r["actual"]))
        ties = sum(1 for r in rs if r["adj"] == r["base"])
        eff = len(rs) - ties
        print(f"  {label:<26} n={len(rs):<6} MAE base {mb:5.2f} -> adj {ma:5.2f} "
              f"({ma-mb:+5.2f})   r base {corr('base'):+.3f} -> adj {corr('adj'):+.3f}   "
              f"adj better {wins}/{eff}" if eff else "")

    for yrs, nm in ((TRAIN, "TRAIN 2017-23"), (HOLD, "HOLDOUT 2024-25")):
        sub = [r for r in rows if r["year"] in yrs]
        print(f"\n{'='*104}\n{nm}  —  pooled (all as-of points)\n{'='*104}")
        report(sub, "ALL rows")
        for k in ("ABSENCE", "SEARCHED"):
            report([r for r in sub if r["kind"] == k], f"break={k} (adj acts)")
        # one row per pitcher-season: middle as-of point
        seen, one = set(), []
        for r in sorted(sub, key=lambda x: (x["pid"], x["year"], x["t"])):
            key = (r["pid"], r["year"])
            if key in seen:
                continue
            cand = [q for q in sub if q["pid"] == r["pid"] and q["year"] == r["year"]]
            one.append(cand[len(cand)//2]); seen.add(key)
        print(f"  {'-'*100}")
        report(one, "ONE row / pitcher-season")
        for k in ("ABSENCE", "SEARCHED"):
            report([r for r in one if r["kind"] == k], f"  ^ break={k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
