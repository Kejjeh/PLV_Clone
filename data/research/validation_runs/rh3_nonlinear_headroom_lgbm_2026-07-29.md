---
signal: rh3_nonlinear_headroom_lgbm
formula: >
  ONE cell. Swap the production learner only; features/rows/target/folds are
  frozen. Estimator = lightgbm.LGBMRegressor with FIXED, pre-declared params
  (no sweep, no inner CV, no early stopping):
    n_estimators=400, learning_rate=0.05, num_leaves=31,
    min_child_samples=40, subsample=0.8, subsample_freq=1,
    colsample_bytree=0.8, random_state=0, n_jobs=1, verbose=-1
  (subsample_freq=1 is declared explicitly because LightGBM ignores
  `subsample` when subsample_freq=0 — declaring it makes the bagging real
  rather than nominal.)
  Baseline = production learner exactly:
    Pipeline(StandardScaler, RidgeCV(alphas=np.logspace(-1,5,80), cv=5)),
  alpha re-tuned per fold, matching engine.cross_year_eval_ridge.
  Both learners are fit and scored on the IDENTICAL train/test rows of each
  fold (single dropna + filter pass before the learner loop; asserted).
  Metric of record = MEAN of the per-held-year Pearson r (the
  `cross_year_r` convention used by validate_delta_grid.py). Pooled
  concat-prediction r is ALSO reported for comparability with the
  2026-07-10 learner_upgrade run, which used pooled r.
  Pass/fail arithmetic delegated to scripts/xfp/lib/rule9.py::rule9_lift
  (unit-tested in tests/test_rule9.py) — not re-derived.
outcome: ros_full_fp_per_pa (plv_clone.models.xfp.rh3.TARGET)
expected_sign: "+"
theory: If any exploitable interaction or nonlinearity survives across seasons
  in the 22 engineered rh3 features, a modest leaf-wise GBM should recover it
  and beat RidgeCV's cross-year r; the 2026-05-24 ceiling audit and the
  2026-07-10 HistGB run both predict it will not.
production_target: rh3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_lgbm_headroom.py
date: 2026-07-29
verdict: REJECTED
---

# rh3 nonlinear headroom — one LightGBM cell through the Rule-9 harness

## What is being tested (and what is NOT)

This is a **LEARNER** test, not a feature test. The feature list is frozen at
the live production `RH3_FEATS` (22 features, imported at runtime from
`plv_clone.models.xfp.rh3` — never copied, per the 2026-07-28 harness-bug
memo). Nothing is added to or removed from the substrate.

**Declared cells: exactly ONE.**

| # | Cell | Learner | Params |
|---|---|---|---|
| N1 | rh3, 22 feats, LOO-by-year | `LGBMRegressor` | fixed, listed in the front-matter |

A parameter sweep would be many Rule-3 cells requiring Bonferroni/BH
correction and would invite exactly the "tune toward a pass" failure this
protocol exists to prevent. **No sweep is run.** The params above are a
single, conventional, modest configuration chosen a priori for a frame of
this size (~36-38k rows, 22 features) and are frozen before the first fit.
If they are wrong for the data, the honest outcome is a REJECTED cell, not a
second guess.

## Frame construction (production parity)

Assembled the same way `scripts/xfp/validate_delta_grid.py` does, so the
baseline is the real 22-feature substrate rather than a curated subset
(**Rule 9**):

1. `rolling = pd.read_csv(rh3.ROLLING_CSV)`, `multiyr = pd.read_csv(rh3.MULTIYR_CSV)`
2. `attach_production_features(rolling, multiyr)` from
   `scripts/xfp/validate_inseason_discipline.py` — replicates `rh3.main()`'s
   attachment: Marcel prior + AAA call-up blend, `lift_h2_aug150`,
   `xwoba_residual_career`, `career_stage`, `ros_opp_sp_xwoba_weighted`,
   `bx_prior_h`, then `apply_shrinkage(SHRINK_SPEC_TO)`.
3. `dropna(RH3_FEATS + [TARGET])`
4. `pa_to >= EVAL_PA_MIN (50)` AND `ros_pa >= ROS_PA_MIN (100)` AND `year != 2020`
5. Folds: leave-one-year-out over `rh3.TRAIN_YEARS = [2018, 2019, 2021, 2022,
   2023, 2024, 2025]`; skip a fold if `len(train) < 100` or `len(test) < 30`
   (production `min_train`/`min_test`).

