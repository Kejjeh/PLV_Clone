---
signal: attack_angle_consistency_delta
formula: std(attack_angle, year T-1) − std(attack_angle, year T-2), per batter, min 100 tracked swings each year
outcome: barrel_per_pa in year T
expected_sign: -
theory: A lower year-over-year SD of attack_angle indicates a more repeatable swing path, which should translate to more consistent contact quality (barrel rate).
production_target: rh3 (component-level — would feed the barrel_pct_to_sh stream)
framing: full-year (offseason draft prep)
holdout_years: [2026]
training_years: [<determined at Step 2.5>]
validation_script: scripts/xfp/validate_attack_angle_consistency_delta.py (not yet written — pending Step 2.5)
date: 2026-05-16
purpose: Test whether attack-angle consistency (a Statcast bat-tracking metric) provides predictive lift on barrel rate above the existing rh3 baseline.
---
