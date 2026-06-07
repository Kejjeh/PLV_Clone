# Shrinkage k Calibration — 2023 holdout (out-of-sample)

## Method
- Candidate pool: top 200 hitters + top 100 SPs by 2022 Statcast volume,
  then re-ranked inside the pool by 2022 actual FP per game / per start
  to define top50 vs lower tiers (NOT 2026 rh3/rp3 — eliminates the
  selection-bias path where current form drives 2023 inclusion).
- as_of dates: 2023-05-01, 2023-06-01, 2023-07-01, 2023-08-01, 2023-09-01, 2023-05-20
- Prior seasons used: 2021, 2022
- Hitter snapshots: **996**  |  SP snapshots: **357**
- Predictors: pure L21, pure L42, pure prior, shrink k in [20, 40, 80, 150, 300, 500], two-year prior shrunk k=80

## Hitter results

### Pooled
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.934 | 1.191 | -0.484 | 0.747 | 996 |
| pure prior year | 0.683 | 0.859 | 0.227 | 0.582 | 996 |
| pure L42 | 0.800 | 1.011 | -0.071 | 0.677 | 996 |
| shrink k=20 | 0.692 | 0.874 | 0.200 | 0.578 | 996 |
| shrink k=40 | 0.672 | 0.844 | 0.254 | 0.553 | 996 |
| shrink k=80 (current) | 0.669 | 0.839 | 0.262 | 0.563 | 996 |
| shrink k=150 | 0.672 | 0.844 | 0.254 | 0.569 | 996 |
| shrink k=300 | 0.676 | 0.850 | 0.244 | 0.564 | 996 |
| shrink k=500 | 0.678 | 0.853 | 0.238 | 0.572 | 996 |
| two-year prior shrunk k=80 | 0.677 | 0.850 | 0.243 | 0.565 | 996 |

### Stratified by season progress
#### progress=early (n=519)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.924 | 1.170 | -0.497 | 0.762 | 519 |
| pure prior year | 0.665 | 0.836 | 0.235 | 0.544 | 519 |
| pure L42 | 0.804 | 1.021 | -0.140 | 0.676 | 519 |
| shrink k=20 | 0.689 | 0.861 | 0.189 | 0.589 | 519 |
| shrink k=40 | 0.665 | 0.830 | 0.247 | 0.560 | 519 |
| shrink k=80 (current) | 0.658 | 0.823 | 0.260 | 0.561 | 519 |
| shrink k=150 | 0.658 | 0.825 | 0.255 | 0.550 | 519 |
| shrink k=300 | 0.660 | 0.829 | 0.248 | 0.544 | 519 |
| shrink k=500 | 0.662 | 0.832 | 0.243 | 0.543 | 519 |
| two-year prior shrunk k=80 | 0.669 | 0.835 | 0.238 | 0.566 | 519 |

#### progress=late (n=312)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 1.004 | 1.281 | -0.700 | 0.769 | 312 |
| pure prior year | 0.705 | 0.884 | 0.191 | 0.586 | 312 |
| pure L42 | 0.822 | 1.023 | -0.084 | 0.705 | 312 |
| shrink k=20 | 0.718 | 0.911 | 0.140 | 0.595 | 312 |
| shrink k=40 | 0.696 | 0.873 | 0.210 | 0.558 | 312 |
| shrink k=80 (current) | 0.694 | 0.865 | 0.224 | 0.578 | 312 |
| shrink k=150 | 0.696 | 0.869 | 0.218 | 0.577 | 312 |
| shrink k=300 | 0.699 | 0.875 | 0.207 | 0.575 | 312 |
| shrink k=500 | 0.701 | 0.878 | 0.202 | 0.579 | 312 |
| two-year prior shrunk k=80 | 0.691 | 0.863 | 0.228 | 0.574 | 312 |

