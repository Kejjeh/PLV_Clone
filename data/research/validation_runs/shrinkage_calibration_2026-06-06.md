# Shrinkage k Calibration — Hitter + SP

## Method
- Pool: top 200 hitters + top 100 SPs by rh3/rp3 rank
- as_of dates: 2024-05-01, 2024-06-01, 2024-07-01, 2024-08-01, 2024-09-01, 2025-05-01, 2025-06-01, 2025-07-01, 2025-08-01, 2025-09-01
- Hitter target: mean BrownU FP/g over [as_of, as_of+30d], require >=5 future games
- SP target: mean BrownU FP/start over next 5 starts, require >=3 future starts
- Hitter snapshots: **1498**  |  SP snapshots: **550**
- Predictors: pure L21, pure L42, pure prior, shrink k in [20, 40, 80, 150, 300, 500], two-year prior shrunk k=80

## Hitter results

### Pooled
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.891 | 1.125 | -0.582 | 0.742 | 1383 |
| pure prior year | 0.680 | 0.857 | 0.083 | 0.585 | 1383 |
| pure L42 | 0.763 | 0.961 | -0.154 | 0.667 | 1383 |
| shrink k=20 | 0.668 | 0.840 | 0.118 | 0.569 | 1383 |
| shrink k=40 | 0.653 | 0.822 | 0.156 | 0.559 | 1383 |
| shrink k=80 (current) | 0.657 | 0.826 | 0.148 | 0.570 | 1383 |
| shrink k=150 | 0.664 | 0.835 | 0.128 | 0.575 | 1383 |
| shrink k=300 | 0.671 | 0.844 | 0.109 | 0.582 | 1383 |
| shrink k=500 | 0.674 | 0.849 | 0.100 | 0.581 | 1383 |
| two-year prior shrunk k=80 | 0.655 | 0.820 | 0.159 | 0.568 | 1383 |

### Stratified by season progress
#### progress=early (n=553)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.882 | 1.094 | -0.617 | 0.740 | 553 |
| pure prior year | 0.680 | 0.851 | 0.022 | 0.577 | 553 |
| pure L42 | 0.776 | 0.971 | -0.273 | 0.683 | 553 |
| shrink k=20 | 0.664 | 0.834 | 0.061 | 0.541 | 553 |
| shrink k=40 | 0.648 | 0.817 | 0.100 | 0.550 | 553 |
| shrink k=80 (current) | 0.654 | 0.820 | 0.091 | 0.582 | 553 |
| shrink k=150 | 0.663 | 0.830 | 0.070 | 0.579 | 553 |
| shrink k=300 | 0.670 | 0.839 | 0.050 | 0.582 | 553 |
| shrink k=500 | 0.674 | 0.843 | 0.040 | 0.579 | 553 |
| two-year prior shrunk k=80 | 0.653 | 0.819 | 0.094 | 0.568 | 553 |

#### progress=late (n=552)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.900 | 1.154 | -0.514 | 0.748 | 552 |
| pure prior year | 0.690 | 0.876 | 0.128 | 0.595 | 552 |
| pure L42 | 0.750 | 0.953 | -0.032 | 0.649 | 552 |
| shrink k=20 | 0.672 | 0.850 | 0.179 | 0.573 | 552 |
| shrink k=40 | 0.660 | 0.837 | 0.205 | 0.572 | 552 |
| shrink k=80 (current) | 0.667 | 0.844 | 0.191 | 0.574 | 552 |
| shrink k=150 | 0.675 | 0.854 | 0.171 | 0.588 | 552 |
| shrink k=300 | 0.682 | 0.864 | 0.153 | 0.578 | 552 |
| shrink k=500 | 0.685 | 0.868 | 0.144 | 0.580 | 552 |
| two-year prior shrunk k=80 | 0.666 | 0.835 | 0.207 | 0.577 | 552 |

#### progress=mid (n=278)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.894 | 1.127 | -0.670 | 0.731 | 278 |
| pure prior year | 0.658 | 0.828 | 0.098 | 0.585 | 278 |
| pure L42 | 0.764 | 0.956 | -0.203 | 0.655 | 278 |
| shrink k=20 | 0.669 | 0.832 | 0.089 | 0.623 | 278 |
| shrink k=40 | 0.649 | 0.802 | 0.153 | 0.562 | 278 |
| shrink k=80 (current) | 0.645 | 0.800 | 0.157 | 0.549 | 278 |
| shrink k=150 | 0.646 | 0.808 | 0.142 | 0.562 | 278 |
| shrink k=300 | 0.650 | 0.816 | 0.124 | 0.584 | 278 |
| shrink k=500 | 0.653 | 0.820 | 0.115 | 0.590 | 278 |
| two-year prior shrunk k=80 | 0.636 | 0.791 | 0.177 | 0.555 | 278 |

