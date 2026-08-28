"""fit_boom_shrinkage — the shrinkage slope for an observed boom% read.

WHY
`/boom-bust-history` prints a boom rate over a short window (SP L8, H L21,
RP L15). A rate from a handful of trials is mostly sampling noise, so the
honest forward statement is not the observed rate but

    forward = base + slope * (observed - base)

with slope < 1. This script measures `slope` per window length, per side, by
OLS of the NEXT-window boom rate on the observed-window boom rate. Strictly
out-of-sample: the two windows never overlap.

Shipped constants live in lib/boom_bust (BOOM_SHRINK_SLOPE*, *_BOOM_BASE)
and are consumed by forward_rate(). Rule 13: diagnostic/display only.

Run:  PLV_BOOM_SIDE={SP|H|RP} python scripts/xfp/fit_boom_shrinkage.py
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts/xfp"))
from validate_boom_window import CFG, SIDE, RP_PANEL  # noqa: E402
from metric_reliability import load, PIT, HIT  # noqa: E402


def main() -> int:
    panel = {"PIT": PIT, "HIT": HIT, "RP": RP_PANEL}[CFG["panel"]]
    by = load(panel, "batter" if CFG["panel"] == "HIT" else "pitcher")
    thr = CFG["boom"]
    is_sp = SIDE == "SP"

    series = []
    for _key, g in by.items():
        rows = [r for r in g if int(r["gs"] or 0) == 1] if is_sp else list(g)
        fp = np.array([float(r["fp"]) for r in rows])
        if len(fp) >= 2 * min(CFG["grid"]):
            series.append((fp >= thr).astype(int))

    base = float(np.mean(np.concatenate(series)))
    print(f"side={SIDE}  boom>={thr:g}  {len(series):,} {CFG['unit']}-seasons  "
          f"base boom rate={base:.3f}\n")
    print(f"  {'window':>8}{'pairs':>9}{'slope':>9}{'95% CI':>18}{'r':>8}")

    out = {}
    for w in CFG["grid"]:
        x, y, owner = [], [], []
        for i, b in enumerate(series):
            # non-overlapping consecutive windows within one player-season
            for s in range(0, len(b) - 2 * w + 1, w):
                x.append(b[s:s + w].mean())
                y.append(b[s + w:s + 2 * w].mean())
                owner.append(i)
        if len(x) < 50:
            print(f"  {'L'+str(w):>8}{len(x):>9}   (too few pairs)")
            continue
        x_, y_ = np.array(x), np.array(y)
        slope = float(np.polyfit(x_, y_, 1)[0])
        r = float(np.corrcoef(x_, y_)[0, 1])
        # cluster bootstrap by player-season — pairs from one season are not
        # independent (don't-do 17c).
        rng = np.random.default_rng(0)
        own = np.array(owner)
        uniq = np.unique(own)
        boots = []
        for _ in range(400):
            pick = rng.choice(uniq, size=len(uniq), replace=True)
            idx = np.concatenate([np.flatnonzero(own == u) for u in pick])
            boots.append(np.polyfit(x_[idx], y_[idx], 1)[0])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        out[w] = slope
        print(f"  {'L'+str(w):>8}{len(x):>9}{slope:>9.3f}"
              f"{f'[{lo:+.3f}, {hi:+.3f}]':>18}{r:>8.3f}")

    print("\n  paste into lib/boom_bust:")
    print("  " + repr({k: round(v, 3) for k, v in out.items()}))
    print(f"  base = {base:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
