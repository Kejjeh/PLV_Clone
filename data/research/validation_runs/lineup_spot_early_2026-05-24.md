---
signal: lineup_spot_early
formula: lineup_spot_to * I[split_day <= 60] (binary mask; on early-season, off after day 60)
outcome: ros_full_fp_per_pa (within-year, post-cutoff)
expected_sign: -
theory: lineup_spot_to alone was MARGINAL (+0.0009, 2026-05-23) with all lift concentrated at split_day=30 (+0.0028) and decaying to zero by split_day=60. The linear `lineup_spot_to * split_day` interaction (2026-05-24) was REJECTED (−0.0001) — Ridge cannot extract a step-function relationship from a monotone linear product because the late-season cells drag the slope. A piecewise binary mask explicitly tells the model "this signal exists only when split_day ≤ 60." If the underlying mid-season decay is genuinely step-function shaped (rather than linear), this framing should rescue the early-season lift in the pooled eval.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_lineup_spot_early.py
date: 2026-05-24
verdict: MARGINAL
purpose: Piecewise rescue round (rh3). The 2026-05-24 linear interaction sweep memo explicitly recommended this framing: "Research-worthy as a piecewise / bucketed candidate: try `lineup_spot_to * I[split_day <= 60]`." This pre-reg executes that recommendation.
---

### Bonferroni / sweep context

3-cell piecewise sweep (rh3):
- lineup_spot_early (this file; I[split_day≤60] mask)
- lineup_spot_early_30 (tighter I[split_day≤30] mask)
- lineup_spot_decay (smooth exp(-split_day/30))

All three frame the same underlying hypothesis (early-season-only lineup-spot signal). Per Rule 3, per-cell α=0.05 → α=0.0167. We report effect-size-based Δr.

### Rule 9 baseline

Full RH3_FEATS as of 2026-05-24 (20 features). `split_day` IS in baseline; `lineup_spot_to` is NOT (rejected MARGINAL 2026-05-23). Candidate added on top — Δr is true incremental lift.

### Step 2.5 data-coverage pre-check

`lineup_spot_to` and `split_day` both present in `rolling_hitters_2018_2026.csv`. Mask is deterministic from `split_day` and incurs no missingness.

### Expected-sign note

Lower lineup_spot_to value = closer to leadoff = more PA/SB/R opportunity. Coefficient should be negative for FP/PA target (a 1-spot increase in lineup spot in the early window predicts lower FP/PA RoS).

### Convergence-curve framing (Rule 8)

Per split_day at 30/60/90/120. By construction the column is zero at split_day > 60 — late-cutoff cells should look identical to baseline (Δr ≈ 0). The 30 and 60 cells are the load-bearing ones. The test is whether pooled lift reaches +0.005 without the late-season drag the linear interaction suffered.

---

## Result — MARGINAL (2026-05-24)

### Headline (Rule 9 baseline = full RH3_FEATS, 20 features)

| Metric | Value |
|---|---|
| Baseline cross_year_r | 0.6167 |
| Extended cross_year_r | 0.6181 |
| **Δr** | **+0.0014** |
| Pooled n | 8,275 |

Below +0.005 production gate → MARGINAL, not promoted. But this is the **strongest pooled lift** any lineup_spot framing has produced (vs +0.0009 for the raw column and −0.0001 for the linear interaction).

### Per-year breakdown (Rule 2b)

| Year | Δr | Sign |
|---|---|---|
| 2018 | +0.0012 | + |
| 2019 | +0.0007 | + |
| 2021 | +0.0026 | + |
| 2022 | +0.0010 | + |
| 2023 | +0.0024 | + |
| 2024 | −0.0001 | − |
| 2025 | +0.0015 | + |

Positives **6/7** (clears Rule 2b cleanly, up from 5/7 on the raw column). Holdout 1/2 — 2024 still ~flat.

### Convergence (Rule 8)

| split_day | Δr |
|---|---|
| 30 | **+0.0027** |
| 60 | +0.0003 |
| 90 | +0.0000 |
| 120 | +0.0000 |

Mask works as designed: late-cutoff cells are exactly zero contribution (Δ=0.0000), and the +0.0027 split_day=30 lift is captured pooled without late-season drag. **This is the framing that captures the +0.0027 signal in pooled form.** Linear interaction had pooled Δr −0.0001 because the 2024 late-season cells went negative; the mask eliminates that drag.

### Sign sanity

Coef −0.0083 (expected −). OK.

### Decision

REJECTED for promotion (Δr +0.0014 < +0.005), but this framing **successfully rescues the early-season signal** that the linear interaction could not. Best lineup_spot framing tested to date. The signal exists and is directionally clean — it's simply too small (~+0.001-0.002 pooled) to clear the production bar against the 20-feature baseline.

### Future re-test viability

If rh3 ever spawns an early-season variant (e.g. `xfp_rh3_april` trained only on split_day ≤ 30 cells), the +0.0027 lift would clear the bar trivially. Within the full-season rh3 framing, the mask dilutes the signal across 78% zero-contribution rows.

