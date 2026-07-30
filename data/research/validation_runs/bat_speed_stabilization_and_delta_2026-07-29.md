---
signal: bat_speed_stabilization_and_delta (Study B2 — two parts)
formula: >
  PART 1 (measurement / stabilization, research-only): from
  data/research/bat_speed_daily.parquet, for each (batter, season) walk the
  batter's game-days in chronological order and take weekly snapshots. At each
  snapshot compute the swing-count-weighted mean over swings SO FAR
  (mean_bat_speed_to = sum(n_swings*mean_bat_speed)/sum(n_swings)) and over the
  REST of that same season (mean_bat_speed_rest). Forward reliability
  r(mean_bat_speed_to, mean_bat_speed_rest) is computed within buckets of
  swings-so-far; the empirical cutoff is the interpolated swing count where r
  crosses 0.50 (decision floor) and 0.70 (high confidence). Repeat identically
  for fast_swing_rate (count-additive: fast_n = fast_swing_rate*n_swings) and,
  as a declared secondary, p90_bat_speed (approximated as the swing-weighted
  mean of daily p90 — NOT a true pooled p90; reported as approximate).
  PART 2 (in-season delta vs rh3, production-target study): at each rolling
  snapshot (batter, year, split_day) with calendar cutoff_date C and lag L,
    RECENT  = swings with game_date in (C - L, C]
    EARLIER = swings with game_date in (C - 2L, C - L]
  both windows strictly at-or-before C (leakage-safe by construction), and
    d_bat_speed = mean_bat_speed(RECENT) - mean_bat_speed(EARLIER)
  gated so BOTH windows clear the Part-1 empirical minimum (r>=0.50 crossing,
  ceil to nearest 25 swings). Same construction for d_fast_swing_rate. The
  candidate entering the screen and the integration is the within-(year,
  split_day) z-score of the signed delta, matching validate_delta_grid.py.
outcome: ros_full_fp_per_pa, EVAL_PA_MIN=50, ROS_PA_MIN=100 (production frame)
expected_sign: "+" for both d_bat_speed and d_fast_swing_rate (rising bat speed
  -> higher forward FP/PA)
theory: Bat speed is the only hitter process metric validated to add forward-FP
  signal beyond the season FP level (2026-06-26). If ANY in-season rate DELTA
  carries forward signal beyond season-to-date levels, bat speed is the one —
  it is the sole declared re-open condition of the in-season-delta family
  closed 2026-07-29. Part 1 supplies the measurement gate that makes Part 2
  honest and replaces two hand-picked/borrowed thresholds
  (plv_clone.stabilization.LITERATURE_ONLY bat_speed=30 swings;
  lib/trend_signal HIT_MIN_SW_CUR/BASE = 80/200).
production_target: rh3 (Part 2) | research-only (Part 1, a measurement gate)
framing: in-season measurement (Part 1) | in-season -> ros (Part 2)
holdout_years: [2026]
training_years: [2024, 2025]
validation_script: scripts/xfp/validate_bat_speed_stabilization.py (Part 1),
  scripts/xfp/validate_bat_speed_delta.py (Part 2)
