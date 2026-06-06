# Phase 3 synthesis — two-layer per-G × E[G] RP architecture

**Date:** 2026-06-06
**Status:** Research complete, NOT promoted.
**Verdict:** **ARCHIVE** — layered architecture does not beat rprs2; document and stop.

## 1. Audit outcome

`src/plv_clone/models/xfp/rprs2.py` is a single-stage RidgeCV predicting `fp_year_total` from 25 features (BASE_FEATS + NEW_FEATS). It implicitly bundles per-G × G because its feature set contains both (a) usage counts that scale with G (`g_to`, `ip_to`, `sv_to`, `hld_to`, `fp_with_role_to`) AND (b) per-rate features (`k_pct_to`, `xwoba_per_pa_to`, etc.). The target `fp_year_total` is a count, so the model naturally absorbs the multiplicative G structure into its coefficients.

`master_panel.parquet` already uses HLD=2 (Phase 0.5 weighting baked into `build_historical_panel.py`). No rebuild was needed. `rolling_relievers_2018_2026.csv` has `role_lag1`, `prior_year_g_rp` (via panel join), `arche_overall_prior` (1,107/2,623 RP rows, ~42% coverage), and `age` (1,860/2,623 ~71%). Sparse coverage was handled with per-fold mean-imputation.

## 2. E[G] model performance

LOYO 2018–2025 ex-2020, n=1,753 RP-years. Anchor = `prior_year_g_rp` alone, R²=0.107. Blend with role + age + arche + prior_fp_per_g lifts to **R²=0.137 (Δ +0.029, bootstrap CI95 [+0.015, +0.044], SIGNIFICANT)**, 5/7 year-folds positive. Drop-test confirms role indicators carry essentially all the marginal lift (role_closer_lag1 −0.019, role_setup −0.012, role_middle −0.010). Archetype and prior fp_per_g are noise on this target (positive Δ when dropped). MAE 12.27 G on a 15.9 G std — ~77% of the irreducible variance is structural (injuries, role changes mid-year, team usage patterns).

E[G] is a real but modest model. It would never displace anything; it exists to provide an explicit appearance factor for layered multiplication.

## 3. Per-G re-validation

Per-G ridge on the same substrate with `prior_year_fp_per_g_rp`, arche, age, role indicators: **R²=0.128, MAE=0.88 FP/g**. Matches the pre-Phase-0.5 dynamic range. The HLD=2 weighting was already canonical in master_panel — Phase 0.5's fix was in the matchup display, not the training target. No coefficient drift detected.

Per-G is fine. Stable, modest R² (per-G has only ~10 FP dynamic range), 7/7 LOYO folds positive.

## 4. ros_layered vs rprs2 head-to-head

At a fair mid-June snapshot (`split_day=72`), predicting actual `fp_total`:

| Model | R² | MAE | n |
|---|---|---|---|
| rprs2-style ridge (`FEATS_RPRS2`, 25 feats) | **0.638** | **39.05** | 1,753 |
| ros_layered (per_g × E[G]) | 0.209 | 58.78 | 1,753 |
| ΔR² (layered − rprs2) | **−0.429** | | |
| ΔMAE (layered − rprs2) | **+19.7** | | |

Bootstrap CI95: rprs2 MAE − layered MAE = [+17.4, +21.3]; layered R² − rprs2 R² = [−0.46, −0.39]. Both decisively in rprs2's favor with no overlap of zero.

**Role bias is the killer.** Mean residual `pred − act` by role:

| role_lag1 | n | rprs2 resid | layered resid | rprs2 MAE | layered MAE |
|---|---|---|---|---|---|
| closer  | 214 | −0.5 | **−9.5** | 46.8 | **80.3** |
| long_low | 158 | −2.6 | **−15.9** | 37.0 | **60.5** |
| middle  | 408 | 0.0 | −0.3 | 38.6 | 51.8 |
| setup   | 184 | −0.4 | −1.5 | 39.4 | 57.8 |

rprs2 is essentially unbiased across roles. The layered model **under-predicts closers by ~10 FP and long_low arms by ~16 FP** because the per-G ridge averages over SV/HLD bonuses; multiplying by E[G] ≈ 60 doesn't recover the role-specific high-leverage scoring premium. rprs2 sees `sv_to`, `hld_to`, `fp_with_role_to` directly and routes that signal correctly.

## 5. Verdict: ARCHIVE

The two-layer hypothesis was that explicit per-G × E[G] separation would give us diagnostic separability (attribute prediction errors to a per-outing quality layer or an appearance layer). In practice:

1. **rprs2 already implicitly does this** — it has g_to / ip_to / sv_to in its feature set, so the appearance information is in there alongside per-outing quality.
2. **Multiplicative composition discards the role-dependent SV/HLD bonus structure** that rprs2 captures additively via `fp_with_role_to` and `sv_per_g_to`. You can't recover a closer's 5-FP-per-save bonus by multiplying a smoothed per-G FP by an appearance count.
3. **E[G]'s own R² ceiling is low (0.14)**, so the multiplicative product amplifies noise rather than reducing it.

The diagnosis that "per-G has low dynamic range" was correct in isolation but irrelevant to ROS prediction quality: the relevant question is whether the model picks up role-dependent FP scaling, and rprs2 already does so cleanly via in-season counting features.

**Do not promote.** Both per-G blend (already shipped in `lib/blend_score.py`) and rprs2 stay as-is. E[G] is preserved as a research artifact in `e_of_g_preds_2026-06-06.parquet` for any future studies of explicit appearance modeling.

### What would change for canonical RPs?

Under ros_layered, Duran/Morejón/Palencia (closers) would have their ROS systematically under-projected by ~9 FP each vs the rprs2 number you already see — the opposite of what we want. **No production impact** because we are not shipping.

## 6. Phase 4 promotion plan

**Not applicable** — verdict is ARCHIVE. Phase 4 is cancelled.

If revisited in future: the productive direction is probably **adding an explicit role-change signal to rprs2** (e.g., "team's prior closer now on IL" already exists in rolling substrate as `prior_closer_on_il` — see whether it's in FEATS_RPRS2; quick check shows it is **not**, which may be a meaningful gap). That's a single-feature addition, not an architecture change, and should go through `/validate-feature`.

## Files

- `scripts/xfp/fit_e_of_g_model.py` (new)
- `scripts/xfp/fit_per_g_revalidation.py` (new)
- `data/research/validation_runs/e_of_g_model_2026-06-06.md`
- `data/research/validation_runs/per_g_revalidation_2026-06-06.md`
- `data/research/validation_runs/phase3_layered_comparison_2026-06-06.json`
- `data/research/validation_runs/e_of_g_preds_2026-06-06.parquet`
- `data/research/validation_runs/phase3_synthesis_2026-06-06.md` (this file)

No production files touched.
