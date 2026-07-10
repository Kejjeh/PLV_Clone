---
signal: stuff_plus_asof (RP) — MULTI-SPLIT extension
formula: FanGraphs Stuff+ (sp_stuff on the type=8 date-range payload, month=1000, qual=0, pageitems=3000) computed over the AS-OF window {Y}-03-01 .. {window_end}, where window_end is the LATEST of {05-01, 06-01, 06-15, 07-01, 08-01, 09-01} whose date is <= the substrate row's cutoff_date (nearest-without-leakage). Joined by mlb_id == pitcher onto EVERY rolling_relievers_2018_2026 row (all ~22-23 split_days per year), years 2021-2025. FG rows restricted to relievers within the window (gs == 0 OR gs/g < 0.4). Rows whose cutoff_date predates the first window (only split_day 30 in 2023/2024/2025) AND any row whose pitcher is absent from its assigned window pull are mean-imputed with the global mean of OBSERVED stuff_plus_asof values (matching the rolling-builder's lag1 imputation pattern), so baseline and candidate score the IDENTICAL row population.
outcome: fp_year_total (rprs2 production TARGET), scored via the production rprs2.cross_year_eval (RidgeCV LOO cross-year), full split_day range, years 2021-2025, g_to >= 5 (production EVAL_G_MIN)
expected_sign: +
theory: CONFIRMATORY re-test of an already-PASSED signal at broader framing. stuff_plus_asof PASSED the June-15 single-split validation earlier today (rp_stuff_plus_asof_2026-07-09.md — lift +0.0059, 5/5 signs, holdout +0.0014, partial r +0.176) but was explicitly licensed ONLY at that split. FEATS_RPRS2 trains at all split_days, so production wiring requires as-of values at every split_day and a rerun through rprs2's own gates. That is this run.
production_target: rprs2
framing: in-season -> ros at ALL split_days (30..~184) — the actual production framing of FEATS_RPRS2
holdout_years: [2024, 2025]
training_years: [2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_rp_stuff_plus_asof_multisplit.py
puller_script: scripts/xfp/pull_fg_asof_rp_windows.py (generalizes pull_fg_asof_rp_0615.py; 0615 caches reused)
date: 2026-07-09
verdict: REJECTED at full-split framing (pooled +0.0019 < +0.005; signs 4/5 — 2025 negative; late-band sign flip −0.0003). Single-split June-15 PASS stands but stuff_plus_asof is NOT licensed for FEATS_RPRS2.
purpose: complete the production-licensing of stuff_plus_asof for rprs2 — the single-split PASS's stated blocking caveat #1.
---

# stuff_plus_asof → rprs2 (RP) — MULTI-SPLIT pre-registration

## Relationship to the earlier run (same day)

This is the follow-up demanded by `rp_stuff_plus_asof_2026-07-09.md` deployment
caveat #1 ("single-split license only"). It is a CONFIRMATORY re-test at
broader framing, not a new hypothesis: the signal, join key, RP filter, FG
endpoint, and expected sign are all unchanged. What changes is the population
(all split_days instead of one per year) and the as-of window assignment
(step-function of pulled windows instead of a single June-15 pull).

## Design (locked before results)

- **Baseline (Rule 9):** the FULL production `FEATS_RPRS2` list (27 features)
  from `src/plv_clone/models/xfp/rprs2.py`, evaluated with the production
  `cross_year_eval` on the identical row population as the candidate run.
- **Candidate:** `FEATS_RPRS2 + ['stuff_plus_asof']` where `stuff_plus_asof`
  is the step-function as-of value described in the frontmatter formula.
- **Population:** ALL `rolling_relievers_2018_2026.csv` rows, years 2021-2025,
  every split_day; `g_to >= 5` and dropna over the 27 production feats +
  target applied inside `cross_year_eval` (production behavior). The candidate
  is mean-imputed where unjoined, so candidate NaNs remove ZERO rows —
  baseline n == candidate n by construction (asserted).
- **Window schedule (pulled BEFORE eval, cached, idempotent):**
  - 2021-2025: end dates 05-01, 06-01, 06-15 (already cached), 07-01, 08-01,
    09-01 — all windows start {Y}-03-01. 25 new pulls + 5 cached.
  - 2026 (production continuity only, NOT part of the eval): 05-01, 06-01,
    07-01 (+ the cached 0709 pull and the daily `fg_pit_2026_current.csv`).
- **Leakage direction:** window_end <= cutoff_date always, so the candidate
  can only carry LESS information than the substrate row (stale by 0-30 days,
  worst at the last pre-window split of each month and at late-Sept splits
  riding the 09-01 window). Staleness is conservative — it can only hurt the
  candidate, never leak future information into it.

## Gates (all pre-registered; ALL must pass for a production license)

1. **Pooled cross-year lift >= +0.005** vs full FEATS_RPRS2
   (`lib/rule9.rule9_lift`, same gate as every rprs2 feature test).
2. **Per-year sign consistency 5/5** (Rule 5 zero-slack — see note below).
3. **Holdout (2024, 2025) mean lift > 0.**
4. **Role-change subset no regression:** `role_change_mask` subset lift
   >= 0.000 (rprs2's own stratified gate population; the model exists to
   serve role-change reads, so the candidate must not degrade them).
5. **Rule 8 split-band convergence:** lift computed within THREE split_day
   bands — early (<= 60), mid (61-100), late (> 100) — from the SAME LOO
   detail frames (no refit). If ANY band's lift is negative (sign flip vs
   the pooled positive), the run FAILS convergence and the signal stays
   unlicensed REGARDLESS of the pooled number. (Rounded to 4dp; a band lift
   of exactly 0.0000 does not fail.)

