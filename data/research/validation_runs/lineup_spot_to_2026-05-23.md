---
signal: lineup_spot_to
formula: PA-weighted average batting-order position season-to-date (1 = leadoff, 9 = bottom). Pre-computed in rolling_hitters_2018_2026.csv from per-game lineup appearances.
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: -
theory: Lower (closer-to-leadoff) lineup spots get more PA per game, more R/RBI opportunities, and SB green-lights on better hitters. All four touch the FP formula directly (R + TB + RBI + BB + SB - K). The rh3 model currently has no lineup-context feature; the cumulative-rate features capture WHAT the hitter does, not HOW MUCH OPPORTUNITY they get.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_lineup_spot_to.py
date: 2026-05-23
verdict: MARGINAL
purpose: Test whether season-to-date lineup spot adds independent predictive lift on RoS FP/PA over the full RH3_FEATS baseline. This is the most theoretically motivated candidate for rh3 v3 — opportunity context is a known FP driver but is not in FEATS.
---

### Bonferroni / sweep context

Three candidates pre-registered same day for rh3 v3 research:
- lineup_spot_to (this file)
- pa_per_started_game_to
- started_pct_to

All three address the same gap (no opportunity/playing-time context in
RH3_FEATS) from different angles. Treat as a 3-cell mini-sweep. Per Rule 3,
the per-cell α=0.05 bar → α=0.0167 per cell. We'll report what the effective
partial-r adjustment is in the writeup.

### Rule 9 baseline

Baseline = full RH3_FEATS = 20 features as of 2026-05-23
(see `src/plv_clone/models/xfp/rh3.py` lines 91-117). NOT a stripped-down
subset. The candidate is ADDED to this baseline. Lift = cross_year_r(baseline + candidate)
− cross_year_r(baseline).

### Convergence-curve framing (Rule 8)

In-season production use case → test at multiple split_day cutoffs
(30, 60, 90, 120) and report stability across cutoffs.

---

## Result — MARGINAL (2026-05-23)

### Headline (Rule 9 baseline = full RH3_FEATS, 20 features)

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended (RH3_FEATS + lineup_spot_to) cross_year_r | 0.6176 |
| **Δr** | **+0.0009** |
| Pooled n | 8,275 hitter-year-split rows |

**Below the +0.005 strict bar → MARGINAL, not eligible for promotion.**

### Per-year breakdown (Rule 2b)

| Year | Baseline r | Extended r | Δr | Sign |
|---|---|---|---|---|
| 2018 | 0.6358 | 0.6345 | -0.0013 | - |
| 2019 | 0.6870 | 0.6884 | +0.0014 | + |
| 2021 | 0.5683 | 0.5720 | +0.0037 | + |
| 2022 | 0.6535 | 0.6553 | +0.0018 | + |
| 2023 | 0.5916 | 0.5933 | +0.0017 | + |
| 2024 | 0.5880 | 0.5830 | -0.0050 | - |
| 2025 | 0.6211 | 0.6231 | +0.0020 | + |

Positive years: **5/7** (meets Rule 2b minimum, but margin is razor-thin).
Holdout (2024-2025): 1/2 positive — weak.

### Convergence curve (Rule 8)

| split_day | Baseline r | Extended r | Δr | n |
|---|---|---|---|---|
| 30 | 0.6008 | 0.6036 | +0.0028 | 1833 |
| 60 | 0.6197 | 0.6200 | +0.0003 | 2235 |
| 90 | 0.6287 | 0.6281 | -0.0006 | 2237 |
| 120 | 0.6365 | 0.6361 | -0.0004 | 1970 |

**Signal decays across the season:** strongest at the 30-day cutoff
(+0.0028) and disappears by mid-season. This means by the time we have
60+ days of in-season data, the lineup-spot information is already
implicit in the cumulative-rate features (`pa_to`, `xwoba_per_pa_to_sh`,
etc. — high-PA top-of-order hitters accumulate different cumulative
profiles than bottom-of-order platoon bats).

### Sign sanity check

Coef in final pipeline (with feature added): **-0.0075** (expected: -).
A 1-spot increase in lineup position (e.g. 3rd to 4th in the order)
predicts a -0.0075 FP/PA tilt before regularization. Direction is
correct; magnitude is small.

### Decision

Do NOT add to RH3_FEATS. The +0.0009 lift is well below the +0.005
production gate and Rule 9 hard assert would block promotion at
pipeline import time anyway. Convergence pattern shows the signal is
strictly redundant with existing features after week ~6.

### Future re-test viability

If a future rh3 variant uses a SHORTER cutoff window (e.g. ranks at
week 4 of the season for early-season FA waves), this signal might
matter — convergence shows the +0.0028 lift at split_day=30. But within
the current rh3 production framing (all split_days, RoS), it's noise.
