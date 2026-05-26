# Bounce probability calibration — 2023-2025 walk-forward backtest

## Overall calibration
- Brier score: 0.2221 (perfect = 0, random = 0.25)
- Log loss: 0.6470
- Expected calibration error (ECE): 0.0197 (< 0.05 = well-calibrated)
- N snapshots with predictions: 15,778

## Calibration curve

| Predicted bucket | n | Mean predicted | Actual bounce rate | Error |
|---|---|---|---|---|
| [0-20%) | 1591 | 13.1% | 17.0% | 0.039 |
| [20-40%) | 5055 | 31.3% | 32.6% | 0.013 |
| [40-60%) | 6293 | 49.1% | 47.2% | 0.019 |
| [60-80%) | 2672 | 67.9% | 65.5% | 0.024 |
| [80-100%] | 167 | 84.4% | 83.2% | 0.012 |

## Slumper-specific calibration (career %ile < 20th) — n=3,357, ECE=0.0214

| Predicted bucket | n | Mean predicted | Actual bounce rate | Error |
|---|---|---|---|---|
| [0-20%) | 0 | — | — | — |
| [20-40%) | 8 | 31.0% | 75.0% | 0.440 |
| [40-60%) | 600 | 57.1% | 59.5% | 0.024 |
| [60-80%) | 2582 | 68.1% | 66.1% | 0.020 |
| [80-100%] | 167 | 84.4% | 83.2% | 0.012 |

## Peaker-specific calibration (career %ile > 80th) — n=2,837, ECE=0.0105

| Predicted bucket | n | Mean predicted | Actual bounce rate | Error |
|---|---|---|---|---|
| [0-20%) | 1413 | 13.1% | 15.1% | 0.021 |
| [20-40%) | 1424 | 25.2% | 25.3% | 0.001 |
| [40-60%) | 0 | — | — | — |
| [60-80%) | 0 | — | — | — |
| [80-100%] | 0 | — | — | — |

## Verdict
**WELL_CALIBRATED**

No threshold adjustment needed. Model probabilities can be used directly.