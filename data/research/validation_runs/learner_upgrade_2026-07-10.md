# Pre-registration: LEARNER UPGRADE test (Ridge → gradient boosting) — 2026-07-10

**Status:** PRE-REGISTERED (written before any evaluation run).
**Engine:** `scripts/xfp/validate_learner_upgrade.py`
**Author:** validation agent, 2026-07-10.

## Hypothesis

The production rh3 / rp3 models are linear (StandardScaler + RidgeCV). A
gradient-boosted tree learner (sklearn `HistGradientBoostingRegressor`, no new
dependencies) on the IDENTICAL features, IDENTICAL rows, IDENTICAL target, and
IDENTICAL leave-one-year-out folds may capture nonlinearities/interactions the
linear model cannot, lifting pooled cross-year r. This is a LEARNER test, not a
feature test — the feature set is frozen at production RH3_FEATS (21) /
RP3_FEATS (24).

## Cells (Bonferroni family of 4)

| Cell | Model | Learner |
|------|-------|---------|
| L1 | rh3 | HistGradientBoostingRegressor (inner-CV tuned per fold) |
| L2 | rp3 | HistGradientBoostingRegressor (inner-CV tuned per fold) |
| L3 | rh3 | Blend: 0.5·Ridge + 0.5·GBM out-of-fold predictions |
| L4 | rp3 | Blend: 0.5·Ridge + 0.5·GBM out-of-fold predictions |

4 cells → the Δr gate is effect-size based (registry convention), but any
interpretive p-style claims use α = 0.05/4 = 0.0125. Blend weight 0.5/0.5 is
FIXED a priori — no weight tuning, no post-hoc weight search.

## Protocol (production parity)

- **rh3:** prep via `scripts/xfp/_validate_rh3_v3_helper.load_and_prep_rh3_inputs()`
  (mirrors rh3.main()); folds/filters exactly `rh3.cross_year_eval`:
  dropna(RH3_FEATS + target), `pa_to >= 50`, `ros_pa >= 100`, `year != 2020`,
  TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025], LOO by year,
  skip fold if train < 100 or test < 30. Target `ros_full_fp_per_pa`
  (post-SB-fix as of today).
- **rp3:** prep via `scripts/xfp/_rp3_validation_harness.prep_rolling()`;
  filters exactly `rp3.cross_year_eval`: dropna(RP3_FEATS + target),
  `gs_to >= 2`, `ros_gs >= 5`, `year != 2020`, same LOO years, skip if
  train < 50 or test < 10. Target `ros_fp_per_start`.
- **Cache-stability guard:** each model's input CSVs are loaded ONCE and the
  prepped DataFrame is pickled to the session scratchpad; every fold chunk
  reloads that pickle (another agent may regenerate the rolling cache
  mid-session). The Ridge baseline r actually measured on this frozen frame is
  the baseline of record (expected ≈ 0.6275 rh3 / ≈ 0.5614 rp3).
- **Identical rows per fold:** Ridge and GBM are fit/scored on the SAME
  train/test frames (single dropna+filter pass before the learner loop);
  script asserts identical n per fold.

## Fairness rules

- **Ridge baseline = production pipeline exactly:** per fold,
  `Pipeline(StandardScaler, RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))` —
  its alpha tunes per fold, same as production `cross_year_eval`.
- **GBM gets a LIGHT inner-CV tune per fold** over this pre-declared grid and
  NOTHING else (no grid expansion after seeing results, no test-year peeking):
  - `max_iter`: {200, 500}
  - `learning_rate`: {0.05, 0.1}
  - `max_leaf_nodes`: {15, 31}
  - `min_samples_leaf`: {50, 200}
  - all other params sklearn defaults; `random_state=0`; early stopping OFF
    (`early_stopping=False`) so max_iter is exact and no validation split
    leaks rows.
- **Inner CV:** 3-fold `KFold(shuffle=True, random_state=0)` on the train-years
  rows only; selection metric = Pearson r between inner-held-out predictions
  and actuals (matches the outer metric). Best config refit on the full
  training fold, then scored once on the held-out year.
- **Blend:** computed post hoc from the SAVED out-of-fold predictions
  (0.5·ridge_pred + 0.5·gbm_seed0_pred per row); no refitting.

## Gates (per cell, same as registry standard)

1. Pooled cross-year r lift ≥ +0.005 vs the measured Ridge baseline.
2. Per-year sign consistency: Δr > 0 in ≥ 5/7 years.
3. Holdout years 2024 & 2025 lift positive (both, or at minimum avg > 0).

Report per-year r for Ridge, GBM, and blend + pooled r + pooled MAE for all.

## Pre-registered honesty checks

(a) **Overfit diagnostic:** per fold, in-sample (train) r for Ridge vs GBM
    (selected config). A much larger train/test r gap for GBM with matched
    held-out r = memorizing year idiosyncrasies → flag even if gates pass.
(b) **Tail check:** pooled pred-decile calibration (10 bins by each learner's
    own predictions): mean pred vs mean actual per decile. GBM must not
    materially worsen top/bottom-decile bias vs Ridge (the league is played
    on the tails). "Materially worsen" = |bias| in decile 1 or 10 grows by
    > 50% AND > 0.5 pooled-MAE units relative to Ridge.
(c) **Stability:** refit the selected config per fold at seeds {0, 1, 2};
    report pooled-r spread across seeds. Headline GBM number = seed 0.

## Interpretation ladder (pre-declared)

- Lift < +0.005 → **REJECTED** — linear is enough on these features; future r
  gains must come from FEATURES/DATA, not learners. Documented dead end.
- +0.005 to +0.01 → **MARGINAL** — report only, no integration recommendation.
- ≥ +0.01 with clean diagnostics (a)-(c) → **PASS** — write the integration
  recipe (pipeline changes; `fit_residual_ci` is residual-based/model-agnostic
  — verify compatibility) but do NOT integrate (Rule 7; orchestrator decides).

Cells are judged independently; a blend PASS with a solo-GBM REJECT is
reported as such (ensemble value, not learner replacement).

## Runtime contingency (pre-declared BEFORE the sweep)

Grid = 16 configs × 3 inner folds = 48 GBM fits per outer fold, 7 folds,
2 models. First run = single fold (2025) per model to measure wall time. If
extrapolated full-sweep time exceeds ~25 min/model, the grid is cut — by
dropping `max_iter=500` (leaving 8 configs) — BEFORE the sweep, and that cut
applies to ALL folds/cells uniformly. No other cut is permitted.

## What would make this invalid

- Any grid value added/removed after seeing held-out results.
- Blend weight tuned after seeing results.
- Rows/filters/target differing between Ridge and GBM within a fold.
- Selecting GBM config on the held-out year.
