# Pre-registration: bx_sp_composite into rp3 — 2026-07-10 (evening)

- **Date written:** 2026-07-10 late evening, BEFORE any evaluation run of the
  composite. Status at write time: `scripts/xfp/validate_bx_sp_composite.py`
  not yet written; no composite column has ever been evaluated through the rp3
  harness. The only observed numbers for this family are the four B-cells and
  the SECONDARY joint report in `bx_ensemble_2026-07-10.md`.
- **Question:** does a SINGLE additive composite of the SP box prior (B2,
  `bx_prior_sp`) and the SP aging-curve level (B4, `bx_age_mult_sp`) clear the
  full gate stack through the rp3 production harness, where each component
  individually missed only gate 1 (+0.0036 / +0.0027 vs the +0.005 bar) and
  the B2+B4 JOINT cleared every gate (+0.0054, 7/7 signs, holdout both years
  positive, both coefs +)? This is the exact "future prereg candidate"
  recorded in the bx_ensemble results: ONE composite cell, ONE gate readout.
- **Protocol:** `/validate-feature` 9-rule protocol; harness
  `scripts/xfp/_rp3_validation_harness.py` (production parity, incl. the
  2026-07-09 ros_opp_xwoba merge + tolerant `_cye`). Baseline = FULL
  production RP3_FEATS (24 features). Expected baseline anchor r ≈ 0.5614
  (n = 19,111); whatever is measured is what counts.

## The ONE cell (no sweep — this is the only construction evaluated)

```
bx_sp_composite = bx_prior_sp + (bx_age_mult_sp − mean_year(bx_age_mult_sp))
```

computed on the bx CSV's SP prediction rows (`mean_year` = per-year mean of
`bx_age_mult_sp` over rows with a non-null `bx_prior_sp`, i.e. the SP leg),
BEFORE the merge into the rolling substrate.

### Construction justification (declared before any result is seen)

- **Units check (from `build_bx_priors.py`, inspected before this prereg):**
  `bx_age_mult_sp` is the delta-method `cum_curve` LEVEL at the player's
  year-T age — a cumulative sum of harmonic-volume-weighted year-over-year
  `fp_per_start` deltas, anchored at age 20. It is therefore an ADDITIVE
  FP/start offset by construction (the "mult" name is a legacy of the design
  doc, as the original prereg itself noted). `bx_prior_sp` is a predicted
  `fp_per_start`. Same units → additive composition is the natural form; no
  multiplicative variant is considered.
- **Scale check (CSV descriptives only — no target/eval contact):** prior
  std ≈ 2.17, age-level std ≈ 2.59 FP/start, correlation ≈ +0.07. Comparable
  scales mean the un-weighted 1:1 sum lets both components speak; the near-zero
  correlation matches the complementarity the joint report showed.
- **Centering:** subtracting the per-year mean of the age level keeps the
  composite anchored at the box prior's LEVEL (interpretable as "box-line
  prior, adjusted for where the player sits on the age curve relative to this
  year's SP population") and removes slow drift in the league age
  distribution across years. Under StandardScaler + Ridge a global affine
  shift is irrelevant; per-year centering is a real (declared) choice.
- **No weight tuning.** The joint Ridge chose ~2:1 standardized weights
  (+0.44 / +0.23); a tuned-weight composite would be a sweep. The 1:1
  raw-units sum is fixed a priori. If 1:1 is materially worse than the free
  joint, the honest outcome is FAIL.
- **Rationale for a composite at all:** rp3 has NO career-stage/age feature;
  B4 was its largest single missing axis (B4 > B3 for exactly this reason),
  and B2 carries box-prior level information partially redundant with
  `prior_fp_per_start`. Forcing Ridge to take them as ONE signal is what the
  joint result demonstrated works, without granting two seats to two
  individually sub-gate features.

## Join + missing-data protocol (mirrors the original B-cells)

- Source: `data/research/xfp_cache/bx_priors_2018_2026.csv` (1,653 SP rows).
- Compute `bx_sp_composite` on the CSV SP rows, then merge onto the harness
  rolling frame on `(pitcher = mlbam, year)` — mlbam joins only, never name.
- Rows without a bx prediction (rookies / sub-floor T−1 lines): fill with the
  per-year mean of the merged composite, then global mean for any residual
  NaN — identical to `_merge_bx` in `validate_bx_ensemble.py`.
- Join rate before fill is reported per year (expect ≈62% overall over all
  rolling rows, per the B2 readout).

## Multiple-look honesty note (declared)

This is the SECOND look at the 2024–2025 holdout for the bx-SP family: the
B2+B4 joint readout (+0.0054, holdout both years positive) was already
observed on these exact years before this prereg was written. The composite
is not the joint (1:1 raw-units vs free Ridge weights), but it is strongly
informed by it. The gate bar is therefore ELEVATED above the house standard:

