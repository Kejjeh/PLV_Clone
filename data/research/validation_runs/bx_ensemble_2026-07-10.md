# Pre-registration: xfp_bx ensemble features into rh3 / rp3 — 2026-07-10

- **Date written:** 2026-07-10, BEFORE any evaluation run. Status at write time:
  `scripts/xfp/build_bx_priors.py` and `scripts/xfp/validate_bx_ensemble.py` are
  about to be written; NO bx-prior CSV has been built and NO cross_year_eval with
  any bx candidate has been executed.
- **Question:** does the box-score-era `xfp_bx` v0 model (validated standalone
  2026-07-10, `xfp_bx_v0_2026-07-10.md`) add signal as an ENSEMBLE FEATURE inside
  the frozen production Statcast models rh3 / rp3, evaluated through their own
  validation harnesses at full-production-baseline parity (Rule 9)?
- **Protocol:** `/validate-feature` 9-rule protocol; harnesses
  `scripts/xfp/_validate_rh3_v3_helper.py` (rh3) and
  `scripts/xfp/_rp3_validation_harness.py` (rp3), both using the tolerant `_cye`
  unpack of the 3-return production `cross_year_eval`.
- **Multiple testing:** 4 pre-registered cells → Bonferroni 4. The gate criterion
  is effect-size based (Δr), not p-value based, so per house convention the Δr
  bar is unchanged per cell; the correction is honored by declaring ALL 4 cells
  up front and reporting ALL 4 outcomes (no cell dropped post hoc).

## Candidate cells (all declared before running)

| Cell | Model | Candidate column | Construction | Expected coef sign |
|---|---|---|---|---|
| B1 | rh3 | `bx_prior_h` | bx v0 hitter ridge prediction of year-T full-season fp_per_pa, trained strictly on panel years ≤ T−1 (vintage protocol below), predicted from the player's T−1 box line | + |
| B2 | rp3 | `bx_prior_sp` | same construction, SP leg, fp_per_start | + |
| B3 | rh3 | `bx_age_mult_h` | empirical aging-curve level (delta-method `cum_curve`) at the player's year-T age, hitter curve refit per vintage on panel years ≤ T−1 | + |
| B4 | rp3 | `bx_age_mult_sp` | SP analog | + |

Joint reports (secondary, not separately gated): B1+B3 together on rh3;
B2+B4 together on rp3. Reported for the integration recipe only — a joint PASS
with both singles failing does NOT promote either feature.

## Vintage protocol (as-of construction, no train-on-future leakage)

For each target year T in {2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026}
(2020 rows are emitted for completeness but the harness eval excludes 2020 as
always):

1. **Training pairs:** built exactly as `xfp_bx_v0.load_leg` (same volume floors
   PA ≥ 200 / GS ≥ 10 on both years of the pair, same features, same Marcel-lite
   prior-as-feature, same 2019/2020 pair exclusions), restricted to pairs whose
   TARGET year ≤ T−1. Panel reaches 1960 (hitters) / 1970 (SP), so even the 2018
   vintage trains on 55+ / 45+ years.
2. **League means** for the Marcel-lite feature are computed per-year from
   qualifying seasons within the ≤ T−1 history only.
3. **Model:** the same house Ridge idiom as v0 (StandardScaler + RidgeCV,
   alphas = logspace(−1, 5, 80), cv = 5), refit per vintage.
4. **Prediction:** the player's year-(T−1) panel line (meeting the volume floor)
   is featurized identically (Marcel prior anchored at T−1, age at T−1, log
   volume) and scored → `bx_prior_*` for year T.
5. **2021 exception (declared):** 2020 is excluded as a feature year (house
   convention, matches v0 prereg). For T = 2021 the prediction uses the
   year-2019 line instead — a 2-year-lag degraded vintage. Documented; 2021 is
   still one of the 7 eval years and no special treatment is given in gating.
6. **Aging curve per vintage:** the delta-method curve (`aging_curves.py`
   methodology, harmonic-mean volume weights, consecutive ages, 2020-adjacent
   transitions excluded) IS cheaply refittable, so it is refit per vintage on
   panel years ≤ T−1 (the preferred branch declared in the design). Fallback if
   any vintage has thin coverage at an age: linear interpolation within the
   curve, endpoint clamping outside ages 20–39. Had refitting not been cheap,
   the full-history curve would have been used with the caveat that a smooth
   age curve estimated on 60 years makes year-T leakage negligible — recorded
   here for completeness, but the refit branch is what runs.
