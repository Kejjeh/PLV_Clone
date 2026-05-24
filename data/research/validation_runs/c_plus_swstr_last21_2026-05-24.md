---
signal: c_plus_swstr_last21
formula: (called strikes + whiffs) / pitches over last 21 days, directly from rolling_pitchers_2018_2026.csv (already population-shrunk version `c_plus_swstr_to_sh` is in RP3_FEATS as the cumulative variant)
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (recent CSW rate → in-season stuff/command quality → forecasts RoS K rate and FP/start)
theory: RP3_FEATS has `c_plus_swstr_to_sh` (shrunk cumulative). Recent CSW captures in-season pitch-shape / arsenal changes that the cumulative averages out. Most actionable SP "stuff is up" signal — when a pitcher adds a sweeper mid-May the cumulative drags but the L21 catches it.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_c_plus_swstr_last21.py
date: 2026-05-24
verdict: MARGINAL
purpose: rp3 v3 ceiling-audit follow-up (2026-05-24). Ceiling audit identified CSW recency as the most plausible single addition since pitch-shape change-points are the dominant in-season stuff signal.
---

# Pre-registration body

## Why this candidate
- `c_plus_swstr_to_sh` (cumulative, shrunk) is in RP3_FEATS. `delta_swstr` is also in RP3_FEATS but only tracks the whiff component (swstr) not the called-strike component.
- A raw L21 CSW figure should give the GBM access to recency on the full CSW composite, which delta_swstr only partially captures.

## Rule 5 sample-size check
- Source column `c_plus_swstr_last21` non-null on 5000/5462 rolling rows (91.5%).
- Comfortable clearance of Rule 5 floors.
- NaN rows filled with population mean.

## Rule 8 framing
- Same in-season → RoS framing as production.

## Rule 9 baseline
Full RP3_FEATS (23 features). Lift measured by adding `c_plus_swstr_last21` to the full set.

## Rule 3 / Bonferroni
3 candidates this push. +0.005 gate is binding.

## Decision rule
- PASS: lift ≥ +0.005 AND sign ≥ 5/7 years AND holdout lift > 0
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a)
- REJECTED: lift ≤ 0 OR wrong sign overall

---

# Results

Ran `scripts/xfp/validate_c_plus_swstr_last21.py` 2026-05-24.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 23 feats) | 0.5509 | — |
| Full cross_year r (+ c_plus_swstr_last21, 24 feats) | 0.5520 | — |
| **Lift Δr** | **+0.0011** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 5/7 years positive | PASS |
| Holdout (2024-2025) avg lift | −0.0008 | FAIL sign |

**Per-year lift:** 2018: +0.0044, 2019: −0.0027, 2021: +0.0002, 2022: +0.0017, 2023: +0.0038, 2024: +0.0005, 2025: −0.0021.

**Data:** 91.5% non-null (5000/5462); NaN filled with population mean (0.2808) so baseline and full ran on identical sets. n=4174.

## Verdict — MARGINAL

`c_plus_swstr_last21` shows the strongest pooled lift of the three candidates (+0.0011) and clears sign consistency (5/7) — but **does not meet the +0.005 gate** and **fails on the holdout**, where 2025 actually goes negative (−0.0021). The early-cohort years (2018, 2023) carry the positive signal; the recent two-year holdout is net-negative, which is the worst pattern for forward generalisation.

Interpretation: the cumulative `c_plus_swstr_to_sh` (in RP3_FEATS) plus `delta_swstr` (also in RP3_FEATS) appear to absorb most of the L21 CSW information. Adding the L21 level introduces a small amount of duplicative signal that helps on average but doesn't survive the holdout — likely overfitting noise in the train years that doesn't carry forward.

**Not promoted.** Documented per Rule 6. Worth revisiting if the cumulative `c_plus_swstr_to_sh` is ever broken into its components (called-strikes-only L21 might still carry orthogonal information that delta_swstr does not).
