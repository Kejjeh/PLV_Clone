---
signal: milb_aaa_translation
formula: predicted MLB FP/PA from the batter's most recent AAA season <= year T with >= 150 AAA PA (prefer same-year), via an OLS translation fit on 2015-2023 AAA->MLB pairs (feats standardized [k_pct, bb_pct, iso, hr_per_pa, age]; MLB target fp_per_pa_actual from hitters_multiyr, MLB season = same year else next, >= 100 MLB PA)
outcome: ros_full_fp_per_pa (rh3 target) — evaluated WITHIN the callup subgroup only
expected_sign: "+"
theory: for callups the season-to-date MLB sample is tiny and the Marcel prior is thin, so the absorber is structurally weak; a translated AAA rate profile carries real skill information the shrunken prior cannot
production_target: research-only
framing: in-season → ros, callup subgroup (prior_pa_eff < 150 AND pa_to < 150 at the split; one row per batter-year = earliest qualifying split; AAA line required)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_milb_aaa_translation.py
date: 2026-07-19
verdict: PASS
---

## RESULT (2026-07-19): PASS, all gates cleared with wide margin
- Pooled TRAIN partial r +0.2763 (p<.001, n=745) vs 0.10 gate.
- Pooled HOLDOUT +0.2378 (p<.001, n=292) vs 0.05 gate.
- Sign consistency 7/7 (each year +0.16..+0.40; every year n>=138, Rule 5 clean).
- Translation fit: 982 pairs, in-sample r 0.277; K% dominates (coef -0.039),
  consistent with the 2026-05-24 finding that AAA K% is the carrying signal.
- Scope: RESEARCH-VALIDATED subgroup prior. Production integration (Rule 7/Step 9)
  is a SEPARATE task: blend translated prior into prior_fp_per_pa for
  prior_pa_eff+pa_to < 150 rows, full-pipeline backtest, user sign-off.

## PRODUCTION INTEGRATION (Step 9, signed off + shipped 2026-07-19)

- Module `src/plv_clone/models/xfp/aaa_translation.py` (frozen spec in docstring);
  blend called in rh3.main() after the Marcel prior; validation-helper mirror updated;
  `_FIT_FP_VERSION` 1 -> 2 (cold refit forced).
- Blend: w_aaa = clip(150 - (prior_pa_eff + pa_to), 0, 150); prior' =
  (prior_pa_eff*prior + w_aaa*aaa_pred) / (prior_pa_eff + w_aaa). Parameter-free,
  anchored on the validated 150-PA boundary. 15,031 rows / 942 callup batters touched.
- Gates: cross_year_r 0.6418 -> 0.6419 (no degradation); golden diff = refit jitter
  only on non-callups (mean |d| 0.001), top movers all callups 68-135 PA shifting
  0.009-0.016 FP/PA (mostly downward — regresses hot thin samples); 763/763 tests pass.

## Design (subgroup incremental, Wave 3B of campaign ledger)

1. **Translation fit** (2015-2023 pairs only; frozen before evaluation): survivorship
   caveat pre-declared — only AAA hitters who reached >= 100 MLB PA enter the fit,
   which compresses the slope; acceptable for a prior whose USE population (callups
   actively getting MLB PA) matches the fit population reasonably well.
2. **Baseline predictions:** LOO by year, production pipeline config
   (StandardScaler + RidgeCV(logspace(-1,5,80), cv=5)) on full RH3_FEATS. Train rows
   use the production filter (pa_to >= 50, ros_pa >= 100). PREDICTION rows = subgroup
   rows of the held year with a lighter floor (pa_to >= 10, ros_pa >= 50) because the
   callup population lives below the production eval floor — pre-declared, applied
   identically to baseline and candidate assessment.
3. **Test:** within subgroup rows, partial r of the translated prior vs the baseline
   residual (candidate residualized on the baseline prediction first).
4. **Gates:** pooled partial r >= 0.10 (train years); sign consistency >= 5/7; holdout
   2024-25 partial r >= 0.05 same sign. **Rule 5 caveat pre-declared:** per-year
   subgroup n may fall under 30 — years below n=30 count as sign-only.

Single declared cell (the 5-feat OLS translation). No variant sweep.

## Closest graveyard relative

MiLB AAA priors already feed rh3's Marcel blend (milb_aaa_iso/kpct prior validations
2026-05). Difference: those are GLOBAL feature adds; this is a SUBGROUP model asking
whether a full translated FP prior beats the production handling exactly where the
production prior is weakest. A global-add framing would be absorbed and is not claimed.
