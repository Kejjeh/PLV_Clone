# Survivorship Bias Check — Shrinkage k Calibration

**Hypothesis:** Existing shrinkage backtest (`shrinkage_calibration_2026-06-06.md`) drew the player pool from CURRENT (2026-06-06) rh3/rp3 top-200 H / top-100 SP, which excludes 2024-2025 players who started ranked but dropped out by today. This inflates measured lift because survivors are easier to predict (stable, healthy, prime-aged).

## Method
- **Time-correct sample:** at each as_of, rank candidates from a superset (top-500 H / top-300 SP by current rh3/rp3) by their ROLLING 60-day FP/g (hitter) or FP/start (SP) computed from MLB Stats API gameLog strictly before as_of. Take top-200 H / top-100 SP.
- **as_of dates** (6 of original 10, to keep runtime bounded): 2024-06-01, 2024-07-01, 2024-08-01, 2025-06-01, 2025-07-01, 2025-08-01
- **Original sample (subset):** same as `shrinkage_calibration_2026-06-06.md` but filtered to the 6 as_of dates above. Pool = top-200 H / top-100 SP by CURRENT rh3/rp3.
- **Shrinkage families re-evaluated**: pure L21, pure L42, pure prior, shrink k in [20, 40, 80, 150, 300, 500], two-year prior shrunk k=80.
- **Caveat (acknowledged):** superset itself is top-500/300 by CURRENT rh3/rp3, so true unicorns who washed out by 2026 are still excluded. This test catches 'top-200 today vs top-500 today peak-then-faded' but not 'never in current top-500'.

## Sample composition comparison

### Hitter pool
- Original sample (current-rank top-200, subset to 6 as_of dates): **900** snapshots, **185** unique pids
- Time-correct sample (rolling-60d top-200 at each as_of): **1102** snapshots, **299** unique pids
- Pid overlap: **178** in both pools
- Pids ONLY in original (survivors): **7** — current top-200 but not top-200 by rolling-60d at any tested as_of
- Pids ONLY in time-correct (peak-then-faded or rookies who broke out): **121** — these are the survivorship-bias-excluded players
- (pid, as_of) pair overlap: **738** / orig=900 / tc=1102
- Example survivors-only (in orig sample, dropped from time-correct):
  - Andruw Monasterio (pid 655316)
  - Jahmai Jones (pid 663330)
  - Ke'Bryan Hayes (pid 663647)
  - Carlos Cortes (pid 666126)
  - Jared Young (pid 676724)
  - Curtis Mead (pid 678554)
  - Jordan Walker (pid 691023)
- Example peak-then-faded (in time-correct, dropped from orig sample):
  - Andrew McCutchen (pid 457705)
  - Starling Marte (pid 516782)
  - Giancarlo Stanton (pid 519317)
  - Marcell Ozuna (pid 542303)
  - Kyle Higashioka (pid 543309)
  - James McCann (pid 543510)
  - Christian Vázquez (pid 543877)
  - Eugenio Suárez (pid 553993)
  - Mike Yastrzemski (pid 573262)
  - Nick Castellanos (pid 592206)

### SP pool
- Original sample (current-rank top-100, subset to 6 as_of dates): **324** snapshots, **83** unique pids
- Time-correct sample (rolling-60d top-100 at each as_of): **540** snapshots, **187** unique pids
- Pid overlap: **75** in both pools
- Pids ONLY in original (survivors): **8**
- Pids ONLY in time-correct: **112**
- (pid, as_of) pair overlap: **280** / orig=324 / tc=540
- Example survivors-only:
  - Cole, Gerrit (pid 543037)
  - Musgrove, Joe (pid 605397)
  - Ohtani, Shohei (pid 660271)
  - Ginn, J.T. (pid 669372)
  - Detmers, Reid (pid 672282)
  - Sheehan, Emmet (pid 686218)
  - Schlittler, Cam (pid 693645)
  - Burns, Chase (pid 695505)
- Example peak-then-faded:
  - Verlander, Justin (pid 434378)
  - Morton, Charlie (pid 450203)
  - Scherzer, Max (pid 453286)
  - Lynn, Lance (pid 458681)
  - Quintana, Jose (pid 500779)
  - Gibson, Kyle (pid 502043)
  - Darvish, Yu (pid 506433)
  - Kelly, Merrill (pid 518876)
  - Anderson, Tyler (pid 542881)
  - Hendricks, Kyle (pid 543294)

## Target distribution (sample difficulty)

