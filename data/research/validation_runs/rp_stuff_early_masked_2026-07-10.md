---
signal: stuff_early / stuff_early_decay (RP) — EARLY-SEASON-MASKED Stuff+ variants
formula: |
  Base quantity: stuff_plus_asof — FanGraphs Stuff+ over the AS-OF window
  {Y}-03-01 .. window_end, window_end = LATEST of {05-01, 06-01, 06-15, 07-01,
  08-01, 09-01} with window_end <= the row's cutoff_date (nearest-without-
  leakage), RP-filtered within the window (gs == 0 OR gs/g < 0.4), joined by
  mlb_id == pitcher. Attach logic reused VERBATIM from
  scripts/xfp/validate_rp_stuff_plus_asof_multisplit.py (not re-derived).
  Centering: centered = stuff_plus_asof - 100 (the Stuff+ scale's defined
  league-average neutral point — NOT the sample mean — so the mask cannot
  inject a level step and the neutral point is data-independent).
  Imputation: unjoined rows (early-April cutoffs + missing-from-window
  pitchers, ~2.8% of rows per yesterday's Step 2.5) get centered = 0.0.
  DECLARED DEVIATION from the multisplit run's observed-mean imputation
  (102.30 raw = +2.30 centered): for a mask/decay-WEIGHTED variable the
  imputed value must be mask-invariant (w * 0 = 0 for every weight w),
  otherwise the imputation itself interacts with the weight. Magnitude is
  immaterial (2.8% of rows, 2.3 Stuff+ points ~ 0.02 SD).
  M1 (hard mask):    stuff_early       = centered * I[split_day <= 100]
  M2 (linear decay): stuff_early_decay = centered * max(0, (140 - split_day)/140)
outcome: fp_year_total (rprs2 production TARGET), scored via the production
  rprs2.cross_year_eval (RidgeCV LOO cross-year), full split_day range,
  years 2021-2025, g_to >= 5 (production EVAL_G_MIN) — the IDENTICAL
  population as the multisplit run (n=28,202 after production dropna).
expected_sign: + (both cells)
theory: |
  Follow-up demanded by rp_stuff_plus_asof_multisplit_2026-07-09.md "what
  survives" section. stuff_plus_asof was REJECTED at full framing because of
  a Rule-8 band sign flip: early <=60 +0.0083 / mid 61-100 +0.0038 / late
  >100 -0.0003 — cumulative outcome features absorb Stuff+ by Aug/Sep and
  the late band (55% of rows) drags the pooled lift under the gate. The
  masked variant keeps the real early signal and zeroes it where it decays.
  M2 is the CONTROL cell: a linear decay instead of a hard mask. If M2 ~ M1
  the signal is robust to functional form; if ONLY M1 works, the hard cutoff
  at 100 is suspect (cherry-picked from yesterday's bands).
production_target: rprs2
framing: in-season -> ros at ALL split_days (30..~184) — the production
  framing of FEATS_RPRS2 (the framing yesterday's signal FAILED at)
holdout_years: [2024, 2025]
training_years: [2021, 2022, 2023, 2024, 2025]
n_cells: 2 (Bonferroni 2 — M1 and M2 declared before any run; no other
  cutoffs, horizons, or functional forms will be tried in this session)
validation_script: scripts/xfp/validate_rp_stuff_early_masked.py
data: data/research/fg_asof/fg_pit_asof_{year}_{MMDD}.csv (30 historical
  windows, cached 2026-07-09, 100% mlbam) — no new pulls needed
date: 2026-07-10
verdict: REJECTED by the pre-registered family rule — M1 (hard mask) pooled
  +0.0043 < +0.005 (its only failed gate); M2 (decay control) passed ALL
  gates but only MARGINALLY (pooled +0.0054, +0.0004 above the gate) and the
  locked rule requires BOTH cells. No production license; no third framing
  may be tried (Bonferroni 2). The lineup_spot MARGINAL precedent repeats.
---

# stuff_early (masked as-of Stuff+) → rprs2 (RP) — pre-registration

## CRITICAL honesty note (pre-registered, binding)

**The <=100 cutoff is a DATA-DERIVED hyperparameter.** It was chosen by
looking at yesterday's band table (early <=60 +0.0083 / mid 61-100 +0.0038 /
late >100 -0.0003) — i.e., the mask boundary was selected FROM the very
evaluation data this run will score. The 140-day decay horizon in M2 is
likewise informed by the same table (weight reaches zero shortly after the
band where the signal died). A bare-gate pass is therefore WEAK evidence,
and the bar is elevated accordingly (below). The lineup_spot precedent is
also pre-acknowledged: 4 framings of that family all came back MARGINAL.
Expectations tempered — this was recorded in yesterday's memo before this
run existed.

## Design (locked before results)

- **Baseline (Rule 9):** the FULL production `FEATS_RPRS2` list (27 features),
  evaluated with the production `cross_year_eval` on the identical row
  population as the candidates. Same convention as the multisplit run
  (expected to reproduce its baseline: pooled r 0.8740, n 28,202).
- **Candidates:** `FEATS_RPRS2 + ['stuff_early']` (M1) and
  `FEATS_RPRS2 + ['stuff_early_decay']` (M2), one at a time — 2 cells total.
- **Population:** ALL `rolling_relievers_2018_2026.csv` rows, years
  2021-2025, every split_day; `g_to >= 5` + production dropna inside
  `cross_year_eval`. Candidates are imputed (centered=0) where unjoined, so
  candidate NaNs remove ZERO rows — baseline n == candidate n (asserted).
- **Attach machinery:** window→split_day mapping and RP-filtered FG join
  copied verbatim from `validate_rp_stuff_plus_asof_multisplit.py`. All 30
  window pulls already cached (Step 2.5 pull-coverage table stands from
  yesterday's memo; join rates 97.2% total will be re-printed before eval).

## Rule 5 sample-size honesty note (pre-acknowledged)

FanGraphs Stuff+ begins 2020; 2020 is COVID-excluded; rprs2's 2019 has no
Stuff+. That leaves EXACTLY **5 usable outcome years (2021-2025)** — the
5-year minimum with ZERO slack. Yesterday's zero-slack 5/5 sign gate is here
replaced by the mission's declared bar: **>=4/5 signs AND holdout years 2024
and 2025 BOTH individually positive** — one wrong-sign year is tolerated
only among 2021-2023; any recent-year (2024/2025) sign flip is a REJECT.
The 2025 fade that killed yesterday's run is exactly what this gate watches.

## Gates (elevated bar — ALL must pass, per cell)

1. **Pooled cross-year lift >= +0.005** vs full FEATS_RPRS2
   (`lib/rule9.rule9_lift`, standard rprs2 gate).
2. **Per-year sign consistency >= 4/5**, AND
3. **Holdout years 2024 and 2025 BOTH individually positive** (stricter than
   the usual mean-of-two > 0).
4. **Role-change subset no regression:** `role_change_mask` subset lift
   >= 0.000 (rprs2's second production gate — the model exists to serve
   role-change reads).
5. **Early-band persistence: lift within split_day <= 60 must be >= +0.005**
   (the masked signal must remain worth the gate where it claims to live —
   not merely survive dilution).
6. **Late-band mechanical check (report, not a gate for M1):** for M1 the
   late >100 band lift is ~0 BY CONSTRUCTION (the candidate is constant 0
   there; any nonzero is ridge-coefficient spillover through the shared fit)
   — reported to confirm the mechanics. For M2 the late band has nonzero
   weight over split_day 101-139, so its late-band lift is reported and must
   be >= -0.0005 (no material sign flip; tolerance because the decay tail is
   a deliberate, small, declared exposure).

## Family verdict rule (pre-registered — the anti-cherry-pick clause)

Because the cutoff is data-derived, a **production-license PASS requires
BOTH cells to pass their gates.** Outcomes:
- **M1 PASS + M2 PASS** → signal is robust to functional form → PASS;
  write integration recipe (but do NOT integrate — Rule 7).
- **M1 PASS + M2 FAIL** → SUSPECT — the hard cutoff carried the result;
  REJECTED for production. No third framing may be tried (Bonferroni 2).
- **M1 FAIL** (regardless of M2) → REJECTED.
Marginal passes (within ~0.001 of any gate) will be labeled MARGINAL in the
verdict per the lineup_spot precedent, even if technically passing.

## Known framing caveats (pre-acknowledged)

- Same staleness structure as yesterday (window_end <= cutoff, 0-31 days
  stale) — conservative, can only hurt the candidates.
- The mid band 61-100 is inside M1's mask at full strength but is decayed to
  weight 0.56-0.28 in M2 — some M1-vs-M2 divergence in the mid band is
  expected from construction, which is why the ROBUSTNESS read is the pooled
  + early-band + holdout agreement, not band-identical numbers.
- The target `fp_year_total` is a full-season total including pre-split FP —
  production convention, identical for baseline and candidates.
- Per-pitcher-year row pooling (~22-23 rows each) — standard rprs2 eval
  convention; per-year r not comparable to single-split runs.
- Report per-cell: pooled, per-year, holdout (both years individually),
  role-change subset, and all three band lifts.

## Step 2.5 data-coverage pre-check

Coverage was established yesterday (30/30 windows cached, join 97.2% total,
imputation 2.8% concentrated in the early band — see
rp_stuff_plus_asof_multisplit_2026-07-09.md). The validation script
re-prints join rates per year and per band BEFORE any eval as confirmation;
no new pulls are required. Step 2.5 considered CLEAR unless the re-print
disagrees with yesterday's table.

## Results (appended AFTER the run, 2026-07-10)

Full stdout: `.cache/test-logs/20260710T234738Z.log` (reproducible via the
validation script). Step 2.5 re-print matched yesterday's table exactly
(97.2% joined, 1,092 rows imputed, early band 87.9%). Baseline reproduced
the multisplit run to the 4th decimal (pooled r 0.8740, n 28,202, per-year
identical) — production parity confirmed.

### M1 — stuff_early (hard mask, `centered * I[split_day <= 100]`)

| year | baseline r | +stuff_early r | Δr |
|---|---|---|---|
| 2021 | 0.8704 | 0.8780 | +0.0076 |
| 2022 | 0.8672 | 0.8754 | +0.0082 |
| 2023 | 0.8926 | 0.8933 | +0.0007 |
| 2024 | 0.8733 | 0.8751 | +0.0018 |
| 2025 | 0.8667 | 0.8691 | +0.0024 |
| **pooled** | **0.8740** | **0.8783** | **+0.0043** |

Gates: (1) pooled **+0.0043 < +0.005 — FAIL**; (2) signs 5/5 — PASS;
(3) holdout 2024 +0.0018 / 2025 +0.0024, both positive — PASS;
(4) role-change subset (n=5,651) +0.0046 — PASS;
(5) early <=60 band +0.0112 — PASS;
(6) late >100 band +0.0013 (mechanical report — the candidate is constant 0
there; the nonzero is ridge-coefficient spillover through the shared refit,
not signal). Bands: early +0.0112 / mid +0.0042 / late +0.0013.
**CELL VERDICT: FAIL (pooled gate only).**

### M2 — stuff_early_decay (control, `centered * max(0,(140-split_day)/140)`)

| year | baseline r | +stuff_early_decay r | Δr |
|---|---|---|---|
| 2021 | 0.8704 | 0.8799 | +0.0095 |
| 2022 | 0.8672 | 0.8771 | +0.0099 |
| 2023 | 0.8926 | 0.8936 | +0.0010 |
| 2024 | 0.8733 | 0.8758 | +0.0025 |
| 2025 | 0.8667 | 0.8697 | +0.0030 |
| **pooled** | **0.8740** | **0.8794** | **+0.0054** |

Gates: (1) pooled **+0.0054 >= +0.005 — PASS (MARGINAL: +0.0004 above the
gate, inside the pre-registered ~0.001 marginality band)**; (2) signs 5/5 —
PASS; (3) holdout 2024 +0.0025 / 2025 +0.0030, both positive — PASS;
(4) role-change subset (n=5,651) +0.0059 — PASS;
(5) early <=60 band +0.0099 — PASS;
(6) late >100 band +0.0023 >= -0.0005 — PASS.
Bands: early +0.0099 / mid +0.0059 / late +0.0023.
**CELL VERDICT: PASS (all gates), labeled MARGINAL per the prereg.**

Diagnostics (context only): raw r M1 +0.2934 / M2 +0.3139; partial r over
all 27 feats M1 +0.1780 / M2 +0.1982. (Per-band partial r for late-band
rows is an artifact under masking — the residualization is global, so a
constant-0 band still shows nonzero partial r; ignore those cells.)

### Verdict: REJECTED — no production license (family rule binds)

The pre-registered family rule is unambiguous: "M1 FAIL (regardless of M2)
→ REJECTED," and Bonferroni 2 forbids trying a third framing in this
session. M1 failed exactly one gate — the pooled +0.005 — with everything
else green.

Honest reading of the inversion (recorded, not acted on):
- The expectation was M1 strong / M2 the robustness check. Reality flipped:
  the SMOOTH decay beat the HARD mask on every metric (pooled, every year,
  role-change, mid band). This actually argues AGAINST the cherry-pick worry
  in one narrow sense — the signal is not an artifact of the 100 boundary,
  it is smoother than the boundary — but it simultaneously shows the
  functional form materially moves the result (+0.0043 vs +0.0054), which
  is exactly the hyperparameter sensitivity the elevated bar existed to
  catch. A MARGINAL pass on the second-tried form of a data-derived family
  is the lineup_spot pattern repeating (4 framings, all MARGINAL), as the
  prereg tempered-expectations note predicted.
- M2's standalone all-gates pass is a registered near-miss, NOT a license.
  Anyone tempted to "just ship M2" should note: the pooled margin is
  +0.0004, the 2023 lift is +0.0010, and the family verdict is REJECTED.

### Future work (would need fresh pre-registration; expectations LOW)

- If this family is ever revisited, the honest next test is a SINGLE
  pre-committed smooth-decay cell (e.g., the same 140-day linear decay, or a
  decay horizon chosen a priori from theory, not from these tables) run
  after new outcome data accumulates (2026 season completion adds a 6th
  year and restores Rule-5 slack). Do not re-tune the horizon on 2021-2025
  — those years are now exhausted for this family (two looks taken).
- No changes were made to rprs2.py, FEATS lists, or any production file.
  New files this session: this prereg + scripts/xfp/validate_rp_stuff_early_masked.py.
  README index row left to the owner session (same convention as prior runs).
