---
signal: bat_speed_level_prior
formula: mean(statcast.bat_speed) for year T-1 per batter, min 100 tracked swings; joined onto outcome rows for year T
outcome: fp_per_pa_actual in year T (full-year framing; rh3 ros analog via standard rh3 harness)
expected_sign: +
theory: Bat speed LEVEL (not delta) is a sustained physical skill that encodes power potential orthogonal to outcome-based features already in RH3_FEATS. Bleday/Chourio-class hitters show +20 FP/600 PA cohort lift. Unlike YoY deltas (rejected 2026-05-16 for sample size), the level only requires one prior year of tracking — so it becomes computable for T=2025 outcomes (prior 2024) and T=2026 outcomes (prior 2025).
production_target: rh3
framing: full-year (prior-year mean predicts current-year per-PA outcome)
holdout_years: [2026]
training_years: [2025]
validation_script: scripts/xfp/validate_bat_speed_level_prior.py (NOT WRITTEN — fails Step 2.5 pre-check)
date: 2026-05-24
verdict: REJECTED — Step 2.5 sample-size
purpose: User asked to mine cheap data sources. Bat-tracking LEVEL is conceptually weaker than the rejected DELTA candidate (2026-05-16) and was hypothesized as a partial-clearance Rule 5 candidate. Pre-check shows it does not even partially clear.
---

### Rule 5 sample-size honesty note (pre-acknowledged, halts at Step 2.5)

Statcast bat tracking began **2024** (mid-season). To compute
`bat_speed_level_prior(T)`, year T-1 must have tracking data.

| Outcome year T | Prior year T-1 | Tracking present? | Usable? |
|---|---|---|---|
| 2019 | 2018 | No | No |
| 2020 | 2019 | No | No |
| 2021 | 2020 | No | No |
| 2022 | 2021 | No | No |
| 2023 | 2022 | No | No |
| 2024 | 2023 | No | No |
| 2025 | 2024 | Yes (partial, mid-2024 onward) | One training year |
| 2026 | 2025 | Yes | HOLDOUT |

Train-eligible: **1 year** (2025 outcomes only).
Rule 2(b) requires sign consistency across ≥ 5 of 7 training years.
This test CANNOT clear the gate; the protocol halts at Step 2.5.

### Data coverage audit (Step 2.5)

- Raw source: `data/research/xfp_cache/statcast_{2024,2025}.parquet`
  contains `bat_speed`, `swing_length`, `swing_path_tilt`. 2024 = 710,631
  pitches; 2025 = 711,897 pitches. Sufficient per-batter swing counts.
- Cache rollup `hitters_multiyr_2015_2026.csv` has
  `avg_swing_speed` populated ONLY for 2026 (435 batters); 2015-2025 = 0
  coverage. So the aggregate is not yet flowing T-1 from the raw parquet
  into the season-level cache used by RH3_FEATS pipelines.
- Even if the parquet were rolled up, only 1 training year exists.

### Verdict

REJECTED at Step 2.5. Same root cause as `bat_speed_delta_prior_year`
(2026-05-16) and `attack_angle_consistency_delta` (2026-05-16). This
hypothesis is UN-VALIDATABLE until at least 2027-2028 outcomes
(N=3 training years: 2025, 2026, 2027) — still short of 5/7 but might
warrant a special-case Rule 5 partial-clearance argument at that point.

### What would unblock validation

- Continue capturing bat-tracking each year. By 2028 outcomes, we have
  T-1 ∈ {2024, 2025, 2026, 2027} = 4 training years. Still 1 short of
  the 5/7 gate but defensible as a Rule 5 partial-clearance candidate
  if effect size is large (≥ +0.010 lift).
- Roll up `bat_speed_mean_per_batter` from
  `data/research/xfp_cache/statcast_*.parquet` into
  `hitters_multiyr_2015_2026.csv` as a one-time materialisation, so
  future runs don't have to re-aggregate the raw pitch table. This is
  cheap infra work (single pandas groupby) and worth doing now even
  though the validation itself is blocked.
