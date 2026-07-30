---
signal: ceiling_audit_refresh
formula: >
  Not a candidate feature. This is a REPAIR + RE-MEASUREMENT of the ceiling
  audit tool itself, plus the consolidation of three divergent copies of the
  rh3 feature assembly into one shared module.
  Repair: scripts/xfp/audit_model_ceiling.py::prep_rh3 / prep_rp3 replaced by
  plv_clone.models.xfp.frames.build_rh3_frame / build_rp3_frame — the SAME
  assembly rh3.main() runs. Every `if CSV.exists(): merge else: col = 0.0`
  silent-zero fallback replaced by a raise (frames.require_cache /
  require_columns), and the frame now self-asserts that every name in
  RH3_FEATS / RP3_FEATS is a real column (frames.assert_feats_present).
  Re-measurement: the three ceilings for rh3 and rp3, unchanged in method,
  on today's substrate:
    1. nonlinear_ceiling — Ridge(RidgeCV alphas=logspace(-1,5,80), cv=5) vs
       XGB(300 trees, depth 3, lr 0.05) vs RF(300, depth 5, leaf 5), same
       FEATS/target/leave-one-year-out folds; verdict on max(positive gap):
       <0.003 AT_CEILING, 0.003-0.010 MILD, >0.010 SIGNIFICANT.
    2. linear_ceiling — fixed-alpha Ridge sweep over logspace(-1,5,13);
       r_std over the "reasonable zone" (within 0.05 of peak r);
       <0.005 STABLE.
    3. feature_ceiling — LassoCV(alphas=logspace(-4,1,50), cv=5) over
       baseline+candidates, refit per held year; candidates = numeric
       substrate cols not in baseline, non-circular, <=40% NaN in training,
       capped at the first 50 by name.
  No model, no FEATS list, no threshold was changed.
outcome: >
  ros_full_fp_per_pa (rh3.TARGET) and ros_fp_per_start (rp3.TARGET) —
  cross-year Pearson r of concatenated held-year predictions.
expected_sign: "+"
theory: >
  Two claims under test. (a) MECHANICAL: if the ceiling audit is fed the real
  production substrate rather than a rotted copy of it, its baseline Ridge r
  must equal production's own recorded cross_year_r — that equality is the
  only thing that makes a "ceiling" number mean what its name says.
  (b) SUBSTANTIVE: the 2026-05-24 audit found AT_CEILING for rh3/rp3 at 20-23
  features and 8.3k/4.2k rows. Today's substrate is 22/24 features and
  38.8k/20.4k rows, with two promoted features (ros_opp_sp_xwoba_weighted,
  bx_prior_h) rh3 did not have then. An independent LightGBM cell run today
  (rh3_nonlinear_headroom_lgbm_2026-07-29, REJECTED at -0.0234 vs Ridge)
  predicts AT_CEILING still holds; a tree model beating Ridge would falsify it.
production_target: rh3, rp3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/audit_model_ceiling.py
date: 2026-07-29
verdict: CONFIRMED_AT_CEILING (nonlinear, both models); tool repaired
---

# Ceiling-audit refresh + one canonical rh3 feature assembly — 2026-07-29

Report of record: [`data/research/ceiling_audit_2026-07-29.md`](../ceiling_audit_2026-07-29.md)
(supersedes the 2026-05-24 edition). Raw stdout with per-phase timings is
reproduced below.

---

## 1. Why the tool had to be repaired first

`audit_model_ceiling.py` was **dead for rh3 and rp3** — not degraded, dead:

```
$ python -X utf8 scripts/xfp/audit_model_ceiling.py --model rh3
  substrate rows: 38758 | baseline feats: 22 | candidate feats considered: 50
KeyError: ['ros_opp_sp_xwoba_weighted', 'bx_prior_h']        (ceiling.py:95)

$ python -X utf8 scripts/xfp/audit_model_ceiling.py --model rp3
KeyError: ['ros_opp_xwoba_weighted']
```