| Stratum | Original mean target | Time-correct mean target | Δ (orig − tc) |
| --- | --- | --- | --- |
| Hitter target FP/g | 2.226 | 2.142 | +0.085 |
| SP target FP/start | 13.041 | 11.533 | +1.507 |

Interpretation: positive Δ = original sample has higher-scoring targets on average = survivors are easier to predict (production hugs the mean).

## Pooled results — original sample (6 as_of dates only)

### Hitter
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.903 | 1.132 | -0.611 | 0.761 | 832 |
| pure prior year | 0.689 | 0.864 | 0.063 | 0.601 | 832 |
| pure L42 | 0.757 | 0.956 | -0.149 | 0.647 | 832 |
| shrink k=20 | 0.675 | 0.845 | 0.103 | 0.584 | 832 |
| shrink k=40 | 0.662 | 0.827 | 0.140 | 0.578 | 832 |
| shrink k=80 (current) | 0.667 | 0.832 | 0.130 | 0.573 | 832 |
| shrink k=150 | 0.674 | 0.842 | 0.109 | 0.583 | 832 |
| shrink k=300 | 0.680 | 0.851 | 0.090 | 0.591 | 832 |
| shrink k=500 | 0.683 | 0.856 | 0.080 | 0.594 | 832 |
| two-year prior shrunk k=80 | 0.661 | 0.828 | 0.140 | 0.568 | 832 |

### SP
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.554 | 6.953 | -1.139 | 4.835 | 273 |
| pure prior year | 3.853 | 4.881 | -0.054 | 3.099 | 273 |
| pure L42 | 4.396 | 5.552 | -0.381 | 3.520 | 267 |
| shrink k=20 | 3.746 | 4.760 | -0.002 | 3.202 | 273 |
| shrink k=40 | 3.783 | 4.797 | -0.018 | 3.130 | 273 |
| shrink k=80 (current) | 3.814 | 4.831 | -0.033 | 3.051 | 273 |
| shrink k=150 | 3.830 | 4.853 | -0.042 | 3.087 | 273 |
| shrink k=300 | 3.841 | 4.866 | -0.047 | 3.094 | 273 |
| shrink k=500 | 3.846 | 4.872 | -0.050 | 3.087 | 273 |
| two-year prior shrunk k=80 | 3.767 | 4.752 | 0.001 | 2.975 | 273 |

## Pooled results — time-correct sample

### Hitter
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.896 | 1.134 | -0.558 | 0.750 | 1007 |
| pure prior year | 0.717 | 0.903 | 0.011 | 0.604 | 1007 |
| pure L42 | 0.746 | 0.945 | -0.083 | 0.640 | 1007 |
| shrink k=20 | 0.695 | 0.871 | 0.080 | 0.601 | 1007 |
| shrink k=40 | 0.684 | 0.858 | 0.109 | 0.591 | 1007 |
| shrink k=80 (current) | 0.692 | 0.866 | 0.092 | 0.581 | 1007 |
| shrink k=150 | 0.700 | 0.878 | 0.066 | 0.589 | 1007 |
| shrink k=300 | 0.707 | 0.889 | 0.043 | 0.596 | 1007 |
| shrink k=500 | 0.711 | 0.894 | 0.031 | 0.606 | 1007 |
| two-year prior shrunk k=80 | 0.687 | 0.862 | 0.099 | 0.586 | 1007 |

### SP
| Predictor | MAE | RMSE | R2 | MEDIAN | N |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.196 | 6.527 | -0.685 | 4.465 | 436 |
| pure prior year | 3.936 | 4.966 | 0.025 | 3.185 | 436 |
| pure L42 | 4.442 | 5.569 | -0.225 | 3.737 | 435 |
| shrink k=20 | 3.798 | 4.818 | 0.082 | 3.206 | 436 |
| shrink k=40 | 3.850 | 4.869 | 0.063 | 3.172 | 436 |
| shrink k=80 (current) | 3.889 | 4.911 | 0.046 | 3.120 | 436 |
| shrink k=150 | 3.910 | 4.935 | 0.037 | 3.150 | 436 |
| shrink k=300 | 3.923 | 4.950 | 0.031 | 3.151 | 436 |
| shrink k=500 | 3.928 | 4.957 | 0.029 | 3.167 | 436 |
| two-year prior shrunk k=80 | 3.893 | 4.905 | 0.049 | 3.047 | 436 |

## Optimal shrinkage k by sample

