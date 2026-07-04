---
signal: april_prior_process_anchor
formula: prior-year full-season velo/SwStr/K-BB process composite as the early-season SP process read (vs in-season-to-date)
outcome: ros_fp_per_start from April cutoffs
expected_sign: +
theory: prior-year process beats in-season process at every cutoff through mid-June (r25 .577 vs r26 .491 at 4/25, no crossover); April bridge partial +.368 vs FP-to-date.
production_target: rp3
framing: in-season → ros
holdout_years: [2026]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: (scheduled — requires an APRIL logged rp3 snapshot)
date: 2026-07-04
verdict: RESEARCH-ONLY
---
Queue #8 disposition: DEFERRED to April 2027 by data constraint — the Rule-9
test needs a same-date APRIL rp3 snapshot, and the snapshot logger
(build_player_projection_history, refresh step 4.10) only went live 2026-06.
Re-run 2027-04 with logged snapshots. Until then: research-only.
