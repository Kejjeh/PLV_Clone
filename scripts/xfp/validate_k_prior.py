"""validate_k_prior — is sp_bench_mc's blend weight k_prior=20 the right one?

WHY THIS, AND WHY IT IS NOT ALREADY ANSWERED
`sp_bench_mc.build_sp_sampler(prior='blend')` mixes a bootstrap of the pitcher's
own past starts with a parametric Gaussian, at weight `n/(n+k_prior)`, default
**k_prior=20**. The family choice was validated (F2, 2026-07-29 — lognormal was
structurally broken and Gaussian replaced it) and the opp_factor application was
fixed (I1, 2026-07-30). **The blend WEIGHT never was.** `k_prior` appears in no
validation memo. It governs the single highest-leverage call the tool makes.

It matters because a single start is the one place distributional shape is worth
computing: with no aggregation the normal approximation is unbiased on average
but has p90 |error| of 8-14pp of win probability per pitcher
(`distribution_shape_2026-08-27.md`). At k_prior=20 a full-season starter (26
starts) still draws ~43% of its mass from the parametric leg.

WHAT IS AND IS NOT TESTED HERE
Scored by CRPS against the REALIZED NEXT START, strictly out-of-sample: the pool
at start i contains only starts 1..i-1.

HONEST LIMITATION, STATED UP FRONT: the production parametric leg is rp3's
predictive mean and band, and historical rp3 snapshots are not reproducible from
game logs alone. The stand-in here is Gaussian(season-to-date mean, global
sigma) — the same FAMILY and the same "smooth summary of the pitcher" role, but
not literally rp3. So this measures the crossover in how much a pitcher's own
start history should outweigh a smooth parametric summary, which is exactly what
k_prior encodes, WITHOUT claiming to reproduce rp3's exact skill. A k_prior
optimum found here should be confirmed against real rp3 snapshots before the
default is changed.

Rule 13: diagnostic. Proposes no change on its own.
"""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts/xfp"))
from metric_reliability import load, PIT  # noqa: E402

SIGMA_GLOBAL = 8.73          # panel median per-start sigma, per the F2 memo
K_GRID = [0, 2, 5, 10, 15, 20, 30, 50, 100, 10**9]
MIN_POOL = 3
NDRAW = 400
SEED = 20260827


def crps(draws: np.ndarray, y: float) -> float:
    """CRPS via the energy identity: E|X-y| - 0.5*E|X-X'|."""
    a = np.abs(draws - y).mean()
    d = draws[: len(draws) // 2]
    e = draws[len(draws) // 2 : 2 * (len(draws) // 2)]
    b = np.abs(d - e).mean()
    return float(a - 0.5 * b)


def main() -> int:
    by = load(PIT, "pitcher")
    rng = np.random.default_rng(SEED)
    rows = []
    for (pid, yr), g in by.items():
        st = [r for r in g if int(r["gs"] or 0) == 1]
        if len(st) < MIN_POOL + 3:
            continue
        fp = np.array([float(r["fp"]) for r in st])
        for i in range(MIN_POOL, len(fp)):
            pool, y = fp[:i], fp[i]
            rows.append((pid, yr, pool, y))
    print(f"panel: {len(rows):,} next-start forecasts over "
          f"{len({(a, b) for a, b, _, _ in rows}):,} pitcher-seasons\n")

    print(f"{'k_prior':>9}{'mean emp wt':>13}{'CRPS':>10}{'vs k=20':>10}")
    out = {}
    for k in K_GRID:
        tot, wts = [], []
        for _, _, pool, y in rows:
            n = len(pool)
            w = 1.0 if k == 0 else (0.0 if k >= 10**9 else n / (n + k))
            wts.append(w)
            mask = rng.random(NDRAW) < w
            d = rng.normal(pool.mean(), SIGMA_GLOBAL, NDRAW)
            ne = int(mask.sum())
            if ne:
                d[mask] = rng.choice(pool, ne, replace=True)
            tot.append(crps(d, y))
        out[k] = float(np.mean(tot))
        lab = "inf (pure param)" if k >= 10**9 else ("0 (pure emp)" if k == 0 else str(k))
        print(f"{lab:>9}{np.mean(wts):>13.3f}{out[k]:>10.4f}"
              f"{out[k]-out.get(20, out[k]):>+10.4f}")

    best = min(out, key=out.get)
    bl = "inf" if best >= 10**9 else best
    print(f"\n  BEST k_prior = {bl}   CRPS {out[best]:.4f}")
    print(f"  production default k=20 -> CRPS {out[20]:.4f}  "
          f"(gap {out[20]-out[best]:+.4f}, {100*(out[20]-out[best])/out[best]:+.2f}%)")
    print(f"  pure parametric        -> {out[10**9]:.4f}")
    print(f"  pure empirical         -> {out[0]:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
