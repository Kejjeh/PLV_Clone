# xwOBA L21d-vs-prior-year-baseline threshold backfit
**Run date:** 2026-06-06
**Sample:** N=347 (hitter, as_of) pairs across 6 dates in 2024+2025
**Frame:** top 250 rh3-ranked hitters
**Filters:** prior-year PA >= 300, L21d PA >= 30, forward 30d PA >= 30

**Forward target FP/g uses TB+BB+HBP-K proxy** (preserves rank vs true BrownU FP/g; R/RBI/SB unavailable from Statcast). Forward xwOBA is the primary skill target.

## Decile table
| Decile | Gap range | Mean gap | N | Fwd xwOBA | Fwd FP/g proxy | Fwd − prior xwOBA |
|---:|:---|---:|---:|---:|---:|---:|
| D1 | [-0.134, -0.060] | -0.079 | 35 | 0.324 | 1.06 | -0.016 |
| D2 | [-0.059, -0.042] | -0.051 | 35 | 0.335 | 1.17 | -0.010 |
| D3 | [-0.041, -0.026] | -0.034 | 34 | 0.323 | 1.15 | -0.006 |
| D4 | [-0.025, -0.013] | -0.020 | 35 | 0.328 | 1.17 | -0.006 |
| D5 | [-0.012, -0.001] | -0.007 | 35 | 0.321 | 1.15 | -0.005 |
| D6 | [-0.001, +0.009] | +0.004 | 34 | 0.336 | 1.25 | +0.009 |
| D7 | [+0.010, +0.024] | +0.016 | 35 | 0.317 | 1.15 | -0.007 |
| D8 | [+0.024, +0.040] | +0.032 | 34 | 0.334 | 1.11 | +0.006 |
| D9 | [+0.040, +0.063] | +0.052 | 35 | 0.341 | 1.28 | +0.021 |
| D10 | [+0.064, +0.190] | +0.085 | 35 | 0.334 | 1.09 | +0.004 |

**Reading guide:** if gap predicts forward skill, fwd_xwoba should rise monotonically across deciles, and fwd_minus_prior should swing from negative (bottom deciles) toward 0 (middle deciles, 'skill holding').

## Current cuts (±0.020 SKILL_HOLDING, <-0.060 REAL_DECLINE)
| Bucket | N | Fwd xwOBA | Fwd FP/g | Fwd − prior xwOBA |
|---|---:|---:|---:|---:|
| SKILL_HOLDING (gap in ±0.020) | 112 | 0.327 | 1.19 | -0.001 |
| MIDDLE (between bands) | 202 | 0.332 | 1.16 | n/a |
| REAL_DECLINE (gap < -0.060) | 33 | 0.322 | 1.05 | -0.016 |

## Empirical optimal cuts
- **REAL_DECLINE cutoff:** `gap < -0.060` (max forward-separation score)
  - Below: N=33, fwd xwOBA=0.322, fwd FP/g=1.05
  - Above: N=314, fwd xwOBA=0.330, fwd FP/g=1.17
- **SKILL_HOLDING band:** `|gap| <= +0.015` (tightest fwd_minus_prior_xwoba)
  - Inside: N=89, fwd_xwoba=0.328, fwd_minus_prior mean=+0.000 (|·| mean=0.032)

## Side-by-side
| Cut set | SKILL_HOLDING band | REAL_DECLINE cutoff | Decline-vs-Hold fwd xwOBA gap |
|---|---|---|---:|
| Current (reference doc) | ±0.020 | <-0.060 | 0.005 |
| Empirical | ±0.015 | <-0.060 | 0.006 |

## Recommendation
**KEEP current cuts ±0.020 / <-0.060.** Empirical optimums are within rounding distance (Δ skill < 0.006, Δ decline < 0.011) — no tighten/loosen lift large enough to justify changing the published reference. The forward-xwOBA separation gap is comparable.

## Calibration plot data (gap bin midpoint vs forward FP/g delta from baseline)
| Gap bin | N | Fwd xwOBA | Fwd FP/g | Fwd FP/g − sample median |
|---|---:|---:|---:|---:|
| (-0.12, -0.1] | 4 | 0.311 | 0.76 | -0.40 |
| (-0.1, -0.08] | 8 | 0.316 | 1.05 | -0.11 |
| (-0.08, -0.06] | 20 | 0.325 | 1.09 | -0.07 |
| (-0.06, -0.04] | 41 | 0.334 | 1.18 | +0.02 |
| (-0.04, -0.02] | 49 | 0.326 | 1.16 | -0.00 |
| (-0.02, 2.78e-17] | 56 | 0.324 | 1.17 | +0.01 |
| (2.78e-17, 0.02] | 56 | 0.330 | 1.21 | +0.05 |
| (0.02, 0.04] | 41 | 0.325 | 1.09 | -0.07 |
| (0.04, 0.06] | 33 | 0.341 | 1.27 | +0.11 |
| (0.06, 0.08] | 21 | 0.332 | 1.15 | -0.01 |
| (0.08, 0.1] | 13 | 0.340 | 1.06 | -0.10 |
| (0.1, 0.12] | 1 | 0.356 | 0.65 | -0.51 |

Sample-median forward FP/g proxy: 1.16

## Caveats
- FP/g uses a TB+BB+HBP-K **proxy** because R/RBI/SB are unavailable from Statcast pitch data. Preserves rank but undercounts absolute magnitude. Forward xwOBA is the cleaner skill signal.
- 2024 prior-year for 2024 as_of dates uses **2023** baseline; 2025 as_of uses **2024**. Both included via ALL_SC[year].
- Min sample sizes enforced (L21d PA >= 30, forward PA >= 30); thin-window hitters silently dropped.
- Sample frame is top-250 rh3 hitters (current snapshot) — this is the population we actually make decisions on, but it biases toward survivors. A truly random MLB sample would include more steep declines.
