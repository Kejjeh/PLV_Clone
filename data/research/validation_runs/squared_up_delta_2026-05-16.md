---
signal: squared_up_rate_delta_prior_year
formula: squared_up_rate(year T-1) − squared_up_rate(year T-2), per batter, both seasons min 100 tracked swings. squared_up = swings with bat_speed ≥ 0.9 × per-batter max bat_speed (a proxy MLB uses; competitive-swing tier).
outcome: barrel_per_pa OR hr_per_pa in year T (component-level outcome, per Rule 4)
expected_sign: +
theory: A higher % of squared-up swings means more consistent damage on contact regardless of raw bat speed. Tests whether the qualitative pattern in Bleday (44%→72% squared-up rate jump) translates to power.
production_target: rh3 (component-level — barrel% feature)
framing: full-year
holdout_years: [2026]
training_years: [2025] only — same Rule 5 issue as Test A
validation_script: scripts/xfp/validate_squared_up_delta.py
date: 2026-05-16
purpose: Component-level retest pattern (Rule 4) — even if bat speed delta doesn't move composite FP, the squared-up rate change might more directly predict barrel%, which then feeds rh3 separately.
---

### Rule 5 sample-size honesty note (pre-acknowledged)

Same constraint as bat_speed_delta: requires 3 consecutive years of bat
tracking. Only 2024+2025+2026 available. Test cannot clear the 5-of-7
year-consistency gate. Expected outcome: REJECTION at Step 5, deferred
to 2027-2028 when more years of tracking exist.