**Non-overlap note.** This study does not construct any window/lag feature,
so the 2026-07-29 non-overlapping-anchor requirement has no candidate to
apply to. The frame is the production frame, which does contain multiple
`split_day` snapshots per batter-year — that is true of the production
baseline itself, and both arms of the comparison see the identical rows, so
it cannot bias the *difference*. It does mean the absolute r values here are
production-convention numbers, not independent-sample numbers, and no
significance claim is made from n.

## Gates (pre-declared, via `rule9_lift`)

1. **Effect:** mean cross-year r lift `>= +0.005` vs the measured RidgeCV
   baseline. (The standard rh3 promotion bar.)
2. **Sign consistency:** `sign_match_years >= 5/7`.
3. **Holdout:** mean lift over 2024 + 2025 positive. The holdout years are
   never used to select anything — there is nothing to select, the config is
   fixed.

Interpretation ladder, fixed in advance:

- lift `< +0.005` → **REJECTED**. Confirms the documented dead end.
- `+0.005` to `+0.01` → **MARGINAL**. Report only; no integration proposal.
- `>= +0.01` with 5/7 signs and positive holdout → **PASS**, write an
  integration recipe but do not integrate (Rule 7 / task constraint 4).

## Descriptive companion (NOT a test cell — no gate, no p-value)

A feature-importance read over the 22 features, reported regardless of the
verdict, aggregated across the 7 LOO folds so it is out-of-sample:

- **LGBM gain importance** (`importance_type='gain'`), mean over folds,
  normalized to % of total gain.
- **LGBM split importance** (`importance_type='split'`), mean over folds.
- **Permutation importance** on the **held-out year** of each fold
  (`sklearn.inspection.permutation_importance`, `n_repeats=5`,
  `random_state=0`, scoring = negative MSE), mean over folds. Held-out-year
  permutation is the honest version; in-sample permutation would just
  re-describe the memorization.
- **Ridge standardized |coef|**, mean over folds, as the linear-side
  comparison.

This is exploratory and is explicitly labelled as such: it may **seed** a
future pre-registered feature-pruning study, but no feature may be dropped
from `RH3_FEATS` on the strength of this table alone. Ranking 22 features
and acting on the bottom of the list without a pre-registered ablation is
precisely a Rule-3 multiplicity violation.

## Prior art (this cell is a CONFIRMATION run, and is priced as such)

1. **`data/research/ceiling_audit_2026-05-24.md` — rh3 nonlinear verdict
   `AT_CEILING`.** Ridge `+0.6167`, XGB `+0.6167` (gap `+0.0000`), RF
   `+0.5830` (gap `−0.0337`), on 8,322 substrate rows / 20 baseline feats.
   `ceiling.py::nonlinear_ceiling` thresholds: positive-side gap `< 0.003`
   → AT_CEILING. XGB exactly tied Ridge; RF lost badly.
2. **`learner_upgrade_2026-07-10` — all four cells REJECTED.** rh3
   `HistGradientBoostingRegressor` with a 16-config inner-CV tune scored
   pooled r `0.5738` vs Ridge `0.6275` → **−0.0537**, winning 1/7 years.
   The 0.5/0.5 Ridge+GBM blend was `0.6257` → **−0.0018**. Diagnostics: GBM
   train-minus-test r gap **+0.386** (Ridge +0.006), and materially worse
   decile-1/decile-10 bias. Registry family `learner_upgrade` is recorded as
   a documented dead end with an explicit "do not re-attempt tree learners /
   GBM / just try XGBoost on the same feature set."
3. **CLAUDE.md #11/#12** — trajectory and in-season delta families closed;
   `inseason_delta_grid_2026-07-29` closed 60 more cells at ~0. The standing
   conclusion is that rh3 r gains must come from FEATURES/DATA.

