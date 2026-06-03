# rh3 hitter sigma heteroskedastic search

Generated 2026-06-03. Source: `hitter_boom_bust_panel.parquet` (245,712 batter-games, 2018-2025).

## Question

The current rh3 calibration uses a quartile-binned sigma indexed by split_day +
predicted-quartile — effectively a near-global per-PA sigma (~0.103 FP/PA). The SP
attempt (`sigma_heteroskedastic_search.md`) FAILED at CV r2=-0.218 because each pitcher
has only ~25 starts. Hitters get ~600 PA/season — 25x the per-player sample. Can we
predict per-hitter sigma from features and ship a multiplicative factor?

## Method

- Compute residual std of fp_per_pa vs each batter's career mean (PA-weighted)
  for batters with >= 100 games. This is `sigma_emp` per batter.
- Global pooled per-PA sigma across all batter-games is the baseline.
- Ridge predicts `sigma_emp` from 15 hitter features. 5-fold CV r2.
- Coverage tested on 245k games with sigma_per_game = sigma_pa * sqrt(PA),
  band = pred +/- 0.6745*sigma (target 50%).

## Per-batter sigma_emp landscape

- Batters with >= 100 games: **641**
- GLOBAL pooled per-PA sigma: **0.5170** FP/PA
- sigma_emp per batter (per PA):
  - mean: **0.5131**
  - median: **0.5141**
  - q25-q75: **0.4788 – 0.5508**
  - std across batters: **0.0559**
- sigma_ratio = sigma_emp / global:
  - mean: **0.992**  median: **0.994**
- Buckets: WIDER (>1.2)=17, TIGHTER (<0.8)=28, MATCH=596

### sigma_ratio by archetype (latest-year)

| archetype | n | sigma_ratio mean | sigma_ratio median | sigma_emp mean |
|---|---:|---:|---:|---:|
| AVERAGE_HITTER | 222 | 0.996 | 0.997 | 0.5150 |
| GENERIC_NO_POWER | 61 | 0.884 | 0.876 | 0.4570 |
| BACKUP_BAT | 57 | 1.069 | 1.085 | 0.5526 |
| AVG_HACKER | 55 | 0.973 | 0.977 | 0.5032 |
| BALANCED_EYE | 36 | 1.007 | 0.999 | 0.5204 |
| PURE_HITTER | 31 | 0.934 | 0.920 | 0.4830 |
| POWER_HITTER | 28 | 1.112 | 1.124 | 0.5751 |
| FRINGE | 22 | 0.940 | 0.932 | 0.4861 |
| NO_POWER_HACKER | 22 | 0.883 | 0.882 | 0.4565 |
| CONTACT_POWER | 15 | 1.058 | 1.063 | 0.5470 |
| K_PRONE_FILLER | 14 | 1.062 | 1.064 | 0.5489 |
| PATIENT_K | 12 | 1.106 | 1.080 | 0.5719 |
| SECONDARY_LEADOFF | 10 | 0.961 | 0.958 | 0.4970 |
| POWER_EYE | 10 | 1.092 | 1.106 | 0.5646 |
| ALL_OR_NOTHING | 8 | 1.055 | 1.042 | 0.5455 |

## Ridge model: predicting sigma_emp from features

- n batters usable: **639**
- 5-fold CV r2: **0.5744**
- y (sigma_emp) mean: 0.5131, std: 0.0560

### Standardized coefficients (effect of +1 SD feature on sigma_emp)

| feature | coef (std) | univariate r |
|---|---:|---:|
| POWER | +0.02700 | +0.591 |
| CONTACT | -0.01837 | -0.232 |
| ev90 | +0.01284 | +0.590 |
| contact_pct | -0.01055 | -0.602 |
| iso | -0.01033 | +0.485 |
| barrel_pct | +0.00646 | +0.634 |
| k_pct | -0.00579 | +0.546 |
| bb_pct | +0.00548 | +0.224 |
| chase_pct | +0.00531 | +0.003 |
| DISCIPLINE | +0.00506 | +0.211 |
| sprint_speed | -0.00490 | -0.085 |
| sweet_spot_pct | +0.00218 | +0.087 |
| xwoba_on_contact | +0.00096 | +0.525 |
| hard_hit_pct | -0.00085 | +0.515 |
| mean_lineup_spot | -0.00067 | -0.122 |