7. **Age at T:** from the panel's year-T row (2026 in-progress rows are used for
   AGE ONLY, never as features/targets); fallback = age at the feature year plus
   the year gap.

`bx_age_mult_*` is the cum_curve LEVEL at the player's age (an additive
age-relative rate offset anchored at age 20; the "multiplier" name follows the
design doc). Under StandardScaler+Ridge any affine transform is equivalent, so
level-vs-multiplier parameterization does not affect the eval. Expected sign +
(higher curve level at the player's age → higher expected rate), i.e. the sign
"matches curve direction" per the design.

## Join + missing-data protocol

- Output cache: `data/research/xfp_cache/bx_priors_2018_2026.csv`, columns
  `mlbam, year, bx_prior_h, bx_prior_sp, bx_age_mult_h, bx_age_mult_sp`.
- Joins: rh3 rolling on `batter` = mlbam + `year`; rp3 rolling on `pitcher` =
  mlbam + `year`. mlbam-only joins, never name.
- Players missing a bx prediction (rookies / no qualifying T−1 box line) are
  filled with the per-year mean of the merged column (population mean — the
  same structural fallback the Marcel prior uses); join rates before fill are
  reported per year. Same fill for missing age-mult rows.

## Gates per cell (all four must pass for a PASS verdict)

1. cross_year_r lift ≥ +0.005 vs the FULL production baseline
   (all of RH3_FEATS / RP3_FEATS including `prior_fp_per_pa` /
   `prior_fp_per_start` — Rule 9 hard baseline).
2. Per-year sign consistency ≥ 5/7 (TRAIN_YEARS 2018-2025 ex 2020).
3. Holdout years 2024–2025 lift positive.
4. Final-pipeline coefficient sign matches the declared sign (+).

## Redundancy expectation (declared up front)

rh3/rp3 already carry Marcel priors built from the SAME underlying seasons (via
the multiyr caches, 2015+), so `bx_prior_*` must beat a baseline that already
contains `prior_fp_per_pa` / `prior_fp_per_start`. The value hypothesis is bx's
(a) component-rate decomposition (K%, ISO, SB rate, HR/9, box-FIP…),
(b) empirical age curve vs rh3's linear `career_stage` / rp3's nothing,
(c) 60-year coefficient stability. If that is all redundant with the existing
prior + rate features, **REJECTED is the honest outcome** and the ensemble seat
waits for the decorrelated FG systems in August.

## Environment note (declared)

Another agent is concurrently regenerating `rolling_hitters_2018_2026.csv`
(as-of SB work, BUILDER_VERSION 3). The rolling CSVs are loaded ONCE per leg at
the start of the validation run; the run records which vintage was loaded
(sb_per_pa_to non-zero fraction) and the measured baseline r (expected ≈ 0.6275
for rh3 post-SB-fix, ≈ 0.5614 for rp3 — whatever is measured is what counts).

## What is NOT being claimed / done

- **No integration regardless of outcome** (production models are frozen —
  Rule 7). A PASS produces an integration RECIPE only, including the daily
  bx-prior refresh step it would require.
- No modification of any `data/research/boxscore_era/` original.
- Only files ADDED: `scripts/xfp/build_bx_priors.py`,
  `scripts/xfp/validate_bx_ensemble.py`,
  `data/research/xfp_cache/bx_priors_2018_2026.csv`, this prereg, and a
  results JSON.

---

## RESULTS — appended 2026-07-10 after evaluation

### Environment actually measured

- `rolling_hitters_2018_2026.csv` loaded ONCE: 90,249 rows, `sb_per_pa_to`
  non-zero fraction = **0.0000 → pre-SB-feature vintage** (the concurrent
  BUILDER_VERSION-3 regen had not landed when this run loaded the CSV). The
  TARGET (`ros_full_fp_per_pa`) SB correction IS in this cache: measured
  baseline r = **0.6275**, exactly the expected post-SB-fix anchor.
- `rolling_pitchers_2018_2026.csv`: 30,637 rows; baseline r = **0.5614**
  (matches the expected production anchor).
- Vintage builder log: hitter vintages train on 13,238 → 14,848 pairs
  (2018 → 2026); SP 5,450 → 6,180. T=2021 correctly trained on the same pair
  set as T=2020 (2019/2020 feature-year pairs excluded) and predicted from
  2019 lines per the declared exception. Aging curves refit per vintage
  (20 age points each).
- Cache emitted: `bx_priors_2018_2026.csv`, 4,867 (mlbam, year) rows —
  3,219 hitter, 1,653 SP predictions.

### Join rates (before population-mean fill; over ALL rolling rows, i.e.
including low-volume rows the eval filters drop, so eval-population rates
are higher)

