# Pre-registration — `prior_closer_on_il` for FEATS_RPRS2

**Date:** 2026-06-06
**Author:** validation agent (Phase 3 follow-up to commit 69bdfca)
**Protocol:** `reference_multitesting_protocol.md` (9-rule)

## Hypothesis

Adding the binary feature `prior_closer_on_il` (1 = pitcher's team had a prior-year top-SV pitcher who is currently on IL, and pitcher is not that closer) to the production `FEATS_RPRS2` baseline (25 features per `src/plv_clone/models/xfp/rprs2.py:57-72`) increases ROS prediction R² beyond noise.

Mechanism: when the primary closer is IL'd, the handcuff inherits SVs. `role_lag1`/`sv_lag1`/`hld_lag1` reflect only T-1 role; this feature is a current-season team-context signal that the lags cannot encode.

## Pass criteria (Rule 3 — 3-part bar)

A PROMOTE verdict requires ALL three:

1. **Pooled R² lift ≥ +0.01** (LOYO pooled correlation², candidate − baseline)
2. **Per-year convergence ≥ 5/7 folds positive** (Rule 8) — folds: 2019, 2021, 2022, 2023, 2024, 2025 (2020 excluded). Note 2018 and 2021 have feature ≡ 0 (no valid T-1 lookup); both are still evaluated as test folds but feature contributes zero variance there — convergence is on the remaining folds where the feature is non-trivial.
3. **p < 0.0056** (Bonferroni: α=0.05 / 9 candidate features tested across recent sessions), two-sided test on lift Δr².

## Sample

- Source: `data/research/xfp_cache/rolling_relievers_2018_2026.csv` (substrate)
- Target: `fp_year_total`
- Filter: `g_to >= 5`, `year in TRAIN_YEARS = [2019, 2021, 2022, 2023, 2024, 2025]` (2020 COVID excluded; 2018 not in train years per existing rprs2.py)
- Feature coverage: 100% non-null, 8.9% positive class (5,014 / 56,303 rows total; ~10% per active year)

## Methodology

- **Harness:** OLS pipeline mirroring `rprs2.cross_year_eval` — StandardScaler → RidgeCV(alphas=logspace(-1, 5, 80), cv=5)
- **Validation:** Leave-One-Year-Out across TRAIN_YEARS
- **Pooled metric:** Pearson r over concatenated out-of-fold predictions; R² = r²
- **Significance:** Paired bootstrap on (pred_baseline, pred_candidate, actual) tuples, 200 resamples; report 95% CI on Δr² and two-sided p-value (fraction of bootstrap Δr² ≤ 0, doubled)
- **Drop test:** refit candidate, then refit with feature removed → confirm pooled r² drops by ≥ lift

## Rule 9 — Full baseline

Baseline = `FEATS_RPRS2` exactly as it ships at HEAD (`BASE_FEATS + NEW_FEATS`, 25 features). No stripped-down comparison.

## Rule 8 — Convergence

Per-year Δr (candidate − baseline) reported; ≥ 5/7 positive required. Years where feature is constant zero (2018 pre-baseline, 2021 post-COVID-gap) contribute no signal but are still counted.

## Honest expectation

Feature is plausibly redundant with `sv_lag1 == 0 & role_setup_lag1 == 1` plus current-season `sv_per_g_to`. Expected outcome distribution:

- 45%: REJECT — redundant with existing lag features; Δr² < +0.005
- 35%: HOLD — small positive lift but fails Bonferroni or convergence
- 20%: PROMOTE — clears 3-part bar (would imply real current-season team-context signal beyond lags)

A modest +0.003 to +0.008 lift would be characteristic of a feature that captures a real but narrow ~9% slice. Bonferroni threshold of 0.0056 is intentionally strict.

## Out of scope

- No production wiring this session (validation only)
- No re-test of the other `prior_closer_*` cousins (`is_team_prior_closer`, `prior_closer_returned_recently`, `prior_closer_days_since_return`) — each would need its own preregistration
- No interaction terms
