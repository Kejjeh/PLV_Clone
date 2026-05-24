---
signal: park_pf_HR_ros
formula: park_pf_HR_ros[pitcher, year] = pf_HR[year, pitcher_primary_team] from park_factors_2018_2026.csv (v1 simplification: SP HOME-park pf, not RoS-schedule-weighted). pitcher_primary_team derived per (pitcher, year) from statcast modal pitcher_team.
outcome: rp3 cross_year_eval Δr on RoS FP/start target (matches rp3 production)
expected_sign: -
theory: HR-friendly home parks inflate ~half a SP's start environments, costing 2*ER + H on each HR. Park is orthogonal to every feature in RP3_FEATS (stuff metrics, command, drift, IL). Coors/GABP/Yankee Stadium SPs should systematically under-perform their stuff-implied FP/start.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_park_pf_HR_ros.py
date: 2026-05-24
verdict: MARGINAL
purpose: Park factors are theoretically the strongest out-of-family signal not in RP3_FEATS. Coors-pitcher penalty is well-known qualitatively; this is the quantitative test of whether RP3's current features have already absorbed it via opponent-quality / xwOBA proxies, or whether explicit park exposure adds lift.
---

### Rule 5 sample-size honesty note (pre-acknowledged)

Park factors are computed per-year from ~180k PAs / year. Pitcher
primary-team-year is derived from statcast (~modal home team while
pitching). Coverage: ~100% of rolling rows that correspond to MLB
SPs in that year.

### v1 simplification (pre-acknowledged)

Uses pitcher's primary HOME park pf_HR, not a half-and-half blend or
true RoS rotation slot weighting. Magnitude UNDER-states true effect;
sign preserved.