## Rule 5 sample-size honesty note (pre-acknowledged)

FanGraphs Stuff+ begins 2020; 2020 is COVID-excluded by construction; rprs2's
TRAIN_YEARS year 2019 has no Stuff+ and is excluded from this eval population.
That leaves EXACTLY **5 usable outcome years (2021-2025)** — meets the 5-year
minimum with ZERO slack, so the sign gate is 5/5 (one wrong-sign year is a
REJECT; no "5 of 7" cushion exists). Stated before running.

## Known framing caveats (pre-acknowledged)

- The 09-01 window serves all September/October splits (staleness up to ~31
  days at the final split). If Stuff+ drifts late-season this dampens the
  candidate; disclosed, conservative.
- Imputed rows (early-April + unjoined) carry the population mean — they
  dilute toward zero lift, they cannot manufacture it. Imputation rate is
  reported per year and per band in Step 2.5 BEFORE any eval.
- The single-split PASS showed a monotonic per-year fade (+0.0103 in 2021 →
  +0.0002 in 2025). If that fade is real, gate 2 (5/5 signs) is the gate most
  at risk here — a 2025 sign flip at broader framing is a REJECT per the
  locked design, and we say so before running.
- The target `fp_year_total` is a full-season total including the pre-split
  portion — production convention, identical for baseline and candidate,
  same as every prior rprs2 validation.
- Eval-population note: pooling ALL split_days means each pitcher-year
  contributes ~22-23 rows (the standard rprs2 eval convention — the
  production gates are scored on exactly this pooled population), so
  per-year r values are NOT comparable to the single-split run's.

## Step 2.5 data-coverage pre-check

(Filled after the pulls + join, BEFORE any model eval — join rates only, no
outcome contact.)

### Pull coverage — 28/28 new pulls OK (30/30 historical windows incl. cached 0615s)

| year | 0501 | 0601 | 0615 | 0701 | 0801 | 0901 |
|---|---|---|---|---|---|---|
| 2021 | 541 | 639 | cached (459 RP) | 713 | 776 | 848 |
| 2022 | 553 | 654 | cached | 722 | 771 | 828 |
| 2023 | 527 | 640 | cached | 727 | 777 | 817 |
| 2024 | 544 | 628 | cached | 694 | 752 | 818 |
| 2025 | 549 | 650 | cached | 731 | 783 | 837 |
| 2026 | 549 | 657 | — | 721 | — | — |

(cell = total pitcher rows in the pull; 100% xMLBAMID mapping and 100%
stuff_plus non-null in every file except 2022-0501 with 552/553.) All cached
to `data/research/fg_asof/fg_pit_asof_{year}_{MMDD}.csv`, idempotent. Puller
gained mid-run driver-relaunch resilience after the first attempt's Chrome
session died at launch (dead-session exceptions now fast-fail → relaunch, 4
relaunch budget); second attempt ran 28/28 clean with zero relaunches.

### Window → split_day mapping (nearest-without-leakage)

Same step-function every year (window_end = latest pulled end date <=
cutoff_date; staleness = cutoff − window_end, range 0-31 days):

