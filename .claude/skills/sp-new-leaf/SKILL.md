---
name: sp-new-leaf
description: Adjudicate whether an SP has ACTUALLY turned a new leaf — one objective verdict (NEW LEAF / PARTIAL / MIRAGE / VARIANCE / DECLINE / WATCH / INSUFFICIENT) for a claimed mid-season change of level, positive or negative. Chains the split-check noise screen, the empirical stabilization cutoffs, a mechanism attribution over fast-stabilizing process metrics, and a two-window persistence check. Use whenever the user says "he's a different pitcher since X", "is the post-ASG run real", "did the recall/IL return change him", "am I selling low if I drop him", or before any add/drop justified by a recent stretch. SP-scoped (hitters have /breakout-sustainability).
---

# sp-new-leaf

Answers ONE question with ONE stable verdict: **did this pitcher's underlying
level actually change, and if so by how much?** Built 2026-08-28 after the
OPTION matched-control study closed the regime-break family for the sixth time
(`option_absence_matched_control_2026-08-28.md`) while the SAME night's Jacob
Lopez read showed what DOES work: results-level breaks carry ~zero signal, but
stabilized process-metric levels carry real signal the moment their sample
clears the empirical cutoffs.

**The core inversion this protocol enforces:** never reason from results back
to skill. Reason from mechanism forward to the results it supports. A 19.5pp
K-BB% break has a 19.2pp matched control; a whiff rate that doubled over 711
pitches has no such twin.

Rule 13 throughout: the verdict NEVER moves rp3/rprs2 or any rank. It is a
decision-layer read for add/drop/hold calls.

## The five gates, in order (stop at the first verdict)

### Gate 0 — frame the split point (Rule 8)
GIVEN by an event (recall, IL return, trade, ASG, a dated pitch-mix or
mechanics change, role change) → bar **z > 1.83**. SEARCHED ("he's been
different lately") → bar **z > 2.58** and say so out loud. Getting this wrong
is how 39% of pitcher-seasons clear a threshold by construction.

### Gate 1 — results screen (owner: /split-check, `lib/split_floor.py`)
Does the results gap (FP/start or K-BB%) clear the within-season noise floor
at the Gate-0 bar? **No → VARIANCE. Stop.** ~89% of apparent in-season change
is sampling noise; most claims die here and should.

### Gate 2 — sample gates on the POST window (owner: `pitcher_cutoff_stabilization`, 2026-07-29)
Every metric you cite must clear its own cutoff in its own denominator:
**velo 150 pitches · whiff 150 swings · SwStr 175-200 pitches · K% 100 TBF ·
GB 50 BIP · CSW 425.** Anything short → **INSUFFICIENT — name the date the
sample matures and re-run then.**
**NEVER cite BB%, chase-against, or hard-hit/HR-against** — they do not
stabilize in-window; a "command improved / HR-prone lately" leg is noise by
construction (canonical: Soriano 2026-08 — his post-ASG BB% "improvement" is
exactly the metric the protocol forbids, while his stabilized stuff was
eroding).

### Gate 3 — mechanism attribution (owner: statcast reads + `stuff_command` lens)
At least ONE of:
- a stabilized process metric moved beyond delta-noise (~√2× the level's
  noise): velo, whiff, SwStr, K%, GB;
- a discrete CHOICE changed (choices stabilize immediately): pitch-mix share
  shift ≥5pp, a new/expanded pitch ≥10% usage, arm-slot change, role change.

**Results without mechanism → MIRAGE** (hot streak; the Soriano-June shape —
bust-run with intact stuff is the same verdict mirrored).
**Mechanism without results → WATCH** (the change is real but not yet cashing).

### Gate 4 — persistence (don't-do #15)
Split the post window into two non-overlapping halves; the mechanism's sign
must hold in BOTH. One half → **WATCH**, not a leaf. (A single window can look
exactly like a trend and reverse in two weeks — Trea Turner.)

## Verdicts

| verdict | meaning | action posture |
|---|---|---|
| **NEW LEAF** | mechanism real, stabilized, persistent, results consistent with it | re-price the player at the mechanism-supported level |
| **PARTIAL** | mechanism real but results OVERSHOOT it | credit the mechanism level, fade the topline (state both numbers) |
| **MIRAGE** | results moved, no stabilized mechanism | expect regression to prior level |
| **VARIANCE** | gap inside the noise floor | no update at all |
| **DECLINE** | negative leaf — stuff eroding (= stuff_command STUFF-DECLINE) | sell/defensible drop |
| **WATCH** | mechanism present but sample/persistence incomplete | hold judgment, re-run at a named date |
| **INSUFFICIENT** | post window below every cutoff | wait; the data cannot answer yet |

## Canonical worked cases (2026-08-28)

- **Jacob Lopez, split = recall 7/05 (GIVEN):** velo flat 90.4→90.3, whiff
  17.8→**29.2** (240+ swings), SwStr 7.8→**14.1** (711 pitches), K% 29.6
  (~165 TBF), ascending L8. **NEW LEAF** — a shape/mix leaf, not a velo leaf.
  The rp3 rank (172) stays put; the decision layer re-prices him (~14/start).
- **Noah Cameron, split = ASG (GIVEN):** whiff 22.3→26.5 ✓, SwStr 10.5→12.8 ✓,
  velo +0.4 ✓, FF share 27.8→18.1 with a new 17.1% SL ✓ — but K% FELL
  21.5→17.8 while FP/start jumped 9.15→16.71. **PARTIAL** — mechanism supports
  ~12-13/start; the 16.71 is sequencing/contact luck on top of a real step.
- **José Soriano, split = ASG:** velo 96.8→96.0 (310 FB), whiff −5.2,
  SwStr −2.2, K% −4.6, sinker share +8.3pp — all stabilized, both post
  halves agree, independently flagged by the velo-trend lens. **DECLINE.**
  His improved BB% is Gate-2-inadmissible and must not rescue the verdict.

## Boundaries (registry seams — do not blur)

- `/split-check` owns Gate 1 and stays SCREEN-ONLY; this skill is the
  composition that adds mechanism + persistence on top.
- `/sp-form --lens breakout|decline` are POOL scanners; this is a SINGLE-ARM
  adjudication with a split point.
- Hitters route to `/breakout-sustainability` / `/slump-or-decline`.
- Calibration status: verdict hold-rates are being measured historically
  (`new_leaf_calibration_2026-08-28.md`, pre-registered). Until that lands,
  the gates are measurement-math-derived, not outcome-calibrated — say so
  when the verdict is load-bearing for a drop.
