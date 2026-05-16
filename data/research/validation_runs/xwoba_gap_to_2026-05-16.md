---
signal: xwoba_gap_to
formula: xwoba_on_contact_to − (woba_v_sum_to / woba_d_sum_to)  [season-to-date within-year]
outcome: fp_per_pa_actual rest-of-season (within-year, post-Aug-01 cutoff)
expected_sign: +
theory: Positive gap (xwOBA exceeds actual wOBA) = unlucky on contact, regresses upward in remaining PAs.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_xwoba_gap_to.py
date: 2026-05-16
purpose: Skill sanity-check — re-run a feature that is already LIVE in rh3 v2 and confirm the new skill produces the +0.0016 number documented in the registry against the FULL production baseline (not the inflated +0.006 from the original curated backtest).
---
