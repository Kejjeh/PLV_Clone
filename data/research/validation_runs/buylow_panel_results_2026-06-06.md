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