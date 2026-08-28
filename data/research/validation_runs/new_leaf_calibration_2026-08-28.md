# Pre-registration — sp-new-leaf verdict calibration (2026-08-28)

**Status: REGISTERED — written before any outcome was computed.**

## Question

The `/sp-new-leaf` protocol (built 2026-08-28) claims a hierarchy: a results
break backed by a **stabilized mechanism** (velo / whiff / SwStr / K% level
shift beyond delta-noise, or a discrete mix/role choice) should HOLD going
forward more than an equal-size results break without one. The regime-break
family's six failures all tested results-level signals; none conditioned on a
stabilized mechanism. This study measures whether Gate 3 actually separates.

## Hypothesis (one directional test)

Among GIVEN-event mid-season splits that clear the split-check noise floor
(z > 1.83), the mean forward **hold fraction** of mechanism-backed splits
exceeds that of results-only splits. Judged at **z > 1.83** (given design,
one primary test). Secondary cells (by event type, by mechanism type,
positive vs negative leafs) are descriptive and BH-FDR corrected.

- hold fraction = (forward_level − pre_level) / (post1_level − pre_level),
  winsorized to [−1, 2]; primary level metric **FP/start**, secondary K-BB%.

## Design (leakage rules are the study)

- Panel: pitcher-seasons 2018–2026, ≥12 GS, with a GIVEN split event:
  IL return, option/recall (`sp_option_events_2017_2026.csv`), trade, or the
  season's ASG break. One row per (pitcher-season, event).
- Admissibility per side: ≥100 TBF and ≥3 GS (the v4 bars).
- **Three disjoint windows, chronological:** PRE (before event) → POST1
  (first starts after the event, used ONLY for classification, minimum
  samples per the stabilization cutoffs) → FORWARD (the next up-to-8 starts
  strictly after POST1, used ONLY for outcomes). No overlap anywhere; a
  season without a non-empty FORWARD window drops with a count reported.
- Mechanism (classified on POST1 vs PRE only): |Δvelo| ≥ 0.7 mph, or
  |Δwhiff| ≥ 4pp, or |ΔSwStr| ≥ 2.5pp, or |ΔK%| ≥ 4pp, or a pitch-mix share
  shift ≥ 5pp / new pitch ≥ 10% usage — each only if POST1 meets that
  metric's cutoff (velo 150 pitches / whiff 150 swings / SwStr 175 / K% 100
  TBF). BB%, chase-against, HR-against are inadmissible.
- Substrate: prefer the local rolling/gamelog panels
  (`rolling_pitchers_2018_2026.csv`, the sp gamelog panel) for levels and the
  FanGraphs as-of caches for mix; fetch nothing beyond MLB Stats API game
  logs if a gap forces it. Report which substrate served each column.

## Honesty requirements

- One-row-per-player-season table beside every pooled number.
- Permutation nulls (if used): assert 1/(B+1) < q/M before believing them.
- Report n per cell; cells with n < 15 are labeled anecdote, not evidence.
- If mechanism-backed and results-only splits do NOT separate, that is the
  finding: Gate 3 is measurement hygiene but not a forward predictor, and the
  skill's claims get downgraded accordingly. Mean reversion winning again is
  an acceptable, reportable outcome — it would be the seventh.

## Pre-committed consequences

- Separation at the bar → the verdict table in `/sp-new-leaf` gains the
  measured hold-rates per verdict; thresholds may be tuned ONCE on the
  reported grid (no re-search).
- No separation → the skill keeps Gates 0–2 (screen + sample honesty) and
  demotes Gates 3–4 from "predictive" to "descriptive" wording.
- Under NO outcome does anything here touch rp3/rprs2 (Rule 13). Any future
  wish to move a rank routes through `/validate-feature` against full
  RP3_FEATS (Rule 9).

## Results

**Appended 2026-08-28 after the run. Registered sections above are untouched.**

### Verdict: DOES NOT SEPARATE

Mechanism-backed splits do NOT hold forward more than results-only splits.
Primary one-sided Welch t (= z) = **−0.18** (p = 0.57; label permutation
p = 0.580, B = 200,000, floor 5.0e-6 < α 0.0336 asserted) vs the bar z > 1.83.
The point estimate is on the WRONG side:

| arm | mean hold_fp | SD | n (pitcher-seasons) | n (rows) |
|---|---|---|---|---|
| mechanism-backed | **+0.445** | 0.781 | 206 | 218 |
| results-only | **+0.495** | 0.837 | 9 | 9 |

(1 season contributed to both arms; per-(pitcher-season, arm) collapse before
the test. Difference −0.051, SE 0.284.)

**The structural finding underneath the null:** the registered Gate-3
thresholds are nearly vacuous as a discriminator. 96.0% of clearing splits are
"mechanism-backed" — and so are **90.2% of NON-clearing splits** (91.2% of all
1,243 admissible events). The mechanism base rate is ~91% regardless of
whether the results broke at all. Two thresholds do most of the vacating:

