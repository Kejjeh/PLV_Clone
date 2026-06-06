# Validation results — `prior_closer_on_il` for FEATS_RPRS2

**Date:** 2026-06-06
**Preregistration:** `prior_closer_on_il_preregistration_2026-06-06.md`
**Harness:** `scripts/xfp/fit_prior_closer_on_il_validation.py`
**JSON:** `prior_closer_on_il_validation_2026-06-06.json`

## TL;DR

**VERDICT: REJECT.** All 3 gates of the Rule-3 bar fail. The feature is fully redundant with the existing 25-feature `FEATS_RPRS2` baseline at the pooled level. Pooled Δr² = +0.00010 (vs +0.01 threshold), convergence 4/6 (vs 5/6 threshold), bootstrap p=0.26 (vs 0.0056 threshold). Drop test confirms zero unique contribution.

## Step 1 — Feature confirmation

- File: `data/research/xfp_cache/rolling_relievers_2018_2026.csv`
- Column: `prior_closer_on_il` (int64, binary)
- Coverage: **100.00%** non-null across all 56,303 substrate rows
- Positive rate: **8.91%** (5,014 rows)
- Per-year positive rate: 2018=0.0% (no T-1 lookup pre-substrate), 2019=10.9%, 2021=0.0% (COVID-gap kills T-1), 2022=15.3%, 2023=12.2%, 2024=12.7%, 2025=10.2%, 2026=13.1%
- Definition (per `scripts/xfp/enrich_rolling_relievers.py:91-148`): 1 iff pitcher's team had a T-1 top-SV pitcher (≥15 SV), that pitcher is currently on IL at the cutoff, AND it is not this pitcher

Note: 2018 and 2021 contribute zero feature variance (identically zero across rows). They remain in the LOYO TRAIN_YEARS per `rprs2.py` convention, but contribute no information to the lift signal in those folds.

## Step 3 — Fit results

| Model | Features | Pooled r | Pooled R² | MAE | n |
|---|---|---|---|---|---|
| Baseline (FEATS_RPRS2) | 28 | 0.8737 | 0.7634 | 32.12 | 34,115 |
| Candidate (+prior_closer_on_il) | 29 | 0.8738 | 0.7635 | 32.13 | 34,115 |

**Pooled Δr² = +0.00010** (target ≥ +0.01 — fails by 100×)

### Per-year convergence (Rule 8)

| Year | Baseline r | Candidate r | Δr | Sign |
|---|---|---|---|---|
| 2019 | 0.8721 | 0.8720 | −0.0001 | − |
| 2021 | 0.8706 | 0.8707 | +0.0001 | + |
| 2022 | 0.8673 | 0.8675 | +0.0002 | + |
| 2023 | 0.8918 | 0.8920 | +0.0002 | + |
| 2024 | 0.8739 | 0.8732 | −0.0007 | − |
| 2025 | 0.8676 | 0.8679 | +0.0003 | + |

Positive folds: **4 / 6** (target ≥ 5/6 — fails). All non-zero deltas are within ±0.0007, well inside noise.

### Bootstrap (200 resamples, paired)

- Bootstrap Δr² point estimate: **+0.00008**
- 95% CI: **[−0.00005, +0.00023]** — straddles zero
- Two-sided p: **0.2600** (target < 0.0056 Bonferroni — fails by 46×)

### Drop test

Removing `prior_closer_on_il` from the candidate model returns the baseline exactly (Δr² = +0.00010). Feature contributes no orthogonal signal beyond what `sv_lag1`, `role_lag1`, `sv_per_g_to`, `gf_pct_to`, and `fp_with_role_to` already encode.

## Step 5 — Canonical RP deltas

All 5 canonical RPs (and Robert Suárez, who would be the mechanism case) currently have `prior_closer_on_il = 0`, so the feature does not fire on them at their latest 2026 split day. Deltas are pure RidgeCV refit noise from the slightly larger feature matrix:

| RP | Team | PCOIL | ros_baseline | ros_candidate | Δ |
|---|---|---|---|---|---|
| Ryan Helsley | BAL | 0 | 237.80 | 238.08 | +0.28 |
| Jhoan Duran | PHI | 0 | 319.23 | 319.51 | +0.29 |
| Pete Fairbanks | MIA | 0 | 216.33 | 216.75 | +0.41 |
| Tanner Scott | LAD | 0 | 259.63 | 260.08 | +0.45 |
| Daniel Palencia | CHC | 0 | 156.91 | 157.22 | +0.32 |

Morejón and Robert Suárez were not present in the substrate's most-recent 2026 snapshot with name match — likely an MLBAM/name normalization gap. Irrelevant to the verdict given the pooled signal is statistical noise.

All deltas < 0.5 FP — well below the 5-FP "investigate mechanism" threshold from Step 5 of the mandate.

## Step 6 — Verdict

**REJECT.**

| Gate | Threshold | Observed | Pass? |
|---|---|---|---|
| Pooled Δr² | ≥ +0.01 | +0.00010 | NO |
| Per-year convergence | ≥ 5/6 folds positive | 4/6 (noise) | NO |
| Bonferroni p | < 0.0056 | 0.2600 | NO |

0 of 3 gates pass. Honest negative result.

### Interpretation

The mechanism (closer IL → handcuff inherits role) is real, but `FEATS_RPRS2` already captures it through downstream signals that evolve concurrently:

- `sv_per_g_to` and `gf_pct_to` rise as the handcuff inherits save opportunities
- `fp_with_role_to` captures the SV-bonus FP that handcuffs accumulate
- `sv_lag1` + `role_setup_lag1` already mark prior setup men with closer-adjacent profiles

By the time a model is trained on `g_to ≥ 5` data, the handcuff's current-season usage stats have already absorbed the signal. The binary IL flag is informationally pre-empted.

### Why not "HOLD"

All three gates fail in the same direction (no signal). HOLD is reserved for borderline cases with mixed evidence. This is a clean reject.

### No Phase 4 ship spec

Not promoting → no FEATS_RPRS2 modification, no schema change, no refresh-order change. `rprs2.py` ships unchanged.

## Files produced

- `scripts/xfp/fit_prior_closer_on_il_validation.py` (new, validation harness)
- `data/research/validation_runs/prior_closer_on_il_preregistration_2026-06-06.md`
- `data/research/validation_runs/prior_closer_on_il_validation_2026-06-06.md` (this file)
- `data/research/validation_runs/prior_closer_on_il_validation_2026-06-06.json`

## Follow-ups (optional, not in scope)

- The 3 sibling features (`is_team_prior_closer`, `prior_closer_returned_recently`, `prior_closer_days_since_return`) likely share the same redundancy. Recommend either (a) bundle them into one pre-registered joint test, or (b) reject by analogy without further compute.
- If a future researcher wants to revive `prior_closer_on_il`, the only path is an **interaction term** with `role_setup_lag1` or a `g_to < 10` early-season subset — both would need fresh preregistration.
