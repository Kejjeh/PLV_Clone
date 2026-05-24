---
signal: pa_per_started_game_to
formula: Average plate appearances per started game, season-to-date. Pre-computed in rolling_hitters_2018_2026.csv as total PA / games started.
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: +
theory: PA density per started game captures playing-time intensity within a game (top-of-order on a high-PA team vs bottom-of-order, or pinch-hit late vs full 9-inning starter). More PA per game means more chances for R/BB/SB beyond what raw lineup spot encodes — especially in extra-inning or high-volume offensive teams. Orthogonal-ish to lineup spot (corr ≈ -0.82 raw; let the regression sort out the independent lift).
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_pa_per_started_game_to.py
date: 2026-05-23
verdict: MARGINAL
purpose: Test whether PA-per-started-game adds independent predictive lift on RoS FP/PA over the full RH3_FEATS baseline. Sibling candidate to lineup_spot_to — opportunity-volume angle.
---

### Bonferroni / sweep context

Three candidates pre-registered same day for rh3 v3 research:
- lineup_spot_to
- pa_per_started_game_to (this file)
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
| Extended (RH3_FEATS + pa_per_started_game_to) cross_year_r | 0.6200 |
| **Δr** | **+0.0033** |
| Pooled n | 8,275 hitter-year-split rows |

**Below the +0.005 strict bar but the strongest candidate of the
3-cell sweep → MARGINAL, not eligible for promotion.**

### Per-year breakdown (Rule 2b)

| Year | Baseline r | Extended r | Δr | Sign |
|---|---|---|---|---|
| 2018 | 0.6358 | 0.6306 | -0.0052 | - |
| 2019 | 0.6870 | 0.6901 | +0.0031 | + |
| 2021 | 0.5683 | 0.5755 | +0.0072 | + |
| 2022 | 0.6535 | 0.6559 | +0.0024 | + |
| 2023 | 0.5916 | 0.5999 | +0.0083 | + |
| 2024 | 0.5880 | 0.5817 | -0.0063 | - |
| 2025 | 0.6211 | 0.6274 | +0.0063 | + |

Positive years: **5/7** (meets Rule 2b minimum).
Holdout (2024-2025): 1/2 positive — same weak holdout pattern as
lineup_spot_to. The 2024 hit (-0.0063) is the largest negative.

### Convergence curve (Rule 8)

| split_day | Baseline r | Extended r | Δr | n |
|---|---|---|---|---|
| 30 | 0.6008 | 0.6044 | +0.0036 | 1833 |
| 60 | 0.6197 | 0.6213 | +0.0016 | 2235 |
| 90 | 0.6287 | 0.6295 | +0.0008 | 2237 |
| 120 | 0.6365 | 0.6387 | +0.0022 | 1970 |

**Signal is positive across all four cutoffs** — more stable than
lineup_spot_to, but still weak. Peak at split_day=30 (+0.0036), trough
at split_day=90 (+0.0008). The convergence pattern (no sign flips)
is the strongest qualitative argument for this candidate; lineup_spot_to
goes negative at split_days 90 and 120.

### Sign sanity check

Coef in final pipeline: **+0.0125** (expected: +).
A 1-PA-per-game increase predicts +0.0125 FP/PA tilt. Direction correct,
magnitude consistent with theory (volume hitters accumulate more
RBI/R/SB chances per PA).

### Why this beat lineup_spot_to despite raw-correlation tie

Both candidates have raw correlation ~0.40 with target. After the full
RH3_FEATS baseline absorbs the lineup-position signal via cumulative
rates, `pa_per_started_game_to` retains slightly more independent
predictive content. Likely because PA-per-game captures team-level
offensive context (your team hits a lot of singles → you bat more
times per game) that's orthogonal to per-PA rate stats.

### Decision

Do NOT add to RH3_FEATS. The +0.0033 lift is below the +0.005
production gate and Rule 9 hard assert would block promotion. The
3-cell Bonferroni context (this is the best of 3 sweep candidates)
also argues for caution.

### Future re-test viability

Worth revisiting if:
- A different baseline configuration (e.g. without `pa_to`) is being
  tested — `pa_per_started_game_to` is partially redundant with `pa_to`.
- Rule 9 gate is ever lowered or scope changes to draft/offseason framing.
- Combined with other opportunity-context features (park factor,
  remaining-schedule strength) into a multi-feature opportunity bundle
  — a joint test might clear +0.005 where individual ones can't.
