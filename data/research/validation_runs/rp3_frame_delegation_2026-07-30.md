---
signal: rp3_frame_delegation
formula: "rp3.main() feature assembly := plv_clone.models.xfp.frames.build_rp3_frame() (delegation; no formula change to any feature)"
outcome: "byte-identity of the assembled rp3 substrate, the Marcel prior table, the shrinkage population means, the fit fingerprint, the LOO cross-year statistics, and the written projections CSV"
expected_sign: "EXACTLY ZERO — this is a proven no-op refactor. Any non-zero delta is a defect, not a result."
theory: >
  rp3 was the LAST model in the repo still carrying a second, divergent copy of
  its own feature assembly. frames.build_rp3_frame existed as a faithful
  transcription but had ZERO callers (rp3.main() never used it), so the two
  copies were pinned only by the fit fingerprint — which is checked at REFIT
  time, not at edit time. An edit to either copy could therefore sit undetected
  until the next refit. This is the same latent structure that produced the rh3
  harness bug (docs/rh3_harness_root_bug_2026-07-28.md): a drifted copy silently
  weakened the Rule-9 BASELINE for ~20 validation harnesses and cost -0.0368
  cross-year r for nine days while printing confident-looking numbers.
production_target: "rp3 (xfp_rp3_projections.csv / xfp_rp3_pipeline.pkl)"
framing: >
  Rule 8 confirmatory / equivalence. This is NOT a modelling study and makes no
  predictive claim: there is no candidate feature, no gate, and no lift to
  measure. The only claim under test is that the refactor changes NOTHING, and
  the null being defended is exact equality, so no multiple-testing correction
  applies. Rule 13 respected in the strongest possible sense — RP3_FEATS is
  untouched in content AND order, and every rp3 output is byte-identical.
holdout_years: "n/a — equivalence proof, not a predictive evaluation. No train/holdout split was used or is meaningful here."
training_years: "n/a for the claim. For completeness the substrate carries 2018-2026 and the fit stage's TRAIN_YEARS are [2018, 2019, 2021, 2022, 2023, 2024, 2025], unchanged by this work."
data_window: "data/research/xfp_cache/rolling_pitchers_2018_2026.csv as of 2026-07-29 09:10 (31,135 rows x 109 assembled columns, 2018-2026), sp_multiyr_2015_2025.csv, il_split_features_2018_2026.csv, ros_schedule_features_2018_2026.csv. Single snapshot — every comparison below is same-snapshot A vs B."
validation_script: >
  Ad-hoc proof scripts (scratchpad, not committed) + the permanent regression
  tests in tests/test_xfp_frames.py:
  test_rp3_frame_is_byte_identical_to_legacy_inline_assembly,
  test_rp3_feats_unchanged_in_content_and_order,
  test_rp3_main_delegates_to_the_canonical_builder,
  test_rp3_frame_exposes_the_prior_table,
  test_every_rp3_feat_present_in_assembled_frame.
date: 2026-07-30
---

# rp3: retire the last divergent copy of a model's feature assembly

## What changed

`rp3.main()`'s inline prep block (the Marcel prior merge, the MiLB rookie-prior
fallback, the IL join + hard guard, the RoS schedule-strength merge + frozen-cache
guard, both shrinkage passes, and the six within-season drift features) was
deleted and replaced by a single call to `frames.build_rp3_frame()`.

`Rp3Frame` gained one field, `prior`, because `main()` needs the un-merged Marcel
prior table *after* assembly for the IL-vet fallback. Returning it on the frame is
what makes the delegation complete: the alternative — rebuilding
`build_prior_table` inside `main()` — would have left a second copy of exactly
the thing this change removes.

No feature formula, no constant, no threshold, and no FEATS entry was touched.

## Measurement — the byte-identity proof

The constraint was that rp3 is production, so equality had to be **shown**, not
asserted. Reference implementation: a frozen verbatim transcription of the
pre-refactor block (`_legacy_rp3_assembly` in `tests/test_xfp_frames.py`), plus
the pre-refactor module recovered directly from `git show HEAD:...` for the
end-to-end leg.

### 1. The assembled substrate

| Check | Result |
|---|---|
| shape | `(31135, 109)` both |
| column set and ORDER | identical |
| dtypes (all 109) | identical |
| `assert_frame_equal(..., check_exact=True)` | **PASS** |
| Marcel prior table (`Rp3Frame.prior`) | `assert_frame_equal(check_exact=True)` **PASS** |
| `pop_means_to` / `pop_means_last21` | equal to the bit (`abs=0, rel=0`) |

### 2. The fit fingerprint

```
legacy assembly    46e24bc9b4187492b95a84fbc3bb57dd
build_rp3_frame    46e24bc9b4187492b95a84fbc3bb57dd
shipped .pkl       46e24bc9b4187492b95a84fbc3bb57dd
```

The shipped bundle's fingerprint is the exact train-year substrate production
last fitted on, so this pins the new frame to the ARTIFACT, independent of any
reference implementation kept in the test file.

