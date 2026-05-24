---
signal: prior_pa_eff_x_pa_to
formula: prior_pa_eff * pa_to (product of two existing post-prep columns)
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: +
theory: Opportunity-converted-to-opportunity. Prior-year PA efficiency × current PA accumulation = "this hitter is in their team's good graces". Captures whether a hitter who earned PA last year is also earning PA this year — a regime-confirmation signal that Ridge cannot express from the two linear marginals.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_prior_pa_eff_x_pa_to.py
date: 2026-05-24
verdict: MARGINAL
purpose: Interaction-term sweep round (rh3). Test whether prior-year × current-year opportunity-product unlocks lift over additive marginals.
---

### Bonferroni / sweep context

4-cell rh3 interaction sweep; see `pa_to_x_hr_per_pa_to_sh_2026-05-24.md`.

### Rule 9 baseline

Full RH3_FEATS as of 2026-05-24. Both `prior_pa_eff` and `pa_to` are RH3_FEATS members.

### Step 2.5 data-coverage pre-check

`prior_pa_eff` is created in `load_and_prep_rh3_inputs()` via Marcel prior merge with `.fillna(0.0)` for first-year players. `pa_to` is raw. Product domain ≥ 0; no NaN expected.

### Convergence-curve framing (Rule 8)

Per split_day at 30/60/90/120. Effect expected to be modest early-season (small pa_to) and grow.

---

## Result — MARGINAL (2026-05-24)

### Headline (Rule 9 baseline = full RH3_FEATS)

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended cross_year_r | 0.6175 |
| **Δr** | **+0.0008** |
| Pooled n | 8,275 |

Positive lift — best of the 4-cell sweep — but well below the +0.005 production gate.

### Per-year breakdown (Rule 2b)

| Year | Δr | Sign |
|---|---|---|
| 2018 | +0.0021 | + |
| 2019 | +0.0011 | + |
| 2021 | +0.0007 | + |
| 2022 | +0.0013 | + |
| 2023 | −0.0004 | − |
| 2024 | −0.0005 | − |
| 2025 | +0.0005 | + |

Positives **5/7** (clears Rule 2b ≥ 5/7). Holdout (2024-2025) **1/2** — the years that matter most are split.

### Convergence (Rule 8)

| split_day | Δr |
|---|---|
| 30 | −0.0016 |
| 60 | −0.0004 |
| 90 | −0.0002 |
| 120 | −0.0001 |

**Every per-split_day Δr is negative.** The pooled positive comes entirely from cross-cutoff variance, not from any one cutoff. This is structurally suspicious — Rule 8 expects the convergence-curve framing to MATCH or exceed the pooled framing for a real signal.

### Sign sanity

Coef **−0.0117** (expected +). **WRONG SIGN.** Theory said "more prior-year PA × more current PA = more opportunity, more production". Ridge instead uses it as a negative offset against the two marginals (prior_pa_eff and pa_to), which suggests the model is using the interaction as a regularization term rather than a directional predictor.

### Why this is MARGINAL not PASS

Three failure modes simultaneously:
1. Pooled Δr +0.0008 is far below +0.005 gate.
2. Every per-split_day Δr is negative (Rule 8 fails).
3. Final-pipeline coefficient sign is wrong (the theory is not what's getting fit).

The pooled positive is real but appears to be a "lucky averaging" artifact of how cross-year LOO interacts with cutoff variance, not a stable predictive signal.

### Decision

MARGINAL → do not promote. Of the four interaction candidates this had the largest pooled Δr (+0.0008) and best per-year count (5/7), but the wrong-sign coefficient plus all-negative per-cutoff convergence kill any honest case for promotion. If anything, the result reinforces that prior_pa_eff and pa_to as linear marginals already capture the opportunity-confirmation signal Ridge needs.

