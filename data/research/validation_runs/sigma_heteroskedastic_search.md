# rp3 sigma heteroskedastic search

Generated 2026-06-03. Source: `multi_year_sp_backtest_starts.csv` (3,229 starts, 2021-2025).

## Question

The current calibration multiplies every pitcher's sigma by **α_global=2.41**.
Can we predict per-pitcher σ — tighter for aces with stable command, wider
for streamers with variable outings — and ship a multiplicative factor?

## Method

- Compute empirical residual std σ_emp for each pitcher with ≥ 10 starts in backtest.
- Compare σ_emp to mean(σ_global) for that pitcher's starts → σ_ratio.
- Fit Ridge predicting σ_emp from features (archetype STUFF/MOVEMENT/CONTROL, K%, BB%,
  HR/BF, swstr%, xwOBA_contact, barrel%, hard-hit%, velo, zone%, gs_to, rank).
- 5-fold CV r² is the gate (target ≥ 0.10).
- Re-score backtest with hetero σ = σ_raw × 2.41 × pitcher_factor (clamped [0.7, 1.5],
  re-centered so mean(factor) = 1).

## Per-pitcher σ_emp landscape

- Pitchers with ≥ 10 backtest starts: **138**
- σ_ratio = σ_emp / σ_global (after α=2.41 rescale)
  - mean: **0.969**
  - median: **0.981**
  - q25-q75: **0.839 – 1.129**
  - std across pitchers: **0.212**
- Buckets: WIDER (>1.2)=19, TIGHTER (<0.8)=30, MATCH=**89**

### σ_ratio by archetype (latest-year archetype for each pitcher)

| archetype | n | σ_ratio mean | σ_ratio median | σ_emp mean |
|---|---:|---:|---:|---:|
| AVERAGE_4_5 | 53 | 0.966 | 0.983 | 8.77 |
| PURE_CONTROL | 16 | 0.921 | 0.951 | 8.37 |
| PURE_MOVEMENT | 11 | 0.936 | 0.972 | 8.47 |
| FILLER | 10 | 0.930 | 0.945 | 8.42 |
| PIT_CHF | 9 | 1.014 | 0.965 | 9.25 |
| WILD_MID | 8 | 0.901 | 0.899 | 8.23 |
| GENERIC_HR_PRONE | 6 | 0.937 | 0.965 | 8.57 |
| PURE_STUFF | 6 | 1.055 | 1.034 | 9.62 |
| MT_RUSHMORE | 4 | 1.201 | 1.157 | 10.91 |
| BAD_BIG_INNINGS | 3 | 0.939 | 1.106 | 8.58 |
| STUFF_PLUS_CTRL | 3 | 1.008 | 0.982 | 9.12 |
| STUFF_MOVE_WILD | 2 | 1.025 | 1.025 | 9.37 |
| PIT_CHF_CTRL | 2 | 0.766 | 0.766 | 6.95 |
| FRINGE | 1 | 1.154 | 1.154 | 10.53 |
| LIABILITY | 1 | 1.284 | 1.284 | 11.66 |

## Ridge model: predicting σ_emp from features

- n pitchers usable (no missing features): **138**
- 5-fold CV r²: **-0.2118**
- y (σ_emp) mean: 8.807, std: 1.921

### Standardized ridge coefficients (effect of +1 SD feature on σ_emp)

| feature | coef (std) | univariate r |
|---|---:|---:|
| MOVEMENT | -0.528 | +0.061 |
| barrel_pct | -0.514 | -0.074 |
| k_pct | +0.424 | +0.166 |
| STUFF | +0.327 | +0.140 |
| swstr_pct | -0.302 | +0.097 |
| bb_pct | +0.209 | +0.086 |
| hard_hit_pct | -0.172 | -0.061 |
| xwoba_contact | +0.158 | -0.071 |
| CONTROL | +0.126 | -0.072 |
| gs_to_mean | +0.119 | +0.081 |
| rank_mean | -0.065 | -0.125 |
| hr_per_bf | -0.056 | -0.037 |
| avg_velo | -0.032 | +0.032 |
| zone_pct | -0.030 | -0.072 |

## Coverage on the 3,229-start backtest

| method | pooled coverage (target 50%) |
|---|---:|
| Global α=2.41 (status quo) | **51.7%** |
| Hetero σ (ridge factor, clamped + re-centered) | **51.2%** |

### Per-pitcher coverage dispersion (pitchers with ≥10 starts)

| method | n pitchers | median cov | q25-q75 cov | std across | frac <25% | frac >75% |
|---|---:|---:|---:|---:|---:|---:|
| Global α | 138 | 53.1% | 45.1-60.0% | 12.9pp | 1.4% | 3.6% |
| Hetero σ | 138 | 53.8% | 45.6-59.8% | 12.6pp | 0.7% | 5.1% |

## Case studies (last backtest snapshot for each)

| pitcher | n_st | rp3 | σ_global | σ_hetero | factor | old p25-p75 | new p25-p75 | σ_emp obs |
|---|---:|---:|---:|---:|---:|---|---|---:|
| Soriano, José | 9 | 11.77 | 8.73 | 9.19 | 1.05 | 5.88–17.66 | 5.58–17.97 | 13.12 |
| Skenes, Paul | 8 | 17.51 | 8.73 | 9.73 | 1.11 | 11.62–23.40 | 10.95–24.08 | 8.53 |
| Rodriguez, Grayson | 16 | 10.54 | 8.73 | 9.36 | 1.07 | 4.65–16.43 | 4.23–16.85 | 11.42 |
| Rodriguez, Grayson | 5 | 12.11 | 8.68 | 9.33 | 1.07 | 6.26–17.97 | 5.82–18.41 | 13.46 |
| Kelly, Merrill | 25 | 12.51 | 8.73 | 9.40 | 1.08 | 6.62–18.40 | 6.16–18.85 | 10.37 |
| Holmes, Grant | 2 | 11.05 | 8.72 | 9.08 | 1.04 | 5.17–16.93 | 4.93–17.18 | nan |
| Cole, Gerrit | 20 | 13.37 | 8.65 | 9.22 | 1.07 | 7.53–19.20 | 7.14–19.59 | 10.82 |
| Strider, Spencer | 11 | 11.96 | 8.73 | 9.16 | 1.05 | 6.07–17.85 | 5.78–18.14 | 8.68 |

## Verdict

**KEEP_GLOBAL — ridge CV r² below 0.05 floor; features cannot predict σ direction.**

### Why not ship
- See r² and coverage tables above. Per-pitcher σ_emp dispersion is not
  predictable from the available features at the ≥ 0.10 r² gate, OR the hetero
  factor does not improve pooled / per-pitcher coverage materially over global.
- Per-pitcher σ_emp variation is consistent with sampling noise on top of a single
  true sigma, not a stable cross-pitcher property the model can lock onto.
