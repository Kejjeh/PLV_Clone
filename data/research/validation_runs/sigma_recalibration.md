# rp3 sigma recalibration — alpha=2.41 global rescale

Generated 2026-06-03. Source: `multi_year_sp_backtest_starts.csv` (3,229 starts, 2021-2025).

## Problem

The multi-year backtest report flagged that `xfp_rp3_p25` / `xfp_rp3_p75`
covered only **21.6%** of actual per-start outcomes vs the **50%** Gaussian
target. Consumers (triangulate, sp-week-plan, fa-pickup-deep-dive) print
those bounds as a "50% interval" — at 21.6% coverage they are ~2.3x too
tight and overstate the model's certainty.

## Root cause

In `src/plv_clone/models/xfp/rp3.py::fit_residual_ci`, sigma is the std
of **LOO ros-avg residuals** (RoS rate vs predicted RoS rate). The target
the band is being read against in production is **per-start FP** — which
has materially more variance than a rate target averaged over many starts.

So the σ estimator is correct *for its training target* (ros-avg) but
under-counts variance *for the consumer use case* (single-start FP). The
fix is a single empirical scaling factor calibrated against the per-start
panel.

## Empirical alpha

```
alpha_global = std(actual_FP − xfp_rp3) / mean(xfp_rp3_sigma_raw)
             = 9.093 / 3.772
             = 2.41
```

Per-tier alphas:

| Tier (rank_at_snap) | n | mean σ_raw | resid std | alpha_tier |
|---|---:|---:|---:|---:|
| Ace #1-10 | 259 | 3.76 | 9.27 | 2.47 |
| SP2/3 #11-30 | 496 | 3.78 | 9.64 | 2.55 |
| Back-end #31-60 | 630 | 3.77 | 9.08 | 2.41 |
| Streamer #61+ | 1,844 | 3.77 | 8.90 | 2.36 |

Tier alphas span only 2.36-2.55 (~8% range). σ_raw is essentially constant
across tiers (the LOO residual table barely varies by pred bucket), so all
tier variation is downstream resid_std.

## Approach chosen — A (global rescale)

**Implementation:** multiply `xfp_rp3_sigma` by α=2.41 post-lookup;
recompute `xfp_rp3_p25 = pred - 0.6745*σ_cal`, `xfp_rp3_p75 = pred + 0.6745*σ_cal`.
Point estimates (`xfp_rp3_per_start`) unchanged. Schema-additive: new
column `sigma_calibration_method` ("global_alpha_v1") + `xfp_rp3_sigma_raw`
preserved for audit.

**Why not tier-specific (B):** tier coverage with global α=2.41 is 49.0%
to 53.7% — all four tiers comfortably inside the 45-55% gate. Tier-α gives
51-53% per tier. The 1-2 pp improvement does not justify the config
complexity (config is still encoded in `sigma_calibration.json` for future
flip).

**Why not quantile regression (C):** residuals are mildly asymmetric
(pooled q25=-4.4, q75=+6.5 — upside tail fatter), but symmetric Gaussian
bands at α=2.41 already pass coverage. Asymmetric bands would shift
medians (the prompt forbids) and complicate the consumer contract
("p25-p75 is a 50% band"). Documented as future work.

## Before / after coverage on backtest

| Tier | n | pre coverage | post coverage |
|---|---:|---:|---:|
| Ace #1-10 | 259 | 20.5% | **49.4%** |
| SP2/3 #11-30 | 496 | 20.0% | **49.0%** |
| Back-end #31-60 | 630 | 23.8% | **53.7%** |
| Streamer #61+ | 1,844 | 21.4% | **52.0%** |
| **Pooled** | **3,229** | **21.6%** | **51.7%** |

All four tiers in 49-54% — passes the 45-55% target band globally.

## Before / after canonical bands

Point estimates unchanged; widths ×2.41.

| Pitcher | rank | xfp_rp3 | sigma raw | p25 old | p75 old | sigma cal | p25 new | p75 new |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Soriano, José | 28 | 12.13 | 3.64 | 9.68 | 14.59 | 8.77 | **6.21** | **18.05** |
| Holmes, Grant | 82 | 10.13 | 3.64 | 7.67 | 12.58 | 8.77 | **4.21** | **16.05** |
| Rodriguez, Grayson | 190 | 8.21 | 3.64 | 5.75 | 10.66 | 8.77 | **2.29** | **14.13** |
| Kelly, Merrill | 181 | 8.38 | 3.64 | 5.92 | 10.83 | 8.77 | **2.46** | **14.30** |

These match what the per-start panel says: Kelly/G-Rod ARE coin-flips on
whether they clear 9 FP vs go negative, and Soriano ALSO has real downside
risk despite a "12.13" headline.

## Operational consequences

1. **`signal` column** still uses p25/p75 (`add` if p25 > replacement,
   `drop` if p75 < replacement). Wider bands mean fewer `add` and fewer
   `drop` flags — the recommendation surface gets more honest /
   conservative. Spot-check on the regenerated CSV: 0 `add` / 0 `drop`
   signals at the current snapshot, where previously a handful of edge
   pitchers tripped these gates on overly-tight bands. This is the
   intended effect — consumers should pick adds by `replacement_delta` /
   point estimate, not by p25 > rep.
2. **Triangulate cards** now print honest bands. Spot-check Soriano:
   `12.13 (6.21-18.05) fp/start` (was 9.68-14.59).
3. **sp-week-plan / matchup dashboard** — point estimates unchanged, so
   start-count math and weak-start-bench logic are unaffected. Only the
   "uncertainty" display widens.

## Pipeline notes

- `rp3.py` now reads `data/research/validation_runs/sigma_calibration.json`
  at projection time and applies `alpha_global` as a multiplier on the
  LOO residual sigma. Raw sigma preserved as `xfp_rp3_sigma_raw`.
- `sigma_calibration_method` column tags every row with the method id
  ("global_alpha_v1") so consumers can detect which calibration produced
  the band.
- Future calibration revisions: update `sigma_calibration.json` and
  re-run `refresh_dashboards.py` (or rewrite the existing projections CSV).
  Backtest re-run is the validation step before flipping the JSON.

## What this does NOT do

- Does not change `xfp_rp3_per_start` (point estimate). Ranking, replacement
  delta, schedule-adjusted variant — all unchanged.
- Does not retrain the model. This is pure variance calibration.
- Does not change `overall_sigma` stored inside the pkl bundle — the JSON
  is the single source of truth at projection time. Anyone who loads the
  pkl and reuses `overall_sigma` directly is reading the un-calibrated
  value. (If we find such consumers later, fold alpha into the pkl too.)

## Files touched

- `src/plv_clone/models/xfp/rp3.py` — added `_load_sigma_calibration()`,
  added `xfp_rp3_sigma_raw` and `sigma_calibration_method` columns to the
  output, multiplied sigma by alpha before computing p25/p75.
- `data/research/validation_runs/sigma_calibration.json` — new config.
- `data/outputs/xfp_rp3_projections.csv` — regenerated with calibrated
  bands. Original backed up to `xfp_rp3_projections.csv.bak`.