## Gates (ALL must pass — elevated bar, fixed before the run)

1. Pooled cross_year_r lift ≥ +0.005 vs the FULL production RP3_FEATS
   baseline (Rule 9 hard baseline, all 24 features incl.
   `prior_fp_per_start` and `ros_opp_xwoba_weighted`).
2. Per-year sign consistency ≥ **6/7** (house standard is 5/7).
3. Holdout 2024 AND 2025 lifts **EACH individually positive** (house
   standard is mean > 0; the stricter each-year reading governs here).
4. Final-pipeline coefficient sign + (via `rp3.train_final` on
   RP3_FEATS + composite).

No MARGINAL band. Anything short of all four = FAIL, and the bx-SP family is
CLOSED until the 2026 season completes (fresh holdout year).

## If PASS — Rule-7 production integration (pre-declared scope)

Mirrors the `bx_prior_h` promotion executed earlier today
(`bx_prior_h_promotion_2026-07-10.md`):

(a) `rp3.py`: `BX_PRIORS_CSV` constant; compute the composite from the CSV
    with the same per-year centering; merge on `(pitcher, year)`; per-year
    mean fill + the house >50%-current-year-NaN hard guard (mirror of the
    `ros_opp_xwoba_weighted` guard); append `'bx_sp_composite'` to RP3_FEATS
    AND to the in-pipeline `v2_added` Rule-9 gate set; machine-readable PASS
    promotion record so `check_feats_validated(RP3_FEATS)` stays green.
(b) Harness parity: identical merge + fill in
    `_rp3_validation_harness.prep_rolling`, idempotent-guarded.
(c) Cold rp3 rerun via run_summary; report final r, internal Rule-9 gate,
    top-15 SP movers.
(d) Full pytest via run_summary; no lock updates.
(e) Refresh dependency: step 1.95 (`build_bx_priors.py`, wired today) already
    regenerates the CSV incl. the SP columns — confirm and note.

## Runner

`scripts/xfp/validate_bx_sp_composite.py` — fresh script (the original
`validate_bx_ensemble.py` is a historical one-shot post-bx_prior_h-promotion
on the rh3 side; the rp3 leg machinery is replicated, not re-run). Results
JSON: `data/research/validation_runs/bx_sp_composite_results_2026-07-10.json`.

---

## RESULTS — appended 2026-07-10 late evening, after the single run

- Substrate: harness `prep_rolling`, 30,637 rolling rows; baseline
  reproduced the expected production anchor exactly: **r = 0.5614**
  (n = 19,111, full 24-feature RP3_FEATS).
- Composite built on 1,653 SP CSV rows (mean 11.28, std 3.48 FP/start —
  the near-zero component correlation means the 1:1 sum widened spread as
  expected). Join rate before per-year-mean fill: **62.4%** overall
  (66.8 / 64.6 / 51.8 (2021, 2-yr-lag vintage) / 66.3 / 59.8 / 62.3 /
  62.6 / 67.5 (2026)) — matches the B2 readout.
- **+ bx_sp_composite: r = 0.5659 → lift +0.0045.**
- Per-year: 2018 +0.0058, 2019 +0.0014, 2021 +0.0012, 2022 +0.0060,
  2023 +0.0058, 2024 +0.0102, 2025 +0.0029 → **7/7 signs**.
- Holdout individually: **2024 +0.0102, 2025 +0.0029 — both positive**
  (mean +0.0066).
- Final-pipe coef: **+0.3544** (+, as declared).

### Gate readout (elevated bar)

| Gate | Result |
|---|---|
| 1. lift ≥ +0.005 | **FAIL** (+0.0045) |
| 2. signs ≥ 6/7 | PASS (7/7) |
| 3. holdout each year + | PASS (2024 +0.0102 / 2025 +0.0029) |
| 4. coef + | PASS (+0.3544) |

### VERDICT: FAIL

The fixed 1:1 raw-units composite recovered most but not all of the free
joint's lift (+0.0054 joint → +0.0045 composite, a −0.0009 give-back to the
a-priori weighting) and lands below the +0.005 bar — under both the elevated
bar AND the house standard. The prereg declared no marginal band and no
weight tuning (a tuned composite would be a sweep on an already
twice-observed holdout). Honest outcome: the signal is real-looking
(7/7 signs, holdout robust, strongly + coef) but sub-gate at the one
pre-declared weighting.

**Family CLOSED until the 2026 season completes** (fresh holdout year).
At season rollover, a fresh prereg may revisit with 2026 as virgin holdout —
that run may pre-declare a weighted form informed by the joint coefs, since
the new holdout will be untouched. rp3 remains without any bx feature;
production untouched by this run.
