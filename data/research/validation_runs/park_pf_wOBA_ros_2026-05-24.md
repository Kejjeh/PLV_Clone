---
signal: park_pf_wOBA_ros
formula: park_pf_wOBA_ros[batter, year] = pf_wOBA[year, hitter_home_team] from park_factors_2018_2026.csv (v1 simplification: hitter HOME-park pf, not RoS-schedule-weighted)
outcome: rh3 cross_year_eval Δr on RoS FP/PA target (matches rh3 production)
expected_sign: +
theory: Hitter-friendly home parks inflate ~half a player's PAs. Park is orthogonal to every feature in RH3_FEATS (skill rates, lineup spot, career stage, IL). Even a coarse hitter-home-park join should add lift if park has any predictive value.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_park_pf_wOBA_ros.py
date: 2026-05-24
verdict: MARGINAL
purpose: Park factors are theoretically the strongest out-of-family signal not in RH3_FEATS. Even if the v1 home-park-only simplification under-states the true RoS-schedule effect, a positive Δr would justify investment in a full RoS-schedule-weighted exposure pipeline.
---

### Rule 5 sample-size honesty note (pre-acknowledged)

Park factors are computed per-year from full statcast (~180k PAs/year),
so the source signal is not sample-limited. The join is per (batter,
year) using the hitter's primary team from hitters_multiyr — every
batter-year has a team, so coverage is ~100% of rolling rows.

### v1 simplification (pre-acknowledged)

The "park exposure" feature here is the hitter's HOME park factor, not
a 50/50 home/away blend or a true RoS-schedule weighting. This is a
1st-order proxy: a Colorado hitter's true park exposure is roughly
(0.5 * COL + 0.5 * mean(NL West away parks)), not 1.0 * COL. So:
  - Magnitude of any lift here UNDER-states the true RoS-park signal
  - Direction (sign) is preserved
  - A negative/null result here is informative: if even the most
    park-amplified subgroup (Coors, GABP) can't move Δr, full RoS
    weighting is unlikely to either.
