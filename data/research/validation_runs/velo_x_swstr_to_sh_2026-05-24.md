---
signal: velo_x_swstr_to_sh
formula: avg_velo_to * swstr_pct_to_sh (product of two existing RP3_FEATS columns; both season-to-date)
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (high velo × high whiff = canonical "stuff index" / ace detector)
theory: Ridge/GBM linear-form features cannot natively express multiplicative effects. avg_velo_to and swstr_pct_to_sh are both in RP3_FEATS individually, but the model never sees their product. Aces sit in the upper-right of the (velo, swstr) plane; an explicit interaction column may unlock signal the linear additive form misses.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_velo_x_swstr_to_sh.py
date: 2026-05-24
verdict: REJECTED
purpose: rp3 v3 ceiling-audit follow-up — 4-cell interaction-term sweep testing whether explicit products of existing RP3_FEATS columns unlock multiplicative signal.
---

## Result — REJECTED (2026-05-24)

| Metric | Value |
|---|---|
| Baseline cross_year_r (RP3_FEATS, 23 feats) | 0.5509 |
| Extended (+ velo_x_swstr_to_sh, 24 feats) | 0.5508 |
| **Δr** | **−0.0001** |
| Pooled n | 4174 |
| Sign consistency | 4/7 years positive |
| Holdout (2024-2025) avg lift | +0.0007 |

Per-year lift: 2018 −0.0016, 2019 +0.0004, 2021 +0.0017, 2022 −0.0002, 2023 −0.0008, 2024 +0.0012, 2025 +0.0002.

### Why this failed
The "stuff index" interaction is structurally absorbed by `avg_velo_to` + `swstr_pct_to_sh` already in the baseline. Ridge inside the rp3 pipeline has enough flexibility (via the GBM stack) that the linear product offers no additional decomposition of the (velo, swstr) plane. Pooled lift indistinguishable from noise; sign sign 4/7 (fails ≥5/7); only modest holdout positivity.

### Decision
REJECTED. Do not add to RP3_FEATS. The canonical ace-detector hypothesis does not survive Rule 9.


## Sweep / Bonferroni context

4-cell interaction sweep (this file is cell 1 of 4):
- velo_x_swstr_to_sh — "stuff index" (this)
- velo_x_delta_velo — level × trajectory
- gs_x_prior_ip_resid — workload × durability prior
- xwoba_x_bb_to_sh — trouble-pitcher detector

Per Rule 3, per-cell α=0.0125 (Bonferroni at α=0.05/4). The +0.005 effect-size gate is the binding constraint and clears Bonferroni in practice.

## Rule 9 baseline

Baseline = full RP3_FEATS as of 2026-05-24 (23 features). Candidate is ADDED. Lift = cross_year_r(baseline + candidate) − cross_year_r(baseline). Baseline r expected = 0.5509.

## Step 2.5 data-coverage pre-check

Both factors are 100%-coverage existing RP3_FEATS members. Product is finite on every row. No fill needed.

## Decision rule

- PASS: lift ≥ +0.005 AND sign consistent ≥ 5/7 years AND holdout lift > 0.
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a).
- REJECTED: lift ≤ 0 OR wrong coef sign.
