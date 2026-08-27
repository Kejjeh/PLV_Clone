---
signal: stuff_regime_delta
formula: k_pct_window - k_pct_to, where k_pct_window = K/TBF over the most recent starts expanding backward until TBF >= 100 (SP K% stabilization minimum, capped at 8 starts; undefined and row-dropped if TBF < 100), and k_pct_to = K/TBF over all starts season-to-date through the same split point
outcome: ros_fp_per_start = mean BrownU SP FP (K + IP*3.3 - H - 2*ER - BB - HBP) over all remaining starts after the split point; requires >= 5 remaining starts
expected_sign: +
theory: when a stabilization-adequate recent window's K rate diverges from the season-to-date level, the window reflects current true talent better than the cumulative level, so the divergence should predict rest-of-season FP beyond the level alone.
production_target: research-only
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2017, 2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_stuff_regime_delta.py
date: 2026-08-26
verdict: REJECTED
---

# stuff_regime_delta — pre-registration

## Motivation

2026-08-26 session: `rp3` rated Jacob Lopez at 9.59 FP/start off a season-to-date
K% of 15.6%, while his most recent 5 starts carried a 31.6% K% over 117 TBF —
above this repo's own published SP K% stabilization minimum of 100 TBF. The
repo's gated stuff windows (`sp_rp_stuff_windows`, `window_full: True`) showed
whiff 25.3% on 150 swings and SwStr 13.1% on 175 pitches against a season SwStr
of 8.5%.

The hypothesis is that rp3, being anchored on season-to-date levels, has no
mechanism to re-anchor when a pitcher's underlying rate genuinely changes
mid-season at a stabilization-adequate sample. This is the same failure family
as the documented `marcel_il` suppression and the Griffin Jax RP→SP role lag.

## What this is NOT

This is explicitly NOT a recency slope / EWMA / trajectory feature. Those were
validated dead for SP projection on 2026-06-24 (Δr ≈ 0 vs the +0.005 gate,
ΔAUC ≈ 0 for per-start bust). The distinction under test: that finding rejects
*slope layered on top of the level*. It does not address whether a
**stabilization-gated level shift within the season** carries signal the
cumulative level misses. If this signal fails, the 2026-06-24 conclusion simply
extends to cover regime shifts too, and the flag must never move a rank.

Primary test is on the CONTINUOUS delta, not a thresholded flag, so that no
threshold is fit to the outcome (Rule 3). The ±0.05 flag is a display artifact
only and is reported as a secondary descriptive cut.

## Rule 9 honesty note — PARTIAL BASELINE

The full RP3_FEATS baseline (24 features) requires
`data/research/xfp_cache/rolling_pitchers_2018_2026.csv` and the per-year
statcast parquets. **Neither is present in this execution environment**, so a
fully Rule-9-compliant integration test CANNOT be run here.

The strongest baseline constructible from MLB Stats API game logs is the
cumulative-level set:

    fp_per_start_to, k_pct_to, bb_pct_to, h_per_start_to,
    ip_per_start_to, gs_to, split_idx

This is a **Rule-9-PARTIAL** validation and is labelled as such in the verdict.
It is, however, the baseline that directly tests the claim being made: the
repo's standing finding is that "the cumulative LEVEL already carries the
decline." If the regime delta adds nothing over that level set, the motivating
claim is falsified and the signal is rejected regardless of what a fuller
baseline might show.

A PASS here does NOT authorise rp3 integration. Integration requires the full
RP3_FEATS baseline run on a machine with the statcast substrate, and is a
separate Rule 7 request.

## Bars (Rule 2)

- (a) effect size: pooled partial r >= 0.10 controlling for the level baseline
- (b) year consistency: same sign in >= 5 of 6 training years (n >= 30/year)
- (c) holdout: partial r >= 0.05, same sign, on 2024-2025

## Rule 8 convergence

Re-validated at split indices 8, 12, 16, 20 starts. Production-ready requires
the same coefficient sign at most cutoffs.

## Amendment (pre-results, 2026-08-26) — confidence ceiling on the tested leg

Recorded BEFORE any validation output was computed; frontmatter unchanged.

On reading `plv_clone.stabilization`, SP `k_pct` is in **NEVER_HIGH_CONFIDENCE**
(not NEVER_STABILIZES). It clears the r>=0.50 decision floor at 100 TBF but never
reaches r=0.70 inside a season, and the module's own guidance is that such a
metric is "usable at the minimums above for a directional read; never the
load-bearing evidence in a drop/add decision on its own."

Consequences, both binding on the verdict:

1. The 100-TBF gate is taken from `SP_MINS['k_pct']`, not hand-picked.
2. Even a PASS here cannot license a K%-only regime call as load-bearing.
   The production flag therefore requires corroboration from `whiff`
   (150 swings) and `swstr` (175 pitches) — SP metrics that are NOT in
   NEVER_HIGH_CONFIDENCE and can carry a high-confidence read.