#### progress=mid (n=165)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.832 | 1.072 | -0.126 | 0.667 | 165 |
| pure prior year | 0.697 | 0.882 | 0.239 | 0.602 | 165 |
| pure L42 | 0.744 | 0.959 | 0.100 | 0.574 | 165 |
| shrink k=20 | 0.654 | 0.843 | 0.304 | 0.515 | 165 |
| shrink k=40 | 0.650 | 0.833 | 0.321 | 0.525 | 165 |
| shrink k=80 (current) | 0.659 | 0.843 | 0.305 | 0.553 | 165 |
| shrink k=150 | 0.672 | 0.855 | 0.284 | 0.568 | 165 |
| shrink k=300 | 0.682 | 0.867 | 0.265 | 0.606 | 165 |
| shrink k=500 | 0.687 | 0.872 | 0.256 | 0.606 | 165 |
| two-year prior shrunk k=80 | 0.675 | 0.873 | 0.254 | 0.518 | 165 |

### Stratified by player tier
#### tier=51-150 (n=717)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.944 | 1.198 | -0.766 | 0.750 | 717 |
| pure prior year | 0.694 | 0.869 | 0.071 | 0.592 | 717 |
| pure L42 | 0.819 | 1.027 | -0.297 | 0.702 | 717 |
| shrink k=20 | 0.702 | 0.875 | 0.058 | 0.592 | 717 |
| shrink k=40 | 0.684 | 0.849 | 0.114 | 0.577 | 717 |
| shrink k=80 (current) | 0.681 | 0.847 | 0.118 | 0.575 | 717 |
| shrink k=150 | 0.684 | 0.853 | 0.106 | 0.574 | 717 |
| shrink k=300 | 0.688 | 0.859 | 0.092 | 0.577 | 717 |
| shrink k=500 | 0.690 | 0.863 | 0.085 | 0.583 | 717 |
| two-year prior shrunk k=80 | 0.692 | 0.862 | 0.086 | 0.566 | 717 |

#### tier=top50 (n=279)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.909 | 1.171 | -0.759 | 0.730 | 279 |
| pure prior year | 0.654 | 0.834 | 0.109 | 0.527 | 279 |
| pure L42 | 0.751 | 0.971 | -0.210 | 0.594 | 279 |
| shrink k=20 | 0.668 | 0.872 | 0.025 | 0.549 | 279 |
| shrink k=40 | 0.643 | 0.832 | 0.112 | 0.512 | 279 |
| shrink k=80 (current) | 0.639 | 0.821 | 0.136 | 0.505 | 279 |
| shrink k=150 | 0.642 | 0.822 | 0.133 | 0.503 | 279 |
| shrink k=300 | 0.646 | 0.826 | 0.125 | 0.540 | 279 |
| shrink k=500 | 0.649 | 0.829 | 0.119 | 0.524 | 279 |
| two-year prior shrunk k=80 | 0.639 | 0.819 | 0.139 | 0.524 | 279 |

## SP results

### Pooled
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.565 | 6.877 | -0.704 | 4.807 | 357 |
| pure prior year | 4.343 | 5.545 | -0.108 | 3.527 | 357 |
| pure L42 | 4.499 | 5.641 | -0.140 | 3.941 | 354 |
| shrink k=20 | 4.193 | 5.317 | -0.019 | 3.527 | 357 |
| shrink k=40 | 4.243 | 5.404 | -0.052 | 3.369 | 357 |
| shrink k=80 (current) | 4.286 | 5.466 | -0.077 | 3.386 | 357 |
| shrink k=150 | 4.311 | 5.500 | -0.090 | 3.449 | 357 |
| shrink k=300 | 4.327 | 5.522 | -0.099 | 3.479 | 357 |
| shrink k=500 | 4.333 | 5.531 | -0.102 | 3.529 | 357 |
| two-year prior shrunk k=80 | 4.114 | 5.281 | -0.005 | 3.349 | 357 |

### Stratified by season progress
#### progress=early (n=193)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.408 | 6.864 | -0.908 | 4.645 | 193 |
| pure prior year | 4.351 | 5.558 | -0.251 | 3.612 | 193 |
| pure L42 | 4.567 | 5.796 | -0.352 | 3.923 | 191 |
| shrink k=20 | 4.173 | 5.330 | -0.150 | 3.440 | 193 |
| shrink k=40 | 4.235 | 5.417 | -0.188 | 3.344 | 193 |
| shrink k=80 (current) | 4.289 | 5.480 | -0.216 | 3.408 | 193 |
| shrink k=150 | 4.317 | 5.514 | -0.231 | 3.486 | 193 |
| shrink k=300 | 4.334 | 5.536 | -0.241 | 3.545 | 193 |
| shrink k=500 | 4.341 | 5.545 | -0.245 | 3.569 | 193 |
| two-year prior shrunk k=80 | 4.059 | 5.298 | -0.137 | 3.148 | 193 |

