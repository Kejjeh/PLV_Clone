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


---

# HITTER SIDE — more observations, LESS signal

Same estimator, hitter panel: **256,456 forecasts / 2,469 hitter-seasons**,
boom = FP >= 5, bust = FP < 0, default window **L21 games**.

## As a probability, L21 also loses to the base rate

| BOOM (next game >= 5 FP), base 0.203 | AUC | Brier | vs base |
|---|---|---|---|
| base rate (constant) | 0.500 | 0.1618 | — |
| **L21 window** | 0.5478 | **0.1666** | **+0.0048 WORSE** |
| season-to-date | 0.5631 | 0.1619 | +0.0000 |
| parametric (smooth) | 0.5632 | **0.1609** | −0.0009 |

| BUST (next game < 0 FP), base 0.205 | AUC | Brier | vs base |
|---|---|---|---|
| **L21 window** | 0.5523 | 0.1674 | **+0.0045 WORSE** |
| **season-to-date** | **0.5685** | **0.1627** | **−0.0002 best** |
| parametric (smooth) | 0.5457 | 0.1670 | **+0.0041 WORSE** |

**A side-specific reversal.** For SPs the smooth parametric leg beat both
windows. For hitter BUST it LOSES to season-to-date. Hitter per-game FP is
strongly right-skewed (skew +1.22, kurtosis 5.09 — measured in
`distribution_shape_2026-08-27.md`), so a Gaussian misprices the left tail that
`bust` is defined on. On the hitter bust line, prefer season-to-date.

## Shrinkage — and the counterintuitive result

| window | n | slope b | **shrinkage** | r |
|---|---|---|---|---|
| L7 | 241,642 | 0.105 | **89%** | 0.165 |
| L14 | 224,359 | 0.192 | 81% | 0.223 |
| **L21 (default)** | 207,076 | **0.267** | **73%** | 0.264 |
| L28 | 189,793 | 0.330 | 67% | 0.294 |
| L40 | 160,165 | 0.414 | 59% | 0.327 |
| L60 | 110,936 | 0.520 | 48% | 0.364 |

**Hitter L21 (73% noise) is NOISIER than SP L8 (65%)** despite resting on 21
observations rather than 8. More data, less signal.

## The mechanism, and it validates itself

Shrinkage is a variance-components ratio: `b = var_true / (var_true + var_samp)`.
Inverting it recovers the TRUE between-player SD of boom rate — and two
independent windows per side agree, which is the internal check:

| | sampling SD | **implied true between-player SD** |
|---|---|---|
| SP L8 | 16.1pp | **11.9pp** |
| SP L20 | 10.2pp | **11.8pp** |
| HITTER L21 | 8.8pp | **5.3pp** |
| HITTER L60 | 5.2pp | **5.4pp** |

**Pitchers spread ~12pp in true boom rate; hitters only ~5pp — less than half.**
Hitters really are more alike in how often they boom, so a longer window still
resolves less of a smaller real difference. That is why 21 games beats 8 starts
on sample size and loses on signal.

## Corrected hitter display

| L21 boom | displayed | forward |
|---|---|---|
| 0/21 | 0.0% | **15.2%** |
| 4/21 | 19.0% | 20.2% |
| 10/21 | 47.6% | **27.9%** |

## Shipped

`forward_rate(observed_rate, window, side="SP"|"H")` now covers both sides,
back-compatible (side defaults to "SP"). Skill carries both tables, the
asymmetry, the parametric caveat and the Trend caution.
