"""sweep_break_params — map the break-detection parameter space by PREDICTIVE value.

The question is not "which config finds the most breaks" (v1 found breaks in 80%
of seasons and lost to doing nothing). It is "which config, used to re-anchor,
best predicts rest-of-season FP/start".

AXES SWEPT
  metric      what the break is tested ON. FP/start is a noisy composite; K% and
              K-BB% are rates. This axis decides whether we detect a pitcher
              changing or a BABIP run.
  min_tbf     sample each segment must carry. THE central tension: a high gate
              buys power per test but the break is only detectable late, when
              little rest-of-season remains to exploit it. A low gate fires
              early but on thinner evidence.
  z_gate      sup|z| threshold. Higher = fewer, surer breaks.
  trigger     'absence' = only split at a >=25d gap (an event; split point is
              given, not chosen). 'search' = best admissible split anywhere.

FIXED: w_prior=5 pseudo-starts of shrinkage toward prior-year FP/start.

PROTOCOL. Stage 1 sweeps TRAIN only. Stage 2 takes the survivors to HOLDOUT once,
with BH-FDR across the cells carried forward. Strictly no lookahead anywhere:
detection at as-of t uses starts 1..t only; the outcome is t+1..N.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANEL = os.path.join(ROOT, "data/research/xfp_cache/sp_gamelogs_2017_2026.csv")

METRICS = ["k_pct", "k_minus_bb", "fp"]
MIN_TBF = [40, 60, 80, 100, 150]
Z_GATE = [1.5, 2.0, 2.5, 3.0, 3.5]
TRIGGER = ["absence", "search"]
W_PRIOR = 5.0
GAP_DAYS = 25
MIN_ASOF, MIN_REMAIN = 10, 5
N_ASOF = 6

TRAIN = [2017, 2018, 2019, 2021, 2022, 2023]
HOLD = [2024, 2025]


def load():
    by = defaultdict(list)
    with open(PANEL) as fh:
        for r in csv.DictReader(fh):
            by[(int(r["pitcher"]), int(r["year"]))].append(r)
    out = {}
    for kk, g in by.items():
        g.sort(key=lambda r: r["game_date"])
        out[kk] = dict(
            date=[dt.date(*map(int, r["game_date"].split("-"))) for r in g],
            k=np.array([float(r["k"]) for r in g]),
            bb=np.array([float(r["bb"]) for r in g]),
            tbf=np.array([float(r["tbf"]) for r in g]),
            fp=np.array([float(r["fp"]) for r in g]),
        )
    return out


def split_stats(num, den, i):
    """(rate1, rate2) for a split before index i."""
    n1, n2 = num[:i].sum(), num[i:].sum()
    d1, d2 = den[:i].sum(), den[i:].sum()
    return (n1 / d1 if d1 else np.nan), (n2 / d2 if d2 else np.nan), d1, d2


def z_at(num, den, i, binomial):
    r1, r2, d1, d2 = split_stats(num, den, i)
    if not (d1 and d2) or not np.isfinite(r1) or not np.isfinite(r2):
        return -np.inf
    if binomial:
        p = (num.sum()) / (den.sum())
        se = np.sqrt(max(p * (1 - p), 1e-9) * (1 / d1 + 1 / d2))
    else:  # mean of a continuous per-start quantity
        v = np.var(num / np.maximum(den, 1e-9))
        se = np.sqrt(max(v, 1e-9) * (1 / d1 + 1 / d2))
    return abs(r1 - r2) / se if se > 0 else -np.inf


def evaluate(data, years, cells):
    acc = {c: {"n": 0, "se_base": 0.0, "se_adj": 0.0, "fired": 0} for c in cells}
    for (pid, yr), D in data.items():
        if yr not in years:
            continue
        n = len(D["fp"])
        if n < MIN_ASOF + MIN_REMAIN:
            continue
        pr = data.get((pid, yr - 1))
        if pr is None or len(pr["fp"]) < 5:
            continue
        fp_prior = pr["fp"].mean()
        lo, hi = MIN_ASOF, n - MIN_REMAIN
        ts = sorted(set(np.linspace(lo, hi, N_ASOF).astype(int).tolist()))
        for t in ts:
            base = D["fp"][:t].mean()
            actual = D["fp"][t:].mean()
            tbf = D["tbf"][:t]
            gapidx = [i for i in range(1, t)
                      if (D["date"][i] - D["date"][i - 1]).days >= GAP_DAYS]
            for c in cells:
                metric, mt, zg, trig = c
                if metric == "k_pct":
                    num, den, binom = D["k"][:t], tbf, True
                elif metric == "k_minus_bb":
                    num, den, binom = D["k"][:t] - D["bb"][:t], tbf, True
                else:
                    num, den, binom = D["fp"][:t] * 1.0, np.ones(t), False
                ct = np.cumsum(tbf)
                cand = [i for i in range(1, t) if ct[i - 1] >= mt and (ct[-1] - ct[i - 1]) >= mt]
                if trig == "absence":
                    cand = [i for i in cand if i in gapidx]
                adj = base
                if cand:
                    zs = [z_at(num, den, i, binom) for i in cand]
                    j = int(np.argmax(zs))
                    if zs[j] >= zg:
                        i = cand[j]
                        post = D["fp"][i:t]
                        adj = (len(post) * post.mean() + W_PRIOR * fp_prior) / (len(post) + W_PRIOR)
                        acc[c]["fired"] += 1
                a = acc[c]
                a["n"] += 1
                a["se_base"] += abs(base - actual)
                a["se_adj"] += abs(adj - actual)
    rows = []
    for c, a in acc.items():
        if not a["n"]:
            continue
        rows.append(dict(metric=c[0], min_tbf=c[1], z_gate=c[2], trigger=c[3],
                         n=a["n"], fire_pct=100 * a["fired"] / a["n"],
                         mae_base=a["se_base"] / a["n"], mae_adj=a["se_adj"] / a["n"],
                         gain=(a["se_base"] - a["se_adj"]) / a["n"]))
    return rows


def main() -> int:
    data = load()
    cells = [(m, t, z, g) for m in METRICS for t in MIN_TBF for z in Z_GATE for g in TRIGGER]
    print(f"sweeping {len(cells)} cells on TRAIN {TRAIN} ...", flush=True)
    rows = evaluate(data, TRAIN, cells)
    rows.sort(key=lambda r: -r["gain"])
    print(f"\n{'='*100}\nTOP 20 BY TRAIN MAE GAIN (positive = adj beats season-to-date level)\n{'='*100}")
    print(f"{'metric':<12}{'minTBF':>7}{'zgate':>7}{'trigger':>9}{'fire%':>8}"
          f"{'MAEbase':>9}{'MAEadj':>8}{'GAIN':>8}")
    for r in rows[:20]:
        print(f"{r['metric']:<12}{r['min_tbf']:>7}{r['z_gate']:>7.1f}{r['trigger']:>9}"
              f"{r['fire_pct']:>8.1f}{r['mae_base']:>9.3f}{r['mae_adj']:>8.3f}{r['gain']:>+8.3f}")
    out = os.path.join(ROOT, "data/outputs/break_param_sweep_train.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out}")
    pos = [r for r in rows if r["gain"] > 0]
    print(f"cells with positive train gain: {len(pos)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
