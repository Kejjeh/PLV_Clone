---
signal: prior_k_per_start
formula: prior-year realized K per start (multiyr k / gs, year T-1), season-constant
outcome: ros_fp_per_start
expected_sign: +
theory: K-sourced FP repeats (r .590 YoY) while IP-sourced FP mean-reverts; the composition of prior FP should refine the Marcel prior.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_rating_queue_batch.py
date: 2026-07-04
verdict: MARGINAL
---
rating_reimagine queue #5. Pre-declared expectation: REJECTED for rp3 — research
already measured in-season beyond-rp3 at -.08; k_pct_to_sh + prior_fp_per_start
likely span it. Run to close the loop and log (Rule 6). Batch Bonferroni N=3.