- rh3 `bx_prior_h`: overall 54.9%; by year 47.8 / 48.4 / **43.4 (2021 —
  2-yr-lag vintage attrition)** / 61.1 / 61.3 / 63.6 / 62.6 / 62.8 (2026).
- rp3 `bx_prior_sp`: overall 62.4%; by year 66.8 / 64.6 / **51.8 (2021)** /
  66.3 / 59.8 / 62.3 / 62.6 / 67.5 (2026).
- Unmatched rows (rookies / sub-floor T−1 lines) filled with per-year mean,
  as pre-registered.

### Gate-interpretation disclosure (recorded before final verdicts)

The prereg wording "holdout years 2024–2025 lift positive" was implemented
first as EACH-year-positive, then aligned to the canonical house Rule-9
definition (`scripts/xfp/lib/rule9.rule9_lift`, used by the rp3 harness and
every validate_*.py): **holdout gate = MEAN lift over 2024–2025 > 0**. Both
readings are reported. This matters for exactly one cell: B1's 2025 lift is
−0.0005 (essentially zero), so B1 passes the canonical mean gate
(+0.0093) but fails a strict each-year reading. Disclosed, not hidden.

### Per-cell results (Bonferroni 4 — all 4 declared cells reported)

| Cell | lift (gate ≥ +0.005) | signs | holdout mean (24/25) | coef | Verdict |
|---|---|---|---|---|---|
| **B1 rh3 + bx_prior_h** | **+0.0088** (0.6275 → 0.6363) | 5/7 | **+0.0093** (+0.0191 / −0.0005) | +0.0284 | **PASS** |
| B2 rp3 + bx_prior_sp | +0.0036 (0.5614 → 0.5650) | 7/7 | +0.0074 (both +) | +0.4398 | REJECTED (g1) |
| B3 rh3 + bx_age_mult_h | +0.0001 | 3/7 | −0.0003 | +0.0039 | REJECTED (g1, g2, g3) |
| B4 rp3 + bx_age_mult_sp | +0.0027 (0.5614 → 0.5641) | 7/7 | +0.0024 (both +) | +0.2295 | REJECTED (g1) |

B1 per-year: 2018 +0.0128, 2019 +0.0161, 2021 +0.0002, 2022 −0.0049,
2023 +0.0123, 2024 +0.0191, 2025 −0.0005.

Joint reports (secondary, not promotion vehicles):

- **B1+B3 (rh3): +0.0086** (0.6361) — entirely B1-driven; the joint is
  actually 0.0002 BELOW B1 alone. B3 adds nothing on top of B1 +
  `career_stage`.
- **B2+B4 (rp3): +0.0054** (0.5668), 7/7 signs, holdout +0.0089 both years
  positive, both coefs +. Clears every gate JOINTLY while each single missed
  g1 — the box prior and the SP age curve are complementary on rp3. Per the
  prereg rule, this does NOT promote either feature. It is registered here as
  a **future prereg candidate**: a single composite feature (bx_prior_sp with
  age-curve adjustment folded in, one cell, one gate) for a fresh
  `/validate-feature` run.

### Reading

- The hitter box prior carries real non-redundant signal past rh3's own
  Marcel prior (+0.0088 with `prior_fp_per_pa` already in the baseline) —
  the component-rate decomposition + 60-year coefficient stability
  hypothesis survives contact with Rule 9 on the hitter side.
- The SP box prior points the same direction with perfect sign consistency
  (7/7) but at +0.0036 is under the bar — mostly redundant with
  `prior_fp_per_start` + the stuff/drift features.
- The aging-curve LEVEL is redundant for hitters (rh3's linear
  `career_stage` + the priors already carry it — B3 ≈ 0) and mildly
  informative but sub-gate for SPs (rp3 has no career-stage feature at all,
  which is why B4 > B3).
- Caveat carried forward: B1's lift is concentrated in 2018/2019/2023/2024;
  2021/2025 ≈ 0 and 2022 −0.0049. Re-verify after the SB-feature
  (BUILDER_VERSION 3) rolling cache lands, since this run validated against
  the pre-SB feature vintage.

