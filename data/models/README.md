# xFP Models

## Production
- **xfp_v11_pipeline.pkl** — CURRENT PRODUCTION (V8.5 features + pitching_plus + fp_strike_pct).
  Cross-year r 0.614, k_bias_hi 0.773, YTD r 0.511, YTD MAE 3.393. Trained on 2020-2025 (n=768).
  Bundle includes: pipeline (Pipeline), features (list), cross_year_r, k_bias_hi, score_current,
  score_tolerance_T1, formula, trained_date, n_train, version='v11', training_years='2020-2025',
  ytd_mae_2026, ytd_r_2026, comparison{...}, note.

## Frozen Reference
- **xfp_v8_pipeline.pkl** — V8 4-feature minimal core. Cross-year r 0.558, k_bias 0.241, score 1.555.
  Kept as ablation reference. **Do not retrain.**

## Superseded (kept for V8.5 vs V11 comparison)
- **xfp_v8_5_pipeline.pkl** — V8.5 (12 features). Cross-year r 0.600, score 1.567. Superseded by V11.
  Used in dashboard for V8.5 vs V11 delta comparisons.

## Archive (`data/models/archive/`)
Failed or intermediate model versions. See `data/research/xfp_model_research.md` for why each was
archived. Contents:
- **xfp_v7_pipeline.pkl** — V7 6-feature BE selection (had Phase 9 score-formula bug).
- **xfp_v9_no_ip_pipeline.pkl** — V9 IP-decomposition stuff-only sub-model (failed to ship).

## Notes
The other model artifacts in this directory (`batted_ball_model_*`, `swing_model_*`, etc.) belong to
the separate PLV pipeline and are unrelated to xFP. Do not modify them through xFP workflows.
