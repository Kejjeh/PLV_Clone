"""variance_forecastability — is a player's VARIANCE a forecastable trait?

WHY THIS QUESTION, AND WHY IT IS NOT THE ONE WE KEPT ASKING
Every study in this repo's break/reliability line asked about the MEAN: can we
tell that a player's talent changed. That question is closed (~89% of apparent
in-season change is sampling noise).

But BrownU is H2H. It is decided by P(my_total > opp_total), which is a property
of the DISTRIBUTION, not the mean. `leverage_engine` already knows this — it
draws per-player samples — but when a model sigma is missing it falls back to a
GLOBAL per-role constant (`variance_bands.fallback_sigma`). If per-player sigma
is forecastable, that fallback is leaving real information on the table, and
every trailing-vs-leading regime call inherits the error.

THE TEST
Matched-denominator halves (200 PA hitters / 250 TBF SP). For each player-season
compute mean and SD of per-game (per-start) FP in each half, then compare:

    r_split(mu)     is talent level a stable trait?      [known: yes]
    r_split(sigma)  is VARIABILITY a stable trait?       [the question]
    partial r(sigma1 -> sigma2 | mu1)  is there variance signal BEYOND talent?

THE CEILING THAT MAKES IT INTERPRETABLE
A sample SD is itself noisy, so raw r_split(sigma) understates how stable sigma
truly is — you cannot tell a low r from "sigma is unstable" versus "sigma is
stable but hard to estimate from 40 games."

The parametric bootstrap resolves that. It redraws BOTH halves for every player
from that player's OWN pooled game distribution. Each player therefore has a
FIXED true sigma by construction, and the resulting r is the highest r_split
attainable at these sample sizes given estimation noise alone. That is a
CEILING, not a null.

    efficiency = observed r_split(sigma) / ceiling

Efficiency near 1.0 means sigma behaves like a fixed player trait. Efficiency
near 0 means sigma genuinely wanders (or is common across players), and a
per-player estimate buys nothing over a role-wide constant.

(An earlier pass in this session called this a "null" and read the observed-below-
bootstrap result as a failure. It is the opposite: it is the measurement working.)

Rule 13: descriptive. Nothing here re-ranks rh3/rp3/rprs2.
"""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts/xfp"))
from metric_reliability import load, halves, HIT, PIT, HALF_PA, HALF_TBF  # noqa: E402

N_BOOT = 200
SEED = 20260827


def corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 30:
        return float("nan")
    x, y = x[ok], y[ok]
    return float(np.corrcoef(x, y)[0, 1]) if x.std() and y.std() else float("nan")


def partial(x, y, z):
    """corr(x, y) with z linearly removed from both."""
    x, y, z = (np.asarray(a, float) for a in (x, y, z))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z = x[ok], y[ok], z[ok]
    A = np.c_[np.ones(len(z)), z]
    rx = x - A @ np.linalg.lstsq(A, x, rcond=None)[0]
    ry = y - A @ np.linalg.lstsq(A, y, rcond=None)[0]
    return float(np.corrcoef(rx, ry)[0, 1]), len(x)


def collect(path, key, denom, half, unit_filter=None):
    by = load(path, key)
    out = []
    for k, rows in by.items():
        h = halves(rows, denom, half)
        if not h:
            continue
        h1, h2 = h
        if unit_filter:
            h1 = [r for r in h1 if unit_filter(r)]
            h2 = [r for r in h2 if unit_filter(r)]
        if len(h1) < 8 or len(h2) < 8:
            continue
        a = np.array([float(r["fp"]) for r in h1])
        b = np.array([float(r["fp"]) for r in h2])
        out.append((k, a, b))
    return out


def analyse(data, label):
    mu1 = np.array([a.mean() for _, a, _ in data])
    mu2 = np.array([b.mean() for _, _, b in data])
    sd1 = np.array([a.std(ddof=1) for _, a, _ in data])
    sd2 = np.array([b.std(ddof=1) for _, _, b in data])
    n = len(data)
    r_mu, r_sd = corr(mu1, mu2), corr(sd1, sd2)
    pr, npr = partial(sd1, sd2, mu1)
    print(f"\n{'='*84}\n{label}   n={n} player-seasons\n{'='*84}")
    print(f"  r_split(mean  FP) = {r_mu:+.3f}      <- talent level")
    print(f"  r_split(SD    FP) = {r_sd:+.3f}      <- VARIABILITY")
    print(f"  partial r(SD1 -> SD2 | mean1) = {pr:+.3f}  (n={npr})")
    print(f"  corr(mean1, SD1)  = {corr(mu1, sd1):+.3f}   (are they the same thing?)")

    rng = np.random.default_rng(SEED)
    boots = []
    for _ in range(N_BOOT):
        s1, s2 = [], []
        for _, a, b in data:
            pool = np.concatenate([a, b])
            s1.append(rng.choice(pool, len(a), replace=True).std(ddof=1))
            s2.append(rng.choice(pool, len(b), replace=True).std(ddof=1))
        boots.append(corr(s1, s2))
    boots = np.array(boots)
    ceiling = float(boots.mean())
    eff = r_sd / ceiling if ceiling else float("nan")
    t_sd = r_sd * np.sqrt(n - 2) / np.sqrt(max(1 - r_sd ** 2, 1e-12))
    print(f"\n  CEILING (both halves redrawn from each player's own pool -> sigma fixed by construction):")
    print(f"    attainable r_split(SD) = {ceiling:+.3f}  (95% {np.percentile(boots,2.5):+.3f} "
          f"to {np.percentile(boots,97.5):+.3f})")
    print(f"    observed {r_sd:+.3f}  ->  EFFICIENCY {eff:5.1%} of attainable   "
          f"(vs zero: t={t_sd:+.2f})")
    return dict(label=label, n=n, r_mu=r_mu, r_sd=r_sd, partial=pr,
                ceiling=ceiling, efficiency=float(eff))


def main() -> int:
    print("IS A PLAYER'S VARIANCE A FORECASTABLE TRAIT?")
    h = collect(HIT, "batter", "pa", HALF_PA)
    p = collect(PIT, "pitcher", "tbf", HALF_TBF,
                unit_filter=lambda r: int(r["gs"] or 0) == 1)
    res = [analyse(h, "HITTERS — per-GAME FP"), analyse(p, "STARTING PITCHERS — per-START FP")]
    print(f"\n{'='*84}\nSUMMARY\n{'='*84}")
    print(f"{'side':<20}{'r(mean)':>9}{'r(SD)':>8}{'ceiling':>9}{'EFFIC':>8}{'partial|mu':>12}")
    for r in res:
        short = r['label'].split(' —')[0]
        print(f"{short:<20}{r['r_mu']:>+9.3f}{r['r_sd']:>+8.3f}{r['ceiling']:>+9.3f}"
              f"{r['efficiency']:>7.0%}{r['partial']:>+12.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
