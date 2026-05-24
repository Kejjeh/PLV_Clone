---
signal: contact_to
formula: Cumulative contact-event count, season-to-date. Pre-computed in rolling_hitters_2018_2026.csv.
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: +
theory: Complements contact_pct_to_sh by carrying volume information — total contact events vs the rate. A hitter with high contact volume has both demonstrated bat-to-ball skill AND the playing time to accumulate it, which proxies for RoS opportunity better than rate alone.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_contact_to.py
date: 2026-05-24
verdict: MARGINAL
purpose: Test whether raw contact-count adds independent predictive lift on RoS FP/PA over the full RH3_FEATS baseline. Surfaced by the 2026-05-24 ceiling audit.
---

### Bonferroni / sweep context

Three raw-count candidates pre-registered same day for rh3 v3 ceiling-audit follow-up:
- bip_to
- contact_to (this file)
- hr_to

All address the same gap (raw-volume counts not encoded in current RH3_FEATS which is rate-dominant). Treat as a 3-cell mini-sweep. Per Rule 3, per-cell α=0.0167. Effect-size gate (+0.005) is binding.

### Rule 9 baseline

Baseline = full RH3_FEATS as of 2026-05-24 (see `src/plv_clone/models/xfp/rh3.py`). NOT a stripped-down subset. Candidate ADDED to this baseline.

### Step 2.5 data-coverage pre-check

- Rows: 15,939; NaN: 0 across all years 2018-2026
- Range: [0, 777], mean ~177
- Coverage: ✓ full

### Convergence-curve framing (Rule 8)

Test at all split_days; report stability.

---

## Result — MARGINAL (2026-05-24)

### Headline (Rule 9 baseline = full RH3_FEATS)

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended (RH3_FEATS + contact_to) cross_year_r | 0.6168 |
| **Δr** | **+0.0001** |
| Pooled n | 8,275 hitter-year-split rows |

Below the +0.005 production gate. Marginal — positive sign but tiny magnitude.

### Per-year breakdown (Rule 2b)

| Year | Baseline r | Extended r | Δr | Sign |
|---|---|---|---|---|
| 2018 | 0.6358 | 0.6358 | +0.0000 | 0 |
| 2019 | 0.6870 | 0.6872 | +0.0002 | + |
| 2021 | 0.5683 | 0.5688 | +0.0005 | + |
| 2022 | 0.6536 | 0.6535 | -0.0001 | - |
| 2023 | 0.5915 | 0.5920 | +0.0005 | + |
| 2024 | 0.5878 | 0.5880 | +0.0002 | + |
| 2025 | 0.6209 | 0.6212 | +0.0003 | + |

Positive years: **5/7** (just clears Rule 2b ≥ 5/7).
Holdout (2024-2025): 2/2 positive — best holdout of the 3-candidate sweep.

### Convergence curve (Rule 8)

| split_day | Baseline r | Extended r | Δr | n |
|---|---|---|---|---|
| 30 | 0.6010 | 0.6006 | -0.0004 | 1833 |
| 60 | 0.6197 | 0.6197 | +0.0000 | 2235 |
| 90 | 0.6287 | 0.6287 | +0.0000 | 2237 |
| 120 | 0.6365 | 0.6365 | +0.0000 | 1970 |

Effectively zero at every split_day; pooled lift comes from cross-year structure not within-cutoff signal.

### Sign sanity

Coef in final pipeline: **+0.0072** (expected: +). Direction OK.

### Why this is MARGINAL not PASS

contact_to is best of the 3-candidate sweep: 5/7 sign + 2/2 holdout + correct coef sign. But pooled Δr is +0.0001, two orders of magnitude below the +0.005 production gate. The signal is real-but-tiny — likely a thin sliver of "volume × contact-quality joint" that isn't fully absorbed by `pa_to` × `contact_pct_to_sh`. Not enough to justify a feature add given the multi-test cost.

### Decision

MARGINAL → do NOT promote to RH3_FEATS. Same family-resemblance to started_pct_to (REJECTED 2026-05-23): raw volume counts are downstream of `pa_to`. Could revisit if rh3 architecture ever supports interaction terms (e.g., explicit `pa_to × contact_pct_to_sh`), at which point this would likely be subsumed.

