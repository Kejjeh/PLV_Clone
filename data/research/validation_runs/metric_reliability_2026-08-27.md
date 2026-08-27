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

---

# ADDENDUM (loop iteration 1) — the "K% beats rp3" reading was WRONG. It was frame.

Last turn I flagged SP K% forward r = +0.540 against rp3's live r ≈ 0.40 as
possibly "the most valuable thing in this session." It is not. Rebuilt on an
rp3-LIKE frame (split at every start, varying rest-of-season window, no
durability filter): 24,052 rows over 1,330 pitcher-seasons.

## The gap decomposes into two frame effects, neither of them skill

**H1 — target-window length dominates.** r rises monotonically with how many
starts the target averages over:

| RoS starts remaining | n | r(K%, RoS FP) |
|---|---|---|
| 2-3 | 1,330 | **0.363** |
| 4-6 | 3,990 | 0.428 |
| 7-10 | 5,300 | 0.473 |
| 11-15 | 5,768 | 0.505 |
| 16+ | 7,664 | **0.523** |

**H2 — the durability filter is survivorship.** My matched-half design required
≥500 TBF, which selects established starters:

| season total TBF | n | r |
|---|---|---|
| <400 | 2,050 | **0.247** |
| 400-600 | 7,603 | 0.450 |
| 600-750 | 9,049 | 0.454 |
| 750+ | 5,350 | **0.529** |

**H3 — split position is NOT a driver** (0.486 → 0.450 across the season).

Pooled over the rp3-like frame: **r = 0.466**, not 0.540. The matched-half-like
subset reproduces 0.528, confirming the original number was correct *for its
frame* and that the frame was the difference.

rp3's ~0.40 is measured on a broader population still (thin seasons,
`marcel_il` rows, short RoS windows) — exactly the cells where r collapses to
0.247. **There is no headroom claim here.** Retracted.

## And K% is not uniquely informative — it is a convenient summary

Player-grouped 5-fold OOS on the same frame:

| model | r | R² |
|---|---|---|
| K% alone | 0.4625 | 0.214 |
| K% + FP level | 0.4904 | 0.241 |
| all 8 game-log features | **0.5328** | 0.284 |
| **everything EXCEPT K%** | **0.5287** | 0.280 |

**Dropping K% costs +0.0041 r.** K% is the best single feature and captures 75%
of the full model's explained variance, but it is nearly redundant with the rest.

Partly mechanical and worth stating: K is a term in the SP FP formula
(`K + IP*3.3 − H − 2ER − BB − HBP`), so K% and FP/start are algebraically linked.
Their collinearity is expected, not a discovery.

## What survives

The v5/reliability headline is unchanged and was never frame-dependent: **within
a fixed frame, K% is the best single SP predictor and beats the pitcher's own FP
level (0.540 vs 0.463; 0.4625 vs the FP-level component here).** The claim that
died is the cross-frame one — that a single rate outperforms the production
model. It does not; it was measured on an easier problem.

**Methodological rule to carry forward:** never compare an r across frames.
Target-window length alone moved r by +0.16 here, which is larger than any
feature effect measured anywhere in this session.

---

# ADDENDUM 2 — bat speed DOES add over the hitter FP level. Gotcha #12 confirmed.

CLAUDE.md #12 names bat speed as the ONE process metric that adds forward-FP
signal beyond the scoring level. Tested here on an independent panel.

Cohort: **572 hitter-seasons / 312 hitters, 2024-2026** (bat tracking is 2024+;
requires >= 80 swings in the first half). Player-grouped 5-fold OOS, matched
200-PA halves, predicting 2nd-half FP/game.

| model | r |
|---|---|
| FP level ALONE | 0.3970 |
| FP level + bat speed | 0.4070 |
| FP level + bat speed + fast-swing% | 0.4158 |
| ALL features | **0.4536** |
| ALL except the bat-speed pair | 0.3957 |

- bat speed over the FP level: **+0.0100 r**
- **bat-speed PAIR over everything else: +0.0579 r**
- **partial r(bat speed, 2H FP | 1H FP level) = +0.1233**,
  95% CI **[+0.042, +0.203]** — **excludes zero**, n=572.

Power check: the smallest partial r detectable at 80% power with n=572 is ~0.117,
and the observed effect is 0.123. So this sits right at the edge of power — the
CI excluding zero is real but the estimate is not precise. Treat +0.12 as
"positive, magnitude uncertain," not as a calibrated coefficient.

**Contrast that earns the headline:** the five ordinary hitter rates
(K%/BB%/TB/HR/SB) added **+0.010** over the FP level on the 9-year panel. The
bat-speed pair adds **+0.058** here. Bat speed is not one of the rates — it is
the exception, exactly as gotcha #12 says, now confirmed from a second direction.

Consistent with gotcha #12's other half: this measures the LEVEL of first-half
bat speed, not its trajectory. The in-season DELTA remains REJECTED
(`bat_speed_stabilization_and_delta_2026-07-29.md`).

**Frame note, applying this session's own rule:** the FP-level baseline reads
0.397 here vs 0.480 on the 9-year panel. Different cohort (2024-26, bat-speed
coverage required). Compare only WITHIN this table — never across frames.
