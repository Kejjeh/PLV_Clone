---
signal: stuff_plus_asof_sp — FanGraphs Stuff+ MAIN EFFECT for rp3 at FULL multisplit framing
formula: |
  Base quantity: stuff_plus_asof — FanGraphs Stuff+ (sp_stuff on the type=8
  date-range payload) computed over the AS-OF window {Y}-03-01 .. window_end,
  where window_end is the LATEST of {05-01, 06-01, 06-15, 07-01, 08-01, 09-01}
  whose date is <= the substrate row's cutoff_date (nearest-without-leakage).
  Window pulls: the EXISTING data/research/fg_asof/fg_pit_asof_{Y}_{MMDD}.csv
  caches (pulled 2026-07-09 for the rprs2 runs; starters confirmed present —
  the RP filter in those runs was applied at attach time, not pull time).
  Attach logic reused VERBATIM from
  scripts/xfp/validate_rp_stuff_plus_asof_multisplit.py (not re-derived),
  with the role filter flipped to STARTERS within the window:
    gs >= 1 AND gs/g >= 0.4   (mirrors lib/pitcher_role.detect_pitcher_role)
  Centering: centered = stuff_plus_asof - 100 (the Stuff+ scale's defined
  league-average neutral point, NOT the sample mean) — adopting the
  mask-invariant imputation standard established by
  rp_stuff_early_masked_2026-07-10 (declared deviation from the rprs2
  multisplit run's observed-mean imputation).
  Imputation: unjoined rows -> centered = 0.0. This includes (a) early-April
  cutoffs before the first window, (b) pitchers absent from their assigned
  window pull, and (c) ALL of 2018/2019 (FanGraphs Stuff+ does not exist
  before 2020, and rp3's TRAIN_YEARS include 2018/2019 — the production
  feature would bear exactly this constant-imputed cost in those years, so
  the validation must too).
outcome: ros_fp_per_start (rp3 production TARGET), scored via the production
  rp3.cross_year_eval (LOO cross-year RidgeCV) on the
  _rp3_validation_harness.prep_rolling() substrate (expected baseline
  cross-year r = 0.5509 with the full 24-feature RP3_FEATS), TRAIN_YEARS
  2018, 2019, 2021, 2022, 2023, 2024, 2025.
expected_sign: +
theory: |
  THE ONE UNTESTED CELL in the Stuff+ family, run to adjudicate the June-6
  single-split anomaly (stuff_vs_rp3_2026-06-06: +0.0095 at one aligned
  split) exactly the way the rprs2 multisplit run adjudicated its own
  single-split PASS. Family state going in (all 2026-07-09..11):
    - rprs2 multisplit main effect:  REJECTED (+0.0019; 2025 negative;
      late-band flip -0.0003) — cumulative outcome features absorb Stuff+
      as the season accrues.
    - rprs2 early-masked rescue (M1/M2): REJECTED (family rule).
    - rp3 stuff×thin-gs interaction (archetype-STUFF reconstruction):
      REJECTED (+0.0001-0.0002) — the shrinkage layer already implements
      the thin-sample prior.
  HONEST PRIOR: REJECTION. rp3's cumulative fp_per_start_to + raw rate
  features + shrinkage are the same absorber that killed the rprs2 cell.
  The run's value is closure: it converts "premature" into "adjudicated"
  and closes the family either way. Infrastructure (as-of window caches,
  attach idiom) already exists; marginal cost is one evaluation.
production_target: rp3
framing: in-season -> ros at ALL split_days — the actual production framing of RP3_FEATS
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
n_cells: 1 (main effect only — no maskings, no interactions, no threshold
  sweeps; those variants were already spent and rejected in the adjacent
  rprs2/rp3 runs and re-trying them here would be post-hoc variant shopping)
validation_script: scripts/xfp/validate_rp3_stuff_plus_asof_multisplit.py
data: data/research/fg_asof/fg_pit_asof_{2021..2025}_{0501,0601,0615,0701,0801,0901}.csv
  + xfp_cache rolling substrate via _rp3_validation_harness.prep_rolling()
date: 2026-07-11
verdict: REJECTED (pooled +0.0032 < +0.005 gate — diluted by the constant-imputed 2018/2019 coverage hole; gates 2-5 ALL passed incl. holdout +0.0115 and NO band flip. Family closed until 2027 rollover per the binding pre-registration; the rollover re-test is genuinely promising — see Results.)
---

# stuff_plus_asof (SP main effect) -> rp3 at full multisplit framing — pre-registration

## Gate precondition (recorded BEFORE the run)

Same-day data-health check: `build_model_scorecard.py` run 2026-07-11 ~13:55
EDT — **0 FAIL / 0 WARN**, including `il_join_match_rate` all_years 0.317x
comparator PASS and the new `il_grid_coverage` 0/173 missing cells (all three
substrates). The substrate this gate measures against is healthy and frozen.

## Design (locked before results)

- **Baseline (Rule 9):** the FULL production `RP3_FEATS` (24 features) from
  `src/plv_clone/models/xfp/rp3.py`, evaluated with the production
  `cross_year_eval` on the identical row population as the candidate run.
- **Candidate:** `RP3_FEATS + ['stuff_plus_asof_c']` (centered, imputed as in
  the frontmatter formula). Imputation everywhere means candidate NaNs remove
  ZERO rows — baseline n == candidate n by construction (asserted).
- **Population:** prep_rolling() substrate; cross_year_eval's own production
  filters (dropna on 24 feats + target, gs_to >= EVAL_GS_MIN,
  ros_gs >= ROS_GS_MIN, year != 2020).
- **Leakage direction:** window_end <= cutoff_date always — the candidate is
  stale by 0-31 days, never forward-looking. FG's Stuff+ model version is
  current-day (retroactive revision) — a PASS would slightly overstate live
  performance; noted, tolerable, and moot on a rejection.

## Gates (all five must pass — mirrors rp_stuff_plus_asof_multisplit)

1. Pooled cross-year lift >= +0.005 vs the FULL 24-feature baseline.
2. Per-year lift sign: >= 5/7 TRAIN_YEARS positive (2018/2019 carry a
   constant-imputed candidate by construction — declared, not an excuse).
3. Holdout (2024, 2025) average lift > 0.
4. **Rule-8 split-band convergence:** lift within bands early <=60 /
   mid 61-100 / late >100 must have NO negative band (4dp). This was the
   rprs2 cell's failure mode and is the expected one here.
5. Full-data linear-probe coefficient on the candidate > 0 (sanity sign).

## Stopping rule + family closure (binding)

- Exactly ONE evaluation run. No re-runs with tweaked filters, window sets,
  centering, or role thresholds. If a bug is found in the script, the fix may
  be re-run only if the bug is mechanical (join/typo) and documented here.
- **On rejection: the entire Stuff+-into-rate-models family — rp3 AND rprs2,
  main effects, maskings, and interactions — is CLOSED until 2027 season
  rollover. No cell 6.** Stuff+'s validated Rule-13 surfaces (marcel_il
  fallback ranking via sp_stuff_model, /sp-stuff-board, /triangulate context)
  are unaffected either way.
