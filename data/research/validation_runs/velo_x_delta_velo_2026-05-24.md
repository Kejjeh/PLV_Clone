---
signal: velo_x_delta_velo
formula: avg_velo_to * delta_velo  (where delta_velo = avg_velo_last21 − avg_velo_to, computed in harness)
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (an ace gaining velo accelerates further; an ace losing velo decays harder — level × trajectory)
theory: avg_velo_to (level) and delta_velo (trajectory) are both in RP3_FEATS individually. Their joint effect — "ace trending up" vs "ace trending down" vs "soft-tosser trending up" — is multiplicative, not additive. Ridge cannot express that without an explicit product column.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_velo_x_delta_velo.py
date: 2026-05-24
verdict: REJECTED
purpose: rp3 v3 ceiling-audit follow-up — 4-cell interaction-term sweep (cell 2 of 4).
---

## Result — REJECTED (2026-05-24)

| Metric | Value |
|---|---|
| Baseline cross_year_r (RP3_FEATS, 23 feats) | 0.5509 |
| Extended (+ velo_x_delta_velo, 24 feats) | 0.5509 |
| **Δr** | **+0.0000** |
| Pooled n | 4174 |
| Sign consistency | 3/7 years positive |
| Holdout (2024-2025) avg lift | +0.0001 |

Per-year lift: 2018 +0.0001, 2019 +0.0000, 2021 −0.0002, 2022 −0.0004, 2023 +0.0001, 2024 +0.0003, 2025 −0.0001.

### Why this failed
Level × trajectory: dead zero pooled lift. The delta_velo feature is already small in magnitude (most pitchers have |delta_velo| < 0.5 mph), so the product mostly tracks avg_velo_to scaled by ~0; the GBM never gets enough variance to extract anything. 3/7 sign agreement is at chance.

### Decision
REJECTED. Do not add to RP3_FEATS.


## Sweep / Bonferroni context

Member of 4-cell interaction sweep (see velo_x_swstr_to_sh_2026-05-24.md). Per-cell α=0.0125; +0.005 lift gate binding.

## Rule 9 baseline

Full RP3_FEATS (23 feats), expected baseline r=0.5509. Candidate added; lift = Δr.

## Step 2.5 data-coverage pre-check

Both factors derived in harness with 100% coverage (delta_velo filled to 0 in harness for pitchers without last21 data). Product is finite on every row.

## Decision rule

PASS / MARGINAL / REJECTED per standard rp3 protocol.
