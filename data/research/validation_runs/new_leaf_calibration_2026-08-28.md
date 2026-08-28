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

_(to be appended by the calibration run)_
