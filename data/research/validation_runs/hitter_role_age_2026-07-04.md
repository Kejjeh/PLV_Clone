---
signal: hitter_role_age
formula: -0.5 * within-year z(mean_lineup_spot) - 0.5 * within-year z(age), from hitter_ratings_master year T
outcome: next-year TOTAL FP (fp_per_pa * pa, year T+1), career panel
expected_sign: +
theory: who keeps the job and the lineup slot predicts T+1 total FP beyond rate and beyond the ratings (2/3 volume channel, 1/3 rate decline).
production_target: research-only
framing: full-year
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_hitter_role_age.py
date: 2026-07-04
verdict: PASS
---
rating_reimagine queue #3. ANNUAL/keeper valuation layer ONLY (in-season null vs rh3
pre-declared, partial <.15 known). Baseline = fp_total(T) + OVERALL(T) +
t1_fp_projection(T) — the strongest annual stack available. Gates: partial >= .10,
5/5 year signs, holdout partial >= .05. Survivorship: conditional on T+1 appearance;
report unconditional variant too.