#### progress=late (n=102)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.928 | 7.051 | -0.614 | 5.347 | 102 |
| pure prior year | 4.433 | 5.620 | -0.026 | 3.593 | 102 |
| pure L42 | 4.355 | 5.424 | 0.054 | 3.805 | 101 |
| shrink k=20 | 4.370 | 5.470 | 0.029 | 3.686 | 102 |
| shrink k=40 | 4.378 | 5.524 | 0.009 | 3.562 | 102 |
| shrink k=80 (current) | 4.392 | 5.566 | -0.006 | 3.524 | 102 |
| shrink k=150 | 4.407 | 5.590 | -0.014 | 3.548 | 102 |
| shrink k=300 | 4.420 | 5.604 | -0.020 | 3.606 | 102 |
| shrink k=500 | 4.425 | 5.611 | -0.022 | 3.601 | 102 |
| two-year prior shrunk k=80 | 4.413 | 5.438 | 0.040 | 3.812 | 102 |

#### progress=mid (n=62)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.453 | 6.623 | -0.383 | 4.555 | 62 |
| pure prior year | 4.170 | 5.373 | 0.090 | 3.040 | 62 |
| pure L42 | 4.525 | 5.503 | 0.046 | 4.044 | 62 |
| shrink k=20 | 3.964 | 5.013 | 0.208 | 3.404 | 62 |
| shrink k=40 | 4.046 | 5.157 | 0.162 | 3.260 | 62 |
| shrink k=80 (current) | 4.104 | 5.254 | 0.130 | 3.088 | 62 |
| shrink k=150 | 4.133 | 5.307 | 0.112 | 3.090 | 62 |
| shrink k=300 | 4.150 | 5.339 | 0.102 | 3.065 | 62 |
| shrink k=500 | 4.157 | 5.352 | 0.097 | 3.055 | 62 |
| two-year prior shrunk k=80 | 3.795 | 4.959 | 0.225 | 2.860 | 62 |

### Stratified by player tier
#### tier=51-100 (n=142)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.882 | 7.264 | -0.976 | 4.957 | 142 |
| pure prior year | 4.279 | 5.452 | -0.113 | 3.340 | 142 |
| pure L42 | 4.656 | 5.792 | -0.254 | 4.191 | 140 |
| shrink k=20 | 4.194 | 5.295 | -0.050 | 3.562 | 142 |
| shrink k=40 | 4.220 | 5.348 | -0.071 | 3.377 | 142 |
| shrink k=80 (current) | 4.246 | 5.392 | -0.089 | 3.357 | 142 |
| shrink k=150 | 4.261 | 5.418 | -0.099 | 3.383 | 142 |
| shrink k=300 | 4.269 | 5.435 | -0.106 | 3.376 | 142 |
| shrink k=500 | 4.273 | 5.442 | -0.109 | 3.362 | 142 |
| two-year prior shrunk k=80 | 4.241 | 5.462 | -0.117 | 3.653 | 142 |

#### tier=top50 (n=215)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.355 | 6.608 | -0.838 | 4.650 | 215 |
| pure prior year | 4.386 | 5.605 | -0.322 | 3.612 | 215 |
| pure L42 | 4.396 | 5.540 | -0.286 | 3.843 | 214 |
| shrink k=20 | 4.192 | 5.331 | -0.196 | 3.478 | 215 |
| shrink k=40 | 4.259 | 5.440 | -0.245 | 3.366 | 215 |
| shrink k=80 (current) | 4.313 | 5.514 | -0.280 | 3.514 | 215 |
| shrink k=150 | 4.344 | 5.554 | -0.298 | 3.531 | 215 |
| shrink k=300 | 4.365 | 5.579 | -0.310 | 3.567 | 215 |
| shrink k=500 | 4.373 | 5.589 | -0.314 | 3.569 | 215 |
| two-year prior shrunk k=80 | 4.031 | 5.158 | -0.120 | 3.259 | 215 |

## Recommended k (2023 only)