date: 2026-07-29
verdict: "PART 1 RESEARCH-ONLY (measurement gate adopted: bat speed stabilizes
  at <=25-30 swings, registry value 50) | PART 2 REJECTED (0 of 6 declared
  cells survive; best cell integrates +0.0035 vs the +0.005 bar — the
  in-season-delta family's sole re-open condition is now closed)"
---

# Study B2 — bat-speed window stabilization + in-season bat-speed delta

## RULE-5 SAMPLE-HONESTY PRE-CHECK (declared BEFORE any result is seen)

**The declared repo-standard split cannot be used, and the year-consistency
gate CANNOT be cleared.** Statcast bat tracking begins in 2024. The substrate
`bat_speed_daily.parquet` spans **2024-04-03 .. 2026-07-28 — exactly three
season cohorts (2024, 2025, 2026)**, and 2024+2025 are precisely the repo's
standard holdout pair. Consequences, declared up front:

1. `holdout_years` is redeclared as **[2026]** and `training_years` as
   **[2024, 2025]**. This is the only split the data admits. 2026 is a
   PARTIAL season, so its eligible rows (`ros_pa >= 100`) exist only at early
   `split_day`s — the 2026 holdout will be small and is expected to be
   **UNDERPOWERED at the longer lags** (L=63 has no 2026 snapshot at all,
   since the 2026 panel stops at split_day 125).
2. **Year-consistency (>=5/7 cohorts) is unreachable.** Max achievable is
   3 cohorts, of which one is partial. Per the protocol's Step-2.5 pre-check,
   **any PASS from this study is EXPLORATORY, not promotable.** A PASS would
   license a *provisional* research-only lens plus a re-run in 2027 when a
   fourth cohort lands — it may NOT move RH3_FEATS.
3. Part 1 has no such problem: it is a pure measurement study (does not use
   the forward-FP outcome at all), so 3 cohorts of ~650 batters each is ample.
   **Part 1 is the durable deliverable of this study regardless of Part 2.**

## Declared cells (Rule 3 — counted BEFORE any result is seen)

### Part 1 (no hypothesis test — reliability curves; no multiplicity control)

| metric | denominator | curve buckets | floors |
|---|---|---|---|
| mean_bat_speed | swings | 25-swing edges, 25..600 | bucket needs >= 200 DISTINCT player-seasons; rest-of-season floor 100 swings |
| fast_swing_rate | swings | same | same |
| p90_bat_speed (secondary, approximate) | swings | same | same |

Reported: forward r per bucket, interpolated r=0.50 and r=0.70 crossings,
n snapshots and n distinct player-seasons per bucket. Empirical minimum =
r>=0.50 crossing, ceil to nearest 25 swings.

### Part 2 (hypothesis test — 6 cells)

2 metrics x 3 lags. **No cell may be added after results are seen.**

| # | candidate | lag L (days) | non-overlapping snapshots | expected sign |
|---|---|---|---|---|
| 1 | dz_bat_speed | 21 | split_day in {44, 86, 128, 170} | + |
| 2 | dz_bat_speed | 42 | split_day in {86, 170} | + |
| 3 | dz_bat_speed | 63 | split_day in {128} | + |
| 4 | dz_fast_swing | 21 | {44, 86, 128, 170} | + |
| 5 | dz_fast_swing | 42 | {86, 170} | + |
| 6 | dz_fast_swing | 63 | {128} | + |

**Non-overlap rule (the 2026-07-29 methodological upgrade):** each snapshot
consumes a **2L-day** span of swings (EARLIER + RECENT), so snapshots within a
batter-year are spaced **>= 2L days** apart and the first usable snapshot is at
`split_day >= 2L`. This is stricter than the delta-grid's >= L spacing, and is
required here because the EARLIER window is itself a window rather than a
season-to-date cumulative. No batter-year contributes overlapping swing spans
to any single cell.

## Multiplicity control (declared)

1. **Screen** (2024-2025 pooled): partial r of the candidate vs
   `ros_full_fp_per_pa`, controls =
   **[season-to-date bat-speed LEVEL at the snapshot, `prior_fp_per_pa`,
   `pa_to`]** — i.e. the delta must beat the *level* of the very same metric,
   which is the control that killed every cell in the 60-cell grid. p from t on
   the partial r, df = n - q - 2.
2. **Benjamini-Hochberg FDR at q = 0.05 across all 6 declared cells**, PLUS
   the economic floor **|partial r| >= 0.05** and correct sign.
3. **Sample floor:** a cell with fewer than **300** usable rows after the
   Part-1 swing gate is reported **UNDERPOWERED** (Rule 5), not
   tested-and-failed.
4. **Holdout gate:** survivors must show same-sign partial r >= 0.05 on **2026**
   (never touched by the screen). If the 2026 cell is under 150 rows the gate is
   reported as UNDERPOWERED and the candidate cannot advance on it.
5. **Integration gate (Rule 9):** leave-one-year-out RidgeCV over the available
   cohorts, baseline = **ALL 22 `plv_clone.models.xfp.rh3.RH3_FEATS`** attached
   via `attach_production_features` (never a curated subset — Rule 9). Bar
   **>= +0.005 mean cross-year r**. This is the only gate that can promote, and
   per the Rule-5 pre-check above, even clearing it yields EXPLORATORY status
   only (3 cohorts < 5).
6. Part 1's r>=0.50 crossing (ceil 25) is the mandatory min-sample for BOTH
   windows in every Part-2 cell. If Part 1 shows bat speed never stabilizes at
   a sample a lag window can supply, that lag's cells are UNDERPOWERED by
   construction, not failed.

## Provisional-row policy (declared)

`provisional_share > 0` marks gf-bridge same-day estimates (0.9% of store
rows). Declared handling: **keep them** (they are the same measurement mapped
from Savant's per-game feed, and excluding them would bias the most recent
window of the 2026 cohort specifically). A sensitivity re-run of the Part-1
`mean_bat_speed` curve with `provisional_share > 0` days dropped is declared
as a robustness check, not a separate cell.

## Prior art being tested / replaced

- `plv_clone.stabilization.LITERATURE_ONLY['bat_speed'] = (30, SWINGS)` — a
  borrowed Savant-guidance figure, explicitly flagged as not ours. Part 1
  measures it.
- `scripts/xfp/lib/trend_signal.HIT_MIN_SW_CUR, HIT_MIN_SW_BASE = 80, 200` —
  hand-picked "conservative relative to the literature figure". Part 1
  measures it.
- CLAUDE.md gotcha #12 / `window_predictive_validity_2026-06-26.md`: bat speed
  is the ONLY process metric with incremental forward-FP signal (partial
  r +0.076); L7 is trusted for bat speed alone.
- `inseason_delta_grid_2026-07-29.md`: 60 cells, 0 finalists, family CLOSED
  with in-season bat-speed deltas named as the SOLE re-open condition. Part 2
  is that re-open attempt.

## RESULT (2026-07-29, both parts run same day)

Frontmatter untouched since pre-registration except the appended `verdict:`
line, per protocol.

### PART 1 — bat-tracking stabilization (`validate_bat_speed_stabilization.py`)

Substrate: 126,434 batter-days, 869 batters, 860,531 swings, 2024-2026.
1,929 player-seasons (season swings p25=123 / p50=362 / p75=728 / p95=1127).
19,540 weekly snapshots from 1,451 player-seasons clear the 100-swing
rest-of-season floor.

Forward reliability on the declared 25-swing grid — **the curve is already far
above BOTH thresholds in the first measurable bucket**:

| swings-to-date | n snapshots | n player-seasons | mean_bat_speed | fast_swing_rate | p90 (approx) |
|---|---|---|---|---|---|
| 37 | 1,405 | 1,170 | **+0.841** | +0.884 | +0.900 |
| 87 | 1,097 | 952 | +0.905 | +0.918 | +0.933 |
| 162 | 843 | 762 | +0.926 | +0.938 | +0.946 |
| 287 | 668 | 615 | +0.939 | +0.947 | +0.956 |
| 437 | 476 | 445 | +0.945 | +0.948 | +0.957 |
| 612 | 317 | 309 | +0.950 | +0.950 | +0.959 |

Because bucket 1 is already r≈0.84, a POST-HOC 5-swing grid was run purely to
locate the crossing (labelled post-hoc in the script; it can change no verdict,
since the answer is "at or below the declared grid's floor" either way):

| swings-to-date | n player-seasons | mean_bat_speed | fast_swing_rate | p90 (approx) |
|---|---|---|---|---|
| **27** | 229 | **+0.736** | **+0.766** | +0.816 |
| 32 | 264 | +0.849 | +0.900 | +0.908 |
| 42 | 319 | +0.864 | +0.912 | +0.912 |
| 52 | 242 | +0.879 | +0.902 | +0.909 |

**Crossings: r>=0.50 AND r>=0.70 are both cleared at or below 25-30 swings,
for all three metrics.** No bucket anywhere in the curve falls below 0.70. The
mechanical registry value (r>=0.50 crossing, ceil to nearest 25) is therefore
**50 swings**, which is conservative — the measured crossing is <=25 and could
not be resolved lower only because fewer than 200 player-seasons exist below
25 swings under a weekly snapshot stride.

Declared robustness check (`--drop-provisional`, 298 batter-days = 0.24%):
curve identical to 3 decimals. Provisional gf-bridge rows are harmless.

**Grades the prior art:**

- `plv_clone.stabilization.LITERATURE_ONLY['bat_speed'] = (30, SWINGS)` —
  **CONFIRMED on our data.** 30 swings sits right at the measured r≈0.74-0.85
  region, comfortably above the 0.50 decision floor and above the 0.70
  high-confidence bar. This is now a MEASURED number, not a borrowed one.
- `lib/trend_signal.HIT_MIN_SW_CUR / HIT_MIN_SW_BASE = 80 / 200` —
  ~~**3x and 7x over-conservative.**~~ **RETRACTED — see CORRECTION 4 below.**
  Those gates guard a YEAR-OVER-YEAR DELTA; this curve measures a LEVEL. The
  multiplier compares against the wrong reference quantity and must not be acted
  on. Directionally there is probably headroom (r=+0.736 already at 27 swings),
  but the number is not derivable from this study.
- **Bat speed is the most reliable in-window hitter metric we have measured,
  by a wide margin.** Compare the 2026-07-29 hitter table: chase/whiff/swstr
  need 150 denominator units to hit 0.50; BB% needs 175 PA and never reaches
  0.70; ISO/HR-rate need ~275 and never reach 0.70. Bat speed clears 0.70 in
  under 30 swings — roughly **one week of playing time**. This is the
  measurement math behind CLAUDE.md #12's "trust L7 only for bat speed".

Interpretation caveat (recorded so it is not over-read): this is *forward
reliability of the LEVEL*. It says a short bat-speed window tells you the rest
of the season's bat speed. It says nothing about whether bat speed predicts
FANTASY POINTS — that is Part 2, and the answer there is different. What Part 1
does buy Part 2 is that a bat-speed DELTA at a 21-day window is genuinely
MEASURABLE (low noise floor), so Part 2 is a fair test of the signal rather
than a test of construction noise. That distinction is exactly what killed
d_bb_pct in the 60-cell grid, and it does NOT apply here.

### PART 2 — in-season bat-speed delta vs rh3 (`validate_bat_speed_delta.py`)

Production frame (all 22 RH3_FEATS attached, `pa_to>=50`, `ros_pa>=100`),
bat-tracking years only: 12,592 rows — 2024: 5,271 | 2025: 5,134 | 2026: 2,187.
Non-overlapping delta frames after the 50-swing gate on BOTH windows:

| lag | splits | rows | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| 21d | 44, 86, 128, 170 | 2,193 | 897 | 873 | 423 |
| 42d | 86, 170 | 798 | 320 | 318 | 160 |
| 63d | 128 | 519 | 265 | 254 | **0** |

**Stage 1 — screen on 2024-2025, controls = [season-to-date bat-speed LEVEL,
prior_fp_per_pa, pa_to], BH-FDR q=0.05 across all 6 declared cells:**

| cell | n | partial r | p | BH crit | outcome |
|---|---|---|---|---|---|
| bat_speed lag63 | 466 | **+0.1126** | 0.0154 | 0.0083 | **FAILS FDR** (rank 1) |
| fast_swing lag63 | 466 | +0.0633 | 0.174 | 0.0167 | fails |
| bat_speed lag42 | 551 | +0.0273 | 0.523 | 0.025 | fails (below 0.05 floor) |
| fast_swing lag42 | 551 | −0.0190 | 0.657 | 0.033 | fails (wrong sign) |
| bat_speed lag21 | 1,380 | +0.0099 | 0.713 | 0.042 | fails (below 0.05 floor) |
| fast_swing lag21 | 1,380 | +0.0091 | 0.736 | 0.050 | fails (below 0.05 floor) |

**0 of 6 cells survive.** 6/6 were testable — no cell was UNDERPOWERED at the
screen, so this is a genuine tested-and-failed result, not a sample excuse.

The near-miss deserves to be named: **bat_speed lag63 = +0.1126** is the
largest partial r any in-season delta has produced in this program (bigger than
hard_hit lag42's +0.081, which was the sole 60-cell survivor). It fails BH-FDR
only because p=0.0154 > 0.0083 at rank 1 of 6. Three things make it
unpromotable regardless:

1. It is **structurally untestable out-of-sample**: lag63 has exactly one
   snapshot (split 128) and the 2026 panel stops at split 125, so the lag63
   cell has **zero 2026 rows**. There is no holdout for it, at all.
2. It is a single split-day, so it also cannot be checked for Rule-8 framing
   stability across the season.
3. The diagnostic integration below shows it does not clear the bar anyway.

**Stage 2 — 2026 holdout:** not reached (0 survivors).

**Stage 3 — Rule 9 integration:** 0 finalists. Family stays closed.

**Stage 3b — DIAGNOSTIC Rule 9, post-hoc, cannot promote.** Run on every
testable cell so that no cell can later be re-litigated as "never actually
integration-tested". Baseline = ALL 22 RH3_FEATS, leave-one-cohort-out RidgeCV:

| cell | n | base r | +cand r | Δr | vs +0.005 bar |
|---|---|---|---|---|---|
| bat_speed lag21 | 1,758 | +0.5713 | +0.5698 | **−0.0015** | fails |
| fast_swing lag21 | 1,758 | +0.5713 | +0.5715 | +0.0002 | fails |
| bat_speed lag42 | 701 | +0.5387 | +0.5405 | +0.0019 | fails |
| fast_swing lag42 | 701 | +0.5387 | +0.5383 | −0.0004 | fails |
| **bat_speed lag63** | 466 | +0.6934 | +0.6970 | **+0.0035** | **fails** |
| fast_swing lag63 | 466 | +0.6934 | +0.6943 | +0.0008 | fails |

Even the most generous post-hoc read — the near-miss cell, no multiplicity
correction, no holdout requirement — lands at **+0.0035, below the +0.005
bar**. The in-season bat-speed delta does not integrate.

Descriptive delta distributions (gated rows): d_bat_speed sd = 1.25 mph (21d),
1.10 (42d), 1.00 (63d); mean +0.13 / +0.25 / +0.20 mph (the small positive mean
is the known within-season warm-up drift, not signal).

### VERDICTS

- **PART 1 — RESEARCH-ONLY / measurement gate ADOPTED.** Bat speed, fast-swing
  rate, and p90 bat speed all clear r>=0.70 within **25-30 swings**; registry
  value **50 swings** (mechanical ceil-25 of the crossing, conservative).
  The 30-swing literature figure is CONFIRMED as ours;
  `lib/trend_signal`'s 80/200 is over-conservative by 3-7x.
- **PART 2 — REJECTED.** The sole declared re-open condition of the
  in-season-delta family has been tested with the substrate it was waiting for.
  **0 of 6 declared cells survive; the best cell integrates at +0.0035 against
  a +0.005 bar even with every gate removed. The family stays CLOSED.**

### What this means, stated plainly

Bat speed is simultaneously the **most measurable** hitter process metric we
have (Part 1) and, *as an in-season change*, **still not predictive of forward
fantasy points** (Part 2). Those are not in tension: bat speed's forward-FP
value — the validated +0.076 partial r from 2026-06-26 — lives in the **LEVEL**
(and in the year-over-year step), not in the within-season drift. A hitter
whose bat speed moved +1.5 mph since June has a real, well-measured 1.5 mph;
that movement carries no additional information about his rest-of-season FP/PA
beyond where his bat speed now sits.

**Consequence for every consumer:** in-season bat-speed trajectory is a
**DESCRIPTIVE / awareness column only (Rule 13)**. It may be displayed. It may
NOT move a projection, a rank, or an add/drop verdict. The load-bearing
bat-speed reads remain (a) the LEVEL and its percentile, and (b) the
year-over-year step.

### Two defects found in EXISTING code while building this study

Both are in the shipped `scripts/xfp/validate_delta_grid.py` / its memo
`inseason_delta_grid_2026-07-29.md`. **Neither changes that study's REJECTED
verdict** — both bias toward false POSITIVES, and it found none — but both
should be fixed before that harness is reused, and the memo's method claim is
currently overstated.

**1. The "non-overlapping windows" claim is only half true there.** In
`build_frames()`, `RECENT` is a true window but `EARLIER` is the CUMULATIVE
season-to-date count at `split_day - L`. So for lag 21 the snapshots at split 79
and 100 have non-overlapping RECENT windows but EARLIER windows of `[0,58]` and
`[0,79]` — sharing ~73% of their sample. Consecutive snapshots of the same
batter-year are therefore still strongly autocorrelated through the EARLIER
leg, and effective n remains inflated relative to the nominal n (the exact
error the memo says the >= L spacing killed). The `>= L` spacing is sufficient
only when BOTH legs are windows. This study's Part 2 uses windowed-EARLIER plus
**>= 2L** spacing, which is the correct construction; recommend adopting it in
`validate_delta_grid.py` if that grid is ever re-run.

**2. Two declared lag-63 / lag-84 snapshots were silently dropped by the inner
join.** `build_frames()` shifts `split_day` by `+L` and inner-joins, so a
snapshot at `S` requires `split_day == S - L` to EXIST in the panel. The panel's
minimum `split_day` is 30, so:

| declared cell | needs split_day | present? |
|---|---|---|
| lag 63 @ split 79 | 16 | **absent — snapshot dropped** |
| lag 84 @ split 79 | −5 | **absent — snapshot dropped** |

The memo declares `63: 79,142` and `84: 79,163`, but lag63 actually ran on
split **142 only** and lag84 on **163 only** — half the declared anchors, with
no warning emitted. This is the mechanical reason lag84 came out at n=75 and was
reported UNDERPOWERED. Recommended fix: assert that every
`NONOVERLAP[L]` entry has `S - L` in `rolling['split_day'].unique()`, and fail
loudly rather than silently shrinking a pre-registered design.

### Follow-ups (declared, not run here)

1. **No re-open condition is left for the in-season-delta family.** It was
   bat speed; bat speed has now been tested. Closing it for good.
2. Re-run Part 2 in 2027 when a **fourth cohort** exists (Rule-5: this run had
   3, one partial — a PASS would have been exploratory anyway). Low priority
   given a −0.0015 to +0.0035 Δr range.
3. Untested and worth its own pre-registration: **year-over-year** bat-speed
   step as an rh3 feature. That is a DIFFERENT framing (full-year, not
   in-season) and this study says nothing about it.
4. `plv_clone/stabilization.py` should move `bat_speed` / `swing_length` out of
   `LITERATURE_ONLY` into `HITTER_MINS` at (50, SWINGS) with this memo cited,
   and `lib/trend_signal.HIT_MIN_SW_*` should be reconsidered against 50.
   **Not done in this run** — no production edits were in scope.

## APPENDIX — the Cam Smith / Bleday / Bichette read (real numbers)

Asked alongside this study: Cam Smith (701358, HOU) was called "the best
longterm process play in the FA pool" on **+2.5 to +3.1 mph bat speed YoY and a
98th-percentile level**. What does his IN-SEASON 2026 trajectory say?

**Framing gate first (this is Part 2's whole point):** in-season bat-speed
trajectory is **DESCRIPTIVE ONLY**. Part 2 just tested it directly and it adds
−0.0015 to +0.0035 Δr against rh3. It must NOT move any verdict in either
direction. The numbers below are context, not evidence. What IS load-bearing is
the **level** and the **YoY step** — and Part 1 says both are measured to
r≈0.95 reliability, so they are trustworthy.

2026 league pool for percentiles: 462 batters with >=100 swings, mean 69.93 mph,
sd 2.71.

| | 2024 | 2025 | 2026 | YoY step | 2026 pctile |
|---|---|---|---|---|---|
| **Cam Smith** | no data | 72.35 (977 sw) | **75.45** (753 sw) | **+3.10 mph** | **98th** |
| **JJ Bleday** | 69.63 (1067) | 69.83 (573) | **71.99** (585) | **+2.16 mph** | 77th |
| **Bo Bichette** | 68.56 (579) | 67.07 (1152) | **68.25** (861) | +1.18 mph | 25th |

**The claim about Cam Smith checks out exactly.** +3.10 mph YoY, 75.45 mph =
z +2.04 = 98th percentile. Both figures are confirmed against the store.

2026 non-overlapping 21-day windows (all clear the 50-swing gate):

| window | Cam Smith | JJ Bleday | Bo Bichette |
|---|---|---|---|
| 03-25..04-14 | 76.16 (145 sw) | — | 66.53 (161) |
| 04-15..05-05 | 74.53 (132) | 72.44 (52) | 68.98 (123) |
| 05-06..05-26 | 74.38 (106) | 72.30 (149) | 68.82 (157) |
| 05-27..06-16 | 74.85 (138) | 71.72 (140) | 68.22 (155) |
| 06-17..07-07 | 76.51 (135) | 71.60 (120) | 68.79 (155) |
| 07-08..07-28 | 76.17 (97) | 72.11 (124) | 68.40 (110) |
| **first -> last** | **+0.01 mph** | **−0.33 mph** | **+1.87 mph** |

Study-shaped deltas as of 2026-07-28 (RECENT vs EARLIER, both >=50 swings):

| | d 21d | pctile | d 42d | pctile | d fast% 42d |
|---|---|---|---|---|---|
| Cam Smith | −0.34 | 43rd | **+1.72** | 91st | **+14.0pp** |
| JJ Bleday | +0.51 | 70th | −0.16 | 42nd | −13.5pp |
| Bo Bichette | −0.38 | 42nd | +0.11 | 53rd | +0.6pp |

### Answers

**Cam Smith — SUPPORTS the verdict, and for a better reason than trajectory.**
His in-season trajectory is essentially **FLAT (+0.01 mph first window to
last)**, with a mild May dip (74.4) and a June-July peak (76.5). The right way
to read that is: **the +3.1 mph YoY step is not an April mirage — it has held
across every 21-day window of the season, none below 74.4 mph.** A flat line at
a 98th-percentile level is the most supportive shape available; a rising line
would add nothing (non-predictive) and a decaying line would have been the one
thing that undercut the story. Month-by-month agrees (Mar 74.75 → Jul 76.32),
and his 42d delta is +1.72 mph (91st pctile) with fast-swing rate +14.0pp.
Nothing here undercuts "best longterm process play." **One caution that is NOT
about bat speed:** his rh3 read is **rank 288/473, 0.4411 FP/PA,
replacement_delta −0.0729, signal=hold** on 392 PA. So the process case and the
current production case genuinely diverge — that is a real conflict to state
out loud per the lens-merge protocol (gotcha #12), and the honest framing is
"elite, well-measured, stable process input; the FP output has not arrived
yet," not "the model is wrong."

**JJ Bleday — mildly UNDERCUT, but only on the secondary metric.** Level is
fine: +2.16 mph YoY holding at 71.99 (77th pctile), and his 21-day windows are
flat-to-slightly-down (72.44 → 72.11, trough 71.60). What is genuinely moving
is **fast-swing rate: 44.2% → 21.7% → 26.6% across the season, −13.5pp on the
42d delta.** Part 1 says that decay is REAL as measurement (fast_swing_rate
forward r +0.77 at 27 swings — it is not noise). Part 2 says it is NOT
predictive of his forward FP. So: note it, do not trade on it. rh3 has him at
**rank 92/473, +0.0246 replacement_delta, hold** — mildly above replacement,
which is the operative number.

**Bo Bichette — trajectory looks like the best of the three and means the
least.** He has the largest first→last window gain (**+1.87 mph**), but that is
almost entirely a **slow start washing out**: 66.53 in the opening window,
then flat at 68.2-69.0 for four straight windows. Every window after mid-April
is within 0.8 mph. And the level is the point: **68.25 mph = 25th percentile**,
below the 2026 mean, and only a partial recovery of his 2024 mark (68.56) after
a 2025 dip (67.07). Bat speed is simply not where his value comes from — he is a
contact/BABIP profile, and rh3 has him **rank 81/473, hold, 459 PA**, which is
the read to use. Do not let the +1.87 mph "riser" shape imply a tier change; per
Part 2 it carries no forward information, and per the level it is below average.

**One-line summary for the boards:** Smith's bat speed is elite AND stable
(support the process case, flag the FP gap); Bleday's level holds while his
fast-swing rate softens (note only); Bichette's apparent in-season climb is a
slow-April artifact on a below-average level (ignore).



---

## CORRECTIONS (from independent adversarial review, 2026-07-29)

The reviewer re-ran this study and reproduced Part 1 bit-for-bit (including all
substrate counts) and Part 2's headline to full float precision. **Both verdicts
stand: Part 1 MEASURED, Part 2 REJECTED.** Four corrections to the surrounding
claims, all accepted:

**1. DECLARED vs REALIZED anchors — this study committed the same defect it
flagged in `validate_delta_grid.py`.** Declared snapshot anchors silently shrank
because the `ros_pa >= 100` filter has no rows past split_day 156:

| lag | declared anchors | REALIZED anchors |
|---|---|---|
| 21 | 4 (incl. 170) | **3** — {44, 86, 128} |
| 42 | 2 (incl. 170) | **1** — {86} |
| 63 | 2 | **1** |

Bias direction is toward LESS power, i.e. against a PASS, so the REJECTED
verdict is unaffected. The assert this study recommended adding to
`validate_delta_grid.py` (every declared anchor must exist AND yield non-zero
rows) should be added here too.

**2. lag42 is ALSO a single-anchor cell.** The memo body treated the missing
Rule-8 framing-stability check as unique to lag63. It applies to lag42 as well.

**3. lag63's power framing was a touch strong.** At n=466 the FDR rank-1 minimum
detectable partial r is ~0.123; the cell measured +0.1126. The correct statement
is: *it failed an FDR threshold it was marginally underpowered for, and then
failed the decisive Rule-9 integration test outright* (+0.0035 vs +0.005;
reviewer's independent OLS re-run +0.0045, still short). Not "no sample excuse."

**4. The `trend_signal` 80/200 recommendation is RETRACTED** (struck above).
Those gates guard `d_bat_speed = cur - base`, a YoY delta whose noise is ~√2× a
level's; Part 1 measured the forward reliability of the LEVEL. **Do not relax
80/200 on this evidence**, and do not re-run `/trending` cells blanked at 30-79
swings until a delta-appropriate gate is derived.

**Non-overlap scope (clarification, not a defect).** The ≥2L spacing guarantee
covers the SWING legs. lag21's 1,380 rows come from 634 batter-years (2.18x), so
their rest-of-season OUTCOME windows overlap and lag21 p-values are
anti-conservative by roughly that factor. Measured as immaterial via
one-snapshot-per-batter-year resampling: +0.0094 ± 0.0213. lag42/lag63 are 1.00
rows per batter-year — clean.

**Rule 5 constraint, disclosed and forced.** Bat tracking starts 2024, so
TRAIN=[2024,2025] / HOLDOUT=[2026] and the ≥5-cohort year-consistency gate is
**UNREACHABLE** (3 cohorts, one partial). Any PASS here would have been
exploratory by construction. Moot — nothing passed. Side effect to record: the
repo's canonical 2024-25 holdout is now consumed for any future
bat-speed-substrate study.

**Downstream actions taken from this memo (2026-07-29):**
- `plv_clone.stabilization`: `bat_speed` promoted from `LITERATURE_ONLY` to
  `HITTER_MINS` at **(50, SWINGS)**; the old literature 30 was confirmed by this
  measurement before retirement. `swing_length` stays literature-only (gf bridge
  does not carry it).
- `docs/stabilization_minimums.md`: full curve + the read-the-level-not-the-
  trajectory rule + the explicit trend_signal non-license.
- `CLAUDE.md` #12 and `inseason_delta_grid_2026-07-29.md`: the family's re-open
  condition struck — **no named re-open condition remains.**
