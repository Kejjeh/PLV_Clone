---
signal: rp_role_first_rating
formula: 0.55*z(SV) + 0.35*STUFF + 0.10*z(FP/g) within year (display composite)
outcome: next-year RP fp_per_g (research); display layer
expected_sign: +
theory: predictable RP FP is role, not run prevention (role r .649 vs skill .248); CONTROL/BATTED_BALL fwd ~0; holds anti-signal.
production_target: research-only
framing: full-year
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: (research: rating_reimagine angle 4; shipped as display OVERALL_FP)
date: 2026-07-04
verdict: RESEARCH-ONLY
---
Queue #6 disposition: SHIPPED as the RP OVERALL_FP display column (2026-07-04).
Model-side companion (sv_pre beyond rprs2, +.175 p=.054 n=123) DEFERRED by
pre-registration until the post-6/06 logged-snapshot sample roughly doubles
(~early August 2026). Not eligible for rprs2 until that re-run.