### Stratified by player tier
#### tier=51-150 (n=1004)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.887 | 1.121 | -0.948 | 0.736 | 1004 |
| pure prior year | 0.651 | 0.817 | -0.034 | 0.570 | 1004 |
| pure L42 | 0.755 | 0.951 | -0.402 | 0.653 | 1004 |
| shrink k=20 | 0.655 | 0.820 | -0.043 | 0.558 | 1004 |
| shrink k=40 | 0.636 | 0.797 | 0.015 | 0.538 | 1004 |
| shrink k=80 (current) | 0.636 | 0.796 | 0.018 | 0.550 | 1004 |
| shrink k=150 | 0.640 | 0.801 | 0.004 | 0.565 | 1004 |
| shrink k=300 | 0.644 | 0.807 | -0.011 | 0.561 | 1004 |
| shrink k=500 | 0.647 | 0.811 | -0.019 | 0.565 | 1004 |
| two-year prior shrunk k=80 | 0.634 | 0.793 | 0.024 | 0.558 | 1004 |

#### tier=top50 (n=379)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.904 | 1.136 | -0.423 | 0.760 | 379 |
| pure prior year | 0.757 | 0.955 | -0.004 | 0.643 | 379 |
| pure L42 | 0.784 | 0.987 | -0.074 | 0.684 | 379 |
| shrink k=20 | 0.704 | 0.890 | 0.127 | 0.618 | 379 |
| shrink k=40 | 0.700 | 0.884 | 0.140 | 0.619 | 379 |
| shrink k=80 (current) | 0.715 | 0.900 | 0.107 | 0.627 | 379 |
| shrink k=150 | 0.729 | 0.919 | 0.069 | 0.621 | 379 |
| shrink k=300 | 0.741 | 0.935 | 0.038 | 0.632 | 379 |
| shrink k=500 | 0.747 | 0.942 | 0.022 | 0.627 | 379 |
| two-year prior shrunk k=80 | 0.711 | 0.887 | 0.132 | 0.598 | 379 |

## SP results

### Pooled
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.343 | 6.771 | -1.050 | 4.540 | 463 |
| pure prior year | 3.965 | 5.050 | -0.140 | 3.230 | 463 |
| pure L42 | 4.443 | 5.626 | -0.441 | 3.439 | 456 |
| shrink k=20 | 3.835 | 4.887 | -0.068 | 3.269 | 463 |
| shrink k=40 | 3.879 | 4.943 | -0.093 | 3.251 | 463 |
| shrink k=80 (current) | 3.918 | 4.989 | -0.113 | 3.307 | 463 |
| shrink k=150 | 3.938 | 5.015 | -0.125 | 3.231 | 463 |
| shrink k=300 | 3.951 | 5.032 | -0.132 | 3.272 | 463 |
| shrink k=500 | 3.957 | 5.039 | -0.135 | 3.235 | 463 |
| two-year prior shrunk k=80 | 3.858 | 4.909 | -0.078 | 3.169 | 463 |

### Stratified by season progress
#### progress=early (n=196)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 4.917 | 6.160 | -0.811 | 4.002 | 196 |
| pure prior year | 3.688 | 4.811 | -0.104 | 2.901 | 196 |
| pure L42 | 4.375 | 5.380 | -0.429 | 3.417 | 192 |
| shrink k=20 | 3.533 | 4.564 | 0.006 | 2.816 | 196 |
| shrink k=40 | 3.592 | 4.660 | -0.036 | 2.904 | 196 |
| shrink k=80 (current) | 3.634 | 4.727 | -0.066 | 2.959 | 196 |
| shrink k=150 | 3.657 | 4.764 | -0.083 | 2.898 | 196 |
| shrink k=300 | 3.671 | 4.787 | -0.093 | 2.911 | 196 |
| shrink k=500 | 3.678 | 4.796 | -0.098 | 2.897 | 196 |
| two-year prior shrunk k=80 | 3.631 | 4.686 | -0.048 | 3.061 | 196 |

#### progress=late (n=184)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.463 | 7.141 | -1.195 | 4.502 | 184 |
| pure prior year | 4.316 | 5.348 | -0.231 | 3.780 | 184 |
| pure L42 | 4.357 | 5.786 | -0.458 | 3.169 | 181 |
| shrink k=20 | 4.202 | 5.230 | -0.177 | 3.770 | 184 |
| shrink k=40 | 4.243 | 5.267 | -0.194 | 3.911 | 184 |
| shrink k=80 (current) | 4.278 | 5.301 | -0.209 | 3.958 | 184 |
| shrink k=150 | 4.295 | 5.321 | -0.219 | 3.894 | 184 |
| shrink k=300 | 4.306 | 5.334 | -0.225 | 3.831 | 184 |
| shrink k=500 | 4.310 | 5.340 | -0.227 | 3.805 | 184 |
| two-year prior shrunk k=80 | 4.120 | 5.153 | -0.143 | 3.588 | 184 |