- **mix ≥ 5pp**: fires on 73% of ALL admissible splits — the median max
  pitch-share shift between two ordinary same-season windows is **7.0pp**
  (p25 = 4.8pp), so the registered threshold sits *below the median of
  ordinary between-window variation* (opponent-mix noise, not a discrete
  choice). Fires on 164/227 clearing rows.
- **|ΔK%| ≥ 4pp**: fires on 159/227 clearing rows and is correlated with the
  K-BB% screen by construction.
- The stuff-metric criteria are rarer (velo 60, whiff 98, SwStr 86 of 227)
  but almost never occur *alone*: only 9 of 227 clearing rows had NO
  qualifying mechanism.

So the results-only arm came out n = 9 — below this study's own n ≥ 15
evidence bar. The primary is an honest null with an unpowered contrast: the
registered thresholds could not populate the comparison the hypothesis needed,
and what contrast exists points the wrong way. This is NOT a coverage
limitation (see provenance below) — it is a property of the thresholds.

Mean reversion won again, the seventh: pooled mean hold fraction of a
noise-floor-clearing break is **+0.46** (FP/start) / **+0.44** (K-BB%) — on
average ~54% of an apparent break evaporates over the next ≤8 starts, and
having a "mechanism" under the registered spec does not change that number.

### Panel construction (counts, per the leakage rules)

- Eligible pitcher-seasons (≥12 GS, 2018–2026): **1,175** (439 pitchers).
  2020 is absent from the event panel entirely (no rows); 2017 excluded by
  design.
- GIVEN events found: ASG 968, IL_RETURN 472, OPTION 153, TRADE 121 →
  **1,698 deduped** (16 duplicate-date events removed, priority
  OPTION > IL_RETURN > TRADE > ASG).
- Admissible (PRE ≥100 TBF + ≥3 GS; POST1 = minimal prefix reaching 100 TBF +
  3 GS; FORWARD ≥1 start): **1,243** rows. Dropped 455 events:
  pre_inadmissible 136 (ASG 18 / IL 57 / OPTION 54 / TRADE 7),
  post1_inadmissible 243 (ASG 55 / IL 126 / OPTION 31 / TRADE 31),
  no_forward 76 (ASG 25 / IL 35 / OPTION 7 / TRADE 9).
  **144 pitcher-seasons had ≥1 event but 0 admissible events.**
- Clearing the split-check noise floor (z > 1.83; Gate-1 OR of K-BB% binomial
  z via `lib/split_floor` and FP/start Welch z): **227 of 1,243** (18.3%) —
  101 cleared on K-BB%, 156 on FP/start. 0 clearing rows had an undefined
  hold_fp. By event: ASG 160, IL_RETURN 39, TRADE 15, OPTION 13.
- Windows: POST1 mean 4.8 GS / 433 pitches; FORWARD mean 5.7 GS (median 7).
  POST1/FORWARD boundary never splits a calendar date.

### Secondary cells (BH-FDR q = 0.10, one-sided mech > results-only)

**None passes.** Every cell is anecdote-labeled — the results-only arm is
n = 9 overall and thinner in every stratum, so no cell has n ≥ 15 per arm.

| cell | n_mech | n_res | mean_mech | mean_res | t | p | BH | note |
|---|---|---|---|---|---|---|---|---|
| hold_kbb overall | 206 | 9 | +0.422 | +0.749 | −0.89 | 0.80 | . | anecdote |
| event=ASG | 152 | 8 | +0.459 | +0.376 | 0.29 | 0.39 | . | anecdote |
| event=IL_RETURN | 37 | 1 | +0.546 | +1.453 | — | — | . | anecdote |
| event=TRADE | 15 | 0 | +0.229 | — | — | — | . | anecdote |
| event=OPTION | 12 | 0 | +0.511 | — | — | — | . | anecdote |
| mech=velo | 56 | 9 | +0.473 | +0.495 | −0.08 | 0.53 | . | anecdote |
| mech=whiff | 93 | 9 | +0.505 | +0.495 | 0.03 | 0.49 | . | anecdote |
| mech=swstr | 82 | 9 | +0.508 | +0.495 | 0.04 | 0.48 | . | anecdote |
| mech=kpct | 152 | 9 | +0.512 | +0.495 | 0.06 | 0.48 | . | anecdote |
| mech=mix | 156 | 9 | +0.446 | +0.495 | −0.17 | 0.57 | . | anecdote |
| leaf=POS | 118 | 3 | +0.331 | −0.008 | 1.14 | 0.18 | . | anecdote |
| leaf=NEG | 89 | 6 | +0.595 | +0.747 | −0.41 | 0.65 | . | anecdote |

(leaf=POS is the only cell tilting the hypothesized way — mech +0.33 vs
res −0.01 — on a 3-season results-only arm. Anecdote, recorded, not evidence.)

### Per-player-season table

One row per (pitcher-season, event) for all 1,243 admissible events —
including every level, window size, z, mechanism delta/flag, and hold
fraction — is the panel deliverable:
`data/research/xfp_cache/sp_new_leaf_panel_2018_2026.csv` (the 227 rows
entering the arms are `clears == True`; the analysis script also prints the
screened table). The 9-row results-only arm in full (hold_fp winsorized):

