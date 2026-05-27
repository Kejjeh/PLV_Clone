---
signal: pitch_shape_early_warning_sweep
formula: |
  Four candidate components validated as a 15-combination sweep (all non-empty subsets of {A,B,C,D}):
  A. pfxz_delta      = avg_pfxz_to (season-to-date at split_day) - prior_year_avg_pfxz (full prior season from sp_multiyr)
  B. csw_last21      = c_plus_swstr_last21 (rolling last-21-days CSW%, already in rolling_pitchers)
  C. ext_delta       = avg_ext_to (season-to-date extension) - prior_year_avg_ext (full prior season from sp_multiyr)
  D. new_pitch_flag  = 1 if pitcher has a pitch type at ≥10% usage in year T that was <5% in year T-1 (from Statcast parquets), else 0
outcome: ros_fp_per_start
expected_sign: +
theory: Pitch-shape improvements observable within the first 3-6 starts (vert rise, extension gain, CSW spike, new pitch) predict above-baseline RoS FP/start because they reflect physical-skill changes that a history-weighted model underweights until ERA stabilizes.
production_target: rp3
framing: in-season → ros
holdout_years_A: [2024, 2025]
holdout_years_B: [2025, 2026]
training_years_A: [2018, 2019, 2021, 2022, 2023]
training_years_B: [2018, 2019, 2021, 2022, 2023, 2024]
bonferroni_cells: 30
bonferroni_adjusted_partial_r_bar: 0.22
validation_script: scripts/xfp/validate_pitch_shape_early_warning.py
date: 2026-05-27
verdict: REJECTED
---

## Sweep structure

| Combo | Signals |
|---|---|
| A | pfxz_delta only |
| B | csw_last21 only |
| C | ext_delta only |
| D | new_pitch_flag only |
| AB | pfxz_delta + csw_last21 |
| AC | pfxz_delta + ext_delta |
| AD | pfxz_delta + new_pitch_flag |
| BC | csw_last21 + ext_delta |
| BD | csw_last21 + new_pitch_flag |
| CD | ext_delta + new_pitch_flag |
| ABC | pfxz_delta + csw_last21 + ext_delta |
| ABD | pfxz_delta + csw_last21 + new_pitch_flag |
| ACD | pfxz_delta + ext_delta + new_pitch_flag |
| BCD | csw_last21 + ext_delta + new_pitch_flag |
| ABCD | all four |

Each combo tested against both holdout configs = 30 cells total.

## Data-coverage pre-check (Step 2.5)

- pfxz_delta: avg_pfxz_to is in rolling_pitchers_2018_2026.csv (2018+). Prior-year avg_pfxz in sp_multiyr_2015_2025.csv (2015+). Delta requires ≥2 consecutive years → training eligible from 2019 onward. All 5 training-A years and 6 training-B years have prior-year data. **PASS.**
- csw_last21: c_plus_swstr_last21 directly in rolling_pitchers_2018_2026.csv. No delta required. All 7 training years covered. **PASS.**
- ext_delta: avg_ext in sp_multiyr (2015+). Season-to-date avg_ext computed from Statcast (2015+). Delta same as pfxz_delta coverage. **PASS.**
- new_pitch_flag: requires 2 consecutive years of Statcast pitch-type data (2015+). Training eligible from 2019. **PASS.**

Rule 5 sample-size: rolling_pitchers has 5,462 rows across 2018-2026 (avg ~780/year). N ≥ 30 per year easily met. Pooled N across 5 training-A years ≈ 3,900, well above 200 minimum.

## Rule 9 baseline

Full RP3_FEATS (24 features):
k_pct_to_sh, bb_pct_to_sh, swstr_pct_to_sh, c_plus_swstr_to_sh, xwoba_per_pa_to_sh,
zone_pct_to_sh, z_swing_pct_to_sh, o_swing_pct_to_sh, avg_velo_to, fp_per_start_to,
gs_to, prior_fp_per_start, prior_gs_eff, is_on_il_at_split, days_since_il_return_imp,
il_stints_to, split_day, delta_velo, delta_swstr, delta_k_pct, delta_bb_pct,
delta_chase, delta_zone, ros_opp_xwoba_weighted

Note: delta_velo, delta_swstr, delta_k_pct etc. are ALREADY in the baseline as in-season rolling deltas
(current season rate minus prior year). The candidate signals test whether pitch-SHAPE deltas
(pfxz, extension) and discrete signals (CSW spike, new pitch) add lift beyond this existing delta layer.

