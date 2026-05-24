---
signal: rh3_opportunity_bundle
formula: pa_per_started_game_to + lineup_spot_to*split_day + park_pf_wOBA_ros (3-feat bundle added simultaneously)
outcome: ros_full_fp_per_pa
expected_sign: + (bundle vs baseline; signs of individual components may vary)
theory: Three independent signal axes (volume, context, venue) tested as a bundle to see if joint Ridge fit compresses collinearity differently than the sum of individual marginals suggests. Each component was sub-gate alone.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_rh3_opportunity_bundle.py
date: 2026-05-24
verdict: MARGINAL
purpose: Per user-requested exhaustive ceiling-audit follow-up. Bundle test of 3 MARGINAL signals from prior individual runs.
---

## Result (2026-05-24)

- baseline cross_year_r: 0.6167
- extended cross_year_r: 0.6203
- **Δr (bundle - baseline): +0.0036**
- per-year positives: 5/7 (PASS sign-consistency)
- holdout (2024-25) positives: 1/2 (FAIL — 2024 -0.0048, 2025 +0.0079)
- sum-of-marginals (prior individual): +0.0046
- joint-vs-sum delta: **-0.0010** (joint fit UNDERSHOT sum-of-marginals; collinearity penalty exceeds compression benefit)

### Joint-fit coefficients (Ridge, scaled)

- pa_per_started_game_to:   +0.015097  (volume; matches individual +0.0033 lift sign)
- lineup_spot_x_split_day:  +0.005886  (context; small, positive)
- park_pf_wOBA_ros:         -0.002716  (venue; **wrong sign** in joint fit — was wrong-sign individually too, ridge keeps pulling it negative)

### Per-split_day Δr

- 30:  +0.0027  (n=1833)
- 60:  +0.0004  (n=2235)
- 90:  +0.0004  (n=2237)
- 120: +0.0020  (n=1970)

Early-season cell carries most of the lift; mid-season cells essentially flat.

### Verdict: MARGINAL

Below +0.005 production gate (Δr +0.0036). Sign-consistency 5/7 passes but holdout 1/2 fails. The bundle hypothesis (joint fit > sum of marginals) was **refuted** — joint fit was -0.0010 below the sum, indicating the 3 axes share more variance with the existing baseline than they share with each other.

### Recommendation

- DO NOT add the bundle to RH3_FEATS.
- `park_pf_wOBA_ros` is confirmed-noise on rh3 (wrong sign both individually and jointly). Park-factor information is already absorbed by career-level priors. Park-factor should be retired from rh3 candidate list pending a per-year, batter-specific home-park weighting (the static team-level join is too coarse).
- `pa_per_started_game_to` remains the most promising solo candidate (joint coef +0.015 is the largest of the three), but a 4th-source bundle adding one more orthogonal axis would be needed to clear +0.005.
- `lineup_spot_x_split_day` interaction is salvageable as a split_day=30-only feature, but production rh3 trains on all cutoffs jointly so it cannot be cleanly slotted.


## Bundle components

1. **`pa_per_started_game_to`** — pre-existing column in `rolling_hitters_2018_2026.csv`. Volume axis. Validated 2026-05-23 individual lift Δr +0.0033 (MARGINAL).
2. **`lineup_spot_x_split_day`** — interaction term `lineup_spot_to * split_day`, both pre-existing columns. Context axis. Validated 2026-05-24 individual lift Δr -0.0001 (REJECTED), but split_day=30 cell showed +0.0027 in isolation.
3. **`park_pf_wOBA_ros`** — joined park factor from `data/research/xfp_cache/park_factors.csv` via the player's `team` in `hitters_multiyr_2015_2026.csv` for the matching year. Venue axis. Validated 2026-05-24 individual lift Δr +0.0014 (MARGINAL, wrong-sign coef).

Sum-of-marginals = +0.0046 (below +0.005 gate). Bundle hypothesis: joint Ridge fit compresses collinearity differently and clears the gate.

## Verdict gates

- **PASS:** bundle Δr ≥ +0.005 AND per-year sign ≥ 5/7
- **MARGINAL:** 0 < Δr < +0.005, or Δr ≥ +0.005 with 4/7 sign
- **REJECTED:** Δr ≤ 0 or sign ≤ 3/7

If PASS, drop-one analysis (Rule 6) identifies the load-bearing component.

DO NOT modify RH3_FEATS on PASS without separate production-promotion review.
