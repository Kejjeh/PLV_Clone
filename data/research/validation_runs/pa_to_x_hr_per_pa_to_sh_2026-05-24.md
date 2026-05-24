---
signal: pa_to_x_hr_per_pa_to_sh
formula: pa_to * hr_per_pa_to_sh (product of two existing rolling-frame columns post-shrinkage)
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: +
theory: Raw expected HRs to date — volume × efficiency. Differentiates an 80-PA hot stretch from sustained 600-PA mashing. Ridge cannot express multiplicative effects from linear features, so the explicit interaction may unlock signal.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_pa_to_x_hr_per_pa_to_sh.py
date: 2026-05-24
verdict: REJECTED
purpose: Interaction-term sweep round (rh3). Test whether the explicit product of cumulative PA × shrunk HR/PA adds independent lift over the full RH3_FEATS baseline (which already contains both factors as marginals).
---

### Bonferroni / sweep context

Four interaction-term candidates pre-registered same day for rh3 (this sweep):
- pa_to_x_hr_per_pa_to_sh (this file)
- bb_pct_x_xwoba_per_pa_to_sh
- lineup_spot_x_split_day
- prior_pa_eff_x_pa_to

All address the same gap: Ridge's inability to express multiplicative effects from linear marginal features. Treat as a 4-cell mini-sweep. Per Rule 3, per-cell α = 0.0125. Effect-size gate (+0.005) is the binding constraint.

### Rule 9 baseline

Baseline = full RH3_FEATS as of 2026-05-24 (see `src/plv_clone/models/xfp/rh3.py`). NOT a stripped-down subset. Candidate is ADDED to this baseline. Lift = cross_year_r(baseline + candidate) − cross_year_r(baseline).

### Step 2.5 data-coverage pre-check

Both `pa_to` and `hr_per_pa_to_sh` are guaranteed present in the post-prep rolling DataFrame (the former is raw; the latter is computed by `apply_shrinkage` in `_validate_rh3_v3_helper.load_and_prep_rh3_inputs`). Product has same domain (no extra NaN expected); mean-fill applied as belt-and-suspenders.

### Convergence-curve framing (Rule 8)

Eval at all split_days (30/60/90/120). Volume × rate is expected to be strongest at higher split_days where pa_to has spread.

---

## Result — REJECTED (2026-05-24)

### Headline (Rule 9 baseline = full RH3_FEATS)

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended cross_year_r | 0.6165 |
| **Δr** | **−0.0002** |
| Pooled n | 8,275 |

Fails +0.005 gate; pooled is mildly negative.

### Per-year breakdown (Rule 2b)

| Year | Δr | Sign |
|---|---|---|
| 2018 | +0.0000 | 0 |
| 2019 | −0.0007 | − |
| 2021 | +0.0003 | + |
| 2022 | +0.0001 | + |
| 2023 | +0.0001 | + |
| 2024 | +0.0001 | + |
| 2025 | −0.0002 | − |

Positives **4/7** (fails ≥ 5/7). Holdout 1/2.

### Convergence (Rule 8)

Negative at every split_day (30: −0.0009, 60: −0.0005, 90: −0.0003, 120: −0.0006). Pattern is the opposite of what the volume × efficiency theory predicts (would expect lift to grow with split_day).

### Sign sanity

Coef +0.0039 (expected +). Direction OK but magnitude vanishes once Ridge re-balances against pa_to and hr_per_pa_to_sh marginals.

### Why this failed

The two marginals are already in RH3_FEATS and `xwoba_per_pa_to_sh` overlaps the HR/power signal substantially. Ridge can synthesize a near-equivalent rank-ordering from the linear combination once those are present, so the explicit product carries no marginal information.

### Decision

REJECTED. Do not add to RH3_FEATS.

