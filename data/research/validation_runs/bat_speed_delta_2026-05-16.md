---
signal: bat_speed_delta_prior_year
formula: bat_speed_mean(year T-1) − bat_speed_mean(year T-2), per batter, both seasons min 100 tracked swings
outcome: fp_per_pa_actual in year T
expected_sign: +
theory: A sustained mechanical change in bat speed (year-over-year) predicts power/FP gains the following season (Bleday hypothesis generalized).
production_target: rh3
framing: full-year (year-prior delta predicts following season)
holdout_years: [2026]
training_years: [2025] only — see Rule 5 honesty note below
validation_script: scripts/xfp/validate_bat_speed_delta.py
date: 2026-05-16
verdict: REJECTED
purpose: Test whether the +20 FP/600 PA effect seen in the Bleday analog cohort (N=7) is robust enough to be used as a predictor in rh3.
---

### Rule 5 sample-size honesty note (pre-acknowledged)

Statcast bat tracking began 2024. To compute `bat_speed_delta(T-1 → T)`,
both year T-1 and T-2 must have tracking data. This gives:
- 2025 outcomes: signal = delta(2023 → 2024), but 2023 has NO bat-tracking → CANNOT compute
- 2026 outcomes: signal = delta(2024 → 2025), both available → CAN compute (one training year)

We have AT MOST one valid training year (2026 outcomes from 2024→2025 delta).
Rule 2(b) requires sign consistency across ≥ 5 of 7 training years. This
test CANNOT clear that gate with current data. The protocol will flag
this in Step 4.

The expected outcome is REJECTION at Step 5 (sample-size honesty). The
finding to log: this hypothesis is UN-VALIDATABLE until at least
2027-2028, when we'll have enough year-stack of bat tracking to test it.
