# Boom_Stack Lookup — 2025 Holdout Calibration Test

Generated 2026-06-06.

## Method

- Panel: `_boom_stack_per_start_panel_cache.parquet`, n=4234 2025 SP starts
  with season-end FP-tier assignment (>=8 starts in year required).
- 3-component v1 stack: skill_spike + recform_hot + opp_soft (range 0-3).
  (park_friendly 4th component is post-2025 rollout; panel does not include it.)
- Predicted rates: `BOOM_RATE_BY_TIER_STACK` (per-tier) and
  `COMPOSITE_BOOM_RATE_BY_STACK_V2` (pooled).
- Outcome: actual_FP >= 20.
- Wilson 95% CI on observed; lookup "passes" the bin when predicted
  rate falls inside the CI.

Overall 2025 SP-start boom rate: **15.6%** (n=4234).

## SP — Tier-aware calibration

| tier | stack | n | obs % | pred % | err pp | obs 95% CI | in-CI? |
|------|-------|---|-------|--------|--------|------------|--------|
| ace | 0 | 128 | 40.6 | 41.9 | -1.3 | [32.5, 49.3] | [PASS] |
| ace | 1 | 95 | 46.3 | 44.6 | +1.7 | [36.6, 56.3] | [PASS] |
| ace | 2 | 26 | 53.8 | 48.7 | +5.1 | [35.5, 71.2] | [thin] |
| ace | 3 | 5 | 40.0 | 56.7 | -16.7 | [11.8, 76.9] | [thin] |
| sp2_sp3 | 0 | 233 | 23.6 | 27.0 | -3.4 | [18.6, 29.5] | [PASS] |
| sp2_sp3 | 1 | 159 | 35.8 | 33.4 | +2.4 | [28.8, 43.6] | [PASS] |
| sp2_sp3 | 2 | 38 | 26.3 | 28.0 | -1.7 | [15.0, 42.0] | [PASS] |
| sp2_sp3 | 3 | 6 | 50.0 | 31.2 | +18.8 | [18.8, 81.2] | [thin] |
| backend | 0 | 222 | 21.2 | 20.3 | +0.9 | [16.3, 27.0] | [PASS] |
| backend | 1 | 142 | 31.0 | 25.1 | +5.9 | [24.0, 39.0] | [PASS] |
| backend | 2 | 56 | 14.3 | 20.7 | -6.4 | [7.4, 25.7] | [PASS] |
| backend | 3 | 7 | 28.6 | 21.5 | +7.1 | [8.2, 64.1] | [thin] |
| streamer | 0 | 1598 | 9.1 | 9.4 | -0.3 | [7.8, 10.6] | [PASS] |
| streamer | 1 | 1176 | 11.0 | 12.2 | -1.2 | [9.3, 12.9] | [PASS] |
| streamer | 2 | 294 | 13.6 | 13.2 | +0.4 | [10.2, 18.0] | [PASS] |
| streamer | 3 | 49 | 14.3 | 17.4 | -3.1 | [7.1, 26.7] | [PASS] |

## SP — Pooled (composite) calibration

| stack | n | obs % | pred % | err pp | obs 95% CI | in-CI? |
|-------|---|-------|--------|--------|------------|--------|
| 0 | 2181 | 13.8 | 12.3 | +1.4 | [12.4, 15.3] | [FAIL] |
| 1 | 1572 | 17.4 | 15.0 | +2.5 | [15.6, 19.4] | [FAIL] |
| 2 | 414 | 17.4 | 19.4 | -2.0 | [14.0, 21.3] | [PASS] |
| 3 | 67 | 20.9 | 20.9 | -0.0 | [12.9, 32.1] | [PASS] |

## Diagnostics

- Tier-aware bins with n>=30 in CI: **12/12**
- Pooled bins in CI: **2/4**
- Pooled monotonic stack 0->3 ascending? **False**

## Verdict

**LOOKUP STILL VALID**

Tier-aware lookup (the production query path) has 12/12 populated bins (n>=30) inside the observed 95% CI on the 2025 holdout. Predictions remain calibrated within sampling noise. Recommend continuing to use as-is.

## Hitter boom_stack note

Hitter boom_stack lookup test is not run here because the live
lineup_amp_hitter component requires same-day lineup state that
was not retroactively cached for 2025 in panel form. The
lineup_amp validation (`hitter_lineup_correlation.md`) covers
2018-2025 + 7/7 years positive but a single-2025 calibration
cell is unavailable from the existing snapshot infrastructure.