---
signal: spray_adj_xwobacon
formula: per BBE, expected wOBA from a (spray-bin x LA-band x EV-tercile) lookup fit on TRAINING years only (2018-2023 ex-2020, actual woba_value means; 6 handedness-adjusted spray bins, GB/LD/FB bands at LA 10/25, EV terciles); per (batter, year, split_day) as-of mean over BBE with game_date <= cutoff, k=40 BBE shrinkage to as-of population mean
outcome: ros_core_fp_per_pa (rh3 harness target)
expected_sign: "+"
theory: direction-aware re-valuation of contact credits legitimate pull-side power that direction-blind xwOBA misses (Wave 2A of campaign ledger; runs because the pre-declared 1A-1 benchmark rule fired)
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_spray_adj_xwobacon.py
date: 2026-07-19
verdict: REJECTED
---

## RESULT: Dr +0.0004, 4/7 years, holdout 1/2, coef WRONG sign (-0.0051). Same
## realized-ISO/HR absorber as pulled_air_rate. Direction axis CLOSED for rh3.

Single cell. Lookup fit on training years only (leakage-safe; applied frozen to
holdout). Prior after Wave 1A: LOW — the realized ISO/HR absorber that killed
pulled_air_rate applies identically; run held to honor the pre-declared conditional.
