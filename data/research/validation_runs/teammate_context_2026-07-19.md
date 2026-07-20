---
signal: teammate_context
formula: per (batter, year, split_day) over the batter's STARTED games with game_date <= cutoff — rbi_context = mean as-of shrunk wOBA/PA (k=60 PA) of the teammates in the 2 lineup spots ahead (wrapping 9→1); r_context = mean as-of shrunk ISO (k=60 AB, from statcast events) of the teammates in the 3 spots behind (wrapping); teammate rates evaluated as-of the same cutoff
outcome: ros_core_fp_per_pa (rh3 harness target)
expected_sign: "+"
theory: R and RBI are structurally team-dependent; the on-base skill ahead and power behind set the RoS conversion ceiling for the counting-stat share of FP, independent of the batter's own rates and own lineup spot
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_teammate_context.py
date: 2026-07-19
verdict: MARGINAL
---

## RESULT (2026-07-19): campaign's best cells, both MARGINAL
- rbi_context: Dr +0.0023, 4/7 years, holdout 1/2, coef + OK.
- r_context:   Dr +0.0027, 5/7 years (passes 2b), holdout 1/2, coef + OK.
- Below the +0.005 gate (family a/2); NOT promoted. First genuinely orthogonal axis
  found by the campaign (own-team spillover), just thin. Legit pre-committable
  re-attempt: joint rbi+r cell on completed-2026 as virgin holdout (~Nov 2026).
- Match rate 97.7% on the rolling grid; teammate rates as-of same cutoff.

## Cells (campaign ledger 2B-1/2B-2; family α/2)

`rbi_context` and `r_context`, each vs full RH3_FEATS. Pre-declared absorption risk:
lineup-spot features + the batter's own realized FP level (which contains R+RBI
to date, and thus his team context to date) may span it; MARGINAL is a live outcome.
Data: hitter_lineup_appearances_{yr}.parquet (started_game rows) + statcast as-of
teammate rates; team per (game, batter) from statcast batting side.