- On PASS: promotion requires the four-way sync in the same commit —
  (a) RP3_FEATS + registry + Step-9 full-pipeline backtest + version bump,
  (b) validate_pitch_shape_early_warning.py FEATS copy,
  (c) _rp3_validation_harness.prep_rolling() FG merge + imputation,
  (d) ADR 0008 amendment (lens_registry classifies stuff_plus context-only;
  a registry-validated as-of variant supersedes that classification and the
  ADR must say so explicitly). Production inference would read the daily
  fg_pit_2026_current.csv guarded by _warn_if_fg_stale (train-asof vs
  inference-live asymmetry documented).

## Results (single run, 2026-07-11 ~14:15 EDT)

Baseline r=0.5613 (n=19,111) | Candidate r=0.5645 (n identical, asserted).

| Gate | Result | Status |
|---|---|---|
| (1) pooled lift >= +0.005 | **+0.0032** | **FAIL** |
| (2) per-year signs >= 5/7 | 6/7 (only 2019 at -0.0004) | PASS |
| (3) holdout (2024,2025) > 0 | **+0.0115** | PASS |
| (4) band convergence | early +0.0058 / mid +0.0046 / late +0.0006 — no flip | PASS |
| (5) probe coef > 0 | +0.474 | PASS |

Per-year lift: 2018 +0.0040, 2019 -0.0004, 2021 +0.0190, 2022 +0.0131,
2023 +0.0021, 2024 +0.0110, 2025 +0.0120.

**VERDICT: REJECTED** under the declared gates. The stopping rule and family
closure bind: no re-scoping, no variant 6, family CLOSED until 2027 rollover.

## Honest read (Rule 6 documentation — for the rollover re-test, not for now)

The rp3/SP cell fails DIFFERENTLY from the rprs2/RP cell, and the difference
matters:

1. **The blocker is COVERAGE, not absorption.** rprs2 failed on a late-band
   sign flip (cumulative features absorb Stuff+ by Aug/Sep). Here the late
   band stays positive (+0.0006), holdout is strongly positive (+0.0115),
   and every FG-covered year is positive (avg ~+0.0114 across 2021-2025).
   The pooled number is dragged under the gate by 2018/2019 — 43% of eval
   rows where FanGraphs Stuff+ DOES NOT EXIST and the candidate is a
   constant 0. That dilution was declared in the design as a real cost the
   production feature would bear; it is also the entire margin of failure.
2. **What changes at rollover:** 2027 adds another FG-covered year (and 2026
   becomes eval-eligible), moving coverage from 5/7 to ~7/9 eval years. If
   the covered-year lift holds at ~+0.01, the pooled number clears the gate
   on dilution arithmetic alone.
3. **Correct rollover design (pre-register THEN, not now):** either (a) the
   same all-years framing with the improved coverage, or (b) an explicitly
   declared FG-era eval (2021+) — defensible since production 2026
   projections only ever score in the FG era, but it must be DECLARED
   before the run, precisely because choosing it after seeing this split
   would be gate-chasing.
4. Do NOT reopen the rprs2 cell on the strength of this read — its failure
   mode (band flip) is real absorption, not coverage.
