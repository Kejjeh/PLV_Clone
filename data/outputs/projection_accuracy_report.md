# Projection Accuracy Report

**Generated:** 2026-07-21  
**Source:** `data/outputs/predictions_history.csv`  
**Backfilled rows:** 444  
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
| 8 | 49 | 364.2 | 289.8 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline, baseline_pre_versioning |
| 9 | 39 | 312.1 | 292.1 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline |
| 10 | 43 | 262.6 | 343.4 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline |
| 11 | 11 | 450.8 | 493.3 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline |
| 12 | 81 | 406.5 | 479.2 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline |
| 13 | 35 | 603.7 | 512.6 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline |
| 14 | 37 | 563.1 | 429.5 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline |
| 15 | 53 | 562.5 | 443.9 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline |
| 16 | 9 | 790.5 | 712.3 | MA_v1, backfill_2024_bayes_shrink, backfill_2025_bayes_shrink, baseline |
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
| `MA_v1` | 139 | 133.5 | 163.0 | +132.4 | 145.9 | 176.9 | +137.0 |
| `backfill_2024_bayes_shrink` | 84 | 74.4 | 133.3 | -43.5 | 72.4 | 135.2 | -53.2 |
| `backfill_2025_bayes_shrink` | 57 | 70.9 | 104.2 | -30.9 | 74.0 | 104.2 | -45.2 |
| `baseline` | 139 | 112.9 | 141.6 | +109.2 | 127.8 | 152.9 | +110.5 |
| `baseline_pre_versioning` | 25 | 37.1 | 44.3 | -33.0 | 39.2 | 44.6 | +12.4 |

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
| 8 | `MA_v1` | 362.0 | 364.2 | -2.2 | 346.4 | 289.8 | +56.6 |
| 8 | `backfill_2024_bayes_shrink` | 327.7 | 349.2 | -21.5 | 315.1 | 373.6 | -58.5 |
| 8 | `backfill_2025_bayes_shrink` | 457.7 | 432.7 | +25.0 | 465.5 | 541.2 | -75.7 |
| 8 | `baseline` | 352.7 | 364.2 | -11.5 | 338.0 | 289.8 | +48.2 |
| 8 | `baseline_pre_versioning` | 342.9 | 364.2 | -21.2 | 341.7 | 289.8 | +51.9 |
| 9 | `MA_v1` | 308.1 | 312.1 | -4.0 | 288.8 | 292.1 | -3.3 |
| 9 | `backfill_2024_bayes_shrink` | 310.5 | 331.7 | -21.2 | 321.1 | 445.8 | -124.7 |
| 9 | `backfill_2025_bayes_shrink` | 481.7 | 565.7 | -84.0 | 473.0 | 393.7 | +79.3 |
| 9 | `baseline` | 301.8 | 312.1 | -10.3 | 282.4 | 292.1 | -9.7 |
| 10 | `MA_v1` | 315.2 | 262.6 | +52.6 | 404.9 | 343.4 | +61.5 |
| 10 | `backfill_2024_bayes_shrink` | 313.4 | 344.1 | -30.7 | 356.7 | 288.4 | +68.3 |
| 10 | `backfill_2025_bayes_shrink` | 489.7 | 528.6 | -38.9 | 502.3 | 521.2 | -18.9 |
| 10 | `baseline` | 310.0 | 262.6 | +47.4 | 397.9 | 343.4 | +54.5 |
| 11 | `MA_v1` | 578.3 | 319.6 | +258.7 | 602.3 | 324.4 | +277.9 |
| 11 | `backfill_2024_bayes_shrink` | 310.1 | 374.3 | -64.2 | 351.4 | 454.1 | -102.7 |
| 11 | `backfill_2025_bayes_shrink` | 531.4 | 565.0 | -33.6 | 504.1 | 477.6 | +26.5 |
| 11 | `baseline` | 536.0 | 319.6 | +216.4 | 548.6 | 324.4 | +224.2 |
| 12 | `MA_v1` | 338.6 | 294.6 | +44.0 | 393.4 | 385.0 | +8.4 |
| 12 | `backfill_2024_bayes_shrink` | 314.9 | 256.8 | +58.1 | 348.5 | 375.4 | -26.9 |
| 12 | `backfill_2025_bayes_shrink` | 533.9 | 502.5 | +31.4 | 461.2 | 489.8 | -28.6 |
| 12 | `baseline` | 327.9 | 294.6 | +33.3 | 387.3 | 385.0 | +2.3 |
| 13 | `MA_v1` | 395.3 | 322.1 | +73.2 | 409.5 | 331.3 | +78.2 |
| 13 | `backfill_2024_bayes_shrink` | 338.7 | 415.2 | -76.5 | 350.5 | 371.7 | -21.2 |
| 13 | `backfill_2025_bayes_shrink` | 458.5 | 431.0 | +27.5 | 462.7 | 507.1 | -44.4 |
| 13 | `baseline` | 391.2 | 322.1 | +69.1 | 401.4 | 331.3 | +70.1 |
| 14 | `MA_v1` | 315.9 | 306.5 | +9.4 | 374.2 | 362.3 | +11.9 |
| 14 | `backfill_2024_bayes_shrink` | 343.9 | 314.0 | +29.9 | 329.9 | 402.9 | -73.0 |
| 14 | `backfill_2025_bayes_shrink` | 457.1 | 402.8 | +54.3 | 491.8 | 631.1 | -139.3 |
| 14 | `baseline` | 311.9 | 306.5 | +5.4 | 365.0 | 362.3 | +2.7 |
| 15 | `MA_v1` | 975.1 | 552.1 | +423.0 | 1016.0 | 581.4 | +434.6 |
| 15 | `backfill_2024_bayes_shrink` | 331.1 | 412.4 | -81.3 | 320.4 | 236.9 | +83.5 |
| 15 | `backfill_2025_bayes_shrink` | 510.6 | 527.3 | -16.6 | 500.1 | 548.3 | -48.2 |
| 15 | `baseline` | 930.8 | 552.1 | +378.7 | 965.7 | 581.4 | +384.3 |
| 16 | `MA_v1` | 414.8 | 43.8 | +371.0 | 322.1 | 31.2 | +290.9 |
| 16 | `backfill_2024_bayes_shrink` | 332.0 | 426.7 | -94.7 | 318.8 | 484.2 | -165.4 |
| 16 | `backfill_2025_bayes_shrink` | 511.9 | 950.3 | -438.4 | 529.6 | 666.4 | -136.8 |
| 16 | `baseline` | 369.0 | 43.8 | +325.2 | 275.2 | 31.2 | +244.0 |
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

