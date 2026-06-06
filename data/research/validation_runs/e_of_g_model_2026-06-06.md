# E[G] (expected season appearances) model — Phase 3

**Date:** 2026-06-06
**Script:** `scripts/xfp/fit_e_of_g_model.py`
**Substrate:** late-season snapshot of `rolling_relievers_2018_2026.csv` joined with `master_panel.parquet` RP rows. n=1,753 (2018, 2019, 2021–2025; 2020 excluded).
**Target:** actual season `g` (range 5–83, mean 50.6, std 15.9).

## Features

| Feature | Source | Role |
|---|---|---|
| `prior_year_g_rp` | panel | T-1 appearances anchor |
| `role_closer_lag1` | rolling | binary T-1 role |
| `role_setup_lag1` | rolling | binary T-1 role |
| `role_middle_lag1` | rolling | binary T-1 role |
| `age` | panel | T-1 age |
| `arche_overall_prior` | panel | T-1 archetype 20-80 |
| `prior_year_fp_per_g_rp` | panel | T-1 quality |

Missing values mean-imputed within each LOYO fold.

## Headline LOYO R²

| Model | R² | r | MAE | n |
|---|---|---|---|---|
| Anchor (`prior_year_g_rp` only) | 0.1073 | 0.328 | 12.52 | 1,753 |
| **Blend (full feats)** | **0.1366** | **0.371** | **12.27** | **1,753** |
| ΔR² | +0.0293 | | −0.25 | |

**Bootstrap ΔR² (200 resamples):** mean +0.030, CI95 [+0.015, +0.044] — **SIGNIFICANT** (CI excludes 0).

## Per-year convergence (Rule 8)

| Year | blend R² | anchor R² | Δ | Pos? |
|---|---|---|---|---|
| 2018 | 0.175 | 0.175 | −0.000 | – |
| 2019 | 0.228 | 0.165 | +0.063 | + |
| 2021 | −0.098 | −0.140 | +0.042 | + |
| 2022 | 0.150 | 0.113 | +0.037 | + |
| 2023 | 0.203 | 0.158 | +0.044 | + |
| 2024 | 0.066 | 0.075 | −0.008 | – |
| 2025 | 0.198 | 0.167 | +0.031 | + |

**Convergence: 5/7 positive folds.** 2018 and 2024 effectively flat (deltas within bootstrap noise). No fold materially negative.

## Per-feature drop test

| Drop feature | Resulting R² | Δfull |
|---|---|---|
| `role_closer_lag1` | 0.118 | **−0.019** (most important) |
| `role_setup_lag1` | 0.125 | **−0.012** |
| `role_middle_lag1` | 0.127 | **−0.010** |
| `age` | 0.134 | −0.003 |
| `prior_year_g_rp` | 0.136 | −0.000 (redundant w/ role) |
| `arche_overall_prior` | 0.137 | +0.000 (noise) |
| `prior_year_fp_per_g_rp` | 0.140 | +0.003 (noise) |

Role indicators carry all the meaningful signal. `arche_overall_prior` and `prior_year_fp_per_g_rp` are noise on this target — confirming closers/setups/middles are role-driven appearance machines and prior quality has no marginal info once role is known.

## Standardized coefficients (full sample fit)

| Feature | Coef |
|---|---|
| `role_closer_lag1` | +3.03 |
| `role_setup_lag1` | +2.54 |
| `role_middle_lag1` | +2.41 |
| `prior_year_g_rp` | +2.00 |
| `age` | +1.19 |
| `arche_overall_prior` | +0.62 |
| `prior_year_fp_per_g_rp` | −0.08 |
| intercept | +50.58 |

Alpha=119.4. Intercept ≈ mean(G). Closer-role indicator adds ~3 G/yr over baseline non-role, prior_year_g adds ~2 G/yr per σ of prior G.

## Sample predictions (2025 hold-out)

Top-8 predicted closers, observed vs predicted:

| pitcher | role_lag1 | prior_g | actual_g | E[G] pred |
|---|---|---|---|---|
| 643377 | closer | 72 | 73 | 62.6 |
| 628452 | closer | 66 | 70 | 62.3 |
| 489446 | closer | 61 | 50 | 62.0 |
| 623352 | closer | 71 | 48 | 61.7 |
| 656546 | closer | 68 | 71 | 61.6 |
| 592094 | setup  | 74 | 65 | 61.6 |
| 547973 | closer | 68 | 67 | 61.5 |
| 455119 | setup  | 45 | 49 | 61.1 |

Predictions cluster in 60–63 G range for known closers/setups; actual G varies 48–73, reflecting the irreducible season-injury/usage variance the model can't see.

## Multi-test gates

- Rule 8 convergence: **PASS** (5/7, all positive bootstrap CI)
- Rule 9 baseline: **PASS** (anchor includes the obvious dominant predictor `prior_year_g_rp`)
- Bonferroni: only one promoted comparison, no inflation
- 2020 exclusion: respected
- Bootstrap CI for ΔR² strictly positive: **PASS**

**Verdict:** E[G] is a real but modest model. R²=0.14, ΔR² +0.03 over anchor. Useful as an explicit appearance predictor for the layered architecture; not promotable as a standalone signal.

## Outputs

- `data/research/validation_runs/e_of_g_preds_2026-06-06.parquet` — hold-out preds 1,753 rows
