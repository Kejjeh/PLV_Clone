---
signal: k_prior (sp_bench_mc blend weight between the empirical bootstrap and the parametric leg)
formula: sampler draws with P(empirical) = n/(n+k_prior) where n = the pitcher's prior starts this season; swept k in {0,2,5,10,15,20,30,50,100,inf}; scored by CRPS against the realized NEXT start, pool at start i containing only starts 1..i-1
outcome: realized BrownU FP of the next start
expected_sign: "-"
theory: a single start is the one decision scale where distributional shape is worth computing, so the weight given to a pitcher's own start history versus a smooth parametric summary should be measured, not assumed
production_target: research-only
framing: single-event, strictly out-of-sample
holdout_years: n/a (all-years sweep, clustered significance)
training_years: [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
validation_script: scripts/xfp/validate_k_prior.py
date: 2026-08-27
verdict: RESEARCH-ONLY
---

# k_prior=20: measured for the first time. Slightly too empirical-heavy, and it
# corrects a claim I made one study earlier.

`sp_bench_mc.build_sp_sampler(prior='blend')` — the DEFAULT mode — mixes a
bootstrap of the pitcher's own past starts with a parametric Gaussian at weight
`n/(n+k_prior)`, **k_prior=20**.

The distribution FAMILY was validated (F2, 2026-07-29 — lognormal assigned zero
density to FP<=0 while 16.4% of starts land there; replaced by Gaussian). The
`opp_factor` application was fixed (I1, 2026-07-30). **The blend WEIGHT never
was** — `k_prior` appears in no validation memo.

## Result: 29,412 next-start forecasts, 1,331 pitcher-seasons

| k_prior | mean empirical weight | CRPS |
|---|---|---|
| 0 (pure empirical) | 1.000 | **5.8729** ← worst |
| 10 | 0.546 | 5.6760 |
| **20 (production)** | **0.388** | **5.6525** |
| 50 | 0.212 | 5.6401 |
| **100** | 0.121 | **5.6344** ← best |
| inf (pure parametric) | 0.000 | 5.6406 |

**Pure empirical is the WORST option**, by a wide margin. The optimum sits at
k≈100 — only 12% empirical weight.

k=20 vs k=100, paired and **clustered by pitcher-season**: mean +0.0138,
SE 0.0031, **t = +4.41** (n=1,331 seasons). Statistically real, and small:
**0.32%** of the CRPS level.

## The parametric edge shrinks with pool size but never reverses

| pool size | n | CRPS empirical | CRPS parametric | emp − param |
|---|---|---|---|---|
| 3-7 | 6,655 | 6.2950 | 5.7600 | **+0.5349** |
| 8-14 | 9,312 | 5.7960 | 5.6003 | +0.1957 |
| 15-21 | 7,732 | 5.6946 | 5.5576 | +0.1370 |
| 22-29 | 5,091 | 5.7513 | 5.6945 | +0.0568 |
| 30+ | 622 | 5.5379 | 5.5050 | **+0.0330** |

Empirical converges toward parametric but is still behind at 30+ starts. The
crossover is beyond a full season's worth of starts.

## THIS CORRECTS `distribution_shape_2026-08-27.md`

That memo (one study earlier, same day) concluded: *"the empirical blend is
load-bearing for single-event decisions."* **That overstated it.**

Both results are true and the reconciliation is the actual science:

- A pitcher's TRUE per-start shape genuinely differs from a matched normal —
  p90 |error| of 8-14pp of win probability. That finding stands.
- But the BOOTSTRAP ESTIMATE of that shape, from <=30 starts, is so noisy that
  using it loses to a smooth normal anyway.

Classic bias-variance: the normal is biased but low-variance; the bootstrap is
unbiased but high-variance, and at realistic n the variance dominates. **Knowing
that a distribution is non-normal does not mean you can estimate its shape well
enough to profit.**

## What is NOT new here — the band width

The sigma sweep on this stand-in points to a **x1.2 wider** band, agreeing on
both CRPS (optimal x1.2) and PIT calibration (in[.1,.9] = 0.819 at x1.2 against
an ideal 0.800, versus 0.734 at x1.0).

**This is directional corroboration of an existing result, not a new finding.**
`band_crps_calibration_2026-07-29.md` already measured the single-start optimum
on real rp3 bands: `c* = 2.65` against the shipped display `x2.41`, a **0.22%**
CRPS gap the repo declined to act on. My x1.2-on-a-global-sigma points the same
way (wider) from a different parameterisation. Production is already near
optimal; nothing to do.

## Honest limitation

The production parametric leg is rp3's own predictive mean and per-pitcher band.
Historical rp3 snapshots are not reproducible from game logs, so the stand-in
here is Gaussian(season-to-date mean, global sigma) — same family, same "smooth
summary" role, but not literally rp3. Since rp3's mean should be BETTER than a
season-to-date mean, the true optimum likely sits at an even HIGHER k_prior than
100, not lower. The direction is safe; the exact value is not.

## Recommendation: measure, do not change (yet)

The k=20 -> k=100 gain is 0.32% CRPS — the same order as the 0.22% band gap the
band study declined to act on. Precedent says leave it.

What IS worth doing is confirming against real rp3 snapshots before any default
moves, because the stand-in limitation cuts in the direction of an even larger
correction. Until then `k_prior=20` is no longer an unmeasured constant — it is
a measured, slightly suboptimal one, with the direction of the error known.

Rule 13: diagnostic. Proposes no change.