### `MA_v1` (n=139)

| Bucket | n | mean predicted | actual win rate | abs gap | status |
|---|---|---|---|---|---|
| 0.00-0.25 | 72 | 0.065 | 0.014 | 0.051 | OK |
| 0.25-0.50 | 28 | 0.331 | 0.107 | 0.224 | OK |
| 0.50-0.75 | 19 | 0.599 | 0.368 | 0.230 | OK |
| 0.75-1.00 | 20 | 0.857 | 1.000 | 0.143 | OK |

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

### `baseline` (n=139)

| Bucket | n | mean predicted | actual win rate | abs gap | status |
|---|---|---|---|---|---|
| 0.00-0.25 | 73 | 0.080 | 0.014 | 0.067 | OK |
| 0.25-0.50 | 24 | 0.361 | 0.000 | 0.361 | OK |
| 0.50-0.75 | 24 | 0.613 | 0.500 | 0.113 | OK |
| 0.75-1.00 | 18 | 0.841 | 1.000 | 0.159 | OK |

### `baseline_pre_versioning` (n=25)

| Bucket | n | mean predicted | actual win rate | abs gap | status |
|---|---|---|---|---|---|
| 0.00-0.25 | 0 | — | — | — | empty |
| 0.25-0.50 | 6 | 0.447 | 1.000 | 0.553 | OK |
| 0.50-0.75 | 11 | 0.594 | 1.000 | 0.406 | OK |
| 0.75-1.00 | 8 | 0.889 | 1.000 | 0.111 | OK |

## 5. Verdict

At least one bucket has N ≥ 5. See `data/outputs/calibration_summary.json` for the machine-readable summary consumed by the calibration gate.


---

Re-generated by `scripts/xfp/report_calibration.py` — overwritten on every refresh.
