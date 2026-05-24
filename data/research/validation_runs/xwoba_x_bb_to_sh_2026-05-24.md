---
signal: xwoba_x_bb_to_sh
formula: xwoba_per_pa_to_sh * bb_pct_to_sh (product of two existing RP3_FEATS, both season-to-date shrunk rates)
outcome: ros_fp_per_start (rp3 production target)
expected_sign: negative (both factors are "bad" — higher xwOBA allowed and higher walk rate both depress FP/start; product is badness² and the coefficient on the interaction should be negative since FP/start drops as the product grows)
theory: Trouble-pitcher detector. A pitcher who allows hard contact AND issues walks has compounding blow-up risk — the product captures that compounding directly. Ridge sees both factors linearly; an explicit product column adds the non-linear "both elevated" failure mode.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_xwoba_x_bb_to_sh.py
date: 2026-05-24
verdict: REJECTED
purpose: rp3 v3 ceiling-audit follow-up — 4-cell interaction-term sweep (cell 4 of 4).
---

## Result — REJECTED (2026-05-24)

| Metric | Value |
|---|---|
| Baseline cross_year_r (RP3_FEATS, 23 feats) | 0.5509 |
| Extended (+ xwoba_x_bb_to_sh, 24 feats) | 0.5508 |
| **Δr** | **−0.0001** |
| Pooled n | 4174 |
| Sign consistency | 3/7 years positive |
| Holdout (2024-2025) avg lift | −0.0001 |

Per-year lift: 2018 +0.0001, 2019 +0.0001, 2021 +0.0000, 2022 −0.0001, 2023 +0.0000, 2024 +0.0001, 2025 −0.0004.

### Why this failed
"Trouble pitcher" badness² is essentially flat noise in every direction. The two factor inputs (xwoba_per_pa_to_sh, bb_pct_to_sh) are both shrunk rate features at high coverage, so their product is well-behaved — but the GBM in rp3 already captures the joint contribution through their individual entries. No marginal compounding effect surfaces in pooled or holdout splits.

### Decision
REJECTED. Do not add to RP3_FEATS.


## Sweep / Bonferroni context

Member of 4-cell interaction sweep (see velo_x_swstr_to_sh_2026-05-24.md). Per-cell α=0.0125; +0.005 lift gate binding.

## Sign-theory note

xwoba_per_pa_to_sh is "allowed by pitcher" → high = bad.
bb_pct_to_sh is "issued by pitcher" → high = bad.
Product = badness². Coefficient on the interaction should be NEGATIVE (more product → lower FP/start). This is the expected sign for the validation harness's sign check.

## Rule 9 baseline

Full RP3_FEATS (23 feats), expected baseline r=0.5509. Candidate added; lift = Δr.

## Step 2.5 data-coverage pre-check

Both factors are 100%-coverage existing RP3_FEATS members. Product is finite on every row. No fill needed.

## Decision rule

PASS / MARGINAL / REJECTED per standard rp3 protocol.