`audit_one()` read the **live** `RH3_FEATS` (22 names) from production, but
`prep_rh3()` carried its own transcription of `rh3.main()`'s assembly that had
never learned about `ros_opp_sp_xwoba_weighted` (promoted 2026-05-24),
`bx_prior_h` (2026-07-10), or `blend_callup_prior` (2026-07-19). It also still
used the `if CSV.exists(): merge ... else: col = 0.0` **silent-zero** pattern on
`lift_h2_aug150` and `xwoba_residual_career` — which the LightGBM importance
study ranked **#2 and #5 of 22** by held-out permutation importance. That is the
exact shape of the 2026-07-28 ROOT bug (`docs/rh3_harness_root_bug_2026-07-28.md`,
−0.0368 cross-year r behind confident-looking output).

**Mitigating, and worth stating plainly:** it failed *loudly*. Unlike the 07-28
bug it cannot have produced a quietly-degraded recorded number, and
`refresh_dashboards.py` never invokes it. The last recorded ceiling numbers
(2026-05-24) pre-date the rot.

### The durable fix

One assembly, `src/plv_clone/models/xfp/frames.py`, imported by all three
former copies:

| former copy | now |
|---|---|
| `rh3.main()` (production) | delegates to `build_rh3_frame()` |
| `validate_inseason_discipline.attach_production_features` | delegates (signature kept for its 3 sibling callers) |
| `audit_model_ceiling.prep_rh3` / `prep_rp3` | delegates; only the eval ROW filter stays local |

