---
signal: spin-rate / spin-axis decline (SP decline-risk board)
outcome: ros_fp_per_start (BrownU FP/start over post-cutoff starts)
verdict: NULL — spin decline is redundant with / weaker than overall-velo decline
date: 2026-06-13
script: scripts/_oneoff/spin_decline_study.py
---

# Spin-rate / spin-axis decline vs overall-velo decline — leakage-safe OOS study

## Question / theory

Post-sticky-stuff era (2021 crackdown onward), spin decline is hypothesized to LEAD velo decline as an earlier stuff-erosion / injury signal. We test whether ANY spin construct adds OOS decline-prediction signal OVER our existing overall-velo YoY flag. THE BAR: a construct wins only if it beats partial-r over BOTH (a) level+FP and (b) level+FP+overall-velo-YoY, at adequate n (>=2000).

## Methods

- Panel `rolling_pitchers_2018_2026.csv`; gate gs_to>=5 & ros_gs>=3; years [2021, 2022, 2023, 2024, 2025]; cutoffs split_day [51, 72, 93, 114] (~4/season). Gated rows: 2897.
- Leakage-safe AS-OF: all spin/velo aggregates use only pitches with `game_date < cutoff_date`; per-type min 30 as-of / 50 prior-year pitches.
- YoY delta = as-of construct minus PRIOR full-season construct (per pitcher).
- Spin-axis shift = circular distance in degrees (wraparound handled via atan2 circular mean + min(d, 360-d)); NEGATED so 'less shift' aligns +r.
- Bauer units = release_spin_rate / release_speed (FB group).
- spin x velo interaction = z(fb_spin_yoy) * z(velo_yoy); min-z = worse-of-the-two standardized drop.
- Baseline (Rule 9): level = rank(swstr_pct_to)+rank(k_pct_to); fp_base = fp_per_start_to.
- Bar 1 = partial-r over [level, fp_base]; Bar 2 (THE bar) ALSO controls overall-velo YoY.
- Bust gap = bust-rate(worst-decline tercile) - bust-rate(best tercile); bust = bottom-tercile ros_fp within (year,split_day).
- Sign: +partial-r => higher spin (less decline) -> higher fwd FP (decline is bad). +bust gap => declining tercile busts more.

## Partial-r table

| Construct | r over level+FP | r ALSO over velo-YoY | bust gap | corr w/ velo-YoY | n | verdict |
|---|---|---|---|---|---|---|
| FB-group spin YoY (FF/SI/FC) | 0.031 | 0.009 | 0.046 | 0.234 | 2539 | NULL |
| FF spin YoY | 0.047 | 0.024 | 0.059 | 0.285 | 2290 | NULL |
| SI spin YoY | 0.004 | -0.038 | 0.004 | 0.294 | 1473 | REJECT-coverage |
| SL spin YoY | -0.004 | -0.022 | 0.023 | 0.171 | 1414 | REJECT-coverage |
| CU spin YoY | 0.069 | 0.051 | -0.031 | 0.196 | 1242 | REJECT-coverage |
| Breaking-group spin YoY (SL/CU/ST..) | 0.033 | 0.015 | 0.016 | 0.191 | 2438 | NULL |
| FB spin in-season drop vs peak | -0.010 | 0.009 | 0.003 | 0.007 | 2601 | NULL |
| FF spin-axis shift YoY (circular) | 0.008 | 0.008 | 0.013 | -0.008 | 2290 | NULL |
| FB Bauer-units (spin/velo) YoY | -0.004 | 0.002 | -0.030 | -0.053 | 2539 | NULL |
| spin x velo interaction (z*z) | -0.064 | -0.055 | -0.004 | -0.090 | 2539 | NULL |
| spin/velo worse-of-two drop (min z) | 0.078 | 0.016 | 0.106 | 0.694 | 2539 | NULL |
| [REF] Overall velo YoY | 0.105 | n/a | 0.107 | 1.000 | 2601 | reference |

Feature rows: **2897**. Reference overall-velo YoY partial-r over level+FP = **0.105**.

## Verdict

**NULL — SPIN DECLINE IS REDUNDANT WITH / WEAKER THAN OVERALL-VELO DECLINE.**

Key reads (auto-generated):
- **CU spin YoY**: raw r 0.069 (vs velo 0.105), marginal-over-velo 0.051, corr-with-velo 0.196, n=1242 -> REJECT-coverage.
- **FF spin YoY**: raw r 0.047 (vs velo 0.105), marginal-over-velo 0.024, corr-with-velo 0.285, n=2290 -> NULL.
- **spin/velo worse-of-two drop (min z)**: raw r 0.078 (vs velo 0.105), marginal-over-velo 0.016, corr-with-velo 0.694, n=2539 -> NULL.
- **Breaking-group spin YoY (SL/CU/ST..)**: raw r 0.033 (vs velo 0.105), marginal-over-velo 0.015, corr-with-velo 0.191, n=2438 -> NULL.

### Honesty notes
- A spin construct that is highly correlated with velo-YoY (corr_w_velo near +1) and whose marginal-over-velo partial-r collapses is COLLINEAR / redundant, not a new signal.
- Per-type spin (FF/SI/SL/CU) and prior-year-dependent constructs lose coverage (per-type + prior-year pitch gates); judge them at their n, not the headline n.
- Wins require beating BOTH bars at n>=2000 (team lens rule). Coverage-limited slices that pass on n<2000 are rejected as self-selected subsets, not roster-wide flags.
