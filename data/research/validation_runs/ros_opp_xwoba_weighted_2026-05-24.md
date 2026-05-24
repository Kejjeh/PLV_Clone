---
signal: ros_opp_xwoba_weighted
formula: For each (pitcher, year, split_day) — pitcher_primary_team's RoS games (game_date > cutoff_date), equal-weight mean of opp_team season xwOBA (estimated_woba_using_speedangle / woba_denom aggregated). Built in scripts/xfp/build_ros_schedule_features.py.
outcome: rp3 cross_year_eval Δr on RoS FP/start target (matches rp3 production)
expected_sign: -
theory: A pitcher who faces a tougher RoS schedule (higher opp xwOBA) will average lower FP/start regardless of stuff. This is the "done right" version of the home-park park-factor proxy that came back MARGINAL — it carries true RoS opponent variation (Yankees-heavy slate vs Rockies-heavy slate) orthogonal to the pitcher's own metrics.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_ros_opp_xwoba_weighted.py
date: 2026-05-24
verdict: PASS
purpose: Quantify whether explicit RoS schedule-opponent quality adds independent lift on rp3, vs being absorbed by pitcher self-metrics + IL + drift already in RP3_FEATS.
---

### Rule 5 sample-size honesty note (pre-acknowledged)

Opponent season-xwOBA is computed across full year (mild look-ahead).
For a per-pitcher RoS-weighted feature this is a deliberate v1
choice — opp identity is the variation, not opp form. v2 could
swap to to-date opp xwOBA. Feature non-null on 96% of rolling rows
across 8 seasons (5255/5462). 2026 split_day=58 has 0 RoS games
(cutoff = today) — rows filled with NaN, harness fills with year-mean.
