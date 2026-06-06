# BUY-LOW signal validation results — 2026-06-06

Pre-registration: `data/research/validation_runs/buylow_panel_prereg_2026-06-06.md`

## Verdict: **FAIL**

### Pass-criterion failures:
- mean_residual=-0.06883613565330789 < +0.015 FP/PA
- CI lower bound=-0.1142068463016126 <= 0

## Pass criteria (from pre-reg)
- Pooled mean residual >= +0.015 FP/PA
- Pooled 95% CI lower bound > 0
- Pooled N >= 30
- No sign flip between 2024 and 2025 means

## Pooled summary
- N: 71
- Mean residual: -0.06883613565330789
- SD: 0.19505122614186887
- 95% CI: [-0.1142068463016126, -0.023465425005003177]

## Per-year summary
### 2024
- N: 34
- Mean residual: -0.07817766947313678
- 95% CI: [-0.1510988479584654, -0.005256490987808171]

### 2025
- N: 37
- Mean residual: -0.060252023494546204
- 95% CI: [-0.11668933786913807, -0.0038147091199543445]

## Per-as-of-date detail

| Year | Anchor | Snapshot | Gap (d) | Status | N flagged | N w/ forward | Mean residual |
|------|--------|----------|---------|--------|-----------|--------------|---------------|
| 2024 | 2024-04-27 | 2024-04-27 | 0 | ok | 7 | 5 | -0.0590 |
| 2024 | 2024-05-27 | 2024-05-27 | 0 | ok | 12 | 8 | -0.0504 |
| 2024 | 2024-06-26 | 2024-06-26 | 0 | ok | 19 | 12 | -0.1030 |
| 2024 | 2024-07-26 | 2024-07-26 | 0 | ok | 14 | 9 | -0.0804 |
| 2025 | 2025-04-26 | 2025-04-26 | 0 | ok | 9 | 7 | -0.0172 |
| 2025 | 2025-05-26 | 2025-05-26 | 0 | ok | 12 | 9 | -0.1332 |
| 2025 | 2025-06-25 | 2025-06-25 | 0 | ok | 17 | 10 | 0.0333 |
| 2025 | 2025-07-25 | 2025-07-25 | 0 | ok | 15 | 11 | -0.1130 |

## Audit trail

Verdict is FAIL. Per plan v11 Decision 12, `buylow_flag` will NOT be
added to the production process-panel CSV. The BUY-LOW conjecture as
pre-registered (composite_pct >= 0.75 AND rh3_pct <= 0.25) does not
predict positive T+30 to T+60 residual vs the model at the bar required
by the 9-rule multi-testing protocol.

## Final verdict — REJECTED

**Status:** REJECTED. The BUY-LOW signal as pre-registered is permanently
archived. The headline finding goes the opposite direction of the conjecture:
the pooled point estimate is **−0.069 FP/PA** (95% CI fully below zero), and
all four pre-reg pass criteria fail except the "no sign flip" check (both
years agree negative — which strengthens, rather than rescues, the rejection).

**Why this fired the wrong way:** "high process composite + low rh3" is not a
hidden-skill flag — it's most often a hitter whose 9-marker composite is
inflated by recent-window K%/whiff or contact-volume that the rh3 model has
already correctly de-rated through its career-stage and prior-FP-per-PA
features. The model wins this fight; the composite is the noisy signal.

**Shipping decision:**
- NO `buylow_flag` column added to `xfp_rh3_projections.csv` or any other
  production CSV in this PR.
- NO `buylow_flag` column added to `hitter_process_panel.csv`. The PR 8
  process-panel build code already asserts `buylow_flag not in panel` per
  plan v11 Decision 12 — that guard stays in place.
- The `composite` and `level_pct` columns continue to ship as research
  outputs in the panel, available for downstream `/triangulate`-style
  diagnostic use, but not as a verdict-driving flag.

**What a future BUY-LOW signal would need to clear:**
1. A different cut (e.g., narrower percentile bounds, gating on K%-controlled
   composite, longer T+ window, or a position-specific stratification) — but
   any new cut requires a fresh pre-registration, fresh dates, no peeking at
   this dataset's results.
2. Bonferroni penalty for the multiple-hypothesis search across cuts must be
   applied honestly — this single rejected hypothesis already burns one
   degree of freedom against any future re-test.
3. Convergence-curve test (see `feedback_convergence_curve_leakage_detector.md`):
   identical lifts across split_day 30/42/56 = leakage smoking gun. Any future
   BUY-LOW candidate must show DIFFERENT lifts at different forward windows
   to avoid the H1-class leakage that contaminated PL-feature signals 2026-05-27.

**Parallel finding worth recording:** the 8/8 as-of dates produced 71 eligible
candidates (≥30 forward PA each) across both years — sample size was NOT the
bottleneck. The signal is genuinely null-to-negative, not under-powered.

This rejection joins the pattern of healthy null results — e.g., the closer-IL
bundle REJECTED at 2026-06-06 — that keep the production signal registry
clean.