| Stratum | Best k (2023) | MAE Δ vs k=80 (2023) | N |
| --- | --- | --- | --- |
| HITTER pooled | shrink k=80 (current) | +0.000 | 996 |
| HITTER early | shrink k=80 (current) | +0.000 | 519 |
| HITTER mid | shrink k=40 | +0.010 | 165 |
| HITTER late | shrink k=80 (current) | +0.000 | 312 |
| HITTER top50 | shrink k=80 (current) | +0.000 | 279 |
| HITTER 51-150 | shrink k=80 (current) | +0.000 | 717 |
| SP pooled | shrink k=20 | +0.094 | 357 |
| SP early | shrink k=20 | +0.116 | 193 |
| SP mid | shrink k=20 | +0.140 | 62 |
| SP late | shrink k=20 | +0.022 | 102 |
| SP top50 | shrink k=20 | +0.121 | 215 |
| SP 51-100 | shrink k=20 | +0.052 | 142 |

## Side-by-side: 2023 holdout vs 2024-2025

| Stratum | Best k 2023 | Best k 2024-25 | 2023 N | 2024-25 N | Stable? |
| --- | --- | --- | --- | --- | --- |
| HITTER pooled | shrink k=80 (current) | shrink k=40 | 996 | 1383 | yes |
| HITTER early | shrink k=80 (current) | shrink k=40 | 519 | 553 | yes |
| HITTER mid | shrink k=40 | shrink k=80 (current) | 165 | 278 | yes |
| HITTER late | shrink k=80 (current) | shrink k=40 | 312 | 552 | yes |
| HITTER top50 | shrink k=80 (current) | shrink k=40 | 279 | 379 | yes |
| HITTER 51-150 | shrink k=80 (current) | shrink k=40 | 717 | 1004 | yes |
| SP pooled | shrink k=20 | shrink k=20 | 357 | 463 | yes |
| SP early | shrink k=20 | shrink k=20 | 193 | 196 | yes |
| SP mid | shrink k=20 | shrink k=20 | 62 | 83 | yes |
| SP late | shrink k=20 | shrink k=20 | 102 | 184 | yes |
| SP top50 | shrink k=20 | shrink k=20 | 215 | 260 | yes |
| SP 51-100 | shrink k=20 | shrink k=20 | 142 | 203 | yes |

**Stability rate:** 12/12 strata within ±1 k-step of 2024-25 optimum.

## Year-over-year stability assessment

- 2023 pooled hitter MAE (k=80): 0.669; 2024-25 pooled hitter MAE (k=80): 0.657
- 2023 pooled SP MAE (k=80): 4.286; 2024-25 pooled SP MAE (k=80): 3.918
- If best-k in 2023 lands within ±1 K-step (e.g., k=40 vs k=80) of 2024-25's best-k for the same stratum, the calibration generalizes.
- A SHIFT (e.g., 2023 picks k=300 but 2024-25 picks k=20) signals the prior calibration is overfit to specific years.

## Caveats
- 2023 had a meaningful MLB rule environment shift (pitch clock introduced, defensive shift restrictions, larger bases) that changed run scoring and stolen-base rates. Hitter FP distributions may not be directly comparable to 2024-25 even with identical scoring formulas.
- 6 as_of dates over a single season vs 10 over two seasons → fewer snapshots → wider sampling uncertainty for 2023 optimum.
- Candidate selection from 2022 Statcast volume is a proxy. Players who broke out IN 2023 (e.g., Corbin Carroll, Spencer Strider's elite run) may be under-represented relative to a true 2023 in-season rh3/rp3 ranking.
- 2021 prior coverage is thinner than 2022 (some 2022-debut players lack 2021 logs) — `pred_2yrK80` fallback uses prior_avg when prior2 missing.
- Same player overlap → correlated errors caveat from the original report still applies.
- Forward-window IL censoring biases retained snapshots toward healthy players (same as original).

## Verdict
See 'Side-by-side' table and stability rate. Interpretation:
- **>=75% stable** → 2024-25 k recommendations generalize, use as-is for /boom-bust-history.
- **50-75% stable** → use k=40-80 hitter / k=20-40 SP as a robust band; tier-level lookups risk overfit.
- **<50% stable** → calibration is year-specific; default to a single global k=80 with broad uncertainty.
