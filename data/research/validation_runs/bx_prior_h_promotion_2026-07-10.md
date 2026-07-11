---
signal: bx_prior_h
formula: Vintage (as-of) xfp_bx v0 hitter ridge prediction of year-T full-season fp_per_pa, trained strictly on box-score panel PAIRS with target year <= T-1 (StandardScaler + RidgeCV, xfp_bx v0 features incl. Marcel-lite prior, K%, ISO, SB rate components), predicted from the player's year-(T-1) box line (T=2021 uses 2019 per the 2020 exclusion). Built by scripts/xfp/build_bx_priors.py -> data/research/xfp_cache/bx_priors_2018_2026.csv; joined on (batter=mlbam, year), NaN filled per-year mean.
outcome: rh3 cross_year_eval Δr on RoS FP/PA target (matches rh3 production)
expected_sign: +
theory: The 60-year box-score-era model carries component-rate decomposition and coefficient stability that is not fully redundant with rh3's own Marcel prior (prior_fp_per_pa) — validated as ensemble cell B1.
production_target: rh3
framing: prior-year box line -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_bx_ensemble.py (B1) + scripts/xfp/validate_bx_preflight.py (post-SB pre-flight)
date: 2026-07-10
verdict: PASS
purpose: Registry PASS record for the bx_prior_h promotion so check_feats_validated(RH3_FEATS) passes. Full prereg + B1 results + pre-flight in bx_ensemble_2026-07-10.md — B1 PASS on pre-SB substrate (+0.0088, 5/7 signs, holdout mean +0.0093); pre-flight on the live-SB BUILDER_VERSION-3 cache PROMOTE (+0.0076, holdout mean +0.0072, coef +0.0264; sign consistency 4/7 on the new substrate, disclosed — the pre-registered pre-flight decision rule was lift + holdout-mean only).
---

# `bx_prior_h` promotion record — 2026-07-10

This file exists as the machine-readable PASS record for the
`validated_signals.check_feats_validated` hard gate. The full
pre-registration, 4-cell results, integration recipe, and the dated
pre-flight section live in `bx_ensemble_2026-07-10.md`; the pre-flight
numbers are in `bx_preflight_results_2026-07-10.json`.

- Original B1 (pre-SB substrate): +0.0088 (0.6275 → 0.6363), 5/7 signs,
  holdout mean +0.0093, coef +0.028 — PASS.
- Pre-flight (live-SB substrate, 2026-07-10 evening): +0.0076
  (0.6343 → 0.6419), holdout mean +0.0072 (2024 +0.0165 / 2025 −0.0021),
  coef +0.0264 — PROMOTE per the pre-registered rule (lift ≥ +0.005 AND
  holdout mean positive). Disclosure: per-year sign consistency on the new
  substrate is 4/7 (2021 −0.0003, 2022 −0.0059, 2025 −0.0021).
