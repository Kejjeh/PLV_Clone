---
signal: metric_reliability (in-season rate reliability + forward value, both sides)
formula: at matched denominator halves (200 PA hitters / 250 TBF SP), per metric — dispersion = mean|z| / 0.798 against binomial sampling SE; r_split = corr(first-half rate, second-half rate) across players; r_fwd = corr(first-half rate, second-half FP)
outcome: second-half FP/game (hitters) or FP/start (SP)
expected_sign: +
theory: a metric whose in-season variation is mostly sampling noise should tell you little about the other half of the season, and less about forward scoring
production_target: research-only
framing: in-season → ros
holdout_years: n/a (descriptive measurement, not a fitted signal)
training_years: [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
validation_script: scripts/xfp/metric_reliability.py
date: 2026-08-27
verdict: RESEARCH-ONLY
---

# Metric reliability, both sides — read the OUTCOME for hitters, the PROCESS for pitchers

Grew out of the v5 break study's incidental finding that pitchers and hitters
invert on walks. 1,805 hitter half-pairs (200 PA/side) and 921 SP half-pairs
(250 TBF/side), 2017-2026.

## THE HEADLINE — a clean inversion

**1st-half feature vs 2nd-half scoring:**

| HITTERS | r_fwd | | STARTING PITCHERS | r_fwd |
|---|---|---|---|---|
| **FP level** | **+0.480** | | **K%** | **+0.540** |
| TB/PA | +0.288 | | FP level | +0.463 |
| K% | −0.234 | | H/TBF | −0.332 |
| HR/PA | +0.230 | | ER/TBF | −0.288 |
| BB% | +0.167 | | BB% | **−0.144** |
| SB/PA | +0.067 | | | |

**For hitters the OUTCOME beats every process metric. For pitchers the PROCESS
beats the outcome.** Player-grouped 5-fold OOS ridge over all features:

    HITTER  multiple r 0.490  vs FP level alone 0.480   -> rates add +0.010
    SP      multiple r 0.541  vs K% alone       0.540   -> everything else adds +0.001

Both sides collapse to a single number, and it is a different KIND of number.

## Independent confirmation of two standing repo findings

- CLAUDE.md #12 ("only bat speed adds forward-FP signal beyond the FP level;
  K%/xwOBACON/HardHit%/BB% are redundant") — reproduced here from a fresh panel
  and a different method: five hitter rates add **+0.010** over the FP level.
- CLAUDE.md #11 ("watch STUFF, not walks") — SP BB% is the WEAKEST forward
  predictor tested, r_fwd **−0.144**, and the sign is the wrong way round.

## Reliability (does the metric describe a stable trait?)

r_split = corr(1st-half rate, 2nd-half rate) across players:

| metric | HITTER | SP |
|---|---|---|
| K% | **0.775** | **0.728** |
| K−BB% | 0.682 | 0.672 |
| **BB%** | **0.625** | **0.483** |
| SB/PA | 0.752 | — |
| HR/PA | 0.541 | — |
| H/TBF | — | 0.367 |
| TB/PA | 0.343 | — |
| ER/TBF | — | 0.230 |

**The walk claim, quantified:** hitter BB% 0.625 vs SP BB% 0.483 (+0.142), while
K% differs by only +0.047. The gap is specific to walks — the walk belongs to the
batter, exactly as the v5 dispersion inversion predicted.

## Does dispersion screen for "worth reading"? For pitchers, yes.

corr(dispersion, r_split), Bernoulli-valid metrics only:

    SP       +0.980   (n=4)  <- dispersion is a near-perfect screen
    HITTER   +0.153   (n=5)  <- no relationship
    pooled   +0.459   (n=9)

Plausible reading: a pitcher faces many batters, so opponent effects average out
and excess variance is mostly the pitcher. A hitter's excess variance is
contaminated by pitcher quality faced, park and lineup context, so it is not a
clean talent signal.

**ARTIFACT TO AVOID.** Dispersion is only valid for genuine 0/1-per-event rates.
TB/PA (0-4 per PA) and ER/TBF (a count) violate the binomial SE, which understates
their sampling variance and INFLATES dispersion: TB/PA 1.809 and ER/TBF 1.362 sit
top of the table while having the LOWEST r_split (0.343, 0.230). Including them
flips the pooled correlation from +0.459 to **−0.526**. Never compute dispersion
on a non-Bernoulli rate.

## Practical consequences

1. **Hitter verdicts should lead with the scoring level**, not the rate slash.
   Rate metrics are context, not evidence (+0.010 over the level).
2. **SP verdicts should lead with K%.** It beats the pitcher's own FP/start.
3. **`/sp-form`'s COMMAND-WATCH deserves its low-conviction status** — SP BB% is
   the weakest signal measured, in reliability and forward value.
4. **`/hitter-form` may treat BB% as a trait read** (r_split 0.625) but not as a
   forecast input (r_fwd +0.167).
5. Dispersion is a cheap screen for a NEW pitcher metric; it is not one for a
   hitter metric.

Rule 13 throughout: descriptive. Nothing here re-ranks rh3/rp3/rprs2.