**Why run it anyway.** (a) LightGBM's leaf-wise growth is a genuinely
different inductive bias from HistGB's and XGB's depth-wise growth, and it
was never tested; (b) both prior runs predate the current 22-feature
substrate (`bx_prior_h` promoted 2026-07-10, AAA call-up blend 2026-07-19)
and the 2026-05-24 audit predates it by two feature generations; (c) it is
cheap. But the expected value is **confirmation, not discovery**, and a
positive result here would be *surprising* and would demand replication
before anyone believed it — that asymmetry is declared now, before the
numbers, so a fluke cannot be laundered into a PASS after the fact.

## Harness-bug exposure (`docs/rh3_harness_root_bug_2026-07-28.md`)

That memo documents two bugs in a *different* harness
(`scripts/xfp/research/validate_rh3_breakout_signals.py`): a `ROOT` anchor
resolving one directory too shallow after a file move, silently zeroing
three baseline inputs, and a hardcoded 21-feature `RH3_FEATS` copy. Both
degraded the Rule-9 baseline by up to −0.0368, i.e. 7.4× the promotion gate.

This study is insulated by construction:

- The new script lives at `scripts/xfp/` and anchors the repo root with the
  **marker walk-up** the memo prescribes
  (`next(p for p in ... if (p/'pyproject.toml').is_file())`), so it is
  move-proof and satisfies `tests/test_repo_root_paths.py`.
- `RH3_FEATS` is **imported live**, never copied. The script asserts
  `len(RH3_FEATS) == 22` and prints the list, so a future promotion that
  changes the count is loud, not silent.
- It reuses `attach_production_features`, whose input CSV constants come
  from the production `rh3` module (`ROLLING_CSV`, `MULTIYR_CSV`,
  `H2_LOCKED_CSV`, `XWOBA_RESID_CSV`, `BX_PRIORS_CSV`) plus a root-relative
  `ros_opp_sp_xwoba_per_hitter.csv`. Every path is existence-checked before
  the run and the measured Ridge baseline is reported so a degraded baseline
  would be visible as an off number.
- **Most importantly, a degraded baseline is the failure mode this design is
  structurally immune to in one direction:** both arms share one frame, so
  any input degradation lowers Ridge *and* LGBM together. It could not
  manufacture a spurious learner lift — it could only shift both absolute
  numbers. The Ridge value is reported against the two independently
  established reference points (0.6418 from the fixed harness / 0.6275 from
  the 07-10 frozen frame) as the check.

## What would invalidate this run

- Any change to the LGBM params after seeing a fold result.
- Adding a second learner, a blend, or a seed sweep and reporting the best.
- Ridge and LGBM seeing different rows within a fold.
- Editing this front-matter after results (a RESULT section is appended
  instead; only `verdict:` is added at the end).

---

# RESULT (2026-07-29, run after the above was written)

**Engine:** `scripts/xfp/validate_lgbm_headroom.py`
**JSON:** `data/research/validation_runs/rh3_nonlinear_headroom_lgbm_2026-07-29_results.json`

## Frame actually measured

```
RH3_FEATS: 22 (live import, asserted)
frame after dropna + pa_to>=50 + ros_pa>=100 + year!=2020:  38,758 rows
pooled test n across the 7 LOO held years:                  36,571 rows
per-year n: 2018 5,154 | 2019 5,387 | 2021 5,258 | 2022 5,055
            2023 5,312 | 2024 5,271 | 2025 5,134 | (2026 2,187, train-only)
```

### Baseline parity — verified, not assumed

The Ridge arm was checked against production by calling
`rh3.cross_year_eval(frame, RH3_FEATS)` directly:

| | this script's Ridge arm | `rh3.cross_year_eval` |
|---|---|---|
| pooled r | 0.6419 | **0.6419** |
| pooled MAE | 0.08463 | **0.0846** |
| pooled n | 36,571 | **36,571** |
| 2018 / 2019 / 2021 | 0.6273 / 0.6946 / 0.5854 | **identical** |
| 2022 / 2023 | 0.6481 / 0.6236 | **identical** |
| 2024 / 2025 | 0.6270 / 0.6437 | **identical** |

Every figure matches to 4 decimals, and the pooled r reproduces the two
independent reference assemblies from 2026-07-28 (`0.6418`, n=36,571). The
Rule-9 baseline is the genuine 22-feature production model — not a
reconstruction of it.

