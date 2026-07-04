---
signal: sp_subs_fp_composite
formula: within-year z-score composite of PRE-SPLIT process stats with weights frozen from the rating_reimagine pre-2026 career-panel ridge fit — 0.174*z(swstr_pct_to) + 0.036*z(c_plus_swstr_to) + 0.035*z(avg_velo_to) + 0.035*(-z(xwoba_per_pa_to)) + 0.030*z(zone_pct_to) + 0.026*(-z(bb_pct_to)), weights renormalized to sum 1
outcome: ros_fp_per_start (rest-of-season FP per start after split_day)
expected_sign: +
theory: SwStr-dominant process composite out-predicts the FP level because whiff skill persists (~.72 YoY) while sequencing luck mean-reverts; the reweighted sub-rating composite beat OVERALL .590 vs .551 on the career panel.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_sp_subs_fp_composite.py
date: 2026-07-04
verdict: REJECTED
---

# sp_subs_fp_composite — rating_reimagine queue #1

## Provenance
7-angle rating study (`data/research/rating_reimagine_2026-07-04.md`, Angle 1):
reweighted SP sub-rating composite with SWING_MISS dominant hit panel forward
r=.590 vs current OVERALL .551 (n=987, CV-by-year), and an in-season partial
of **+.434 beyond rp3** — but that window was CONFOUNDED (rp3 snapshot 6/06 vs
an FP window opening 5/04; ratings were full-season constructs relative to a
misaligned window). This run is the clean re-test.

## Rule 9 pre-declaration — expected redundancy
The full production RP3_FEATS baseline **already contains the shrunk split-day
substrate of every composite constituent**: `swstr_pct_to_sh`, `k_pct_to_sh`,
`bb_pct_to_sh`, `c_plus_swstr_to_sh`, `zone_pct_to_sh`, `xwoba_per_pa_to_sh`,
`avg_velo_to` — all free Ridge parameters — plus the FP level, Marcel priors,
IL features, the validated drift deltas, and RoS schedule. A fixed linear
combination of already-present features adds information ONLY through its
within-year z-normalization / implicit-prior effect under regularization.
**Pre-registered expectation: gain ≈ 0 (the `stuff_contact_composite` /
`xwoba_contact_to` algebraic-redundancy pattern).** We run it anyway to close
queue #1 empirically and log the number (Rule 6) — and because the +.434
confounded partial is the strongest unexplained residual in the program.

## Rule 8 framing note
The research composite was built from FULL-SEASON ratings; production use is
in-season → RoS, so the candidate here is reconstructed from **pre-split
(`*_to`) columns only**. Full-season construction would leak the outcome
window and is not tested.

## Step 2.5 data coverage
Source: `rolling_pitchers_2018_2026.csv` + `sp_multiyr` (current through the
2026-07-04 multiyr fix). All constituent columns exist 2018+. Training-eligible
years: 2018, 2019, 2021, 2022, 2023 (5 ≥ 5 ✓). Per-year SP-split rows ≫ 30 ✓.
Holdout 2024-2025 untouched by weight-freezing (weights come from the pre-2026
career-panel fit, which includes 2024-25 panel years — NOTE: this weakens
holdout purity for the WEIGHTS but not for the model fit; flagged honestly.
Mitigation: the composite's weights are dominated by one term (SwStr .174 vs
≤.036 others), so weight overfit risk is minimal.)

## Gates
(a) partial r ≥ 0.10 vs full-baseline predictions; (b) sign-consistent ≥ 5/5
training years; (c) holdout Δr and partial ≥ 0.05 same sign; headline:
cross-year r gain vs the +0.005 strict bar. Bonferroni: single candidate,
no sweep — no-op.
