---
signal: milb_aaa_kpct_prior
formula: mean K% across all AAA stints in the PRIOR season (year-1) per batter, min 50 PA at AAA to qualify. NaN-filled with training-year population median computed on rows that had a prior-year AAA stint.
outcome: ros_fp_per_pa (rh3 production target)
expected_sign: negative (more whiff at AAA → more whiff in MLB → −K contribution dominates → lower RoS FP/PA)
theory: K% travels well between AAA and MLB — among the most stable plate-discipline carryovers in prospect research. For callups, it's a leading-style predictor of "does the bat play". For up-and-down guys with a recent AAA stint, it cross-checks whether their MLB rate (small sample) is real or noise.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_milb_aaa_kpct_prior.py
data_layer_script: scripts/xfp/build_milb_aaa_priors.py
date: 2026-05-24
verdict: MARGINAL
purpose: Second test of the MiLB data layer. Pairs with milb_aaa_iso_prior — together they cover the two highest-stability AAA→MLB carryovers.
---

# Pre-registration body

## Why this candidate

K% is one of the most stable AAA→MLB carryovers in the prospect literature. For a callup, prior-year AAA K% is plausibly a stronger leading indicator of MLB K% than the first ~50-200 MLB PA itself (high variance early). The MLB-side shrunken k_pct_to_sh in RH3_FEATS already moves on its own data; the question is whether AAA K% adds *independent* lift on top.

Honest expectation: this is more likely than ISO to carry incremental signal because K% is rate-stable across levels, while ISO is somewhat park/league-context-dependent (AAA ball, especially 2019+, has very different run environments).

## Rule 5 sample-size check

Same as `milb_aaa_iso_prior` — see that pre-reg. 28% of rolling rows have a real prior-year AAA stint; 2021 MLB rows are blank due to the 2020 MiLB cancellation.

## Rule 8 framing

In-season → RoS, all split_days. Identical to rh3 production framing.

## Rule 9 baseline

Full RH3_FEATS (18 features). Extended = baseline + `milb_aaa_kpct_prior`.

## Rule 3 / Bonferroni

Two candidates in this push. +0.005 production gate is binding.

## Decision rule

- **PASS**: Δr ≥ +0.005 AND ≥5/7 years positive AND coef sign matches expected (negative)
- **MARGINAL**: 0 < Δr < +0.005 OR (Δr ≥ +0.005 but one of the other gates fails)
- **REJECTED**: Δr ≤ 0 OR coef sign wrong overall

Verdict appended after results, never pre-filled.

---

# Results

Ran `scripts/xfp/validate_milb_aaa_kpct_prior.py` on 2026-05-24.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RH3_FEATS, 18 feats) | 0.6167 | — |
| Extended cross_year r (+ milb_aaa_kpct_prior, 19 feats) | 0.6198 | — |
| **Δr** | **+0.0031** | sub-gate (gate ≥ +0.005) |
| Sign consistency | 6/7 years positive | PASS (≥ 5/7) |
| Holdout (2024-2025) | 2/2 positive | PASS |
| Coef sign | −0.0083 (expected −) | OK |

**Per-year Δr:** 2018: +0.0014, 2019: +0.0015, 2021: +0.0024, 2022: +0.0035, 2023: −0.0040, 2024: +0.0038, 2025: +0.0073.

**Verdict: MARGINAL.** Δr falls short of the +0.005 hard gate but clears every other consistency check (6/7 years, 2/2 holdout, correct negative coef sign). Notably this is the **best Δr from a candidate-feature push in the last 3 sessions** (~20 attempts have come in at +0.000 to +0.001). The lift is concentrated in the most recent years (2024 +0.0038, 2025 +0.0073) — encouraging given AAA-MiLB-data-layer maturity has grown over time. Only the 2023 fold dissents (−0.0040), which is small.

**Do not promote** to RH3_FEATS per the +0.005 hard gate (Rule 9). But this is the **strongest evidence yet** that MiLB-data-layer signal is real and out-of-family. Justified next steps:
1. Add `pybaseball.statcast_minor_league_batter` AAA xwOBA prior (2021+ only) — more direct skill measure than counting-stat K%.
2. Test a *combination* — e.g., (`milb_aaa_kpct_prior` + AAA-xwOBA-prior + multi-year AAA averaging) to see if joint lift clears +0.005.
3. Consider restricting the feature to the subset of rolling rows with a real prior-year stint (the 28%) and validating lift *on that subpopulation only* — if the lift there is +0.010+, an indicator-interaction encoding may make the whole-population lift clear the gate.

**Sanity check — 2026 callups:** the priors file now has 525 batter-2026 rows (AAA 2025 → MLB 2026). Spot-check a few prominent 2025 callups against their actual MLB performance to confirm the join is producing sensible values before any further investment.