### 3. `cross_year_eval` reproduces the shipped bundle from BOTH assemblies

| Statistic | Bundle (recorded) | Legacy assembly | Delegating assembly |
|---|---|---|---|
| `cross_year_r` | 0.5617 | **0.5617** | **0.5617** |
| `cross_year_mae` | 2.8394 | **2.8394** | **2.8394** |
| `baseline_rp2_r` | 0.5484 | **0.5484** | **0.5484** |
| `delta_r_vs_rp2` | +0.0133 | **+0.0133** | **+0.0133** |
| n | 19,111 | 19,111 | 19,111 |

Per-year r dictionaries were compared as whole objects and are equal. The Rule-9
promotion gate for `ros_opp_xwoba_weighted` therefore still fires on exactly the
same number it fired on before (+0.0133, gate +0.005).

### 4. End-to-end A/B of `main()` itself

Pre-refactor `rp3.py` (from `git show HEAD`) and the delegating `rp3.py` were run
in the **same process on the same day** against the same caches, with
`MODEL_PKL`/`PROJ_CSV` redirected to a temp directory so the working tree was
never written. Same-day/same-process matters: `apply_schedule_strength` reads the
live `pitcher_schedule_2026.csv` probables cache, so a naive comparison against
the shipped CSV shows ~41 rows of `schedule_factor` drift that has nothing to do
with this change.

* projections CSV: **raw byte-equal** (357 pitchers x 35 columns)
* bundle: `fit_fingerprint`, `cross_year_r`, `cross_year_mae`, `baseline_rp2_r`,
  `delta_r_vs_rp2`, `overall_sigma` (3.6208006514971247), `n_train` (19111),
  `features`, `training_years`, `replacement_sp_rank`, `pop_means_to`,
  `pop_means_last21` — all equal.

`RP3_FEATS` compared element-by-element against the pre-refactor list: identical
in content **and order**, 24 entries.

## Mutation check — do the new guards actually bite?

A test that passes both before and after is worthless. Seven divergences were
injected in-process (no file edits) and the guards re-run:

| Mutation | Caught? |
|---|---|
| single cell of `delta_velo` perturbed by 1e-12 | yes |
| dtype-only change (`il_stints_to` int64 -> float64), values equal | yes |
| silent-zero: `ros_opp_xwoba_weighted` constant-filled to 0.0 | yes (frame **and** fingerprint) |
| a feature dropped from the frame (`bb_pct_to_sh`) | yes, named in the error |
| `RP3_FEATS` order permuted | yes — **by the new FEATS-order test only** |
| Marcel prior table perturbed by 1e-9 | yes |
| `pop_means_to` perturbed by 1e-15 | yes |

The two structural tests were also replayed against `HEAD`'s `rp3.py`/`frames.py`
via AST and fail there on every assertion (`build_rp3_frame` not called;
`build_prior_table`/`compute_population_means`/`apply_shrinkage` re-implemented;
all four substrate CSVs re-read; `Rp3Frame` has no `prior` field).

## Incidental finding (NOT fixed here — outside this change's file set)

`engine.fit_fingerprint` hashes `sorted(feats)`, so it is **order-insensitive**.
A reordering of `RP3_FEATS` therefore does *not* move the fingerprint, the
warm-fit path loads the cached bundle instead of refitting, and
`pipe.predict(valid[RP3_FEATS].values)` — which passes a bare positional ndarray
— silently maps every Ridge coefficient to the wrong column.

Measured cost of swapping merely the FIRST TWO of the 24 features, on the 271
current-season pitchers actually projected:

* mean |delta| **2.587 FP/start** (max 5.946) on a mean projection of 9.801
* Spearman correct-vs-permuted 0.9567; mean absolute rank shift **17.6 places**
* fingerprint: **unchanged**

This is latent, not active — `RP3_FEATS` matches the shipped bundle's `features`
today (verified). `engine.py` is outside this change's file set and was not
touched. `test_rp3_feats_unchanged_in_content_and_order` is now the guard that
catches it; making the fingerprint order-sensitive would be the real fix and
belongs to whoever owns `engine.py`.

## Not done

* `engine.fit_fingerprint` order-sensitivity (above) — reported, not fixed.
* No rh3-side work; `rh3.py` was already delegating and was not touched.
* No refit was performed. The shipped `xfp_rp3_pipeline.pkl` and
  `xfp_rp3_projections.csv` are unchanged on disk — deliberately, since the
  proof is that a refit would reproduce them byte-for-byte.

verdict: PASS — delegation proven byte-identical at every level (substrate, prior table, population means, fit fingerprint, LOO cross-year statistics r=0.5617/mae=2.8394/delta=+0.0133, and the raw bytes of the projections CSV). Zero behaviour change, which is the required outcome. The last divergent copy of an xFP feature assembly is retired, and the divergence can no longer be re-introduced silently: test_rp3_main_delegates_to_the_canonical_builder fails structurally if the copy comes back.