| window | serves cutoffs | split_days (typical) |
|---|---|---|
| IMPUTED (pop. mean) | cutoff < 05-01 | sd 30 in 2023 (04-29), 2024 (04-27), 2025 (04-26) only |
| {Y}-05-01 | 05-01 .. 05-31 | 30-58 (2021/2022), 37-58/65 (2023-2025) |
| {Y}-06-01 | 06-01 .. 06-14 | 58/65-72 (2025: 72-79) |
| {Y}-06-15 | 06-15 .. 06-30 | 79-93 varies (the single-split run's splits) |
| {Y}-07-01 | 07-01 .. 07-31 | ~93-121 |
| {Y}-08-01 | 08-01 .. 08-31 | ~121-156 |
| {Y}-09-01 | 09-01 .. season end | ~149/156-184 |

Full 113-row per-(year, split_day) table with exact staleness_days is printed
by the validation script (verbatim in its stdout, reproducible).

### Join / imputation rates (years 2021-2025, g_to >= 5, pre-dropna)

| slice | rows | joined | rate |
|---|---|---|---|
| 2021 | 8,127 | 8,007 | 98.5% |
| 2022 | 7,900 | 7,850 | 99.4% |
| 2023 | 7,757 | 7,453 | 96.1% |
| 2024 | 7,561 | 7,257 | 96.0% |
| 2025 | 7,968 | 7,654 | 96.1% |
| band early <=60 | 6,899 | 6,064 | 87.9% |
| band mid 61-100 | 9,815 | 9,780 | 99.6% |
| band late >100 | 22,599 | 22,377 | 99.0% |
| **TOTAL** | **39,313** | **38,221** | **97.2%** |

1,092 rows (2.8%) mean-imputed at 102.30 (the observed mean) — concentrated
in the early band (the three IMPUTED sd-30 year-cells + pitchers with g_to>=5
by the cutoff but no appearance by the earlier window end). Step 2.5 CLEAR —
coverage is not the binding constraint. Proceeded to eval.

## Results (appended AFTER the run, 2026-07-09)

Eval population after production dropna(27 feats + target), g_to >= 5:
**28,202 rows** (2021: 6,030 / 2022: 5,705 / 2023: 5,344 / 2024: 5,526 /
2025: 5,597). Baseline n == candidate n (asserted; imputation removed 0 rows).

| year | baseline r (FEATS_RPRS2) | +stuff_plus_asof r | Δr |
|---|---|---|---|
| 2021 | 0.8704 | 0.8743 | +0.0039 |
| 2022 | 0.8672 | 0.8712 | +0.0040 |
| 2023 | 0.8926 | 0.8933 | +0.0007 |
| 2024 | 0.8733 | 0.8738 | +0.0005 |
| 2025 | 0.8667 | 0.8663 | **−0.0004** |
| **pooled** | **0.8740** | **0.8759** | **+0.0019** |

Gates:
1. pooled lift **+0.0019 < +0.005 — FAIL**
2. sign consistency **4/5 — FAIL** (2025 negative; zero-slack gate as
   pre-acknowledged — the single-split run's 2025 fade to +0.0002 crossed
   zero at broader framing, exactly the pre-flagged risk)
3. holdout (2024, 2025) mean lift **+0.0000 (+0.00005) — PASS** (degenerate)
4. role-change subset (n=5,651): r 0.8719 → 0.8733, lift **+0.0014 — PASS**
5. Rule-8 split-band convergence — **FAIL (sign flip)**:

| band | n | baseline r | candidate r | lift |
|---|---|---|---|---|
| early <=60 | 5,400 | 0.7203 | 0.7286 | **+0.0083** |
| mid 61-100 | 7,301 | 0.8342 | 0.8380 | **+0.0038** |
| late >100 | 15,501 | 0.9437 | 0.9434 | **−0.0003** |

Diagnostics (context, not gates):
- raw r(stuff_plus_asof, fp_year_total) = +0.4465 (n=28,202)
- partial r over ALL 27 production feats = **+0.1195** (p=3e-90) pooled, but
  band-decomposed: early **+0.1716** → mid **+0.1538** → late **+0.0632**
- the information content decays monotonically with season progress: by
  August/September the baseline's cumulative outcome features (fp_with_role_to,
  k_pct_to, xwoba_per_pa_to…) have absorbed what Stuff+ knew, and the as-of
  window staleness (0-31 days) further dampens the late reads. The late band
  is 55% of the pooled rows, so it drags the pooled lift below the gate.

### Verdict: REJECTED at full-split framing — stuff_plus_asof is NOT licensed for FEATS_RPRS2

Three of five pre-registered gates fail (pooled lift, 5/5 signs, band
convergence). Per the locked design — and per the mission's explicit Rule-8
condition that a band sign flip fails convergence regardless of the pooled
number — the signal stays UNLICENSED for production wiring into FEATS_RPRS2.
Do NOT add stuff_plus_asof to rprs2.

Status of the earlier single-split PASS: `rp_stuff_plus_asof_2026-07-09.md`
remains a valid June-15-split research finding (its own gates passed on its
own framing), but its deployment caveat #1 is now RESOLVED NEGATIVELY: the
broader framing it required was run and failed. The recent-year fade it
flagged (caveat #2) materialized as a 2025 sign flip.

### What survives / possible future work (NOT run here — would need fresh pre-registration)

- The early/mid-season signal is real and non-trivial (band lifts +0.0083 /
  +0.0038, partial r +0.17/+0.15). A masked variant
  (`stuff_plus_asof * I[split_day <= 100]`, analogous to the lineup_spot_early
  framing family) is the natural follow-up — but the lineup-spot precedent
  (4 framings, all MARGINAL) and the 2025 fade both temper expectations, and
  it must clear its own pre-registered run before any wiring.
- The 30-window as-of pull cache (`fg_pit_asof_{year}_{MMDD}.csv`) and the
  generalized puller (`scripts/xfp/pull_fg_asof_rp_windows.py`, resilient,
  idempotent) are reusable data infrastructure for ANY future as-of FG
  validation (SP or RP), independent of this verdict. 2026 continuity windows
  (0501/0601/0701) are also cached.
- No changes were made to rprs2.py, FEATS lists, refresh_dashboards.py, or
  any production file. README index row left to the owner session (same
  convention as the single-split run).
