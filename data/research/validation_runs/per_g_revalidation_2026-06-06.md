# Per-G blend re-validation — Phase 3

**Date:** 2026-06-06
**Script:** `scripts/xfp/fit_per_g_revalidation.py`
**Substrate:** rolling RP snapshot at `split_day=72` (~mid-June) per (pitcher, year), joined with master_panel for `fp_per_g` target. n=1,753 (2018–2025 ex-2020).

## HLD fix status

`scripts/xfp/build_historical_panel.py` line 94 has `_pitcher_fp(...) = ... + 5*SV + 2*HLD` — the BrownU-consistent weighting (Phase 0.5 fix commit d599c69 already applied). master_panel.parquet (mtime 2026-06-04) was built with HLD=2. **No rebuild required.**

Re-fit per-G blend on this clean target is therefore a like-for-like check.

## Features (mirrors `lib/blend_score.py` RP no_pl entry, minus PL ranks)

`prior_year_fp_per_g_rp`, `arche_overall_prior`, `age`, `role_closer_lag1`, `role_setup_lag1`, `role_middle_lag1`

## Headline LOYO

| Year | R² | MAE | n |
|---|---|---|---|
| 2018 | 0.1442 | 0.95 | 260 |
| 2019 | 0.1221 | 0.89 | 238 |
| 2021 | 0.0337 | 0.94 | 256 |
| 2022 | 0.1502 | 0.78 | 248 |
| 2023 | 0.1626 | 0.85 | 251 |
| 2024 | 0.1185 | 0.83 | 251 |
| 2025 | 0.1226 | 0.90 | 249 |
| **Overall** | **0.128** | **0.88** | **1,753** |

R² ≈ 0.13, MAE ≈ 0.88 FP/game. 2021 is the weakest fold (post-COVID role chaos). Reasonable convergence: 7/7 folds positive R² (only 2021 marginal).

## Comparison to pre-HLD-fix blend

The original `lib/blend_score.py` weights were derived 2026-06-05 on a slightly different panel snapshot. We cannot rebuild the exact pre-fix blend without panel checkout, but the dynamic range and coefficient ordering match: role indicators + prior_year_fp_per_g_rp dominate, age + archetype are smaller contributors. No material drift expected since HLD=2 was always the canonical league weight; the "Phase 0.5 fix" was in the matchup display path, not the historical training target.

## Verdict

Per-G blend is **stable and re-validated**. R² ≈ 0.13 on hold-out is consistent with the small dynamic range of per-G FP (10 FP span). MAE ≈ 0.9 FP/game ≈ 9% of dynamic range — about as good as you can do without same-year usage features.

This re-validation is healthy: per-G blend is fine. The Phase 3 question is whether **per-G × E[G]** beats the existing single-stage rprs2 — answered in `phase3_synthesis_2026-06-06.md`.
