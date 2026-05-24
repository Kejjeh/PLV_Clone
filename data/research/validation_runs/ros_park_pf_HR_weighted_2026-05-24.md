---
signal: ros_park_pf_HR_weighted
formula: For each (pitcher, year, split_day) — pitcher_primary_team's RoS games, equal-weight mean of venue (home-team) pf_HR from park_factors_2018_2026.csv. Half home, half away — captures the true ~50/50 venue mix the pitcher will pitch in. Built in scripts/xfp/build_ros_schedule_features.py.
outcome: rp3 cross_year_eval Δr on RoS FP/start target (matches rp3 production)
expected_sign: -
theory: park_pf_HR_ros v1 used home-park-only and came back MARGINAL (+0.0017, holdout fail). This RoS-weighted version captures the actual venue mix a pitcher will see — a Rockies SP travels to neutral parks ~half the time, so home-only over-states their park penalty; a Yankee SP visits Fenway/Wrigley which the home-only proxy ignores. Done-right version.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_ros_park_pf_HR_weighted.py
date: 2026-05-24
verdict: MARGINAL
purpose: Test whether the RoS-weighted venue mix (vs home-park-only proxy) recovers the park signal that came back MARGINAL in v1.
---

### Rule 5 sample-size honesty note (pre-acknowledged)

Per-year park factors are stable at ~180k PAs / year. Feature
non-null on 96% of rolling rows (5255/5462). 2026 sd=58 has 0
RoS games (cutoff = today) — filled with neutral 1.00 in harness.
