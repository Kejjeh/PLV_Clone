---
signal: vaa_ff_prior
formula: prior_year(vaa_ff) — vertical approach angle (degrees) of the pitcher's four-seam fastball at the plate, averaged across the prior season; from sp_statcast_features_2015_2025.csv shifted forward by 1 year. NEGATIVE values (more negative = steeper descent from above the zone).
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (LESS-steep VAA, i.e. value closer to zero / less negative, indicates a "flat" fastball that gets whiffs up in the zone). Distribution is roughly -7° to -3°; pitchers with VAA closer to -4° (Spencer Strider archetype) historically have elite K%.
theory: Vertical Approach Angle is the Pitcher List / Driveline-validated "flat fastball" effect — a pitcher whose fastball reaches the plate with a less-steep descent (VAA closer to 0) gets more swings-and-misses up in the zone because it crosses the line of sight late. Not in RP3_FEATS today. Conceptually independent of raw velocity and spin (encoded in different existing features).
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_vaa_ff_prior.py
date: 2026-05-23
verdict: REJECTED
purpose: rp3 v3 research — re-fill the v2_added slot vacated when the 6 SP-drift features were demoted (joint lift +0.0015, below +0.005 gate). Tests whether VAA captures fastball quality the current `avg_velo_to` feature misses.
---

# Pre-registration body

## Why this candidate
- Listed in the rp3 v3 research brief under "Vertical Approach Angle (VAA) — steeper = more whiffs, especially up in zone." (Note: brief says "steeper = more whiffs" but the literature actually has it the OPPOSITE — FLATTER VAA, i.e. LESS negative, drives whiff% on high fastballs. The expected_sign here reflects the literature, not the brief paraphrase.)
- Already cached in `sp_statcast_features_2015_2025.csv` as `vaa_ff` for ALL years 2015-2026 with 98% non-null coverage (9092/9279).
- Distribution: mean -5.67°, std 0.73°, range [-10.28, -3.02]. Real variation, no truncation.
- Current RP3_FEATS captures fastball velocity but NOT fastball pitch-shape / approach angle.

## Rule 5 sample-size check (pre-acknowledged)
- Source data: 2015-2026 cached, prior-year join clears all training years.
- Per-year eligible n ≈ 130-180 ≫ 30 ✓
- Pooled n ≈ 1000+ ≫ 200 ✓
- Holdout 2024-2025 n ≈ 300 ≫ 100 ✓

## Rule 8 framing
- Production is in-season → RoS. This is a prior-year feature, structurally constant within season.
- Per the deep pitch-shape audit (2026-05-13), pitch-shape features that pass full-year framing fail in-season framing due to coef sign flips. **Critical distinction**: that test used CURRENT-season pitch-shape on partial-season data. THIS test uses PRIOR-YEAR pitch-shape as a stable input. The framing-mismatch failure mode does not apply — a prior-year value is not subject to early-season small-sample sign flips because it doesn't change within season.

## Rule 9 baseline
Full RP3_FEATS (23 features) — all current production inputs. Per the rh3/rp3 v2 audit, stripped-down baselines over-claim lift by 4×.

## Rule 3 / Bonferroni
Joint candidate set: {avg_ext_prior, pitch_entropy_prior, vaa_ff_prior}. Per-cell α=0.0167 if Bonferroni-adjusted; the +0.005 effect-size gate is well above noise floor.

## Decision rule
- PASS: lift ≥ +0.005 AND sign consistent ≥ 5 of 7 years AND holdout lift > 0.
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a).
- REJECTED: lift ≤ 0 OR wrong sign on coefficient.

verdict will be appended after results, never pre-filled.

---

# Results

Ran `scripts/xfp/validate_vaa_ff_prior.py` 2026-05-23.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 23 feats) | 0.5509 | — |
| Full cross_year r (+ vaa_ff_prior, 24 feats) | 0.5520 | — |
| **Lift Δr** | **+0.0011** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 4/7 years positive | **FAIL** (need ≥ 5) |
| Holdout (2024-2025) avg lift | +0.0030 | PASS sign |

**Per-year lift:** 2018: +0.0072, 2019: +0.0010, 2021: -0.0002, 2022: +0.0054, 2023: -0.0165, 2024: +0.0093, 2025: -0.0032.

**Data:** 87.1% coverage (4753/5459 rolling rows had prior-year `vaa_ff`). NaN filled with population mean (-5.694°). Per-year non-null counts 612-661 ≫ Rule 5 floor. n=4174 pitcher-split rows in eval.

## Verdict — REJECTED

VAA fails on BOTH (a) effect size and (b) sign consistency. The pooled +0.0011 lift is below the +0.005 gate, and the 2023 year has an unusually large *negative* lift (-0.0165) that dragged down the pooled result. Only 4 of 7 training years are positive — below the 5/7 threshold even on the loose check.

The holdout window (2024-2025) average lift IS positive at +0.0030, which is at least encouraging directional evidence, but a single passing gate out of three is not enough.

The VAA literature describes a real biomechanical effect — flat fastballs *do* get whiffs up. The interpretation here is most likely: by the time you condition on `avg_velo_to`, `swstr_pct_to_sh`, and `c_plus_swstr_to_sh` (which encode the whiffs the flat-fastball is producing), the VAA itself becomes redundant. The model doesn't need to know HOW the whiffs happen — it can see the whiffs themselves. VAA may add value to a much earlier-season projection (e.g., week 4 cutoff where in-season rates are still noisy), but our production framing is RoS at established cutoffs where the rate features have stabilised.

**Not promoted to RP3_FEATS. Permanently rejected for rp3 as a prior-year scalar.** Documented per Rule 6.

Could potentially be revisited as part of a CURRENT-season pitch-shape vector if combined with extension and velocity — but the 2026-05-13 deep-pitch-shape audit established that in-season pitch-shape features fail framing-stability, so this is a low-priority direction.
