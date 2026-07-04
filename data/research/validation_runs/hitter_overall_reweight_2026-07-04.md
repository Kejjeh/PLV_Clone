---
signal: hitter_overall_reweight
formula: 0.58*CONTACT + 0.17*POWER + 0.17*SB + 0.08*DISCIPLINE
outcome: T+1 fp_per_pa (annual, research)
expected_sign: +
theory: shipped OVERALL weights describe skill, not FP value (fwd .477 < FP-carry .510); refit weights reach .515 (pillar) / .548 (subs).
production_target: research-only
framing: full-year
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: (research: rating_reimagine angle 1; shipped as display OVERALL_FP)
date: 2026-07-04
verdict: RESEARCH-ONLY
---
Queue #7 disposition: SHIPPED as the hitter OVERALL_FP display column
(2026-07-04). In-season null vs rh3 pre-declared (partial -.041) — never an
rh3 candidate. Sub-level variant (.548, drops CONTACT_QUALITY/SPRAY at the
margin) is a future display enhancement, not queued for production.
