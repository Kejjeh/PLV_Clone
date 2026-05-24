---
signal: started_pct_to
formula: Fraction of team games for which the batter appeared in the starting lineup, season-to-date. Pre-computed in rolling_hitters_2018_2026.csv.
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: +
theory: A batter who has started a high fraction of team games is more established in the lineup and faces less risk of role downgrade. Lower started_pct often indicates a platoon/bench role (less talent-curated starting lineups → lower RoS expected FP). Captures durability + role-stability signal that's only weakly proxied by PA volume.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_started_pct_to.py
date: 2026-05-23
verdict: REJECTED
purpose: Test whether started-fraction-of-games adds independent predictive lift on RoS FP/PA over the full RH3_FEATS baseline. Sibling candidate to lineup_spot_to — role-stability angle.
---

### Bonferroni / sweep context

Three candidates pre-registered same day for rh3 v3 research:
- lineup_spot_to
- pa_per_started_game_to
- started_pct_to (this file)

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

## Result — REJECTED (2026-05-23)

### Headline (Rule 9 baseline = full RH3_FEATS, 20 features)

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended (RH3_FEATS + started_pct_to) cross_year_r | 0.6164 |
| **Δr** | **-0.0003** |
| Pooled n | 8,275 hitter-year-split rows |

**Negative Δr. Feature actively hurts (very slightly) the model.
REJECTED.**

### Per-year breakdown (Rule 2b)

| Year | Baseline r | Extended r | Δr | Sign |
|---|---|---|---|---|
| 2018 | 0.6358 | 0.6359 | +0.0001 | + |
| 2019 | 0.6870 | 0.6866 | -0.0004 | - |
| 2021 | 0.5683 | 0.5683 | +0.0000 | 0 |
| 2022 | 0.6535 | 0.6537 | +0.0002 | + |
| 2023 | 0.5916 | 0.5916 | +0.0000 | 0 |
| 2024 | 0.5880 | 0.5876 | -0.0004 | - |
| 2025 | 0.6211 | 0.6211 | +0.0000 | 0 |

Positive years: **2/7** (fails Rule 2b ≥ 5/7 requirement).
Holdout (2024-2025): 0/2 positive.

### Convergence curve (Rule 8)

| split_day | Baseline r | Extended r | Δr | n |
|---|---|---|---|---|
| 30 | 0.6008 | 0.6005 | -0.0003 | 1833 |
| 60 | 0.6197 | 0.6196 | -0.0001 | 2235 |
| 90 | 0.6287 | 0.6295 | +0.0008 | 2237 |
| 120 | 0.6365 | 0.6364 | -0.0001 | 1970 |

Effectively zero signal at every cutoff.

### Sign sanity check

Coef in final pipeline: **+0.0005** (expected: +).
Direction is correct but coefficient is so small the feature isn't
doing anything. Likely because `started_pct_to` is highly correlated
with the cumulative-rate features themselves (a player who's started
80% of games has the PA volume to push their `xwoba_per_pa_to_sh`
toward its true mean; the ranking is implicit).

### Why this failed

Hypothesized role-stability signal was already fully encoded in
`pa_to` (the cumulative PA cue) and the cumulative-rate features.
The marginal lift over a model that knows your PA volume + xwOBA +
ISO + K%/BB% etc. is zero. Started-pct doesn't add information; it's
a noisy proxy for what `pa_to` already captures.

### Decision

REJECTED. Do not add to RH3_FEATS. Permanently out — the
relationship is structurally redundant with `pa_to`. Re-test only
viable if the rh3 architecture ever drops `pa_to` (extremely unlikely).
