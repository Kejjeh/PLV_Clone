# Projection Accuracy Report

**Generated:** 2026-06-17  
**Source:** `data/outputs/predictions_history.csv`  
**Backfilled rows:** 150  
**Minimum N per bucket to trust:** 5

## 1. Periods covered

| Period | n rows | my_final | opp_final | model_versions |
|---|---|---|---|---|
| 2 | 7 | 500.6 | 543.8 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 3 | 7 | 521.5 | 579.5 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 4 | 7 | 516.0 | 531.8 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 5 | 7 | 448.9 | 450.2 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 6 | 7 | 484.8 | 552.9 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 7 | 16 | 351.0 | 300.0 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline_pre_versioning |
| 8 | 7 | 542.7 | 453.0 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 9 | 7 | 587.0 | 543.0 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 10 | 7 | 472.3 | 487.2 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 11 | 7 | 450.8 | 493.3 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 12 | 7 | 406.5 | 479.2 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 13 | 7 | 603.7 | 512.6 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 14 | 7 | 563.1 | 429.5 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 15 | 7 | 562.5 | 443.9 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 16 | 7 | 790.5 | 712.3 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 17 | 7 | 349.7 | 680.9 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 18 | 7 | 540.4 | 408.2 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 19 | 7 | 553.3 | 540.0 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 20 | 7 | 418.0 | 518.0 | backfill_2024_bayes_shrink, backfill_2025_bayes_shrink |
| 21 | 4 | 395.0 | 317.0 | backfill_2024_bayes_shrink |
| 22 | 4 | 290.6 | 379.3 | backfill_2024_bayes_shrink |

## 2. Error metrics — all snapshots

Error = projected − actual. Bias > 0 means model over-projects.

| Model | n | my MAE | my RMSE | my bias | opp MAE | opp RMSE | opp bias |
|---|---|---|---|---|---|---|---|
| `backfill_2024_bayes_shrink` | 84 | 74.4 | 133.3 | -43.5 | 72.4 | 135.2 | -53.2 |
| `backfill_2025_bayes_shrink` | 57 | 70.9 | 104.2 | -30.9 | 74.0 | 104.2 | -45.2 |
| `baseline_pre_versioning` | 9 | 56.1 | 58.7 | -56.1 | 27.3 | 28.9 | -27.3 |

## 3. Error metrics — latest snapshot per (period, model)

This is the "what the dashboard showed at end of week" view.

