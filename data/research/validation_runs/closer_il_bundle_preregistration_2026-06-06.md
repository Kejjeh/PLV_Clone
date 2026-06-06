# Pre-registration: closer-IL bundle (3 sibling features) — 2026-06-06

## Hypothesis
The 3-feature closer-IL sibling bundle adds R² lift to rprs2 ROS prediction beyond
the current 28-feature FEATS_RPRS2 baseline (Rule 9 full baseline).

Bundle features:
- `is_team_prior_closer` (binary)
- `prior_closer_returned_recently` (binary)
- `prior_closer_days_since_return` (numeric; 999 = never-IL / N/A sentinel)

## Context
Single-feature `prior_closer_on_il` (commit dcd17d5) REJECTED: ΔR²=+0.0001, p=0.26.
Agent flagged that 3 sibling features may share redundancy with concurrent in-season
signals (`role_closer_lag1`, `sv_lag1`, `hld_lag1`, `gf_pct_to`, `sv_per_g_to`, etc.)
but should be tested as a JOINT BUNDLE to keep Bonferroni honest.

This is the FINAL CALL for the closer-IL feature family. REJECT → permanently archive.

## Pass criteria (3-part bar; Rule 3, Rule 8, Rule 9)
1. **Pooled R² lift ≥ +0.01** vs 28-feature baseline (joint bundle add-in)
2. **Per-year convergence ≥ 5/7 folds positive** (Rule 8; folds = LOYO across
   2019, 2021, 2022, 2023, 2024, 2025 — 6 evaluable folds, so practical bar 5/6)
3. **Joint test (bootstrap two-sided p) < 0.0056** — Bonferroni penalty for
   ~9 candidate features tested in recent sessions

## Sample
- Substrate: `data/research/xfp_cache/rolling_relievers_2018_2026.csv`
- Years: 2019, 2021, 2022, 2023, 2024, 2025 (2020 COVID excluded; 2018 reserved)
- Filter: `g_to >= 5`
- Target: `fp_year_total`

## Methodology
- LOYO across TRAIN_YEARS
- Per-fold StandardScaler + RidgeCV(alphas=logspace(-1,5,80), cv=5)
- Three fits compared:
  1. Baseline (28 feats)
  2. Baseline + `is_team_prior_closer` (29 feats)
  3. Baseline + 3-feature bundle (31 feats)
- Joint test: bootstrap 200 resamples on Δr² (bundle vs baseline), two-sided p
- Drop test: per-feature individual removal from the bundle
- Canonical RP scoring: Duran, Helsley, Fairbanks, T. Scott, Morejón, Palencia

## Honest expectation
Bundle is likely also redundant because the strongest concurrent in-season signals
(`role_closer_lag1`, `sv_lag1`, `hld_lag1`, `gf_pct_to`) already encode "is this
pitcher functionally the closer" — which is what `is_team_prior_closer` proxies
across years. Days-since-return is a low-frequency event with high sentinel-value
density (999s). Bonferroni-adjusted bar of p<0.0056 is correctly steep.

If REJECT, the closer-IL family is permanently archived.
