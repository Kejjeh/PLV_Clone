---
signal: stuff_x_control
formula: within-year z(swstr_pct_to_sh) * within-year z(zone_pct_to_sh minus bb-rate direction — z(-bb_pct_to_sh)) interaction term
outcome: ros_fp_per_start
expected_sign: +
theory: command is worth ~0 for low-stuff arms and ~+1.4 FP/start atop high stuff (quadrants 8.90/9.00/11.19/12.60); the additive baseline can't express the gate.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_rating_queue_batch.py
date: 2026-07-04
verdict: REJECTED
---
rating_reimagine queue #4. Research partial .121/.126±.031 but baseline was FP-level,
never rp3. Rule-9 expectation: Ridge is linear, cannot span a product term, so this
is NOT algebraically redundant — a genuine test. Batch Bonferroni N=3.