| Period | Model | proj my | actual my | err my | proj opp | actual opp | err opp |
|---|---|---|---|---|---|---|---|
| 2 | `backfill_2024_bayes_shrink` | 0.0 | 607.1 | -607.1 | 0.0 | 540.9 | -540.9 |
| 2 | `backfill_2025_bayes_shrink` | 349.0 | 522.8 | -173.8 | 321.8 | 572.7 | -250.9 |
| 3 | `backfill_2024_bayes_shrink` | 273.0 | 321.7 | -48.7 | 283.7 | 277.4 | +6.3 |
| 3 | `backfill_2025_bayes_shrink` | 403.7 | 458.4 | -54.7 | 431.4 | 439.4 | -8.0 |
| 4 | `backfill_2024_bayes_shrink` | 293.9 | 410.1 | -116.2 | 288.7 | 338.2 | -49.5 |
| 4 | `backfill_2025_bayes_shrink` | 427.0 | 520.1 | -93.1 | 462.4 | 458.8 | +3.6 |
| 5 | `backfill_2024_bayes_shrink` | 329.6 | 462.7 | -133.1 | 301.7 | 336.2 | -34.5 |
| 5 | `backfill_2025_bayes_shrink` | 493.0 | 434.3 | +58.7 | 467.6 | 454.2 | +13.4 |
| 6 | `backfill_2024_bayes_shrink` | 349.8 | 363.8 | -14.0 | 314.7 | 383.9 | -69.2 |
| 6 | `backfill_2025_bayes_shrink` | 485.6 | 534.1 | -48.5 | 497.4 | 548.0 | -50.6 |
| 7 | `backfill_2024_bayes_shrink` | 315.6 | 429.1 | -113.5 | 322.9 | 386.7 | -63.8 |
| 7 | `backfill_2025_bayes_shrink` | 457.7 | 442.0 | +15.7 | 506.2 | 578.1 | -71.9 |
| 7 | `baseline_pre_versioning` | 323.7 | 351.0 | -27.3 | 281.5 | 300.0 | -18.5 |
| 8 | `backfill_2024_bayes_shrink` | 327.7 | 349.2 | -21.5 | 315.1 | 373.6 | -58.5 |
| 8 | `backfill_2025_bayes_shrink` | 457.7 | 432.7 | +25.0 | 465.5 | 541.2 | -75.7 |
| 9 | `backfill_2024_bayes_shrink` | 310.5 | 331.7 | -21.2 | 321.1 | 445.8 | -124.7 |
| 9 | `backfill_2025_bayes_shrink` | 481.7 | 565.7 | -84.0 | 473.0 | 393.7 | +79.3 |
| 10 | `backfill_2024_bayes_shrink` | 313.4 | 344.1 | -30.7 | 356.7 | 288.4 | +68.3 |
| 10 | `backfill_2025_bayes_shrink` | 489.7 | 528.6 | -38.9 | 502.3 | 521.2 | -18.9 |
| 11 | `backfill_2024_bayes_shrink` | 310.1 | 374.3 | -64.2 | 351.4 | 454.1 | -102.7 |
| 11 | `backfill_2025_bayes_shrink` | 531.4 | 565.0 | -33.6 | 504.1 | 477.6 | +26.5 |
| 12 | `backfill_2024_bayes_shrink` | 314.9 | 256.8 | +58.1 | 348.5 | 375.4 | -26.9 |
| 12 | `backfill_2025_bayes_shrink` | 533.9 | 502.5 | +31.4 | 461.2 | 489.8 | -28.6 |
| 13 | `backfill_2024_bayes_shrink` | 338.7 | 415.2 | -76.5 | 350.5 | 371.7 | -21.2 |
| 13 | `backfill_2025_bayes_shrink` | 458.5 | 431.0 | +27.5 | 462.7 | 507.1 | -44.4 |
| 14 | `backfill_2024_bayes_shrink` | 343.9 | 314.0 | +29.9 | 329.9 | 402.9 | -73.0 |
| 14 | `backfill_2025_bayes_shrink` | 457.1 | 402.8 | +54.3 | 491.8 | 631.1 | -139.3 |
| 15 | `backfill_2024_bayes_shrink` | 331.1 | 412.4 | -81.3 | 320.4 | 236.9 | +83.5 |
| 15 | `backfill_2025_bayes_shrink` | 510.6 | 527.3 | -16.6 | 500.1 | 548.3 | -48.2 |
| 16 | `backfill_2024_bayes_shrink` | 332.0 | 426.7 | -94.7 | 318.8 | 484.2 | -165.4 |
| 16 | `backfill_2025_bayes_shrink` | 511.9 | 950.3 | -438.4 | 529.6 | 666.4 | -136.8 |
| 17 | `backfill_2024_bayes_shrink` | 363.5 | 403.0 | -39.5 | 328.9 | 315.0 | +13.9 |
| 17 | `backfill_2025_bayes_shrink` | 494.2 | 402.5 | +91.7 | 539.6 | 564.0 | -24.4 |
| 18 | `backfill_2024_bayes_shrink` | 365.7 | 245.6 | +120.1 | 326.2 | 262.6 | +63.6 |
| 18 | `backfill_2025_bayes_shrink` | 489.5 | 370.9 | +118.6 | 474.4 | 384.8 | +89.6 |
| 19 | `backfill_2024_bayes_shrink` | 360.2 | 386.5 | -26.3 | 323.0 | 303.8 | +19.2 |
| 19 | `backfill_2025_bayes_shrink` | 505.7 | 457.4 | +48.3 | 469.6 | 429.0 | +40.6 |
| 20 | `backfill_2024_bayes_shrink` | 361.5 | 309.6 | +51.9 | 358.0 | 359.0 | -1.0 |
| 20 | `backfill_2025_bayes_shrink` | 503.3 | 488.2 | +15.1 | 527.3 | 632.1 | -104.8 |
| 21 | `backfill_2024_bayes_shrink` | 344.3 | 362.4 | -18.1 | 357.9 | 385.6 | -27.7 |
| 22 | `backfill_2024_bayes_shrink` | 359.0 | 379.2 | -20.2 | 322.9 | 400.3 | -77.4 |

## 4. Win-probability calibration

Buckets on raw `win_probability`. A well-calibrated model has mean predicted ≈ actual win rate. Buckets with N < 5 are flagged INSUFFICIENT.

### `backfill_2024_bayes_shrink` (n=84)

| Bucket | n | mean predicted | actual win rate | abs gap | status |
|---|---|---|---|---|---|
| 0.00-0.25 | 0 | — | — | — | empty |
| 0.25-0.50 | 39 | 0.467 | 0.385 | 0.083 | OK |
| 0.50-0.75 | 45 | 0.536 | 0.489 | 0.047 | OK |
| 0.75-1.00 | 0 | — | — | — | empty |

### `backfill_2025_bayes_shrink` (n=57)

| Bucket | n | mean predicted | actual win rate | abs gap | status |
|---|---|---|---|---|---|
| 0.00-0.25 | 0 | — | — | — | empty |
| 0.25-0.50 | 29 | 0.408 | 0.310 | 0.098 | OK |
| 0.50-0.75 | 26 | 0.589 | 0.500 | 0.089 | OK |
| 0.75-1.00 | 2 | 0.760 | 1.000 | 0.240 | INSUFFICIENT |

### `baseline_pre_versioning` (n=9)

| Bucket | n | mean predicted | actual win rate | abs gap | status |
|---|---|---|---|---|---|
| 0.00-0.25 | 0 | — | — | — | empty |
| 0.25-0.50 | 0 | — | — | — | empty |
| 0.50-0.75 | 7 | 0.642 | 1.000 | 0.358 | OK |
| 0.75-1.00 | 2 | 0.953 | 1.000 | 0.047 | INSUFFICIENT |

## 5. Verdict

At least one bucket has N ≥ 5. See `data/outputs/calibration_summary.json` for the machine-readable summary consumed by the calibration gate.


---

Re-generated by `scripts/xfp/report_calibration.py` — overwritten on every refresh.
