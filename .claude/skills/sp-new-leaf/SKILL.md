---
name: sp-new-leaf
description: Adjudicate whether an SP has ACTUALLY turned a new leaf — one objective verdict (NEW LEAF / PARTIAL / MIRAGE / VARIANCE / DECLINE / WATCH / INSUFFICIENT) for a claimed mid-season change of level, positive or negative. Chains the split-check noise screen, the empirical stabilization cutoffs, a mechanism attribution over fast-stabilizing process metrics, and a two-window persistence check. Use whenever the user says "he's a different pitcher since X", "is the post-ASG run real", "did the recall/IL return change him", "am I selling low if I drop him", or before any add/drop justified by a recent stretch. SP-scoped (hitters have /breakout-sustainability).
---

# sp-new-leaf

Answers ONE question with ONE stable verdict: **did this pitcher's underlying
level actually change, and if so by how much?** Built 2026-08-28 after the
OPTION matched-control study closed the regime-break family for the sixth time
(`option_absence_matched_control_2026-08-28.md`) while the SAME night's Jacob
Lopez read showed what stabilized process metrics can MEASURE: a whiff rate
that doubled over 711 pitches is a real, current fact in a way a bare results
break never is. (Same-night calibration then showed measurement is ALL it is —
the mechanism does not predict persistence; see the shrinkage section.)

**The core inversion this protocol enforces:** never reason from results back
to skill. Attribute what changed through the stabilized metrics; price what
comes next through the calibrated shrinkage. A 19.5pp K-BB% break has a
19.2pp matched control; a doubled whiff rate has no such twin — but neither
one holds forward better than the other.

Rule 13 throughout: the verdict NEVER moves rp3/rprs2 or any rank. It is a
decision-layer read for add/drop/hold calls.

## The five gates, in order (stop at the first verdict)

