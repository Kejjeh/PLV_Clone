---
signal: avg_velo_last21
formula: mean fastball velocity (MPH) over last 21 days of pitches thrown, directly from rolling_pitchers_2018_2026.csv
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (higher recent velocity → more swing-and-miss → higher FP/start)
theory: RP3_FEATS already contains avg_velo_to (cumulative season-to-date) and delta_velo (last21 minus to). The level of recent velocity itself may carry information that neither captures: a pitcher whose cumulative is 94 but recently sits 92 has a negative delta — but the raw 92 (which forecasts the RoS arm) is only encoded indirectly via the delta. Adding the raw L21 level gives the model the recency anchor in absolute terms.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_avg_velo_last21.py
date: 2026-05-24
verdict: MARGINAL
purpose: rp3 v3 ceiling-audit follow-up (2026-05-24). The ceiling audit flagged that the within-season velocity trajectory is collapsed into delta_velo only. Testing whether the absolute L21 level adds incremental lift on top of the (cumulative, delta) pair.
---

# Pre-registration body

## Why this candidate
- RP3_FEATS already has `avg_velo_to` (cumulative) and `delta_velo` (last21 − to). The raw level of `avg_velo_last21` is technically a linear combination of the two, so a linear model would gain nothing — but rp3 is gradient-boosted, and non-linearity in the velocity → outcome map (e.g., 94 → 95 matters less than 92 → 93) means the absolute recency anchor may carry incremental information.
- Cited in the 2026-05-24 ceiling audit as the most natural complement to `delta_velo`.

## Rule 5 sample-size check
- Source column `avg_velo_last21` non-null on 5000/5462 rolling rows (91.5%).
- Per-year non-null easily clears the 30-floor.
- NaN rows filled with population mean to keep eval set identical between baseline and full.

## Rule 8 framing
- Production framing is in-season → RoS at split rows of 30/60/90/120 days. The L21 recency window is already used by the model elsewhere (delta_velo is built from it). Same framing as production.

## Rule 9 baseline
Full RP3_FEATS (23 features) as listed in `rp3.py`. Lift measured by adding `avg_velo_last21` to that full set.

## Rule 3 / Bonferroni
3 candidates this push (`avg_velo_last21`, `c_plus_swstr_last21`, `avg_pfxz_to`). +0.005 production gate is well above noise floor and is the binding bar regardless of Bonferroni.

## Decision rule
- PASS: lift ≥ +0.005 AND sign ≥ 5/7 years AND holdout lift > 0
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a)
- REJECTED: lift ≤ 0 OR wrong sign overall

Verdict appended after results, never pre-filled.

---

# Results

Ran `scripts/xfp/validate_avg_velo_last21.py` 2026-05-24.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 23 feats) | 0.5509 | — |
| Full cross_year r (+ avg_velo_last21, 24 feats) | 0.5510 | — |
| **Lift Δr** | **+0.0001** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 4/7 years positive | FAIL (need 5/7) |
| Holdout (2024-2025) avg lift | +0.0011 | PASS sign |

**Per-year lift:** 2018: −0.0006, 2019: −0.0007, 2021: +0.0003, 2022: −0.0005, 2023: +0.0008, 2024: +0.0020, 2025: +0.0002.

**Data:** 91.5% non-null (5000/5462); NaN filled with population mean (88.529 mph) so the baseline and full evals run on identical row sets. n=4174 pitcher-split rows in LOO eval.

## Verdict — MARGINAL

`avg_velo_last21` adds essentially nothing on top of the cumulative + delta velocity pair already in RP3_FEATS. The GBM apparently is already extracting the non-linear recency information from the (`avg_velo_to`, `delta_velo`) pair without needing the raw L21 level — which is the expected outcome given that the level is a direct linear combination of the two (`avg_velo_last21 = avg_velo_to + delta_velo`). Lift of +0.0001 is within run-to-run noise.

The 2024 +0.0020 cell is the only meaningful positive year; holdout average +0.0011 is positive-sign but trivial. Not promoted. Confirms that the velocity dimension is well-encoded by the existing (cumulative, delta) pair. Documented per Rule 6 so this is not re-explored.
