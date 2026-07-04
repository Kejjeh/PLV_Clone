---
signal: low_fb_reliance
formula: binary flag — prior-year fastball share (FF+SI+FC pitches / all pitches, full season T-1) < 0.48
outcome: ros_fp_per_start
expected_sign: "-"
theory: kitchen-sink secondary-reliant arms under-deliver next season at fixed FP/OVERALL (~-0.75 FP/start Q1 residual); regime-emergent 2023+.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_rating_queue_batch.py
date: 2026-07-04
verdict: REJECTED
---
rating_reimagine queue #2. Research: partial +.153/+.170 vs rp3 (n=118, 2025->26),
+.147 vs FP+OVERALL (n=353, CI [+.037,+.244]), persistence .81. CAVEAT pre-declared:
regime-emergent (2021 partial negative, monotone rise to +.175 by 2025) — the 5-of-7
year-consistency gate is EXPECTED TO FAIL on pre-2023 years; the honest question is
whether the recent-era effect survives the full baseline at all, and per-year signs
will be read with the regime lens. Bonferroni: 3 pre-registered candidates in this
batch (alpha adjusted; report raw + adjusted).