### Gate 0 — frame the split point (Rule 8)
GIVEN by an event (recall, IL return, trade, ASG, a dated pitch-mix or
mechanics change, role change) → bar **z > 1.83**. SEARCHED ("he's been
different lately") → bar **z > 2.58** and say so out loud. Getting this wrong
is how 39% of pitcher-seasons clear a threshold by construction.

### Gate 1 — results screen (owner: /split-check, `lib/split_floor.py`)
Does the results gap clear the within-season noise floor at the Gate-0 bar?
K-BB% via `split_floor`; FP/start via `split_floor_fp` (calibrated
2026-08-28 — a naive Welch z on FP is too lenient by ×1.18 and worse for
big windows; FP searched bar is 2.92). **No → VARIANCE. Stop.** ~89% of
apparent in-season change is sampling noise; most claims die here and should.

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

### Gate 3 — mechanism attribution (DESCRIPTIVE, not predictive — see calibration)
At least ONE of:
- a stabilized process metric moved beyond delta-noise (~√2× the level's
  noise): velo, whiff, SwStr, K%, GB;
- a discrete CHOICE changed: pitch-mix share shift (calibration note: ≥5pp
  sits BELOW the 7.0pp median of ordinary between-window mix variation —
  demand ~≥10pp or a genuinely NEW pitch ≥10% usage before calling it a
  choice), arm-slot change, role change.

**Results without mechanism → MIRAGE**. **Mechanism without results → WATCH.**
Gate 3 tells you WHAT changed — it does NOT raise the probability the change
persists (calibrated 2026-08-28: mechanism-backed clearing splits held
+0.445 of their gap forward vs +0.495 for results-only, z = −0.18 — no
separation, and the registered thresholds fired on 91% of ALL splits).

### Gate 4 — persistence to date (don't-do #15; also descriptive)
Split the post window into two non-overlapping halves; the mechanism's sign
must hold in BOTH. One half → **WATCH**, not a leaf. This certifies the change
has lasted SO FAR; per the calibration it does not license projecting it
forward beyond the shrinkage below.

## Verdicts

| verdict | meaning | action posture |
|---|---|---|
| **NEW LEAF** | mechanism real, stabilized, persistent, results consistent with it | the change HAPPENED; forward, apply the shrinkage below — never the raw post level. Caveat on every use: mechanism-backed hold-rate is NOT distinguishable from results-only (+0.445 vs +0.495), and ~54% of any clearing break mean-reverts over the next ≤8 starts |
| **PARTIAL** | mechanism real but results OVERSHOOT it | state both numbers (mechanism level vs topline), then price via the shrinkage below — the mechanism does not earn a better hold-rate than a bare results break |
| **MIRAGE** | results moved, no stabilized mechanism | expect regression to prior level |
| **VARIANCE** | gap inside the noise floor | no update at all |
| **DECLINE** | negative leaf — stuff eroding (= stuff_command STUFF-DECLINE) | descriptive unless the RESULTS gap also cleared Gate 1; a mechanism-only decline prices at the season blend |
| **WATCH** | mechanism present but sample/persistence incomplete | hold judgment, re-run at a named date |
| **INSUFFICIENT** | post window below every cutoff | wait; the data cannot answer yet |

## Forward pricing — the calibrated shrinkage (2026-08-28, n=227 clearing splits 2018-2026)

A Gate-1-clearing break holds, on average, **+0.46** of its FP/start gap over
the next ≤8 starts — i.e. **~54% of any clearing break mean-reverts** —
(**+0.33** for positive breaks, **+0.60 to +0.75** for negative ones —
declines persist more than breakouts), and having a mechanism does not change
that number. So the forward point estimate is
`pre + hold×(post − pre)` — which usually lands very close to the model's own
blended projection. **The verdict tells you what happened; rp3's blend remains
the best forward number.** A split that never cleared Gate 1 prices at the
season blend, full stop, whatever the mechanism says.

### The held-window update (Gate 5, sequential — the one refinement that cleared a bar)

Measured 2026-08-28 on the 36 cleared POSITIVE breaks with two disjoint
forward windows (4+4 starts): a break that HELD its first forward window
(≥0.5 of the gap) kept holding in the second — mean **+0.87**, P(≥0.5) =
**73%** — vs **+0.25** / 38% for first-window misses. Welch t = +2.31,
one-sided p = 0.014, clears the given bar. Survivorship disclosed: 79 breaks
lacked 8 forward starts (their partial hold +0.29, population-typical — the
exclusion hides no pile of successes). POS breaks only; no NEG conditional
measured.

**Rule:** after a cleared positive break, once a DISJOINT post-classification
window of ~4 starts holds ≥0.5 of the gap, upgrade the forward hold from
+0.33 to **+0.87 (with a 27% full-revert branch)**. Until such a window
exists, the pooled shrinkage stands. This is sequential evidence doing the
work the mechanism story cannot: two null results say mechanism SIZE predicts
nothing (continuous dose-response rho = −0.07 across 121 cleared POS breaks;
the +8pp whiff-class tail hold of +0.52-0.60 at n≤13 is anecdote-tier), while
the break simply CONTINUING is the strongest forward signal we have measured.

Process texture (descriptive): in the extreme whiff-jump class, the whiff
LEVEL partially reverts in the forward window (~-30% of the spike, 11 of 12
cases) yet retains most of its gain over the pre baseline — the league
adjusts partially; the skill mostly stays.

## Canonical worked cases (2026-08-28)

- **Jacob Lopez, split = recall 7/05 (GIVEN):** velo flat 90.4→90.3, whiff
  17.8→**29.2** (240+ swings), SwStr 7.8→**14.1** (711 pitches), K% 29.6
  (~165 TBF), ascending L8. **NEW LEAF** — a shape/mix leaf, not a velo leaf
  (and NOT a new pitch: the slider predates the option with identical shape;
  the whole arsenal simply whiffs ~2x on unchanged movement, vs a neutral
  4.53 R/G opponent slate). The rp3 rank (172) stays put. Forward: his break
  is the largest stabilized whiff jump in the 2018-2026 panel AND it already
  held a disjoint forward window at 1.63 → the Gate-5 held-window update
  applies: price ≈ pre + 0.87×gap ≈ **11-13** with a ~27% full-revert branch
  (not the raw 15.9 post level, and not the naive pooled ~8 either). Full
  audit: `lopez_special_case_2026-08-28.md`.
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
- Calibration status: **MEASURED 2026-08-28 — DOES NOT SEPARATE**
  (`new_leaf_calibration_2026-08-28.md`; the seventh consecutive
  mean-reversion win). Mechanism-backed clearing splits held **+0.445** of
  their gap forward (n=206 pitcher-seasons) vs **+0.495** for results-only
  (n=9): one-sided Welch **z = −0.18**, permutation p = 0.58, against the
  registered bar z > 1.83 — the point estimate sits on the WRONG side. The
  registered mechanism thresholds also proved nearly vacuous: they fire on
  ~91% of ALL admissible splits (mix ≥ 5pp alone on 73%, against a 7.0pp
  MEDIAN ordinary between-window mix shift), which is what left the
  results-only arm at n=9. Consequence applied: Gates 0-2 are the
  load-bearing screen; Gates 3-4 are descriptive attribution only. Forward
  expectations come from the shrinkage table above, never from the mechanism
  story. When a verdict here is load-bearing for a drop, quote the shrunk
  forward number next to it.
