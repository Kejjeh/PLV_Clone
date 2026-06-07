# Tier Re-weighting Test — 2026-06-06

## Question

Does the current Tier A (Blended xFP + rh3/rp3) / Tier B (sustainability + xwOBA L21d + xwOBACON YoY) / Tier C (boom-bust + boom_stack) / Tier D (context) hierarchy match empirical lens lift?

Data: re-computed bootstrap lifts (2000 resamples, seed=42) from `lens_weight_backtest_2026-06-06.snapshots.csv` (511 snapshots: 362 H + 149 SP across 4 as-of dates in 2025).

## Method

- Rank each lens by **95% bootstrap CI lower bound** (most defensible positive lift)
- A lens is **promoted to Tier A** if its CI excludes zero AND its lift exceeds the median lift of current Tier A lenses
- A lens is **demoted to Tier D** if its CI is strictly below zero (wrong direction) or it has < 5 BUY/FADE observations (inconclusive — context only)
- A lens stays in **Tier B/C** if CI excludes zero but lift below Tier A median (B) or CI crosses zero (C)

## Results — by position group

### SPs (n=149 snapshots)

_Tier A median lift threshold for promotion: +0.00 FP/g_

| Rank | Lens | Current | Proposed | n BUY | n FADE | Lift | 95% CI | Δ Tier |
|---|---|---|---|---|---|---|---|---|
| 1 | boom-bust (L3_boom) | C | A | 62 | 29 | +5.44 | [+2.68, +8.02] | C → A |
| 2 | sustainability (L4_sust) | B | C | 51 | 36 | +0.58 | [-2.16, +3.18] | B → C |
| 3 | Blended xFP (L1_blend) | A | D | 56 | 0 | — | INCONCLUSIVE | A → D |
| 4 | rh3 / rp3 rank (L2_rank) | A | D | 149 | 0 | — | INCONCLUSIVE | A → D |
| 5 | xwOBA L21d (L5_xwoba_l21) | B | D | 0 | 0 | — | INCONCLUSIVE | B → D |
| 6 | xwOBACON YoY (L6_xwobacon_yoy) | B | D | 0 | 0 | — | INCONCLUSIVE | B → D |


### Hitters (n=362 snapshots)

_Tier A median lift threshold for promotion: +0.00 FP/g_

| Rank | Lens | Current | Proposed | n BUY | n FADE | Lift | 95% CI | Δ Tier |
|---|---|---|---|---|---|---|---|---|
| 1 | boom-bust (L3_boom) | C | A | 133 | 44 | +0.47 | [+0.20, +0.75] | C → A |
| 2 | xwOBA L21d (L5_xwoba_l21) | B | C | 85 | 31 | -0.01 | [-0.39, +0.38] | B → C |
| 3 | xwOBACON YoY (L6_xwobacon_yoy) | B | C | 99 | 102 | -0.21 | [-0.45, +0.05] | B → C |
| 4 | Blended xFP (L1_blend) | A | D | 175 | 0 | — | INCONCLUSIVE | A → D |
| 5 | rh3 / rp3 rank (L2_rank) | A | D | 362 | 0 | — | INCONCLUSIVE | A → D |
| 6 | sustainability (L4_sust) | B | D | 56 | 0 | — | INCONCLUSIVE | B → D |


## Key findings

1. **SP boom-bust (L3) dominates**: lift = +5.44 FP/g with CI [+2.68, +8.02], p(lift≤0)=0.000. The only SP lens with a conclusive positive lift in this sample. **Recommendation: promote boom-bust to Tier A for SPs**, given Tier A's rh3/rp3 and Blended xFP are INCONCLUSIVE (no FADE observations because of top-rank sampling).

2. **Hitter boom-bust (L3) is the only conclusive positive lens**: lift = +0.47 FP/g, CI [+0.20, +0.75]. xwOBA L21d and xwOBACON YoY (currently Tier B) had negative or zero lift in this sample. **Recommendation: promote boom-bust to Tier A for hitters**, and demote L5/L6 to Tier C (variance) or Tier D (context) pending a larger/cleaner backtest.

3. **Tier A primary signals are unmeasurable in this sample**: L1_blend + L2_rank produced 100% BUY votes (sample drawn from top-100 by rh3/rp3 — no FADE arm). The current Tier A label may still be correct on theoretical/production grounds, but the empirical justification needs a balanced rank sample.

## Specific re-tiering recommendation

**SPs**:
- Tier A: Blended xFP, rh3-rank, **boom-bust (promoted from C)**
- Tier B: sustainability (no change)
- Tier C: removed (boom-bust was the only occupant)
- Tier D: archetype + age/boundary + PL + live_marginal (no change)

**Hitters**:
- Tier A: Blended xFP, rh3-rank, **boom-bust (promoted from C)**
- Tier B: sustainability (kept — production 9-marker decomp, simplified version was inconclusive here)
- Tier C: xwOBA L21d, xwOBACON YoY (demoted from B — CI crosses or is below zero in this sample)
- Tier D: archetype + PL + live_marginal (no change)

## Caveats (carry forward from backtest report)

- **Top-rank sampling**: Tier A lenses (L1, L2) had zero FADE observations, so their empirical lift is untestable here. The promotion of boom-bust to Tier A is conditional on Tier A primary signals being theoretically sound on production grounds, not on direct head-to-head measurement in this sample.
- **N=511 snapshots, 4 as-of dates**: bootstrap CIs are wide; replication across more dates + balanced rank sampling is needed before locking in tier reassignment.
- **Recency leak in L1/L2**: current 2026 rh3/rp3 ranks proxy for 2025 historical ranks — L2 in particular would look weaker in a true real-time test.
- **L4 sustainability simplified**: 2-marker SP / xwOBA-gap H decomposition vs production 9-marker panel. Real Tier B might be stronger than measured.
- **L5 baseline**: 2024 full-season xwOBA vs production "2025 baseline" framing.
- **No IL censoring**: forward windows containing IL stints depress lift for high-talent players unfairly.

## Bottom line

The lens-weight backtest **does not support** the current Tier C placement of boom-bust for either position group. Boom-bust had the largest measurable lift in the sample. Whether to formally re-tier depends on:
1. Replicating the result on a balanced (top-rank + bottom-rank) sample
2. Adding historical rank snapshots so L1/L2 can be measured against a real FADE arm
3. Stress-testing whether boom-bust lift survives under a fully-leaky-free production L1/L2

Until then: treat this as **observational evidence for elevating boom-bust** alongside the headline Tier A projection, not for demoting any current Tier A signal.
