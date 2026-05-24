---
signal: lineup_spot_early_30
formula: lineup_spot_to * I[split_day <= 30] (tight binary mask; on at the earliest cutoff only)
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: -
theory: The +0.0028 lift on lineup_spot_to (2026-05-23) and +0.0027 lift on the linear interaction (2026-05-24) were both concentrated at split_day=30 specifically. By split_day=60 the per-cell Δr is already +0.0003 (noise). A tight I[split_day ≤ 30] mask isolates the genuine signal cell without including the noisy 31–60 day cells that the wider mask would still pool over. Risk: smaller nonzero count may not give Ridge enough signal to move pooled r.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_lineup_spot_early_30.py
date: 2026-05-24
verdict: MARGINAL
purpose: Tighter-window companion to lineup_spot_early. Tests whether the early-season signal is "first month only" vs "first two months." If `_30` outperforms `_early` (60-day), this confirms the signal is razor-thin to opening day; if `_early` outperforms, the 30-day cell was lucky and the broader mask is preferred.
---

### Bonferroni / sweep context

Part of the 3-cell piecewise rh3 sweep (see lineup_spot_early_2026-05-24.md).

### Rule 9 baseline

Full RH3_FEATS as of 2026-05-24 (20 features).

### Step 2.5 data-coverage pre-check

`lineup_spot_to` and `split_day` both present. Mask deterministic. Nonzero rows will be only the split_day=30 cell (~1833 rows of 8275 = 22%).

### Expected-sign note

Negative coefficient expected (lower lineup spot = better hitter; FP/PA target).

### Convergence-curve framing (Rule 8)

Per split_day. Expect Δr ≈ 0 at sd>30 by construction. Load-bearing cell is sd=30.

---

## Result — MARGINAL (2026-05-24)

### Headline

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended cross_year_r | 0.6172 |
| **Δr** | **+0.0005** |
| Pooled n | 8,275 |

Right at the +0.005 gate boundary but rounds below. Smallest pooled lift of the three piecewise candidates.

### Per-year breakdown (Rule 2b)

| Year | Δr | Sign |
|---|---|---|
| 2018 | +0.0002 | + |
| 2019 | +0.0002 | + |
| 2021 | +0.0008 | + |
| 2022 | +0.0011 | + |
| 2023 | −0.0003 | − |
| 2024 | +0.0006 | + |
| 2025 | +0.0002 | + |

Positives **6/7**. **Holdout 2/2** — only candidate this round with full holdout coverage. But all per-year magnitudes are tiny.

### Convergence (Rule 8)

| split_day | Δr |
|---|---|
| 30 | **+0.0027** |
| 60 | +0.0000 |
| 90 | +0.0000 |
| 120 | +0.0000 |

Same +0.0027 at sd=30 as the wider mask. By construction sd>30 cells contribute exactly 0. The signal is genuinely concentrated at the 30-day cutoff.

### Sign sanity

Coef −0.0040 (expected −). OK. Smaller magnitude than `_early` because the mask covers fewer rows.

### Decision

REJECTED for promotion. The tight mask hits only 22% of training rows (4172/8275), too few to move pooled r meaningfully despite the per-cell signal being real. The wider 60-day mask gets nearly 3× the pooled lift (+0.0014 vs +0.0005) by capturing the small residual 31–60 day contribution and improving Ridge's coefficient estimate from a larger nonzero sample.

**Conclusion:** wider window > tighter window for pooled eval. The signal is "first ~6 weeks fading," not "first month only."