| Position | Original optimal k | Original MAE | Time-correct optimal k | Time-correct MAE | Δ MAE |
| --- | --- | --- | --- | --- | --- |
| Hitter | shrink k=40 | 0.662 | shrink k=40 | 0.684 | +0.022 |
| SP | shrink k=20 | 3.746 | shrink k=20 | 3.798 | +0.052 |

## Per-predictor lift comparison

Lift = (pure L21 MAE) − (predictor MAE). Higher = better lift over pure-recent baseline.

### Hitter
| Predictor | Orig MAE | Orig lift | TC MAE | TC lift | Inflation (orig − tc) |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 0.903 | +0.000 | 0.896 | +0.000 | +0.000 |
| pure prior year | 0.689 | +0.213 | 0.717 | +0.179 | +0.034 |
| pure L42 | 0.757 | +0.146 | 0.746 | +0.149 | -0.004 |
| shrink k=20 | 0.675 | +0.227 | 0.695 | +0.201 | +0.026 |
| shrink k=40 | 0.662 | +0.240 | 0.684 | +0.211 | +0.029 |
| shrink k=80 (current) | 0.667 | +0.235 | 0.692 | +0.204 | +0.031 |
| shrink k=150 | 0.674 | +0.229 | 0.700 | +0.196 | +0.033 |
| shrink k=300 | 0.680 | +0.223 | 0.707 | +0.189 | +0.034 |
| shrink k=500 | 0.683 | +0.219 | 0.711 | +0.185 | +0.034 |
| two-year prior shrunk k=80 | 0.661 | +0.241 | 0.687 | +0.209 | +0.032 |

### SP
| Predictor | Orig MAE | Orig lift | TC MAE | TC lift | Inflation (orig − tc) |
| --- | --- | --- | --- | --- | --- |
| pure L21 | 5.554 | +0.000 | 5.196 | +0.000 | +0.000 |
| pure prior year | 3.853 | +1.701 | 3.936 | +1.259 | +0.442 |
| pure L42 | 4.396 | +1.158 | 4.442 | +0.753 | +0.405 |
| shrink k=20 | 3.746 | +1.809 | 3.798 | +1.398 | +0.411 |
| shrink k=40 | 3.783 | +1.772 | 3.850 | +1.345 | +0.427 |
| shrink k=80 (current) | 3.814 | +1.741 | 3.889 | +1.306 | +0.434 |
| shrink k=150 | 3.830 | +1.724 | 3.910 | +1.286 | +0.438 |
| shrink k=300 | 3.841 | +1.714 | 3.923 | +1.273 | +0.441 |
| shrink k=500 | 3.846 | +1.709 | 3.928 | +1.268 | +0.441 |
| two-year prior shrunk k=80 | 3.767 | +1.788 | 3.893 | +1.302 | +0.486 |

## Severity assessment

Heuristic: classify by max( |Δ best-MAE|, |Δ best-predictor lift| ) vs an MAE-scale threshold.
- **Hitter scale ~ 0.6-0.9 FP/g:** LOW <0.02, MODERATE 0.02-0.05, MEANINGFUL 0.05-0.10, SEVERE >0.10
- **SP scale ~ 3.5-4.5 FP/start:** LOW <0.20, MODERATE 0.20-0.50, MEANINGFUL 0.50-1.00, SEVERE >1.00

- **Hitter:** Δ best-MAE = +0.022 | Δ best-predictor lift = +0.029 | classification: **MODERATE (add caveat to prior backtest summaries)**
- **SP:** Δ best-MAE = +0.052 | Δ best-predictor lift = +0.411 | classification: **MODERATE (add caveat to prior backtest summaries)**

## Recommendation

- Add an explicit caveat to `shrinkage_calibration_2026-06-06.md`: 'pool selection used current rank, lifts may be modestly inflated by survivorship'.
- Optimal k recommendations remain usable but should be re-validated when a true historical rank source becomes available.

## Caveats of this test
- Superset itself is current-rank top-500/300. Players who fell out of the top-500/300 entirely by 2026-06-06 are still excluded from both pools. True survivorship bias is BOUNDED-BELOW by this test; the real magnitude may be larger.
- 6 as_of dates (vs original 10) chosen to bound MLB Stats API cost.
- Time-correct ranking uses a single window (60 days). A multi-window blend (season-to-date + L60) might select a slightly different pool.
- Forward target censoring (≥5 future games / ≥3 starts) is identical to original calibration, so no relative bias introduced.