The whiff/swstr legs of the production flag are NOT validated by this run:
they need pitch-level statcast, which is absent here. This run validates the
K% leg only. That asymmetry is stated in the verdict and must survive into any
registry entry.

---

# RESULTS — REJECTED (2026-08-26)

Panel: 21,197 split-rows over **1,327 pitcher-years**, 2017-2025 (ex 2020).
Window gate `SP_MINS['k_pct']` = 100 TBF; median window = 5 starts.
Signal distribution: mean −0.0011, sd 0.0322.

## The three bars

| Gate | Bar | Result | |
|---|---|---|---|
| (a) pooled partial r | ≥ 0.10 | **+0.0468** (p=1.5e-08, N=14,601) | ❌ FAIL |
| (b) year sign consistency | ≥ 5 of 6 | **6 / 6 positive** | ✅ PASS |
| (c) holdout partial r | ≥ 0.05 | **+0.0216** (n=4,856) | ❌ FAIL |
| integration gain (holdout) | +0.005 | **−0.0000** (0.5143 → 0.5143) | ❌ FAIL |

Per-year partial r: 2017 +0.0580 · 2018 +0.0909 · 2019 +0.0305 ·
2021 +0.0039 · 2022 +0.0264 · 2023 +0.0295.

## Rule 8 convergence — UNSTABLE

split 8 **+0.1178** (n=297) · split 12 **−0.0015** (n=266) ·
split 16 +0.0218 (n=225) · split 20 +0.0571 (n=173).

Magnitude swings by an order of magnitude and crosses zero. Fails the
"same sign and stable at most cutoffs" requirement on its own.

## The decisive check — pseudo-replication

21,197 rows come from only 1,327 pitcher-years (~16 highly correlated split-rows
each), which inflates both N and significance. Collapsing to **one row per
pitcher-year** (split nearest 15):

    holdout partial r = −0.0488  (n=297)   ← SIGN FLIPS

The pooled positive is substantially an artifact of repeated measurement on the
same pitcher-seasons. With one independent observation per pitcher-year the
effect reverses. Combined with a holdout below the bar and a literally zero
integration gain, the verdict is unambiguous.

## Descriptive residue (NOT a validated cut)

Holdout raw means, uncontrolled for level: REGIME-UP 11.41 FP/start (n=272) ·
stable 10.92 (n=4,292) · REGIME-DOWN 10.90 (n=292). The ~+0.5 FP gap for
REGIME-UP disappears once the cumulative level is controlled for — i.e. the raw
gap is the level talking, exactly as the 2026-06-24 finding predicts.

## Interpretation

The 2026-06-24 conclusion **extends**: it is not only slope/EWMA features that
are dead for SP projection. A *stabilization-gated in-season level shift* in K%
also adds ~nothing beyond the cumulative season-to-date level. The level really
does already carry it.

Practical consequence: "his recent K% is way up, the model can't see it" is NOT
a supportable reason to prefer one SP over another. The window is a description
of what happened, not a prediction of what comes next.

## What this run does NOT settle

Only the **K% leg** was tested — the sole leg buildable from game logs. SP
`whiff` (150 swings) and `swstr` (175 pitches) are NOT in NEVER_HIGH_CONFIDENCE
and could in principle behave differently, but testing them needs pitch-level
statcast, absent in this environment. That re-test is the only remaining path;
until it is run and passes, no whiff/swstr regime flag may move a rank either.

Also Rule-9-PARTIAL: baseline was the cumulative-level set, not full RP3_FEATS.
Since the signal failed against the *weaker* baseline, a fuller baseline could
only reduce the measured lift further — the REJECTED verdict is safe under that
limitation.

## Registry entry

### stuff_regime_delta — REJECTED (2026-08-26)
- **Standalone validation:** `scripts/xfp/validate_stuff_regime_delta.py`.
  Pooled partial r +0.0468 vs the ≥0.10 bar, N=14,601 (21,197 rows /
  1,327 pitcher-years).
- **Integration validation (Rule-9-PARTIAL, cumulative-level baseline):**
  cross-year r 0.5143 → 0.5143, gain **−0.0000**. FAIL vs the +0.005 bar.
- **Per-year:** 6/6 positive sign, but all magnitudes < +0.10.
- **Framing tested:** in-season → ros.
- **Convergence curve:** splits 8/12/16/20 → +0.118 / −0.002 / +0.022 / +0.057 — unstable, crosses zero.
- **Pseudo-replication check:** one row per pitcher-year → holdout partial r **−0.0488**, sign flip.
- **Definition (canonical):** `stuff_regime_delta` = `k_pct_window − k_pct_to`, window expanded backward to the first size clearing `stabilization.SP_MINS['k_pct']` (100 TBF), capped at 8 starts.
- **Status:** REJECTED — no lift over the cumulative level; sign flips once pseudo-replication is removed. Not shipped as a lens. Re-open only if the whiff/swstr leg is tested on pitch-level statcast.