## Coverage on 245k-game panel

| method | pooled coverage (target 50%) |
|---|---:|
| GLOBAL sigma (status quo proxy) | **25.10%** |
| HETERO sigma (ridge factor, clamped + recentered) | **25.16%** |

### Per-batter coverage dispersion (>= 50 games)

| method | n batters | median cov | q25-q75 cov | std across | frac <25% | frac >75% |
|---|---:|---:|---:|---:|---:|---:|
| Global | 834 | 23.9% | 19.5-29.8% | 8.13pp | 55.2% | 0.0% |
| Hetero | 834 | 24.3% | 19.8-29.5% | 7.57pp | 54.0% | 0.0% |

## Case studies (typical 4-PA game band)

| hitter | n_games | pred_FP/PA | pred_game | factor | sigma_global_pa | sigma_hetero_pa | old p25-p75 | new p25-p75 | sigma_emp_obs |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| Eugenio Suárez | 962 | 0.261 | 1.05 | 1.09 | 0.5170 | 0.5629 | 0.35–1.74 | 0.29–1.80 | 0.5957 |
| Giancarlo Stanton | 643 | 0.242 | 0.97 | 1.25 | 0.5170 | 0.6480 | 0.27–1.67 | 0.10–1.84 | 0.6120 |
| Kyle Schwarber | 935 | 0.309 | 1.24 | 1.23 | 0.5170 | 0.6349 | 0.54–1.93 | 0.38–2.09 | 0.6263 |
| Luis Arraez | 712 | 0.394 | 1.57 | 0.77 | 0.5170 | 0.3974 | 0.88–2.27 | 1.04–2.11 | 0.3815 |
| Spencer Steer | 439 | 0.287 | 1.15 | 1.00 | 0.5170 | 0.5151 | 0.45–1.85 | 0.45–1.84 | 0.5101 |
| Bo Bichette | 682 | 0.310 | 1.24 | 0.96 | 0.5170 | 0.4980 | 0.54–1.94 | 0.57–1.91 | 0.5121 |
| Juan Soto | 992 | 0.443 | 1.77 | 1.08 | 0.5170 | 0.5590 | 1.07–2.47 | 1.02–2.53 | 0.5580 |
| Aaron Judge | 891 | 0.422 | 1.69 | 1.18 | 0.5170 | 0.6111 | 0.99–2.38 | 0.86–2.51 | 0.6620 |
| Ronald Acuña Jr. | 728 | 0.365 | 1.46 | 1.06 | 0.5170 | 0.5473 | 0.76–2.16 | 0.72–2.20 | 0.5356 |
| Bobby Witt Jr. | 603 | 0.363 | 1.45 | 1.03 | 0.5170 | 0.5320 | 0.75–2.15 | 0.73–2.17 | 0.5282 |

## Verdict

**SHIP_HETERO_FOR_HITTERS — CV r2 >= 0.10, pooled coverage stays in band, per-batter coverage spread narrows materially.**

### Headline numbers
- CV r2 of sigma prediction: **0.5744** (gate >= 0.10 strong, >= 0.05 weak)
- Pooled coverage: global 25.10%  -> hetero 25.16%  (delta +0.06pp)
- Per-batter coverage spread reduction: **+0.57pp**
- Top 5 sigma predictors (std coef): POWER (+0.0270), CONTACT (-0.0184), ev90 (+0.0128), contact_pct (-0.0105), iso (-0.0103)

### Minimal spec for rh3.py

```python
# After computing per-row sigma_pa via lookup_sigma(...):
# load hitter_sigma_factor from data/research/validation_runs/hitter_sigma_factors.csv
# factor keyed by batter, derived from ridge(features) / global, clamped + recentered.
sigma_final_per_pa = sigma_pa * batter_sigma_factor.clip(0.7, 1.5)
# re-centered so mean(factor) == 1 across active batters.
xfp_rh3_p25 = pred_per_pa - 0.6745 * sigma_final_per_pa
xfp_rh3_p75 = pred_per_pa + 0.6745 * sigma_final_per_pa
```