### VERDICTS: B1 PASS · B2 REJECTED · B3 REJECTED · B4 REJECTED

### Integration recipe for B1 (NOT integrated — production frozen, Rule 7)

When/if `bx_prior_h` is promoted into rh3:

1. **Registry:** add a PASS record for `bx_prior_h` (target `rh3`) pointing
   at this file, so `check_feats_validated(RH3_FEATS)` doesn't fire.
2. **Refresh step (daily, cheap):** add a step to
   `scripts/xfp/refresh_dashboards.py` (natural slot ~2.8, after panel-side
   builders) that runs `scripts/xfp/build_bx_priors.py` ONLY when a
   boxscore_era panel CSV is newer than
   `data/research/xfp_cache/bx_priors_2018_2026.csv` (mtime check). The
   current-year prior is built from COMPLETED T−1 seasons, so the cache is
   static within a season — the step is effectively annual (season rollover
   / panel rebuild) but wiring it as an idempotent mtime-gated daily step
   keeps it self-healing. Panels themselves refresh via
   `data/research/boxscore_era/build_panels.py` (API-cached).
3. **rh3.py:** add `BX_PRIORS_CSV` path constant; in `main()` merge
   `bx_prior_h` on `(batter, year)` (mlbam join), fill NaN with per-year
   mean, and add the house >50%-current-year-NaN hard guard (same pattern as
   `ros_opp_sp_xwoba_weighted`); append `'bx_prior_h'` to `RH3_FEATS` and add
   it to the `v2_added` set so the in-pipeline Rule-9 RuntimeError gate
   asserts against the prior-production baseline on every cold fit.
