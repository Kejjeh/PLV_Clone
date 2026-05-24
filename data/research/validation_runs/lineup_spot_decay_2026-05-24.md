---
signal: lineup_spot_decay
formula: lineup_spot_to * exp(-split_day / 30) (smooth exponential decay; weight ≈1 at sd=0, ≈0.37 at sd=30, ≈0.14 at sd=60, ≈0.05 at sd=90, ≈0.018 at sd=120)
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: -
theory: A step-function mask (I[sd≤60] or I[sd≤30]) is a strong assumption that the early-season signal vanishes at a precise cutoff. Reality is more likely continuous decay. An exponential with τ=30 places ~63% of weight in the first 30 days and effectively zero weight past 120, which matches the observed per-cutoff Δr decay pattern (0.0028 → 0.0003 → −0.0006 → −0.0004). The smooth-decay framing gives Ridge a continuously-differentiable signal that lets it find the right intensity without committing to a hard boundary.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_lineup_spot_decay.py
date: 2026-05-24
verdict: MARGINAL
purpose: Smooth-decay sibling to the two step-function candidates. Tests whether the observed cutoff-decay shape is better captured by exp(-sd/30) than by a hard mask. If decay PASSes while masks fail (or vice versa), the result tells us whether the underlying signal is "hard cutoff" or "gradient fade."
---

### Bonferroni / sweep context

Part of the 3-cell piecewise rh3 sweep (see lineup_spot_early_2026-05-24.md).

### Rule 9 baseline

Full RH3_FEATS as of 2026-05-24 (20 features).

### Step 2.5 data-coverage pre-check

`lineup_spot_to` and `split_day` both present. Decay weight is deterministic; no NaN introduction.

### Expected-sign note

Negative coefficient expected. The decay weight is always positive, so the sign comes from lineup_spot_to (1=best, 9=worst → low value = higher FP/PA → negative coef).

### Convergence-curve framing (Rule 8)

Per split_day. Unlike the masks, this is nonzero everywhere — late-cutoff cells contribute a small residual. We expect Δr to track the decay shape: largest at sd=30, smaller at sd=60, near-zero at sd≥90.

---

## Result — MARGINAL (2026-05-24)

### Headline

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended cross_year_r | 0.6182 |
| **Δr** | **+0.0015** |
| Pooled n | 8,275 |

Highest pooled lift of the three (+0.0015 vs +0.0014 mask-60 vs +0.0005 mask-30) but still below the +0.005 gate.

### Per-year breakdown (Rule 2b)

| Year | Δr | Sign |
|---|---|---|
| 2018 | +0.0008 | + |
| 2019 | +0.0010 | + |
| 2021 | +0.0026 | + |
| 2022 | +0.0026 | + |
| 2023 | +0.0011 | + |
| 2024 | +0.0000 | 0 |
| 2025 | +0.0011 | + |

Positives **6/7** (2024 a clean zero, not negative — better than `_early`'s −0.0001 in 2024). Holdout 1/2.

### Convergence (Rule 8)

| split_day | Δr |
|---|---|
| 30 | **+0.0027** |
| 60 | +0.0003 |
| 90 | −0.0006 |
| 120 | −0.0004 |

Same shape as the linear interaction (also +0.0027 / +0.0003 / −0.0006 / −0.0004). The exponential decay at τ=30 still allows late-cutoff cells to contribute small negative Δs (because exp(-90/30)=0.05 isn't quite zero). The 60-day hard mask sets those exactly to zero. Despite this, the smooth-decay pooled lift edges out the mask by +0.0001 — likely Ridge benefiting from a more continuous gradient.

### Sign sanity

Coef −0.0089 (expected −). OK.

### Decision

REJECTED for promotion. Marginally the best of the three piecewise framings pooled, but the gap to the 60-day mask is +0.0001 — within numerical noise. The decay framing and the 60-day mask are effectively tied; both substantially outperform the tight 30-day mask.

### Comparative summary across the 3-cell piecewise sweep

| Framing | Δr pooled | Positives | Holdout | sd=30 cell |
|---|---|---|---|---|
| lineup_spot_early (I[sd≤60]) | +0.0014 | 6/7 | 1/2 | +0.0027 |
| lineup_spot_early_30 (I[sd≤30]) | +0.0005 | 6/7 | **2/2** | +0.0027 |
| lineup_spot_decay (exp(-sd/30)) | **+0.0015** | 6/7 | 1/2 | +0.0027 |

All three reproduce the +0.0027 sd=30 cell. None clears the +0.005 gate. Conclusion: the lineup_spot early-season signal is **real, directionally clean, and stable across framings** but its pooled magnitude (~+0.001-0.0015) is structurally below the production bar in the full-season rh3 setting. The signal exists but is too small to earn promotion.

