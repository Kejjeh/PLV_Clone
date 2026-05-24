---
signal: bb_pct_x_xwoba_per_pa_to_sh
formula: bb_pct_to_sh * xwoba_per_pa_to_sh (product of two existing shrunk columns)
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: +
theory: Discipline × power synergy. Soto-archetype detector — both axes simultaneously elite is more valuable than additive marginals suggest (premier hitters get pitched around, which compounds production via BB AND xwOBA on contact).
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_bb_pct_x_xwoba_per_pa_to_sh.py
date: 2026-05-24
verdict: REJECTED
purpose: Interaction-term sweep round (rh3). Test discipline × power Ridge-explicit interaction.
---

### Bonferroni / sweep context

4-cell rh3 interaction sweep; see `pa_to_x_hr_per_pa_to_sh_2026-05-24.md`.

### Rule 9 baseline

Full RH3_FEATS as of 2026-05-24.

### Step 2.5 data-coverage pre-check

Both factors are RH3_FEATS members (post-shrinkage); coverage guaranteed.

### Convergence-curve framing (Rule 8)

Per split_day at 30/60/90/120. Synergy hypothesis predicts the lift grows with sample size (more PA = more reliable rate estimates of each factor).

---

## Result — REJECTED (2026-05-24)

### Headline (Rule 9 baseline = full RH3_FEATS)

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended cross_year_r | 0.6167 |
| **Δr** | **+0.0000** |
| Pooled n | 8,275 |

Effectively zero pooled lift.

### Per-year breakdown (Rule 2b)

| Year | Δr | Sign |
|---|---|---|
| 2018 | −0.0001 | − |
| 2019 | −0.0002 | − |
| 2021 | +0.0003 | + |
| 2022 | +0.0000 | 0 |
| 2023 | +0.0001 | + |
| 2024 | +0.0003 | + |
| 2025 | +0.0000 | 0 |

Positives **3/7** (strict; 5 if counting zeros). Holdout 1/2.

### Convergence (Rule 8)

Flat (≤ |0.0001|) across all split_days. The Soto-archetype synergy hypothesis is not visible in cross-year LOO at any cutoff.

### Sign sanity

Coef +0.0053 (expected +). Direction OK but Ridge cannot lever the joint information beyond what bb_pct_to_sh + xwoba_per_pa_to_sh marginals already provide.

### Why this failed

xwoba_per_pa_to_sh already aggregates discipline × power because xwOBA itself weights BB events. The interaction is largely collinear with the marginal, so Ridge zeros out the marginal information transfer.

### Decision

REJECTED.

