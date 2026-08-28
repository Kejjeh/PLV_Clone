"""metric_reliability — which in-season metrics are worth reading, and why?

The v5 study produced an over-dispersion figure per metric (total variation
divided by pure sampling variation) and found pitchers and hitters INVERT on
walks: SP bb_pct 1.053 (least real) vs hitter bb_pct 1.139 (most real).

That raised a claim worth testing rather than asserting: if a metric's variation
is mostly sampling noise, reading it off half a season should tell you little
about the other half — and little about forward scoring.

THREE QUANTITIES, MEASURED AT A MATCHED SAMPLE SIZE
  dispersion   total |z| / half-normal expectation. >1 means real movement
               exists on top of sampling noise.
  r_split      corr(first-half metric, second-half metric) ACROSS players.
               This is reliability: does the metric describe a stable trait?
  r_fwd        corr(first-half metric, second-half FP/game or FP/start).
               This is what actually earns a metric a place in a decision.

Sample is matched by DENOMINATOR, not by games: each player's season is cut at
the point where the first segment reaches HALF_N events, and the second segment
must also reach HALF_N. Otherwise durable players dominate one side of the
correlation and the reliability estimate is a playing-time artifact.

Rule 13: descriptive. Nothing here re-ranks rh3/rp3/rprs2.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIT = os.path.join(ROOT, "data/research/xfp_cache/hitter_event_panel_2017_2026.csv")
PIT = os.path.join(ROOT, "data/research/xfp_cache/sp_event_panel_2017_2026.csv")
OUT = os.path.join(ROOT, "data/outputs/metric_reliability.csv")

HALF_PA = 200      # hitters: 200 PA per half
HALF_TBF = 250     # pitchers: 250 TBF per half


def corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 30:
        return float("nan"), int(ok.sum())
    x, y = x[ok], y[ok]
    if x.std() == 0 or y.std() == 0:
        return float("nan"), len(x)
    return float(np.corrcoef(x, y)[0, 1]), len(x)


def halves(rows, denom_key, half_n):
    """Cut at the point the first segment reaches half_n; require the same after."""
    d = np.array([float(r[denom_key]) for r in rows])
    c = np.cumsum(d)
    if c[-1] < 2 * half_n:
        return None
    i = int(np.searchsorted(c, half_n) + 1)
    if i >= len(rows) or (c[-1] - c[i - 1]) < half_n:
        return None
    return rows[:i], rows[i:]


def rate(rows, num_keys, den_key, sign=None):
    n = sum(float(r[den_key]) for r in rows)
    if not n:
        return float("nan")
    v = 0.0
    for j, k in enumerate(num_keys):
        s = sign[j] if sign else 1
        v += s * sum(float(r[k]) for r in rows)
    return v / n


def load(path, key):
    by = defaultdict(list)
    with open(path) as fh:
        for r in csv.DictReader(fh):
            by[(int(r[key]), int(r["year"]))].append(r)
    for k in by:
        by[k].sort(key=lambda r: r["game_date"])
    return by


def dispersion(pairs):
    """|z| mean / 0.798 over the matched halves."""
    zs = [p for p in pairs if np.isfinite(p)]
    return (np.mean(zs) / 0.798) if zs else float("nan")


def run_side(name, by, denom, half_n, metrics, fp_per):
    out = []
    for label, num, sign in metrics:
        a, b, fwd, zl = [], [], [], []
        for key, rows in by.items():
            h = halves(rows, denom, half_n)
            if not h:
                continue
            h1, h2 = h
            r1, r2 = rate(h1, num, denom, sign), rate(h2, num, denom, sign)
            if not (np.isfinite(r1) and np.isfinite(r2)):
                continue
            n1 = sum(float(x[denom]) for x in h1)
            n2 = sum(float(x[denom]) for x in h2)
            # sampling SE of the difference, treating each event as +-1/0
            p = abs(rate(h1 + h2, num, denom, sign))
            v = max(p * (1 - p), 1e-6) if len(num) == 1 else max(
                sum(abs(rate(h1 + h2, [k], denom)) for k in num) - p ** 2, 1e-6)
            se = np.sqrt(v * (1 / n1 + 1 / n2))
            zl.append(abs(r2 - r1) / se if se > 0 else np.nan)
            a.append(r1)
            b.append(r2)
            units = fp_per(h2)
            fwd.append(units)
        rs, n_rs = corr(a, b)
        rf, _ = corr(a, fwd)
        out.append(dict(side=name, metric=label, n=n_rs,
                        dispersion=dispersion(zl), r_split=rs, r_fwd=rf))
    return out


def main() -> int:
    hb = load(HIT, "batter")
    pb = load(PIT, "pitcher")

    def hit_fp(rows):
        g = len(rows)
        return (sum(float(r["fp"]) for r in rows) / g) if g else float("nan")

    def pit_fp(rows):
        st = [r for r in rows if int(r["gs"] or 0) == 1]
        return (sum(float(r["fp"]) for r in st) / len(st)) if st else float("nan")

    hm = [("K%", ["k"], None), ("BB%", ["bb"], None), ("K-BB%", ["k", "bb"], [1, -1]),
          ("HR/PA", ["hr"], None), ("SB/PA", ["sb"], None), ("TB/PA", ["tb"], None)]
    # the SP panel carries no HR column; ER/TBF stands in as the runs-allowed lens
    pm = [("K%", ["k"], None), ("BB%", ["bb"], None), ("K-BB%", ["k", "bb"], [1, -1]),
          ("H/TBF", ["h"], None), ("ER/TBF", ["er"], None)]

    rows = run_side("HITTER", hb, "pa", HALF_PA, hm, hit_fp) + \
        run_side("SP", pb, "tbf", HALF_TBF, pm, pit_fp)

    print(f"\n{'='*94}")
    print(f"METRIC RELIABILITY — matched halves ({HALF_PA} PA / {HALF_TBF} TBF per side)")
    print(f"{'='*94}")
    print(f"{'side':<8}{'metric':<9}{'n':>6}{'dispersion':>12}{'r_split':>10}{'r_fwd(FP)':>12}"
          f"   reading")
    for r in rows:
        if r["r_split"] != r["r_split"]:
            continue
        rd = ("worth reading" if r["r_split"] >= 0.50 else
              "weak" if r["r_split"] >= 0.30 else "NOT worth reading")
        print(f"{r['side']:<8}{r['metric']:<9}{r['n']:>6}{r['dispersion']:>12.3f}"
              f"{r['r_split']:>10.3f}{r['r_fwd']:>12.3f}   {rd}")
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {OUT}")
    good = [r for r in rows if np.isfinite(r["r_split"]) and np.isfinite(r["dispersion"])]
    d = [r["dispersion"] for r in good]
    s = [r["r_split"] for r in good]
    f = [r["r_fwd"] for r in good]
    print(f"\ncorr(dispersion, r_split) = {corr(d, s)[0]:+.3f}   "
          f"corr(dispersion, r_fwd) = {corr(d, f)[0]:+.3f}   (n={len(good)} metrics)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
