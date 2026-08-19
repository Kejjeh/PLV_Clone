---
signal: role_lag_missing
formula: role_lag_missing = 1 if role_lag1 is null else 0 (prior-year reliever role absent from relievers_multiyr). Variants also RE-ENCODE the imputed lag columns; see Variants below.
outcome: fp_year_total (rprs2 TARGET), leave-one-year-out across TRAIN_YEARS, plus strict 2024-2025 holdout
expected_sign: negative coefficient on the flag (a lag-missing arm is a rookie/returnee/converted starter and projects below a same-in-season-line arm with an established prior role); the DECISION-RELEVANT claim is a positive cross_year_r gain
theory: lag-missing rows receive internally inconsistent imputation - counts (sv_lag1/hld_lag1) get the population MEAN while rates (sv_per_g_lag1/hld_per_g_lag1) get 0.0 - so the ridge is told "~4 SV and ~8 HLD last year" and "save rate exactly 0" simultaneously; a missingness flag lets it identify and discount that contradiction instead of averaging it.
production_target: rprs2
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_role_lag_missing.py
date: 2026-08-18
verdict: REJECTED
---

# rprs2 `role_lag_missing` — pre-registration

## Why this run exists
47% of the live 2026 RP universe (174/368 on 2026-08-18) has a null `role_lag1`.
Canonical symptom: **Jacob Latz** — 25 SV, 67% GF share, 305.8 FP, PL's #6
reliever — projects **below replacement** (xfp_ros 51.8 vs replacement 64.5,
replacement_delta −10.4), which reads downstream as a drop signal.

Root cause traced to `scripts/xfp/enrich_rolling_relievers.py:166-194`:

```
sv_lag1, hld_lag1, g_lag1, ip_lag1, fp_lag1, fp_per_g_lag1  -> population MEAN
role_closer/setup/middle_lag1                               -> 0
sv_per_g_lag1, hld_per_g_lag1                               -> 0.0
```

Counts imputed to the mean, rates imputed to zero. The model cannot tell an
imputed row from a measured one, and the two imputations disagree.

Latz specifically: `relievers_multiyr` has rows for 2024 and 2026 but **no 2025**,
so the year_target=2026 lag merge finds nothing.

## Variants (Rule 3 — 3 cells, Bonferroni α/3)
- **A — flag only:** baseline + `role_lag_missing`. Imputation untouched.
- **B — flag + consistent ZERO:** counts also set to 0 where missing (matches
  what the rate columns already do).
- **C — flag + consistent MEAN:** rate columns set to population mean where
  missing (matches what the count columns already do).

## Gates
- Rule 9 baseline = the FULL 28-feature `FEATS_RPRS2`. No curated subset.
- Headline: LOO cross-year r gain ≥ **+0.005** vs that baseline.
- Rule 2(b): sign consistency across ≥5 of 6 available cohorts (2020 absent).
- Rule 2(c): strict holdout partial r ≥ +0.05, same sign, on 2024-2025 never trained on.
- Rule 8: convergence across split_day buckets — sign must not flip.
- Subgroup: r on lag-missing rows only (where the fix is supposed to act).

## Rule 5 honesty note
Rows are (pitcher, year, split_day), so the 13,934 lag-missing training rows are
only **739 unique pitcher-years**. Pooled r is computed on rows (matching how the
production harness fits), but the effective independent n is the pitcher-year
count and per-year consistency is judged on that basis. Cohorts available: 6
(2019, 2021-2025); 2020 is excluded league-wide as a short season, so the "5 of 7"
bar is applied as "5 of 6".


---

# RESULT — REJECTED (2026-08-18)

Rule 9 baseline (28 production features): pooled LOO cross-year **r = 0.8698**,
lag-missing subgroup r = 0.8381, n = 34,115.

| Cell | pooled r | gain | subgroup gain | per-year positive |
|---|---|---|---|---|
| A — flag only | 0.8696 | **−0.0002** | −0.0000 | **0/6** |
| B — flag + consistent ZERO | 0.8696 | **−0.0002** | −0.0002 | 2/6 |
| C — flag + consistent MEAN | 0.8696 | **−0.0002** | −0.0000 | 0/6 |

Strict holdout (train 2019/2021/2022/2023 → test 2024, 2025), best cell A:
2024 −0.0002, 2025 −0.0006. **Negative, fails Rule 2(c).**

Rule 8 convergence by split_day — 0-60 −0.0003, 60-90 −0.0001, 90-120 −0.0001,
120-150 +0.0000, 150+ +0.0000. Flat-to-negative everywhere; no cutoff helps.

Bonferroni (Rule 3): 3 cells at α/3. **0 of 3 pass even the unadjusted bar.**

## Why it fails — algebraic redundancy

The flag is already implied by features in the baseline. All 27,994 lag-missing
rows carry all-zero role one-hots (`role_closer_lag1 = role_setup_lag1 =
role_middle_lag1 = 0`); the only other all-zero rows are the 5,772 genuine
`long_low` arms. Correlation with the flag in the training frame is **0.80**, and
missingness is a strict SUBSET of all-zero. The ridge can already separate these
rows; an explicit indicator adds no information.

Same failure mode as `xwoba_contact_to` (rp3, 2026-05-25) and
`stuff_contact_composite` — a candidate that restates something the baseline
already encodes.

## What this corrects

The run was motivated by the claim that Jacob Latz's below-replacement
`xfp_ros` (51.8 vs replacement 64.5) was an ARTIFACT of the model being blind to
his imputed lag features. **That claim is not supported.** The model can already
identify lag-missing rows and still projects him there, and lag-missing arms
genuinely average a lower full-year target (137.5 vs 174.5 FP).

The actual arithmetic behind Latz's low RoS is the RoS subtraction, not
imputation: `xfp_ros = xfp_full_year − fp_actual_2026` = **357.6 − 305.8 = 51.8**.
His full-year projection (357.6) is essentially identical to Jhoan Duran's
(359.6) — the difference in RoS is that Latz has already BANKED more of his
season (305.8 vs 276.3). That is the metric behaving as designed for a
forward-looking decision, not a defect.

## What stays

The `data_quality_tag` (`lag_imputed` / `data_driven`) shipped on the rprs2 output
the same day remains — it is a transparency label with no model effect, and it is
still the right way to flag that 47% of the pool carries synthetic lag inputs
(notably rows like Ben Joyce, rprs2 #1 on 5 games). But it must NOT be read as
"this projection is wrong": this run is the evidence that the projection does not
measurably improve when the imputation is flagged or made self-consistent.

## Residual code defect (real, but not a scoring bug)

`enrich_rolling_relievers.py:166-194` imputes counts to the population mean and
rates to 0.0 for the same rows. Cells B and C made each self-consistent and both
scored −0.0002, so this is a tidiness issue with no measurable projection impact.
Fixing it is safe but must not be sold as an accuracy improvement.
