"""validate_boom_window — is an L8 boom%/bust% read decision-grade?

WHY ASK
`/boom-bust-history` reports SP boom% and bust% over the **last 8 starts**, and
its own description contrasts "a 37% boom hot streak (Bradish)" with "0% boom
25% bust cap-fodder (Valdez)". Those are 3/8 versus 0/8.

A proportion from 8 trials has a sampling SE of sqrt(p(1-p)/8) — about **15
percentage points** at p=0.25. The immediate question is whether an L8 boom rate
distinguishes pitchers at all, or whether it is mostly the same coin landing
differently.

This follows directly from `k_prior_blend_weight_2026-08-27.md`, which found a
bootstrap of a pitcher's own history loses to a smooth parametric summary at
n<=30 starts. L8 is n=8.

THREE PREDICTORS OF THE SAME THING, all available at the same moment:
  L8       boom rate over the last 8 starts        (what the tool shows)
  STD      boom rate over ALL starts season-to-date (a longer window)
  PARAM    P(FP >= 17) under N(season-to-date mean, global sigma)
           — a smooth summary that never counts a single start

Scored against (a) whether the NEXT start booms, and (b) the boom rate over the
next 8 starts. Strictly out-of-sample: everything at index i uses starts < i.

Rule 13: diagnostic. Nothing here re-ranks anything.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts/xfp"))
from metric_reliability import load, PIT, HIT  # noqa: E402

# Per-side config. Thresholds are the shipped display cutoffs from
# lib/boom_bust (SP_BOOM/BUST, H_BOOM/BUST); windows are the /boom-bust-history
# defaults; sigma is the panel-mean per-unit SD.
SIDES = {
    "SP": dict(boom=17.0, bust=5.0, window=8, sigma=8.73,
               grid=(3, 5, 8, 12, 20), panel="PIT", unit="start"),
    "H":  dict(boom=5.0, bust=0.0, window=21, sigma=3.30,
               grid=(7, 14, 21, 28, 40), panel="HIT", unit="game"),
}
SIDE = os.environ.get("PLV_BOOM_SIDE", "SP")
CFG = SIDES[SIDE]
SP_BOOM, SP_BUST = CFG["boom"], CFG["bust"]
SIGMA_GLOBAL = CFG["sigma"]
W = CFG["window"]


def norm_sf(x):
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def auc(scores, labels):
    s = np.asarray(scores, float)
    y = np.asarray(labels, int)
    if y.sum() == 0 or y.sum() == len(y):
        return float("nan")
    order = np.argsort(s)
    ranks = np.empty(len(s), float)
    ranks[order] = np.arange(1, len(s) + 1)
    # average ranks for ties
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt))
    np.add.at(sums, inv, ranks)
    ranks = (sums / cnt)[inv]
    n1 = y.sum()
    n0 = len(y) - n1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def main() -> int:
    is_sp = SIDE == "SP"
    by = load(PIT if is_sp else HIT, "pitcher" if is_sp else "batter")
    print(f"side={SIDE}  boom>={SP_BOOM}  bust<{SP_BUST}  window=L{W}  "
          f"sigma={SIGMA_GLOBAL}\n")
    rows = []
    for (pid, yr), g in by.items():
        st = [r for r in g if (int(r["gs"] or 0) == 1)] if is_sp else list(g)
        if len(st) < W + 2:
            continue
        fp = np.array([float(r["fp"]) for r in st])
        boom = (fp >= SP_BOOM).astype(int)
        bust = (fp < SP_BUST).astype(int)
        for i in range(W, len(fp)):
            m = fp[:i].mean()
            rows.append(dict(
                key=(pid, yr),
                l8_boom=boom[i - W:i].mean(),
                std_boom=boom[:i].mean(),
                par_boom=norm_sf((SP_BOOM - m) / SIGMA_GLOBAL),
                l8_bust=bust[i - W:i].mean(),
                std_bust=bust[:i].mean(),
                par_bust=1 - norm_sf((SP_BUST - m) / SIGMA_GLOBAL),
                y_boom=int(boom[i]), y_bust=int(bust[i]),
                nxt8_boom=boom[i:i + W].mean() if i + W <= len(fp) else np.nan,
            ))
    n = len(rows)
    ent = "pitcher" if SIDE == "SP" else "hitter"
    print(f"panel: {n:,} forecasts / {len({r['key'] for r in rows}):,} {ent}-seasons")
    base_b = np.mean([r["y_boom"] for r in rows])
    base_u = np.mean([r["y_bust"] for r in rows])
    print(f"base rates: boom {base_b:.3f}  bust {base_u:.3f}")
    print(f"SE of a boom rate from {W} starts at p={base_b:.2f}: "
          f"{math.sqrt(base_b*(1-base_b)/W):.3f}  ({100*math.sqrt(base_b*(1-base_b)/W):.0f}pp)\n")
    U = CFG["unit"]

    for lab, keys, y in ((f"BOOM (next {U} >= {SP_BOOM:g} FP)",
                          ("l8_boom", "std_boom", "par_boom"), "y_boom"),
                         (f"BUST (next {U} < {SP_BUST:g} FP)",
                          ("l8_bust", "std_bust", "par_bust"), "y_bust")):
        yy = [r[y] for r in rows]
        print(f"=== {lab} ===")
        print(f"  {'predictor':<26}{'AUC':>8}{'Brier':>9}{'vs base':>10}")
        print(f"  {'base rate (constant)':<26}{'0.500':>8}{brier([np.mean(yy)]*n, yy):>9.4f}"
              f"{0.0:>+10.4f}")
        bb = brier([np.mean(yy)] * n, yy)
        for k, nice in zip(keys, (f"L{W} window", "season-to-date", "PARAMETRIC (smooth)")):
            p = [r[k] for r in rows]
            print(f"  {nice:<26}{auc(p, yy):>8.4f}{brier(p, yy):>9.4f}{brier(p,yy)-bb:>+10.4f}")
        print()

    sub = [r for r in rows if np.isfinite(r["nxt8_boom"])]
    print(f"=== REGRESSION TO THE MEAN: what an L{W} boom read is worth (n={len(sub):,}) ===")
    print(f"  {f'L{W} boom (x/{W})':>15}{'n':>8}{f'next-{W} boom%':>15}")
    for k in range(0, W + 1):
        s = [r for r in sub if abs(r["l8_boom"] - k / W) < 1e-9]
        if len(s) < 40:
            continue
        nxt = np.mean([r["nxt8_boom"] for r in s])
        print(f"  {k}/{W} = {100*k/W:>5.0f}%{len(s):>8}{100*nxt:>14.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
