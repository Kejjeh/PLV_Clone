---
signal: sprint_speed_lag1 (RE-TEST under corrected target)
formula: player's prior-year (T-1) Savant season sprint speed; missing -> population mean (same construction as the 2026-07-09 original run)
outcome: ros_full_fp_per_pa (rh3 target, AS CORRECTED by sb_target_fix_2026-07-10 — SB points now included via (mlb_r+mlb_rbi+mlb_sb)/mlb_pa allocation)
expected_sign: +
theory: >
  The 2026-07-09 REJECTED verdict was earned against a target that omitted
  the SB scoring term entirely (bug: sb_target_fix_2026-07-10). Sprint speed
  showed emphatic component signal (partial r +0.499 on RoS SB/PA beyond
  sb_per_pa_to_sh + prior) but zero composite lift — unsurprising when the
  composite paid nothing for steals. Post-fix, the target carries SB points
  AND the model has NO live SB feature (sb_per_pa_to_sh remains a dead-zero
  column pending an as-of source; the Marcel prior carries SB only at the
  blended-FP level). Prior-year sprint speed is therefore the best available
  leakage-safe SB-skill proxy. Re-test justified by a material, documented
  target correction — not by result-shopping.
production_target: rh3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_sprint_speed_lag1.py (unchanged from the original run; reads the regenerated rolling cache)
date: 2026-07-10
multiple_look_caveat: >
  Second look at the same cells + same holdout window. The look is justified
  by a target BUG FIX (the first test was against a mis-specified outcome),
  but we acknowledge the reuse of holdout 2024-2025: treat a bare-gate pass
  (+0.005 to +0.007) with caution; a clear pass (>= +0.008 with 6/7 signs)
  is actionable. Only the lag1 cell is re-tested (delta cell died on wrong
  sign, not on the target bug — stays rejected).
gates: cross_year_r lift >= +0.005 vs FULL 21-feature RH3_FEATS (on the corrected target), sign consistency >= 5/7 years, holdout 2024-2025 positive, coefficient sign +.
---

# RESULTS (appended after run)

## RESULTS (2026-07-10, post-SB-fix target)

| cell | baseline r | +cand r | lift (gate +0.005) | signs | holdout 24/25 | coef | verdict |
|---|---|---|---|---|---|---|---|
| sprint_speed_lag1 | 0.6275 | 0.6310 | **+0.0035** | 6/7 | 1/2 | +0.0110 (+) OK | **MARGINAL** |
| sprint_speed_delta | 0.6275 | 0.6270 | −0.0005 | 1/7 | 0/2 | wrong sign | REJECTED (unchanged) |

The target correction moved lag1 from a hard zero (−0.0004 on 2026-07-09)
to +0.0035 with clean year signs — the mechanism is real and now partially
expressed in the composite — but it remains under the gate and fails the
pre-registered clear-pass bar (≥ +0.008) required for a second look at the
same holdout. NOT promoted. Status: strongest known bench candidate for
rh3; re-test conditions: (a) a leakage-safe as-of SB source materializes
(making sb_per_pa_to_sh live — then test sprint_speed as its complement),
or (b) TRAIN_YEARS grows a year (fresh holdout, 2026 complete).

verdict: MARGINAL