**Observation, not a bug:** the frame carries 2,187 **2026** rows
(`split_day` 30–93 only; later 2026 snapshots are removed by
`ros_pa >= 100` because the season is incomplete). They are never a held-out
test year, but they *are* in the training set of all 7 folds. This is exactly
what production `cross_year_eval` does — same `dropna`, same `filter_fn`,
same `year != held` train split — so parity holds and both arms see them
identically. Their mean `ros_pa` is 188 vs 251 for completed seasons, i.e. a
shorter but genuinely-observed horizon, not leakage. Flagged only so a future
reader does not mistake the 38,758 → 36,571 gap for a filter bug.

## Headline — Cell N1: REJECTED

| Learner | mean cross-year r | pooled r | pooled MAE |
|---|---|---|---|
| **RidgeCV (production)** | **0.6357** | **0.6419** | 0.08463 |
| LightGBM (fixed params) | 0.6123 | 0.6121 | 0.08744 |
| **lift** | **−0.0234** | −0.0298 | +0.00281 (worse) |

Gates via `rule9_lift`:

| Gate | Bar | Actual | Result |
|---|---|---|---|
| Mean cross-year r lift | ≥ +0.005 | **−0.0234** | **FAIL** |
| Sign consistency | ≥ 5/7 years | **1/7** | **FAIL** |
| Holdout 2024-25 mean lift | > 0 | **−0.0120** | **FAIL** |

Three of three gates fail, all in the same direction. The lift is −4.7× the
promotion bar.

## Per-year detail

| held year | Ridge r | LGBM r | Δ | n |
|---|---|---|---|---|
| 2018 | 0.6273 | 0.6230 | −0.0043 | 5,154 |
| 2019 | 0.6946 | 0.6597 | −0.0349 | 5,387 |
| 2021 | 0.5854 | 0.5446 | −0.0408 | 5,258 |
| 2022 | 0.6481 | 0.6255 | −0.0226 | 5,055 |
| 2023 | 0.6236 | 0.5864 | −0.0372 | 5,312 |
| **2024 [HOLDOUT]** | 0.6270 | **0.6465** | **+0.0195** | 5,271 |
| 2025 [HOLDOUT] | 0.6437 | 0.6002 | −0.0435 | 5,134 |

**2024 is the one year LightGBM wins, and it is a holdout year.** This is
worth stating plainly because it is the cheapest available lesson in why the
sign-consistency gate exists: a study that had looked only at 2024 would have
reported "+0.0195 lift on untouched holdout data" and had a plausible-sounding
PASS. Six of the other years contradict it, including the other holdout year
by more than twice the magnitude. The 2024 result is noise, and the
pre-registered 5/7 gate is what makes that conclusion available rather than a
judgement call after the fact.

## Overfit diagnostic

| Learner | mean in-sample r | mean held-out r | gap |
|---|---|---|---|
| RidgeCV | 0.6399 | 0.6357 | **+0.0043** |
| LightGBM | 0.9095 | 0.6123 | **+0.2973** |

The same signature the 2026-07-10 HistGB run recorded (Ridge +0.006 / GBM
+0.386). LightGBM reaches in-sample r ≈ 0.91 and transfers 0.61. Ridge's
train and held-out r differ by 0.004 — it has essentially no capacity left to
surrender. **The failure is bias/transfer, not tuning.**

### Honest note on the comparison to the 07-10 run

Fixed-param LightGBM did **substantially better** than the inner-CV-tuned
HistGB: pooled lift **−0.0298 vs −0.0537**. That is a real, reportable
difference and it points the same way as the 07-10 memo's own observation
that inner 3-fold CV on shuffled mixed-year rows selected the most flexible
grid corner in all 14 folds. Less tuning produced a better tree model here.
It still lost to Ridge in 6 of 7 years. The gap between the two GBM runs is
about *how badly* trees lose, not about whether they win.

## Feature importance over the 22 features (descriptive)

Mean over the 7 LOO folds. Permutation importance is measured on each fold's
**held-out year** (`n_repeats=5`, negative-MSE scoring) and reported as MSE
increase ×1e5. Ridge |coef| is on the standardized scale. Sorted by LGBM
gain.