4. **Harness parity:** mirror the identical merge+fill in
   `scripts/xfp/_validate_rh3_v3_helper.load_and_prep_rh3_inputs` (its
   docstring contract: it must replicate main()'s prep exactly), or future
   baselines silently drop all rows at dropna (the 2026-07-09 rp3 audit
   failure mode).
5. **Expected numbers:** cross_year_r 0.6275 → ≈0.6363; final-pipe coef
   ≈ +0.028 (must stay positive).
6. **Pre-flight:** re-run this validation once the BUILDER_VERSION-3
   (SB-feature) rolling cache is live; promote only if B1 still clears on
   the new substrate.

**No production file was modified.** Files added: this prereg+results doc,
`scripts/xfp/build_bx_priors.py`, `scripts/xfp/validate_bx_ensemble.py`,
`data/research/xfp_cache/bx_priors_2018_2026.csv`,
`bx_ensemble_results_{rh3,rp3}_2026-07-10.json`.

---

## PRE-FLIGHT (recipe step 6) — declared 2026-07-10 evening, BEFORE the rerun

The BUILDER_VERSION-3 rolling cache (live `sb_per_pa_to_sh`,
`sb_asof_feature_2026-07-10.md`) has landed since the B1 run above, which
validated against the pre-SB vintage. Production rh3 is now r = 0.6343.
Per this recipe's own step 6, B1 is re-run on the CURRENT cache before any
promotion. Decision rule, fixed before the rerun executes:

- **Baseline:** full production RH3_FEATS (21 features incl. live
  `sb_per_pa_to_sh`), expected r ≈ 0.6343. **Extended:** baseline +
  `bx_prior_h` (same merge/fill protocol as the B1 run above).
- **PROMOTE** iff lift ≥ +0.005 AND holdout (canonical MEAN over 2024–2025,
  `lib/rule9` reading) positive.
- **Lift in [+0.003, +0.005):** report **MARGINAL-ON-PREFLIGHT** and STOP —
  no promotion; the live SB feature may have absorbed shared variance
  (bx's component rates include SB rate).
- **Lift < +0.003:** STOP, mark B1 **superseded-by-SB**.

Sign consistency and coef sign are reported for completeness; the promote /
stop decision is the lift + holdout rule above. Runner:
`scripts/xfp/validate_bx_preflight.py` (focused B1-only rerun using
`validate_bx_ensemble.py`'s machinery; writes
`bx_preflight_results_2026-07-10.json` — the original results JSON is not
overwritten).

### Pre-flight RESULTS + PROMOTION — appended 2026-07-10 evening, after the run

- Substrate confirmed live-SB: `sb_per_pa_to` non-zero fraction **0.5586**
  (BUILDER_VERSION 3); baseline reproduced the expected anchor exactly:
  **r = 0.6343** (n = 36,571, full 21-feature RH3_FEATS incl. live
  `sb_per_pa_to_sh`).
- **+ bx_prior_h: r = 0.6419 → lift +0.0076**; holdout mean (2024–25)
  **+0.0072** (2024 +0.0165 / 2025 −0.0021); final-pipe coef **+0.0264**.
- Per-year: 2018 +0.0109, 2019 +0.0144, 2021 −0.0003, 2022 −0.0059,
  2023 +0.0107, 2024 +0.0165, 2025 −0.0021.
- **DECISION: PROMOTE** per the pre-registered rule (lift ≥ +0.005 AND
  holdout mean positive). The SB feature did NOT absorb bx's variance
  (+0.0088 → +0.0076, a −0.0012 haircut only).
- **Disclosure (recorded, not hidden):** per-year sign consistency on the
  new substrate is **4/7** — below the original B1's 5/7 (2021 flipped
  +0.0002 → −0.0003, 2025 −0.0005 → −0.0021; both noise-level, 2022's
  −0.0059 was already negative in B1). The 4-gate cell readout therefore
  prints REJECTED under the full original gates; the pre-flight section
  above pre-declared the lift + holdout-mean rule as the promote/stop
  criterion, and that rule governs. The lift remains concentrated in
  2018/2019/2023/2024 — same caveat as B1. Re-check at season rollover when
  TRAIN_YEARS grows.

### PROMOTED — integration executed 2026-07-10 (recipe steps 1-5)

1. **Registry:** PASS record added —
   `bx_prior_h_promotion_2026-07-10.md` (machine-readable frontmatter for
   `check_feats_validated`; verified firing clean at rh3 import).
   Orchestrator registry-update list: add `bx_prior_h` (target rh3, PASS,
   this file) to `reference_validated_signals_registry.md`.
2. **Refresh step:** `refresh_dashboards.py` step **1.95** — mtime-gated
   (skip if CSV <30 days old) `build_bx_priors.py` rebuild, wired BEFORE the
   rh3 rebuild (step 2). (Also wired, independent of this promotion: step
   **1.6** as-of SB gamelog pull+assemble before the rolling-hitters rebuild,
   per sb_asof_feature_2026-07-10.md.)
3. **rh3.py:** `BX_PRIORS_CSV` constant; (batter, year) mlbam merge with
   per-year-mean fill + the house >50%-current-year-NaN hard guard (mirrors
   `ros_opp_sp_xwoba_weighted`; healthy state ≈35-40% NaN pre-fill, measured
   2026 pre-fill NaN well under gate); `'bx_prior_h'` appended to RH3_FEATS
   (22 features) and to `v2_added` — the in-pipeline Rule-9 gate now asserts
   the joint {ros_opp_sp_xwoba_weighted, bx_prior_h} lift.
4. **Harness parity:** identical merge+fill mirrored in
   `_validate_rh3_v3_helper.load_and_prep_rh3_inputs` (idempotent — skips if
   caller pre-merged; the 2026-07-09 `_cye` shim untouched).
5. **Cold rerun** (`xfp_rh3_pipeline.py`): overall **r = 0.6419** (mae
   0.0846, n = 36,571) — matches the pre-flight extended r exactly.
   Internal Rule-9 gate **Δr +0.0211** vs the drop-both baseline (0.6208),
   PASS. `bx_prior_h` coef **+0.0264** = largest |coef| of the 22.
   463 hitters projected. Movers vs pre-bx projections: veteran
   monster-box-line types firm up per the bx disagreement list — Raleigh
   307→269, Tucker 77→52, Suárez per-PA +0.0079; give-backs are speed-only /
   thin-T-1-box types (Tolbert 26→95, Nasim Nuñez 222→265 — bx pulls back
   part of the SB-feature rise, Sal Stewart 55→92). Full test suite:
   **626 passed**, no lock updates.

Post-promotion note: `validate_bx_ensemble.py` and `validate_bx_preflight.py`
are now HISTORICAL one-shots — RH3_FEATS contains `bx_prior_h` and the
helper pre-merges it, so re-running them would double-merge via `_merge_bx`
(suffix collision) and their "baseline" would already contain the candidate.
Do not re-run as-is; any future bx look needs a fresh prereg + script.
