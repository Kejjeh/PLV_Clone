# Confidence Label Calibration — empirical test

**Date**: 2026-06-06  •  **Inputs**: shrinkage_h_snap_2026-06-06.parquet (1498 H), shrinkage_sp_snap_2026-06-06.parquet (550 SP)

**Question**: Do merge-protocol confidence labels (HIGH >=6 / MED 4-5 / LOW 2-3 / NULL <2) predict materially better forward FP/game?

**Method**: 8 lens votes synthesized from available snapshot proxies (xFP rank, boom/bust quartile, prior baseline, stability, L21 vs L42, YoY direction, career-length decline). Target = forward 30d FP/game. Replacement = bottom-tier median. Signed delta uses net BUY/FADE direction so a correct FADE on a poor performer counts positive.

**Caveat**: production lenses include archetype + xwOBA + age, which the snapshot parquets do not carry. This test validates the LABEL CONCEPT (does agreement count predict outcome quality?) not the exact 8 production lenses.

## 1. Label distribution

| Label | H (n) | SP (n) | Pooled |
|---|---:|---:|---:|
| HIGH | 77 | 16 | 93 |
| MED | 366 | 150 | 516 |
| LOW | 572 | 211 | 783 |
| NULL | 483 | 173 | 656 |
| **Total** | **1498** | **550** | **2048** |

## 2. Hitter — signed FP delta vs replacement

Replacement-level (51-150 tier median target): **2.000 FP/g**

| Label | n | mean signed Δ | 95% CI | raw mean target | %BUY net | %FADE net |
|---|---:|---:|---|---:|---:|---:|
| HIGH | 77 | +0.458 | [+0.268, +0.645] | 2.070 | 38% | 62% |
| MED | 366 | +0.409 | [+0.316, +0.503] | 2.296 | 64% | 36% |
| LOW | 572 | +0.175 | [+0.105, +0.241] | 2.174 | 63% | 37% |
| NULL | 483 | +0.129 | [+0.050, +0.206] | 2.144 | 36% | 28% |

Monotone HIGH > MED > LOW > NULL? **YES** — order: ['+0.458', '+0.409', '+0.175', '+0.129']
HIGH vs MED 95% CI overlap: **OVERLAP**

## 3. SP — signed FP delta vs replacement

Replacement-level (51-100 tier median target): **12.510 FP/g**

| Label | n | mean signed Δ | 95% CI | raw mean target | %BUY net | %FADE net |
|---|---:|---:|---|---:|---:|---:|
| HIGH | 16 | +0.560 | [-1.135, +2.396] | 12.320 | 38% | 62% |
| MED | 150 | +1.255 | [+0.485, +1.982] | 13.700 | 63% | 37% |
| LOW | 211 | +0.649 | [+0.027, +1.269] | 13.287 | 66% | 34% |
| NULL | 173 | +0.211 | [-0.489, +0.911] | 12.852 | 42% | 28% |

Monotone HIGH > MED > LOW > NULL? **NO** — order: ['+0.560', '+1.255', '+0.649', '+0.211']
HIGH vs MED 95% CI overlap: **OVERLAP**

## 4. Pooled (H + SP, z-scored within kind)

| Label | n | mean signed z | 95% CI |
|---|---:|---:|---|
| HIGH | 93 | +0.494 | [+0.305, +0.677] |
| MED | 516 | +0.348 | [+0.265, +0.437] |
| LOW | 783 | +0.126 | [+0.064, +0.195] |
| NULL | 656 | +0.033 | [-0.047, +0.109] |

Monotone HIGH > MED > LOW > NULL? **YES** — order: ['+0.494', '+0.348', '+0.126', '+0.033']
HIGH vs MED 95% CI overlap: **OVERLAP**

## 5. Recommendation

- HIGH vs MED gap, H: **+0.049 FP/g** (HIGH=+0.458, MED=+0.409)
- HIGH vs MED gap, SP: **-0.695 FP/g** (HIGH=+0.560, MED=+1.255)

### Verdict: FAIL — labels are not calibrated. HIGH does NOT materially beat MED at 95% CI.

### Cutoff suggestion

Per-agreement-count signed z (n>=20 only):

| agreement | n | mean signed z | 95% CI |
|---:|---:|---:|---|
| 0 | 224 | +0.001 | [-0.127, +0.113] |
| 1 | 432 | +0.049 | [-0.058, +0.142] |
| 2 | 383 | +0.099 | [+0.010, +0.198] |
| 3 | 400 | +0.153 | [+0.060, +0.244] |
| 4 | 323 | +0.210 | [+0.110, +0.309] |
| 5 | 193 | +0.580 | [+0.435, +0.739] |
| 6 | 72 | +0.428 | [+0.207, +0.640] |

Use this table to choose cutoffs that separate strata by at least 0.1 signed-z (~1 FP/g for SP, ~0.1 FP/g for H).
