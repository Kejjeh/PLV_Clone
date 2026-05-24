---
signal: milb_aaa_iso_prior
formula: mean ISO across all AAA stints in the PRIOR season (year-1) per batter, min 50 PA at AAA to qualify. NaN-filled with training-year population median computed on rows that had a prior-year AAA stint.
outcome: ros_fp_per_pa (rh3 production target)
expected_sign: positive (more raw power at AAA → more power once promoted → higher RoS FP/PA, via TB/HR contribution)
theory: rh3 has zero MLB-substrate signal on callups (cumulative rates are NaN-filled with priors). Bringing in prior-year AAA performance is the natural OUT-OF-FAMILY signal — it's information that literally cannot be derived from MLB-only Statcast. Even for veterans who did a brief AAA rehab stint in year-1, the marginal information is plausibly nonzero.
production_target: rh3
framing: in-season → ros (matches rh3 cross_year_eval at all split_days)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_milb_aaa_iso_prior.py
data_layer_script: scripts/xfp/build_milb_aaa_priors.py
date: 2026-05-24
verdict: REJECTED
purpose: First test of the MiLB data layer for hitter callups. Hypothesis is that rh3 v3 has untapped lift on the ~28% of rolling rows that have a prior-year AAA stint.
---

# Pre-registration body

## Why this candidate

rh3's RH3_FEATS are all MLB-substrate rates (iso_to_sh, k_pct_to_sh, etc.). For a fresh callup with no MLB PA, every shrunken rate is just the population prior — so the model has effectively no batter-specific signal. The Marcel prior (`prior_fp_per_pa`) covers veterans with multi-year MLB history but is zero for true rookies.

Prior-year AAA ISO is the most natural "power level coming in" signal. If it carries any independent lift on top of the (now slowly-accumulating) MLB rates plus the Marcel prior, that's evidence the data layer is worth building out further (xwOBA via Statcast MiLB, multi-year AAA, AA cross-check, etc.).

## Rule 5 sample-size check

- AAA leaderboard from MLB Stats API covers 2015-2026. Prior-year join is well-populated for MLB years 2018, 2019, 2022, 2023, 2024, 2025, 2026.
- **2021 MLB rows get ZERO prior-year coverage because the 2020 MiLB season was cancelled (COVID)**. This is a real data gap. Those rows fall back to the population-median NaN-fill, contributing essentially noise to the 2021 LOO fold.
- Median PA-prior across rows with a prior stint = 229 PA — well above the 50 PA min filter floor.
- Coverage: 4,448 / 15,939 rolling rows (~28%) have a real prior-year AAA stint. The remaining 72% (mostly established MLB regulars) get the population-median fill and behave identically between baseline and extended.

## Rule 5 honesty note (AAA Statcast)

This test uses MLB Stats API counting-stat-derived ISO, **not** Baseball Savant AAA Statcast xwOBA. The xwOBA flavor would be the stronger candidate (it's how rh3 already treats MLB) but would require a separate `pybaseball.statcast_minor_league_batter` pull and is bounded to 2021+. Treating this run as an inexpensive first probe; if either of these counting-stat candidates clears, the xwOBA pull is justified.

## Rule 8 framing

In-season → RoS, all split_days (30/60/90/120). Identical framing to the rh3 production cross_year_eval. The candidate value itself is fully pre-season-known (no leakage of in-season AAA data into the prediction).

## Rule 9 baseline

Full RH3_FEATS (18 features as currently in `rh3.py`: 13 cumulative shrunken rates + 4 prior/sample features + lift_h2_aug150 + xwoba_residual_career + career_stage). Extended = baseline + `milb_aaa_iso_prior`.

## Rule 3 / Bonferroni

Two candidates in this push (`milb_aaa_iso_prior`, `milb_aaa_kpct_prior`). The +0.005 production gate is well above any noise floor and is the binding bar regardless of Bonferroni.

## Decision rule

- **PASS**: Δr ≥ +0.005 AND ≥5/7 years positive AND coef sign matches expected
- **MARGINAL**: 0 < Δr < +0.005 OR (Δr ≥ +0.005 but one of the other gates fails)
- **REJECTED**: Δr ≤ 0 OR coef sign wrong overall

Verdict appended after results, never pre-filled.

---

# Results

Ran `scripts/xfp/validate_milb_aaa_iso_prior.py` on 2026-05-24.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RH3_FEATS, 18 feats) | 0.6167 | — |
| Extended cross_year r (+ milb_aaa_iso_prior, 19 feats) | 0.6167 | — |
| **Δr** | **+0.0000** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 3/7 years positive | FAIL (need 5/7) |
| Holdout (2024-2025) | 0/2 positive | FAIL |
| Coef sign | −0.0012 (expected +) | WRONG SIGN |

**Per-year Δr:** 2018: −0.0009, 2019: −0.0003, 2021: +0.0004, 2022: +0.0001, 2023: +0.0002, 2024: −0.0003, 2025: −0.0008.

**Verdict: REJECTED.** ISO does not travel through this join meaningfully — likely AAA park/league context distorts the raw power signal enough that the MLB-side cumulative iso_to_sh already captures whatever's predictive. The negative coefficient is a tell: high-AAA-ISO callups may be subtly *worse* MLB hitters (Quad-A bat archetype). Real but small effect, swamped by noise from the 72% population-median-filled population.

**Next step:** do NOT promote. The pairing test (`milb_aaa_kpct_prior`) carries the genuine MiLB-data-layer signal.

