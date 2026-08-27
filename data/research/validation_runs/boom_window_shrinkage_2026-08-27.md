---
signal: boom_window_shrinkage (forward value of a short-window boom/bust rate)
formula: regress the NEXT 8 starts' boom rate on the trailing L{3,5,8,12,20} boom rate; slope b = the fraction of an observed gap that survives, 1-b = shrinkage toward the base rate. Also AUC/Brier for predicting whether the NEXT start booms, comparing the L8 window against season-to-date and against a parametric P(FP>=17) under N(season-to-date mean, global sigma)
outcome: boom = next start FP >= 17; bust = next start FP < 5; and boom rate over the next 8 starts
expected_sign: +
theory: a proportion from 8 trials has ~16pp of sampling SE, so most of an observed boom-rate gap should be noise; and per k_prior_blend_weight_2026-08-27 a smooth parametric summary should beat a short empirical window
production_target: research-only
framing: single-event and next-window, strictly out-of-sample
holdout_years: n/a (all-years measurement)
training_years: [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
validation_script: scripts/xfp/validate_boom_window.py
date: 2026-08-27
verdict: RESEARCH-ONLY
---

# An L8 boom rate is 65% noise, and as a probability it is worse than the base rate

`/boom-bust-history` reports SP boom%/bust% over the **last 8 starts** and, in
its own description, contrasts *"a 37% boom hot streak (Bradish)"* with *"0%
boom 25% bust cap-fodder (Valdez)"*. Those are 3/8 and 0/8.

A proportion from 8 trials carries a sampling SE of **16 percentage points** at
the observed base rate of 0.293. This measures what survives.

Panel: **22,757 forecasts / 1,331 pitcher-seasons**, 2017-2026, strictly
out-of-sample.

## 1. As a probability, the L8 window is worse than saying nothing

Predicting whether the NEXT start booms (base rate 0.293):

| predictor | AUC | Brier | vs base rate |
|---|---|---|---|
| base rate (constant) | 0.500 | 0.2072 | — |
| **L8 window (n=8)** | 0.5982 | **0.2163** | **+0.0091 WORSE** |
| season-to-date | 0.6142 | 0.2058 | −0.0014 |
| **PARAMETRIC (smooth)** | **0.6209** | **0.2007** | **−0.0065 best** |

Same for bust (base 0.257): L8 Brier **+0.0147 worse** than the base rate.

The L8 rate has some ranking ability (AUC 0.598) but is so badly calibrated that
using it AS a probability loses to a constant. And the smooth parametric summary
beats both windows on both metrics — the same ordering
`k_prior_blend_weight_2026-08-27.md` found, at an even smaller n.

## 2. Shrinkage by window: the shorter the window, the more of it is noise

Slope of (next-8 boom rate) on (window boom rate):

| window | n | slope b | **shrinkage (1−b)** | forward r |
|---|---|---|---|---|
| L3 | 20,095 | 0.179 | **82%** | 0.253 |
| L5 | 17,433 | 0.261 | 74% | 0.304 |
| **L8 (the default)** | 13,445 | **0.353** | **65%** | 0.347 |
| L12 | 8,696 | 0.431 | 57% | 0.371 |
| L20 | 2,013 | 0.575 | 42% | 0.411 |

Even a 20-start window is 42% noise.

## 3. The skill's own canonical example, corrected

| | displayed | forward estimate |
|---|---|---|
| "0% boom cap-fodder" (0/8) | 0.0% | **19.7%** |
| "37% boom hot streak" (3/8) | 37.5% | **33.0%** |
| 5/8 | 62.5% | 41.8% |
| **gap** | **37.5pp** | **13.2pp** |

**A 0/8 pitcher is not a pitcher who never booms — he booms about one start in
five.** The raw display invites precisely the wrong inference, and it is the
inference the skill's own description models.

The 13.2pp that survives is real and decision-relevant. The 24pp that does not
is what gets someone dropped.

## 4. The Trend arrow is mostly noise against noise

The skill derives UP/FLAT/DOWN from L3 vs L5 vs L8 — three estimates that are
**82% / 74% / 65%** noise. Two of the three windows feeding the trend are
shorter, and therefore worse, than the headline number.

## Shipped

`scripts/xfp/lib/boom_bust.forward_rate(observed_rate, window)` returns
`base + slope*(observed - base)`, interpolating for unlisted windows and clamping
rather than extrapolating. **Additive only** — no existing output changes, callers
opt in. The `/boom-bust-history` skill now carries the shrinkage table, the
corrected canonical example, and the Trend caution.

Rule 13: a DISPLAY calibration. It never moves rh3/rp3/rprs2.

## What this does NOT say

It does not say boom/bust history is useless. Ranking skill is real (AUC 0.60
for boom), the L20 window retains 58% of an observed gap, and actuals remain the
only lens that shows variance at all. It says the RAW RATE is the wrong number to
put on screen, and that the shorter the window, the more the display overstates.