| pitcher | year | event | pre FP | post1 FP | fwd FP | hold_fp | z_fp | Δvelo | Δwhiff | ΔSwStr | ΔK% | mix max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 554430 | 2026 | ASG | 19.06 | 8.87 | −12.80 | +2.00 | 2.63 | −0.41 | +1.7pp | +0.6pp | −0.2pp | 3.7pp |
| 570632 | 2022 | ASG | 13.20 | 1.86 | 5.76 | +0.66 | 2.54 | +0.32 | −2.5pp | −2.3pp | +2.7pp | 3.1pp |
| 592791 | 2021 | ASG | 9.34 | 17.62 | 7.34 | −0.24 | 3.26 | −0.06 | −0.0pp | +0.2pp | −2.7pp | 2.9pp |
| 592791 | 2023 | ASG | 6.57 | 13.96 | 10.75 | +0.57 | 2.03 | −0.50 | −0.9pp | +0.6pp | +1.6pp | 4.3pp |
| 596295 | 2023 | ASG | 5.11 | 12.80 | 2.43 | −0.35 | 2.50 | −0.49 | −3.9pp | −0.7pp | −0.7pp | 4.1pp |
| 657006 | 2024 | ASG | 16.35 | 7.38 | 12.83 | +0.39 | 1.91 | −0.58 | −2.7pp | −2.3pp | −0.5pp | 3.7pp |
| 657746 | 2023 | ASG | 15.45 | 6.44 | 10.53 | +0.55 | 1.88 | −0.51 | +3.3pp | +0.3pp | +2.1pp | 4.3pp |
| 666201 | 2022 | ASG | 16.91 | 10.28 | 20.65 | −0.56 | 2.35 | −0.01 | −0.9pp | −0.4pp | −0.1pp | 3.3pp |
| 673540 | 2025 | IL_RETURN | 15.85 | 6.80 | 2.70 | +1.45 | 3.21 | −0.58 | −1.9pp | −2.1pp | −3.2pp | 4.5pp |

### Coverage / provenance (per column)

| column | substrate | coverage |
|---|---|---|
| FP/start, K, BB, TBF, GS (all 3 windows) | `sp_event_panel_2017_2026.csv` (MLB Stats API game logs, the v4 panel) | 100% |
| velo (FF/SI mean, `trend_signal` convention), whiff, SwStr, pitch mix | `statcast_{2018..2026}.parquet` pitch-level, `build_rolling_pitchers.py` SWING_DESC/SWSTR_DESC verbatim | **100.0% of POST1 window games** (mean 1.000, min 1.000); all 5 mechanism metrics classifiable on 227/227 clearing rows |
| OPTION events | `sp_option_events_2017_2026.csv` (transactions endpoint, cached) | as cached |
| IL_RETURN events | `il_transactions_2015_2026.parquet` (transactions endpoint, league-wide cache) — PLACE inside a ≥14d appearance gap | 2015-02 → 2026-08 |
| TRADE events | mid-season `team_id` change in the panel (v4 `classify()` convention) | 100% |
| ASG events | league-wide break derived from panel game dates (resume dates 2018-07-19 … 2026-07-16), only when the pitcher's own gap < 14d | 100% |

**Zero network calls were needed** — every column was served locally, so the
option transactions JSON cache was not extended and there is NO
mixed-coverage caveat: the mechanism classification ran on the full panel,
nothing was silently shrunk.

Implementation decisions fixed before outcomes were computed (recorded for
audit): screen = Gate-1 OR (K-BB% binomial z per `lib/split_floor`, FP/start
Welch z), both at the registered 1.83; POST1 = minimal post-event prefix
reaching 100 TBF + 3 GS, extended so it never splits a calendar date; velo
gated on POST1 total pitches ≥ 150 per `stabilization.SP_MINS`; new pitch =
PRE share < 2% and POST1 ≥ 10%; ASG events suppressed when the pitcher's own
cross-break gap was ≥14d (so IL/option absences spanning the break are not
mislabeled ASG); one-sided Welch on per-(pitcher-season, arm) means.

### Pre-committed consequence that applies

**"No separation → the skill keeps Gates 0–2 (screen + sample honesty) and
demotes Gates 3–4 from 'predictive' to 'descriptive' wording."** The
threshold-tuning clause does NOT trigger (it was conditional on separation).
Follow-up (wording only, not done in this run): update
`.claude/skills/sp-new-leaf/SKILL.md` — Gate 3/4 language becomes
descriptive attribution ("what changed"), not a forward-holding claim; the
calibration-status note should cite this result: hold fractions do not
differ by mechanism-backing (mech +0.445 vs results-only +0.495, z = −0.18,
n = 206/9), pooled hold ≈ +0.46, and the registered mechanism thresholds
fire on ~91% of ALL admissible splits (mix ≥5pp alone fires on 73%; the
median ordinary between-window mix shift is 7.0pp). Rule 13 stands: nothing
here touches rp3/rprs2.

Analysis script: `scripts/_oneoff/new_leaf_calibration.py` (re-runnable;
statcast per-game aggregates cached under `--cache-dir`, default tempdir;
seed 20260828).
