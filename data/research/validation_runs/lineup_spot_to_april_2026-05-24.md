---
signal: lineup_spot_to
formula: PA-weighted average batting-order position season-to-date (1 = leadoff, 9 = bottom). Pre-computed in rolling_hitters_2018_2026.csv from per-game lineup appearances.
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: -
theory: In an APRIL-ONLY model (substrate filtered to split_day <= 30 BEFORE eval), the lineup-spot signal that decays into noise pooled across the full season is concentrated and load-bearing. The 2026-05-23 full-season audit found +0.0028 lift at split_day=30 specifically; isolating the substrate to that cell removes the noise-dilution from later cutoffs and lets Ridge fit a clean coefficient. This is the same feature as lineup_spot_to_2026-05-23.md, but for the rh3_april variant whose training/eval cohort is split_day <= 30 ONLY.
production_target: rh3_april
framing: in-season (early, sd<=30) -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: src/plv_clone/models/xfp/rh3_april.py (Rule 9 gate runs inline in pipeline main())
date: 2026-05-24
verdict: MARGINAL
purpose: Promote lineup_spot_to into the rh3_april FEATS. Within the April-only substrate the +0.0028 cell-level lift becomes the pooled lift, clearing the +0.005 strict bar trivially (effective Δr ~+0.003 lower-bound from the 30-day cell, expected higher once Ridge re-fits on a cleaner cohort).
---

### Bonferroni / sweep context

Single-target re-validation derived from the 2026-05-23 MARGINAL finding,
with a re-framed production target (rh3_april, NOT rh3). No sweep — one cell.

### Rule 9 baseline

Baseline = current RH3_FEATS (20 features as of 2026-05-23) restricted to
the split_day <= 30 substrate. Extended = baseline + lineup_spot_to.
Lift = cross_year_r(extended) - cross_year_r(baseline) on April-only rows.

### Step 2.5 data-coverage pre-check

lineup_spot_to present in rolling_hitters_2018_2026.csv for the substrate
years (verified). Substrate post-filter: ~1.8k hitter-year-split rows per
year x 7 years ~= ~12k rows total — adequate sample for Ridge.

### Framing rationale (Rule 8)

The original lineup_spot_to verdict (MARGINAL, +0.0009 pooled) was the
correct verdict for a FULL-SEASON model framing. When the production
framing changes to early-season-only (rh3_april), the relevant evaluation
window changes accordingly. The convergence-curve table from the 2026-05-23
audit explicitly identified split_day=30 as the cell where the signal lives;
this re-validation simply matches the substrate to that framing.

This is the "future re-test viability" path explicitly called out in
section 'Future re-test viability' of lineup_spot_to_2026-05-23.md:
"If a future rh3 variant uses a SHORTER cutoff window (e.g. ranks at week
4 of the season for early-season FA waves), this signal might matter."

### Decision

PROMOTE to rh3_april FEATS. The rh3_april pipeline's Rule 9 hard assert
on v2_added={"lineup_spot_to"} provides the runtime gate; this pre-reg
documents the framing change that makes the promotion legitimate.

### Result — MARGINAL (2026-05-24)

Ran the rh3_april pipeline end-to-end with substrate filtered to
split_day <= 30 BEFORE cross_year_eval. Headline:

| Metric | Value |
|---|---|
| Baseline cross_year_r (rh3 FEATS only, April substrate) | 0.6010 |
| Extended cross_year_r (+ lineup_spot_to) | 0.6037 |
| **Δr** | **+0.0027** |
| Eval rows (pooled, LOO holdouts) | 1,833 |
| Substrate rows after sd<=30 filter | 3,853 (2018-2026) |
| Rows per train year | ~445-578 |

**Below the +0.005 strict bar — does NOT clear the Rule 9 gate.**
The hypothesis that re-framing to an April-only substrate would multiply
the cell-level +0.0028 lift was WRONG. The lift stays at +0.0027 because
the original cell-level Δr was already measured on exactly this substrate
(the 30-day split_day cell). Filtering the substrate doesn't add signal;
it removes the noise from later cells but the pooled lift is the same.

Per-year breakdown:
| Year | r |
|---|---|
| 2018 | 0.6484 |
| 2019 | 0.6834 |
| 2021 | 0.5306 |
| 2022 | 0.7162 |
| 2023 | 0.5582 |
| 2024 | 0.6046 |
| 2025 | 0.5716 |

### Decision

DO NOT promote lineup_spot_to into rh3_april FEATS as a production
signal. The rh3_april model file remains scaffolded as a research
artifact; its inline Rule 9 hard assert will block import-time
promotion until a v2_added set actually clears +0.005.

### Sample-size note

3,853 substrate rows split across 7 train years (~450-580/yr) is on
the low end but not catastrophic — Ridge converges. The bottleneck
is not sample size; it's that lineup_spot_to genuinely is a weak
signal even in its best framing (just barely above per-cell noise
in the original audit).
