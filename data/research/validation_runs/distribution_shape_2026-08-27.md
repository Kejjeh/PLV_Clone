---
signal: distribution_shape (per-player variance forecastability + where distributional shape matters for P(win))
formula: matched-denominator halves (200 PA / 250 TBF); r_split of per-game (per-start) FP mean vs SD; ceiling from a parametric bootstrap redrawing both halves from each player's own pooled distribution; P(win) error = empirical-bootstrap minus matched-normal across deficits and aggregation scales
outcome: P(win) in a BrownU-style H2H week
expected_sign: +
theory: BrownU is decided by P(my_total > opp_total), a property of the DISTRIBUTION. If per-player variance is forecastable and distributional shape is mispriced by the normal approximation, the leverage engine is leaving win probability on the table.
production_target: research-only
framing: in-season → ros
holdout_years: n/a (descriptive measurement)
training_years: [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
validation_script: scripts/xfp/variance_forecastability.py
date: 2026-08-27
verdict: RESEARCH-ONLY
---

# Variance and shape: forecastable, and almost entirely irrelevant — except in one place

Every prior study in this line asked about the MEAN. This asks about the
DISTRIBUTION, because that is what `P(my_total > opp_total)` actually depends on
and what `leverage_engine` actually draws from.

## 1. Hitter variance IS a forecastable trait. Pitcher variance is not.

Matched halves, r_split of per-game (per-start) FP SD. The **ceiling** is a
parametric bootstrap that redraws both halves from each player's own pooled
distribution — every player then has a FIXED true sigma by construction, so the
resulting r is the most attainable at these sample sizes given estimation noise.

| side | n | r(mean) | r(SD) | ceiling | **efficiency** | partial r(SD1→SD2 \| mean1) |
|---|---|---|---|---|---|---|
| HITTERS | 1,805 | +0.480 | **+0.437** | +0.591 | **74%** | **+0.361** |
| STARTING PITCHERS | 909 | +0.465 | +0.082 | +0.352 | **23%** | +0.080 (t=2.49) |

Hitter variability is nearly as stable as hitter talent, and carries substantial
information BEYOND talent level (partial r +0.361). SP per-start variability is
close to common across starters — a role-wide constant loses little.

Also note the sign flip on `corr(mean, SD)`: **+0.583 for hitters** (better
hitters are more volatile in absolute terms — more extra-base upside) vs
**−0.162 for SPs** (better starters are marginally steadier).

*A methodology note recorded against myself: the first pass labelled this
bootstrap a "null" and read observed-below-bootstrap as failure. It is a
CEILING. Redrawing from a player's own pool preserves between-player sigma
differences rather than destroying them.*

## 2. …and it barely moves P(win). The CLT eats it.

4,000 simulated BrownU weeks (13 hitters × 6 games) from the real joint
(mu, sigma) distribution, per-player sigma vs the global fallback:

    mean |error| 0.37pp | median 0.24pp | p90 0.89pp | max 2.59pp
    weeks over 1pp: 7.8%    weeks over 2pp: 0.4%

P(win) depends on total variance only through `sqrt(v1+v2)`, and summing 78
draws averages individual sigma differences away.

## 3. The normal approximation is not the problem either

Per-game hitter FP is genuinely non-normal — **skew +1.22, kurtosis 5.09**. It
does not matter:

| aggregation | normal-approx P(win) error |
|---|---|
| 13 hitters × 6 games (78 draws) | ≤ **0.46pp**, flat across every deficit |
| SP weekly total, 2-9 starts | ≤ **0.15pp** |

The SP row has a non-obvious cause: **a single SP start is ALREADY a CLT
aggregate** over within-start events, so its FP is near-normal to begin with
(**skew −0.39, kurtosis 3.19** vs the hitter game's +1.22 / 5.09). That is why
even a 2-start week needs no shape correction.

## 4. THE ONE PLACE SHAPE MATTERS: a single start

With no aggregation at all, the normal approximation is unbiased on average but
wrong per-pitcher by a lot:

| deficit | mean error | **p90 \|error\|** |
|---|---|---|
| −20 | −0.32pp | **8.47pp** |
| −10 | +1.47pp | **14.41pp** |
| 0 | −0.51pp | **10.24pp** |
| +10 | −0.57pp | 5.80pp |
| +20 | +0.10pp | 0.26pp |

Individual starters have idiosyncratic start-distribution shapes that a matched
normal cannot represent. At a −10 FP deficit the p90 error is **14.4pp of win
probability** — decision-changing on its own.

## Design principle this yields

**Aggregation scale, not player identity, decides whether distributional detail
is worth computing.**

- Team totals (hitter weeks, SP weeks): the cheap normal path is accurate to
  <0.5pp. Per-player sigma and empirical shape are both ~free to ignore.
- **Single-event decisions (one start — `/sp-bench-mc`, a cap-driven bench call):
  the empirical blend is load-bearing** and worth its cost.

That is a testable claim about where `leverage_engine._blend_draws` earns its
keep, and it points the opposite way from intuition: the expensive machinery
matters least for the biggest aggregates.

## Not shipped as a change

No engine modification is proposed. Finding 1 is real science with no practical
payoff at team scale (finding 2), and finding 4 describes behaviour the engine
already has. Documented so nobody builds a per-player-sigma feature expecting a
win, and so the single-start path is not "optimised" into a normal approximation.

Rule 13: descriptive. Nothing here re-ranks rh3/rp3/rprs2.