`rp3.py` was **not** refactored (outside this change's file set), so it still
holds a second copy of its own prep — see §5.

### Byte-identity proof (production must not move)

| check | result |
|---|---|
| `assert_frame_equal(build_rh3_frame(), frozen verbatim copy of the old inline block)`, `check_exact=True` | **PASS** — 91,628 rows × 122 cols, identical shape / column order / dtypes / values |
| shrinkage `pop_means_to`, `pop_means_last21` | identical, exact |
| `rh3._fit_fingerprint(frame, RH3_FEATS)` vs shipped `xfp_rh3_pipeline.pkl` | `e0a8c460764c27e639aa0909103eae3c` == `e0a8c460764c27e639aa0909103eae3c` |
| `rp3._fit_fingerprint(frame, RP3_FEATS)` vs shipped `xfp_rp3_pipeline.pkl` | `46e24bc9b4187492b95a84fbc3bb57dd` == `46e24bc9b4187492b95a84fbc3bb57dd` |
| **golden A/B**: `rh3.main()` refactored vs `rh3.main()` at `e107f36`, full run | `data/outputs/xfp_rh3_projections.csv` md5 `c07d6ad1240e9e0c6c2faeaf4edeb713` **both ways** |
| `validate_inseason_discipline` substrate, all 32 columns it reads | identical, exact, 91,628 rows |

The fingerprint match is the load-bearing one: it is an md5 over the train-year
slice of FEATS+target+year+split_day, so it pins the frame to the artifact
production last fitted on — independent of any reference copy kept in a test.

---

## 2. Measurement — the three ceilings, today

| model | rows | feats | ridge_r | xgb_gap | rf_gap | alpha r_std | feat Δr | NONLINEAR | LINEAR | FEATURE |
|---|---|---|---|---|---|---|---|---|---|---|
| rh3 | 38,758 | 22 | **+0.6419** | −0.0084 | −0.0817 | 0.0056 | +0.0038 | **AT_CEILING** | ALPHA_SENSITIVE | **BASELINE_OPTIMAL** |
| rp3 | 20,400 | 24 | **+0.5617** | −0.0210 | −0.0310 | 0.0027 | +0.0196 | **AT_CEILING** | **STABLE** | REPLACE_BASELINE |

### The mechanical claim, verified

| model | audit baseline ridge_r | shipped bundle `cross_year_r` |
|---|---|---|
| rh3 | +0.6419 | **0.6419** |
| rp3 | +0.5617 | **0.5617** |

The audit's baseline now **is** production's baseline, to 4 decimal places, for
both models. This equality was structurally unavailable before (the tool
crashed), and it is the property that makes every Δr in this report comparable
to the +0.005 promotion gate.

### Movement vs the 2026-05-24 edition

| | rh3 2026-05-24 | rh3 today | rp3 2026-05-24 | rp3 today |
|---|---|---|---|---|
| rows | 8,322 | 38,758 | 4,240 | 20,400 |
| feats | 20 | 22 | 23 | 24 |
| ridge_r | +0.6167 | **+0.6419** | +0.5509 | **+0.5617** |
| xgb_gap | +0.0000 | −0.0084 | −0.0162 | −0.0210 |
| alpha r_std | 0.0083 | 0.0056 | 0.0093 | **0.0027** |
| FEATURE verdict | REPLACE_BASELINE | **BASELINE_OPTIMAL** | REPLACE_BASELINE | REPLACE_BASELINE |

rh3's +0.0252 r is not a finding of this run — it is the two promoted features
plus 4.7× the rows, already banked in the bundle.

---

## 3. Verdicts

**NONLINEAR — AT_CEILING holds for both. Confirmed, and now on 4.7×/4.8× the
rows.** Every tree gap is *negative*: XGB −0.0084 (rh3) / −0.0210 (rp3), RF
−0.0817 / −0.0310. Nothing recovers Ridge's signal, let alone beats it. This
agrees in sign and rough magnitude with today's independent LightGBM cell
(−0.0234 on the mean-of-per-year-r convention, REJECTED). **Do not spend more
effort on learner swaps for rh3 or rp3.** Three independent runs now say the
same thing (05-24 XGB/RF, 07-10 HistGB, 07-29 LGBM + this).

**LINEAR — rp3 improved to STABLE (r_std 0.0093 → 0.0027). rh3 remains
ALPHA_SENSITIVE at r_std 0.0056, marginally over the 0.005 bar** (was 0.0083).
Note the threshold was NOT loosened to make this pass; rh3 fails it and is
reported as failing. Peak r sits at α≈3162 for both models, an order of
magnitude above rh3's May peak (α≈316) — consistent with heavier shrinkage
being right on a 4.7×-larger panel. `r_at_chosen` exceeds `ridge_r` by +0.0002
(rh3) / +0.0006 (rp3), i.e. production's per-fold RidgeCV is within 0.0006 of
the best fixed alpha in hindsight. Practically: rh3's alpha choice is worth a
look, but the entire prize is ≤ +0.0002.

**FEATURE — rh3 flipped to BASELINE_OPTIMAL. This is the real news.** In May,
Lasso over baseline+50 candidates beat the baseline by +0.0056 and kept 7 new
columns → REPLACE_BASELINE. Today Δr = **+0.0038, below the +0.005 gate**, with
exactly **one** candidate kept (`hr_to`, a raw home-run count that is a
volume/skill proxy for `hr_per_pa_to_sh` × `pa_to`, both already in FEATS). The
two promotions since May closed the gap the May audit was pointing at. rh3's
22-feature baseline is now the best linear read of its own substrate.

13 of 22 rh3 baseline features get zeroed by Lasso, which is *not* evidence they
are useless: RidgeCV keeps correlated features and distributes weight, Lasso
picks one of each correlated group. The Ridge baseline (+0.6419) still beats
Lasso's 10-feature survivor set on held-out years; that is the number that
decides.

**rp3 FEATURE — REPLACE_BASELINE at Δr +0.0196, but treat it as a LEAD, not a
result.** 21 candidates survive, and the list is dominated by raw `_last21`
counts (`bb_pct_last21`, `in_zone_last21`, `o_swing_last21`, `swing_last21`,
`barrel_n_last21`, `gb_n_last21`, `gs_last21`, …) plus raw cumulative counts
(`bb_to`, `hr_to`, `in_zone_to`, `out_zone_to`). Three reasons the +0.0196 is
optimistically biased and must not be promoted from here:

1. **Selection and evaluation share the folds.** LassoCV picks its own α per
   held year over the same leave-one-year-out structure the r is read from.
   Candidate *set* selection (the 50-column cap, the ≤40% NaN screen) was done
   once on the whole panel. This is a screening statistic, not a Rule-9 lift.
2. **`gs_last21` and the raw counts encode volume**, and rp3's target is a
   per-start rate whose denominator is correlated with starts made. Volume
   leakage into a rate target is exactly the trap `/validate-feature` exists to
   catch.
3. **It contradicts a closed family.** Gotcha #11 / the `inseason_delta_grid`
   entry closed in-season *deltas*; these are in-season *levels*, which is a
   different family — so it is a legitimate re-open — but the six `delta_*`
   features Lasso zeroed here are already documented as sub-gate
   (+0.0015 in 2026-05-23), and this result partly restates that.

**Action: pre-register the rp3 last21-levels family through `/validate-feature`
against the full 24-feature baseline before anything moves.** No FEATS change is
made by this run.

---

## 4. Raw run output (verbatim)

```
=== rh3 ceiling audit ===
  substrate rows: 38758 | baseline feats: 22 | candidate feats considered: 50
  [nonlinear] done in 268s
  [linear] done in 2s
  [feature] done in 81s
  nonlinear: ridge=+0.6419  xgb=+0.6336  rf=+0.5603  xgb_gap=-0.0084  rf_gap=-0.0817  AT_CEILING
  linear:    alpha=3162.2777  r_at_chosen=+0.6421  r_std=0.0056  ALPHA_SENSITIVE
  feature:   baseline=+0.6419  extended=+0.6457  delta=+0.0038  BASELINE_OPTIMAL
             survived: 10/72 feats  baseline zeroed: 13  new feats kept: 1
             kept: hr_to

=== rp3 ceiling audit ===
  substrate rows: 20400 | baseline feats: 24 | candidate feats considered: 50
  [nonlinear] done in 134s
  [linear] done in 1s
  [feature] done in 116s
  nonlinear: ridge=+0.5617  xgb=+0.5407  rf=+0.5307  xgb_gap=-0.0210  rf_gap=-0.0310  AT_CEILING
  linear:    alpha=3162.2777  r_at_chosen=+0.5623  r_std=0.0027  STABLE
  feature:   baseline=+0.5617  extended=+0.5813  delta=+0.0196  REPLACE_BASELINE
             survived: 36/74 feats  baseline zeroed: 9  new feats kept: 21
```

Wall clock ≈ 10 min for both models (contended CPU). `rprs2` was **not** re-run
in this pass — its prep was already clean (28/28 feats, 47,014 rows) and no
repair was needed there; its 2026-05-24 verdicts (AT_CEILING / ALPHA_SENSITIVE /
BASELINE_OPTIMAL) stand un-refreshed and are labelled as such.

---

## 5. Honest limits

1. **rp3 still holds a second copy of its assembly.** `rp3.py` was outside this
   change's file set, so `build_rp3_frame` is a faithful transcription of
   `rp3.main()`'s prep rather than an extraction from it. It is pinned
   empirically — the fit fingerprint matches the shipped bundle — but the two
   can still drift if someone edits `rp3.main()` and not `frames.py`. The
   fingerprint test will catch that drift *the next time rp3 is refit*, not at
   the moment of editing. Unifying it is a one-function change to `rp3.main()`
   plus the same byte-identity proof done here for rh3.
2. **The candidate cap moved.** The audit takes "the first 50 candidates by
   name" — and the repaired substrate has more numeric columns than the rotted
   one, so *which* 50 differ from May. The candidate set is a screening
   convenience, not a pre-registered hypothesis space; the FEATURE verdicts
   should be read as "nothing in a broad 50-column sweep clears the gate for
   rh3", not as an exhaustive search.
3. **rh3's ALPHA_SENSITIVE verdict is on a 13-point grid**, coarse by design.
   The +0.0002 headroom it implies is inside the noise of everything else in
   this report.
4. **Nothing here re-validates any shipped feature.** The Δr numbers are
   screening statistics from a tool, not `/validate-feature` runs.

---

## Related

- `docs/rh3_harness_root_bug_2026-07-28.md` — the silent-zero failure mode this
  change eliminates by construction
- `data/research/validation_runs/rh3_nonlinear_headroom_lgbm_2026-07-29.md` —
  independent nonlinear-headroom cell (REJECTED, −0.0234); §"Incidental finding"
  is the bug report this run closes
- `data/research/ceiling_audit_2026-05-24.md` — superseded edition
- `tests/test_xfp_frames.py` — byte-identity, fingerprint, and
  every-FEAT-present guards (15 tests)