#### progress=mid (n=83)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 6.081 | 7.287 | -1.281 | 5.387 | 83 |
| pure prior year | 3.840 | 4.918 | -0.039 | 2.784 | 83 |
| pure L42 | 4.788 | 5.825 | -0.458 | 3.882 | 83 |
| shrink k=20 | 3.735 | 4.835 | -0.004 | 3.127 | 83 |
| shrink k=40 | 3.753 | 4.851 | -0.011 | 2.969 | 83 |
| shrink k=80 (current) | 3.789 | 4.876 | -0.021 | 2.921 | 83 |
| shrink k=150 | 3.809 | 4.893 | -0.029 | 2.839 | 83 |
| shrink k=300 | 3.824 | 4.905 | -0.033 | 2.776 | 83 |
| shrink k=500 | 3.830 | 4.910 | -0.036 | 2.779 | 83 |
| two-year prior shrunk k=80 | 3.814 | 4.871 | -0.019 | 2.772 | 83 |

### Stratified by player tier
#### tier=51-100 (n=203)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.667 | 7.023 | -1.577 | 5.120 | 203 |
| pure prior year | 4.237 | 5.376 | -0.510 | 3.278 | 203 |
| pure L42 | 4.593 | 5.646 | -0.709 | 4.091 | 199 |
| shrink k=20 | 4.065 | 5.147 | -0.384 | 3.498 | 203 |
| shrink k=40 | 4.125 | 5.232 | -0.430 | 3.443 | 203 |
| shrink k=80 (current) | 4.176 | 5.295 | -0.465 | 3.383 | 203 |
| shrink k=150 | 4.204 | 5.330 | -0.484 | 3.395 | 203 |
| shrink k=300 | 4.220 | 5.352 | -0.497 | 3.337 | 203 |
| shrink k=500 | 4.226 | 5.361 | -0.502 | 3.313 | 203 |
| two-year prior shrunk k=80 | 4.089 | 5.170 | -0.396 | 3.285 | 203 |

#### tier=top50 (n=260)
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.090 | 6.568 | -0.931 | 3.973 | 260 |
| pure prior year | 3.753 | 4.780 | -0.023 | 3.153 | 260 |
| pure L42 | 4.326 | 5.610 | -0.416 | 3.268 | 257 |
| shrink k=20 | 3.655 | 4.673 | 0.023 | 3.189 | 260 |
| shrink k=40 | 3.687 | 4.706 | 0.009 | 3.239 | 260 |
| shrink k=80 (current) | 3.715 | 4.737 | -0.004 | 3.286 | 260 |
| shrink k=150 | 3.730 | 4.755 | -0.012 | 3.213 | 260 |
| shrink k=300 | 3.741 | 4.767 | -0.017 | 3.149 | 260 |
| shrink k=500 | 3.746 | 4.772 | -0.019 | 3.146 | 260 |
| two-year prior shrunk k=80 | 3.678 | 4.696 | 0.013 | 3.043 | 260 |

## Recommended weights

| Stratum | Best shrinkage predictor | MAE improvement vs k=80 | N |
| --- | --- | --- | --- |
| HITTER pooled | shrink k=40 | +0.004 | 1383 |
| HITTER early | shrink k=40 | +0.005 | 553 |
| HITTER mid | shrink k=80 (current) | +0.000 | 278 |
| HITTER late | shrink k=40 | +0.007 | 552 |
| HITTER top50 | shrink k=40 | +0.016 | 379 |
| HITTER 51-150 | shrink k=40 | +0.000 | 1004 |
| SP pooled | shrink k=20 | +0.082 | 463 |
| SP early | shrink k=20 | +0.101 | 196 |
| SP mid | shrink k=20 | +0.054 | 83 |
| SP late | shrink k=20 | +0.076 | 184 |
| SP top50 | shrink k=20 | +0.060 | 260 |
| SP 51-100 | shrink k=20 | +0.111 | 203 |

## Caveats
- Player overlap across as_of dates produces correlated errors (no clustered SE adjustment).
- Forward-window IL censoring is not corrected: a target window with <5 games (H) / <3 starts (SP) is dropped, which biases retained snapshots toward healthy players.
- Rookies / players without enough prior-year games (<20 H games or <5 SP starts) are dropped from shrinkage-with-prior predictors (NaN propagation).
- 2024 vs 2025 year-effects not modeled; pooled across both.
- Targets are simple per-game means; volatility (std) not directly evaluated.
- MLB Stats API gameLog is canonical for stats but does not adjust for park or opponent.

## What this changes in /boom-bust-history
If optimal k differs materially from 80 in any stratum, the skill projection step should pick k from a lookup keyed on (position, season_progress, player_tier). If the pooled optimum is within ~1 MAE point of k=80, retaining k=80 as a single global default is defensible.
