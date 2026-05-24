---
signal: rp3_schedule_strength_bundle
formula: Joint addition of [ros_opp_xwoba_weighted, ros_park_pf_HR_weighted] to RP3_FEATS in a single Ridge fit. Compare Δr vs sum-of-marginal Δr from each individual candidate.
outcome: rp3 cross_year_eval Δr on RoS FP/start target
expected_sign: both negative (more hostile opp / venue → fewer FP)
theory: Opponent quality and park venue are conceptually independent (opp = lineup talent; venue = HR-friendliness). Bundle should give close-to-additive lift, not redundancy. If bundle Δr ≈ sum-of-marginals → both carry independent info; if bundle Δr ≪ sum → they're proxying for each other (good schedules tend to also be in good parks).
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_rp3_schedule_strength_bundle.py
date: 2026-05-24
verdict: PASS
purpose: Decide whether to promote both or only the stronger one — Rule 9 baseline-honest joint fit answers it.
---

### Rule 5 sample-size honesty note (pre-acknowledged)

Both inputs share the same data layer (96% non-null coverage,
2018-2026). Bundle test inherits that coverage.
