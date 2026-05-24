---
signal: gs_x_prior_ip_resid
formula: gs_to * prior_ip_resid, where prior_ip_resid = (prior_year ip_per_start from sp_multiyr_2015_2025.csv with gs>=5) minus league mean ip_per_start across qualifying pitchers. NaN prior filled with 0 (mean residual).
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (current-season workload × proven prior-year durability = workhorse marker; a high-GS pitcher with a positive IP-residual is demonstrating their durability is real)
theory: gs_to is in RP3_FEATS (workload signal). Prior-year IP/start residual is not in baseline, but more importantly the INTERACTION encodes "workhorse confirmation": high current GS gets a positive boost when prior-year IP/start was above league norm, and a discount when prior-year IP/start was below. Note: name reformulated from the brief's `gs_x_ip_resid_lag1` since no `ip_resid_lag1` column exists in rolling_pitchers_2018_2026.csv; we derive it from sp_multiyr ip_per_start.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_gs_x_prior_ip_resid.py
date: 2026-05-24
verdict: REJECTED
purpose: rp3 v3 ceiling-audit follow-up — 4-cell interaction-term sweep (cell 3 of 4).
---

## Result — REJECTED (2026-05-24)

| Metric | Value |
|---|---|
| Baseline cross_year_r (RP3_FEATS, 23 feats) | 0.5509 |
| Extended (+ gs_x_prior_ip_resid, 24 feats) | 0.5496 |
| **Δr** | **−0.0013** |
| Pooled n | 4174 |
| prior_ip_per_start coverage | 65.7% |
| Sign consistency | 2/7 years positive |
| Holdout (2024-2025) avg lift | −0.0023 |

Per-year lift: 2018 −0.0002, 2019 +0.0003, 2021 +0.0001, 2022 −0.0025, 2023 +0.0000, 2024 −0.0004, 2025 −0.0043.

### Why this failed
Worst result of the 4-cell sweep. Holdout NEGATIVE (−0.0023), 2025 particularly bad (−0.0043). The "workhorse marker" interaction actively HURTS the model. Plausible mechanism: gs_to early in season is heavily influenced by role assignment (rotation luck) more than durability; multiplying by prior IP/start residual amplifies a noisy early-season GS reading. `prior_gs_eff` already in RP3_FEATS appears to capture the durability prior more cleanly.

### Decision
REJECTED. Do not add to RP3_FEATS. Wrong direction on the holdout that matters most.


## Sweep / Bonferroni context

Member of 4-cell interaction sweep (see velo_x_swstr_to_sh_2026-05-24.md). Per-cell α=0.0125; +0.005 lift gate binding.

## Column-name note

Brief specified `ip_resid_lag1`; this column does not exist in `rolling_pitchers_2018_2026.csv`. Substitute: compute prior-year `ip_per_start` from `sp_multiyr_2015_2025.csv`, subtract the cohort league mean, attach via standard `attach_prior_year_feature` helper. This preserves the "durability prior × current workload" theory intact.

## Rule 9 baseline

Full RP3_FEATS (23 feats), expected baseline r=0.5509. Candidate added; lift = Δr.

## Step 2.5 data-coverage pre-check

`gs_to` is 100% coverage (RP3_FEATS member). Prior IP/start coverage ~65% of rolling rows (similar to avg_ext_prior). Missing prior filled with 0 residual → interaction = 0 on those rows. Same-eval-set guarantee maintained.

## Decision rule

PASS / MARGINAL / REJECTED per standard rp3 protocol.