| rank | feature | LGBM gain % | LGBM splits | perm (heldout, ×1e5) | Ridge \|coef\| |
|---|---|---|---|---|---|
| 1 | `bx_prior_h` | 24.67 | 1,082 | **232.92** | 0.02457 |
| 2 | `prior_fp_per_pa` | 10.13 | 1,171 | 13.62 | 0.01203 |
| 3 | `xwoba_per_pa_to_sh` | 9.37 | 428 | 60.52 | 0.01424 |
| 4 | `xwoba_residual_career` | 6.84 | 1,213 | 38.95 | 0.01224 |
| 5 | `lift_h2_aug150` | 6.79 | 910 | 101.95 | 0.01237 |
| 6 | `prior_pa_eff` | 5.87 | 1,144 | 14.85 | 0.00505 |
| 7 | `iso_to_sh` | 4.47 | 374 | 42.17 | 0.01725 |
| 8 | `ros_opp_sp_xwoba_weighted` | 3.72 | 535 | 22.23 | 0.01593 |
| 9 | `k_pct_to_sh` | 3.65 | 422 | 20.96 | 0.01449 |
| 10 | `hard_hit_pct_to_sh` | 3.24 | 506 | 53.57 | 0.01707 |
| 11 | `in_play_pct_to_sh` | 2.60 | 433 | 18.06 | 0.00739 |
| 12 | `sb_per_pa_to_sh` | 2.51 | 477 | 17.51 | 0.01306 |
| 13 | `contact_pct_to_sh` | 2.46 | 307 | 9.07 | 0.00941 |
| 14 | `career_stage` | 2.41 | 520 | 2.70 | 0.00503 |
| 15 | `swstr_pct_to_sh` | 1.85 | 406 | 6.61 | 0.00241 |
| 16 | `hr_per_pa_to_sh` | 1.83 | 331 | 6.19 | 0.00796 |
| 17 | `barrel_pct_to_sh` | 1.72 | 420 | 12.87 | 0.00798 |
| 18 | `whiff_pct_to_sh` | 1.72 | 188 | 6.48 | 0.00941 |
| 19 | `chase_pct_to_sh` | 1.70 | 448 | **−4.90** | 0.00251 |
| 20 | `bb_pct_to_sh` | 1.27 | 357 | **−0.19** | 0.00273 |
| 21 | `pa_to` | 0.88 | 221 | 6.95 | 0.00689 |
| 22 | `split_day` | 0.33 | 106 | 4.02 | 0.00170 |

### Reading of the table

**1. The four externally-joined priors dominate — and that independently
explains the size of the 2026-07-28 harness bug.** `bx_prior_h`,
`lift_h2_aug150`, `xwoba_residual_career`, and `ros_opp_sp_xwoba_weighted`
rank **1st, 2nd, 5th, and 7th by held-out permutation importance** (232.9,
102.0, 39.0, 22.2) out of 22. Those are precisely the four features the
`ROOT`-path bug damaged: three were silently zeroed and the fourth
(`bx_prior_h`) was the missing 22nd feature. The memo measured that
degradation at **−0.0368** cross-year r. This importance ranking, computed
by a completely different method and for a different purpose, says the bug
removed the #1, #2, #5, and #7 most load-bearing features in the model — so
a −0.037 hit is exactly the right order of magnitude. Two independent
measurements corroborating each other is the strongest thing in this memo.
The practical lesson: **rh3's leverage sits disproportionately in the merged
side-table features, which are also the ones whose joins fail silently.**
Those merges deserve the loudest guardrails in the pipeline, and per the
07-28 fix they now have them.

**2. Both learners agree on the top of the list, which is *why* the tree has
no edge.** `bx_prior_h` is #1 by LGBM gain (24.7%) *and* by Ridge
standardized |coef| (0.0246). The rate features Ridge weights most
(`iso_to_sh` 0.0173, `hard_hit_pct_to_sh` 0.0171, `ros_opp_sp` 0.0159) are
also the rate features LGBM permutes worst (42.2, 53.6, 22.2). When the
linear and the tree model locate the same structure, the tree's extra
capacity has nothing to spend itself on except year-specific noise — which
is what the +0.297 overfit gap is.

