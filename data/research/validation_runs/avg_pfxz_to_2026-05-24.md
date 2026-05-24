---
signal: avg_pfxz_to
formula: average vertical induced pitch break (feet, Statcast pfx_z), season-to-date, directly from rolling_pitchers_2018_2026.csv
outcome: ros_fp_per_start (rp3 production target)
expected_sign: positive (higher induced vertical break on the fastball → more whiffs up + ground balls down → higher FP/start). Sign may be small or noisy if mix of FF-heavy and SI-heavy pitchers dilutes the average.
theory: Vertical induced movement is a stable stuff signal. None of the current RP3_FEATS encodes pitch shape directly — they're all outcome rates (K%, BB%, swstr%, etc.) or velocity. pfxz is an upstream stuff metric that should add information.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_avg_pfxz_to.py
date: 2026-05-24
verdict: REJECTED
purpose: rp3 v3 ceiling-audit follow-up (2026-05-24). Pitch-shape metrics (pfxz, vaa) were called out as plausibly orthogonal to the outcome-rate features already in RP3_FEATS.
---

# Pre-registration body

## Why this candidate
- Pitch shape (induced vertical break) is structurally upstream of swstr/CSW — adding it could let the GBM correctly weight outcome rates that are skill-anchored vs luck-anchored.
- Note: `avg_pfxz_to` is averaged across the pitcher's entire arsenal, so a pitcher who mixes a high-IVB four-seam with a sinker may show a noisy mid-range value. Single-pitch isolation (FF-only IVB) would be cleaner but isn't currently cached at the rolling-split level.

## Rule 5 sample-size check
- Source column `avg_pfxz_to` non-null on 5462/5462 rolling rows (100%).
- Comfortable clearance.

## Rule 8 framing
- Cumulative season-to-date feature, consistent with framing of `avg_velo_to` already in RP3_FEATS.

## Rule 9 baseline
Full RP3_FEATS (23 features). Lift measured by adding `avg_pfxz_to`.

## Rule 3 / Bonferroni
3 candidates this push. +0.005 gate binding.

## Decision rule
- PASS: lift ≥ +0.005 AND sign ≥ 5/7 years AND holdout lift > 0
- MARGINAL: lift in (0, +0.005] OR fails one of (b)/(c) while clearing (a)
- REJECTED: lift ≤ 0 OR wrong sign overall

If the basic test rejects, may follow up with `abs(avg_pfxz_to)` (magnitude rather than signed value) since both very-high-IVB and very-low-IVB pitchers can succeed (riding fastballs vs heavy sinkers). Not part of this pre-reg.

---

# Results

Ran `scripts/xfp/validate_avg_pfxz_to.py` 2026-05-24.

| Test | Value | Pass? |
|---|---|---|
| Baseline cross_year r (RP3_FEATS, 23 feats) | 0.5509 | — |
| Full cross_year r (+ avg_pfxz_to, 24 feats) | 0.5502 | — |
| **Lift Δr** | **−0.0007** | **FAIL** (gate ≥ +0.005) |
| Sign consistency | 1/7 years positive | FAIL |
| Holdout (2024-2025) avg lift | +0.0001 | PASS sign (trivially) |

**Per-year lift:** 2018: −0.0004, 2019: −0.0001, 2021: −0.0007, 2022: −0.0005, 2023: −0.0016, 2024: +0.0000, 2025: +0.0002.

**Data:** 100% non-null (5462/5462), so the fill is cosmetic. n=4174.

## Verdict — REJECTED

`avg_pfxz_to` is **net-negative on lift** and **monotonically wrong-signed** across 6 of 7 training years. The signed-average vertical break across a pitcher's entire arsenal mixes high-IVB four-seamers with heavy sinkers, producing a noisy mid-range value that — when handed to a GBM that already has all the downstream outcome rates (`swstr_pct_to_sh`, `c_plus_swstr_to_sh`, `xwoba_per_pa_to_sh`) — appears to act as a distraction rather than a signal.

The outcome rates downstream of pitch shape are already in the model; adding the upstream shape itself without disambiguating which pitch it's on is worse than not having it.

**Not promoted.** Documented per Rule 6. The hypothesis is not fully closed — a follow-up with `abs(avg_pfxz_to)` (magnitude) or pitch-type-isolated FF-only IVB might salvage the underlying theory. But the simple signed arsenal-average is dead.