## Overlap note

csw_last21 (signal B) is conceptually related to c_plus_swstr_to_sh (baseline) but captures
RECENT form rather than season-average. The baseline uses shrunk season-to-date CSW;
csw_last21 is raw recent-window. These are not algebraically redundant — one can be rising
while the other is stable, which is the signal of interest.

## Convergence curve

Per Rule 8 (in-season framing), run at split_day cutoffs: 30, 42, 56, 70, 84 (approximately
weeks 4, 6, 8, 10, 12). Report coefficient sign stability across cutoffs for any combo
that passes the main gate.

**Not run — 0/30 cells passed the main gate.**

## Results (2026-05-27)

Baseline cv_r = 0.5515 (holdout_A), 0.5503 (holdout_B). Trained against full 24-feature RP3_FEATS.

| combo | holdout | cv_lift | ho_lift | signs |
|---|---|---|---|---|
| B (csw_last21) | A | +0.0022 | −0.0027 | 5/5 |
| B (csw_last21) | B | +0.0015 | −0.0008 | 6/6 |
| AB | A | +0.0022 | −0.0034 | 5/5 |
| AB | B | +0.0012 | −0.0003 | 6/6 |
| BCD | A | +0.0033 | −0.0051 | 3/5 |
| BCD | B | +0.0029 | −0.0075 | 4/6 |
| A (pfxz_delta) | A | −0.0013 | −0.0008 | 5/5 |
| A (pfxz_delta) | B | −0.0011 | +0.0001 | 6/6 |

**Summary:** 0/30 cells pass. Best cv_lift = +0.0033 (BCD, holdout_A). **Every holdout lift is negative** except for two near-zero cases (D/holdout_A: +0.0004; ABC/holdout_B: +0.0009). The small training-set gains are overfitting noise — these signals add nothing that the existing RP3_FEATS delta layer (delta_velo, delta_swstr, delta_k_pct, c_plus_swstr_to_sh) does not already capture.

**Root cause:** The model already ingests the downstream performance signals (CSW%, strikeout rate, swinging-strike rate changes) that pitch-shape signals predict. Adding pitch-shape deltas upstream is redundant — any info in pfxz_delta that matters for RoS FP/start is already proxied by delta_swstr; any info in csw_last21 is already proxied by c_plus_swstr_to_sh + delta_swstr. The PL lead-time we observed in roundups operates through human evaluation of novel pitch shapes, not through a measurable FP/start lift in historical data once the full feature set is controlled for.

## Registry entry

```
### pitch_shape_early_warning_sweep — REJECTED (2026-05-27)
- **Standalone validation:** scripts/xfp/validate_pitch_shape_early_warning.py
  30-cell sweep (15 combos × 2 holdout configs). Baseline cv_r = 0.5515 (holdout_A),
  0.5503 (holdout_B). Best cv_lift = +0.0033 (BCD, holdout_A). No combo reaches +0.005.
- **Holdout:** ALL 30 holdout lifts are negative or zero. Comprehensive reversal confirms
  training gains are overfitting, not signal.
- **Per-year (B, holdout_A):** 2018:+ 2019:+ 2021:+ 2022:+ 2023:+ (sign-consistent
  but lift far below bar)
- **Framing tested:** in-season → ros
- **Convergence curve:** not run (no combo passed main gate)
- **Bonferroni context:** 30 cells tested; 0 passed at adjusted bar (partial r ≥ 0.22,
  cv_lift ≥ +0.005, holdout positive)
- **Root cause:** RP3_FEATS already contains delta_swstr, delta_k_pct, c_plus_swstr_to_sh
  which are the downstream manifestations of pitch-shape changes. Pitch-shape deltas
  (pfxz, extension) and discrete flags (new pitch, CSW window) add no residual lift.
- **Components:**
  - A (pfxz_delta): avg_pfxz_to − prior_year_avg_pfxz (sp_multiyr)
  - B (csw_last21): c_plus_swstr_last21 from rolling_pitchers
  - C (ext_delta): avg_ext_szn − prior_year_avg_ext (Statcast parquets + sp_multiyr)
  - D (new_pitch_flag): 1 if pitch type ≥10% in year T was <5% in year T-1
- **Status:** REJECTED — holdout reversal + cv_lift below bar in all 30 cells
```