**3. `pa_to` and `split_day` rank LAST by LGBM gain** (0.88%, 0.33%) — a
mild surprise worth recording, since they are the frame's two
sample-size/horizon controls and one might expect a tree to lean on them for
interaction structure. Ridge also gives them small coefficients (0.0069,
0.0017). They are doing a narrow job (scaling the shrinkage-vs-observation
tradeoff), not carrying skill signal.

**4. Two features have ≤0 held-out permutation importance:**
`chase_pct_to_sh` (**−4.90** — permuting it *improves* LGBM's held-out MSE)
and `bb_pct_to_sh` (−0.19, indistinguishable from zero). Their Ridge
coefficients are also the 3rd and 4th smallest (0.0025, 0.0027). Two lenses
agreeing that these two contribute ~nothing makes them the natural first
candidates for a pruning study. This is *suggestive* and no more, for three
reasons that must travel with the number: (a) it is measured inside a learner
that lost by 0.023, so it is weak evidence about the Ridge model actually in
production; (b) the nine shrunken contact/discipline rates are heavily
collinear with each other and with `xwoba_per_pa_to_sh`, so single-feature
importance systematically understates the block — dropping them one at a time
would each look free and collectively be expensive; (c) low *average*
importance is not no value, since a feature can be cheap insurance on a small
subpopulation. It is, however, a suggestive convergence with the 2026-07-29
cutoff study, which found chase and BB% to be among the slowest-stabilizing
hitter metrics (BB% needs 175 PA and never reaches r=0.70 in-window).

**Explicit non-authorization:** nothing in this table may move `RH3_FEATS`.
Ranking 22 features and cutting the tail is a 22-cell implicit sweep. A real
pruning study needs its own pre-registration: leave-one-feature-out (and
leave-one-*block*-out) ablation under the production RidgeCV learner, BH-FDR
across the declared cells, and the +0.005 bar applied in the *removal*
direction with the 2024-25 holdout untouched.

## Verdict: REJECTED

**There is no nonlinear headroom in rh3, and this is now the third
independent method to say so.**

| Study | Date | Learner | Growth strategy | vs Ridge (pooled) |
|---|---|---|---|---|
| `ceiling_audit` | 2026-05-24 | XGBoost | depth-wise | `+0.0000` → AT_CEILING |
| `ceiling_audit` | 2026-05-24 | RandomForest | bagged | `−0.0337` |
| `learner_upgrade` L1 | 2026-07-10 | HistGB, inner-CV tuned | depth-wise, binned | `−0.0537` |
| `learner_upgrade` L3 | 2026-07-10 | 0.5·Ridge + 0.5·HistGB | blend | `−0.0018` |
| **this run, N1** | **2026-07-29** | **LightGBM, fixed params** | **leaf-wise** | **−0.0298** |

Answering the question the prior art left open: the 2026-05-24 audit's
`AT_CEILING` verdict for rh3 (XGB gap `+0.0000`, RF gap `−0.0337`) **still
holds on the current 22-feature substrate**, two feature generations later.
Four architecturally distinct tree ensembles — depth-wise, histogram-binned
depth-wise, leaf-wise, and bagged — land at or below RidgeCV. The tuned one
did worse than the untuned one. Every GBM shows a +0.30 to +0.39 in-sample
gap where Ridge shows +0.004.

The features are already engineered, shrunk, and pre-transformed; the signal
in them is linear-and-additive to within measurement error, and the residual
is irreducible-given-these-features rather than functional-form error.
**rh3's ceiling is a DATA ceiling, not a MODEL ceiling.**

Registry consequence: the `learner_upgrade` family stays **CLOSED for rh3**,
now with LightGBM named explicitly alongside XGBoost / HistGB / RandomForest
so the next agent does not spend the cycles. Narrow, legitimate re-open
conditions:

- **A materially different substrate** — raw per-pitch or per-PA sequence
  data rather than 22 pre-aggregated season-to-date rates, where a learner
  could construct features Ridge cannot be handed.
- **A different target** — e.g. a classification target for bust risk, where
  the shipped `sp_floor` model already lives on the pitcher side.
- **A distributional objective** — quantile/pinball loss for the p25/p75
  bands. That is a different question from mean cross-year r and is **not**
  answered by this run.

No production file was touched. `RH3_FEATS`, production sigma, and all `.pkl`
artifacts are unchanged.

---

## Incidental finding (BUG) — `audit_model_ceiling.py` is dead for rh3 and rp3

Reproduced while sourcing the prior-art ceiling verdict:

```
$ python -X utf8 scripts/xfp/audit_model_ceiling.py --model rh3
=== rh3 ceiling audit ===
  substrate rows: 38758 | baseline feats: 22 | candidate feats considered: 50
!!! rh3 audit FAILED: KeyError: ['ros_opp_sp_xwoba_weighted', 'bx_prior_h']
  ceiling.py:95  sub = df.dropna(subset=list(feats) + [target_col])
```

**Cause.** `audit_one()` takes the **live** feature list
(`feats = list(rh3_mod.RH3_FEATS)`, line 250 — correct, and exactly what the
07-28 memo asked for), but `prep_rh3()` (lines 55-127) was never updated to
attach the features promoted since it was written. It builds the Marcel prior,
`lift_h2_aug150`, `xwoba_residual_career`, `career_stage`, and the shrinkage
blocks — and stops. Missing:

| Missing from `prep_rh3()` | Promoted |
|---|---|
| `ros_opp_sp_xwoba_weighted` | before 2026-07-10 |
| `bx_prior_h` | 2026-07-10 |
| `blend_callup_prior()` (AAA call-up prior into `prior_fp_per_pa`) | 2026-07-19 |

The first two crash it. The third would **not** crash — it would silently
leave `prior_fp_per_pa` un-blended, i.e. a quietly different (weaker)
baseline than production, in the tool whose entire job is measuring the
baseline's ceiling.

**Same class of defect for rp3**, verified by column check:
`prep_rp3()` yields 20,400 rows but is missing `ros_opp_xwoba_weighted` of
`RP3_FEATS` (24) → same `KeyError` path. **`prep_rprs2()` is clean**
(28/28 `FEATS_RPRS2` present, 47,014 rows).

**Impact on this study: none.** This study does not use `ceiling.py` or the
driver; it builds its frame via `attach_production_features` and its Ridge arm
was verified equal to `rh3.cross_year_eval` to 4 decimals. The bug is upstream
of a *different* artifact.

**Impact elsewhere: the rh3 ceiling verdict on record is stale and cannot
currently be refreshed.** `data/research/ceiling_audit_2026-05-24.md` is the
newest ceiling artifact — 2 months old, **20** baseline features, and 8,322
substrate rows against today's 38,758. Its `AT_CEILING` rh3 verdict is what
this study was asked to confirm; the confirmation had to come from a
purpose-built script because the standing tool no longer runs. Two of three
production models cannot be ceiling-audited until `prep_*` is repaired.

**Mitigating:** it fails **loudly** (crash on a missing column), not silently,
so unlike the 2026-07-28 `ROOT` bug it cannot have produced a quietly-degraded
number. Nothing needs re-running; nothing recorded is suspect. `grep` shows no
live caller — `refresh_dashboards.py` does not invoke it — so the daily refresh
is unaffected. This is a broken diagnostic, not a broken model.

**Not fixed here** (task scope: validation + memo + new `validate_*.py` only).
Recommended fix, in priority order:

1. Have `prep_rh3()` / `prep_rp3()` call the same assembly production and the
   validation harnesses use rather than maintaining a third parallel copy —
   `attach_production_features` already does the full 22-feature rh3 job
   including `blend_callup_prior`. **Three divergent copies of the same
   assembly is the root cause; deleting one is the durable fix.** A copy of a
   baseline is a baseline that will eventually be wrong (07-28 memo, Bug 2).
2. Delete the `if CSV.exists(): merge else: col = 0.0` fallbacks in
   `prep_rh3()` and raise instead, per fix #2 of the 07-28 memo. This matters
   more than it looks: the two features guarded that way,
   `lift_h2_aug150` and `xwoba_residual_career`, are **#2 and #5 of 22 by
   held-out permutation importance** in the table above. A silent zero there
   is close to the worst available case.
3. Add a smoke test asserting each `prep_*()` yields every column of its
   model's live `FEATS` list. That converts this whole class from
   "discovered by an agent two months later" to a red test on the commit that
   promotes a feature.
