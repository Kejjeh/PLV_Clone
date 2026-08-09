---
name: prior-year-peg
description: Peg a player to his OWN prior-year baseline and classify the direction he is travelling — RECOVERING / STALLED / SUSTAINED / OVEREXTENDED. Answers "is he clawing back to last year" and "is he about to regress to last year", which field-relative ranks (rh3, replacement delta, RoS FP/game) structurally cannot see. Use when comparing an underperformer against an overperformer, before adding a hot bat, before dropping a slumping one, or whenever a verdict rests on "is this real".
---

# prior-year-peg

Every other board here ranks a player against the FIELD. That is the right
frame for *who is better* and the wrong frame for *is this real*, because it
cannot see the only baseline mean-reversion actually pulls toward: **the
player's own prior-year level.**

```bash
python scripts/xfp/run_prior_year_peg.py "Jarren Duran" "Caleb Durbin"
python scripts/xfp/run_prior_year_peg.py --roster
python scripts/xfp/run_prior_year_peg.py --since 2026-06-01 --team TOR "Bo Bichette"
```

## The four regimes

|  | process supports it | process contradicts it |
|---|---|---|
| **above** prior level | **SUSTAINED** — real level change | **OVEREXTENDED** — regression risk |
| **below** prior level | **RECOVERING** — buy the claw-back | **STALLED** — no recovery yet |

A move smaller than ±0.030 fp/PA is **AT-LEVEL** — noise, not a regime.

## The baseline is a BLEND, not last season alone (validated 2026-08-09)

"Pegged to last year" is the intuitive frame, but last year is usually the
anomaly: **|last season − 3-year level| exceeds the ±0.030 band 64.5% of the
time** (n=1,916), so a naive 1-year peg most often sets its zero point further
off the player's real level than the move it is trying to detect. Predicting
the current season's fp/PA (n=1,165 with three full 200+ PA prior years):

| baseline | r | MAE |
|---|---|---|
| prior 1 year | 0.501 | 0.1010 |
| prior 3 years, PA-weighted | 0.558 | 0.0915 |
| **blend 40% 1yr / 60% 3yr** | **0.562** | **0.0906** |

MAE difference 1yr−3yr = +0.0096, 95% CI [+0.0062, +0.0131].

The edge is **asymmetric**, which is why a blend and not pure 3-year: after a
**career year** the 1-year peg is biased **−0.083** (nobody returns to it)
while 3-year is only −0.012; after a **down year** 1-year is +0.042 and 3-year
−0.038, roughly a wash. Pure 3-year would overstate the recovery owed by a
declining veteran — exactly the Altuve/Duran case this board gets used on.

The report **shows both** baselines and flags when they diverge past the band,
naming the direction the naive read would have erred. With fewer than two
qualifying seasons it falls back to last year alone and **says so** — Durbin
prints `1yr only (1 qualifying season in the 3yr window)`.

Scope: the blend was validated on **fp/PA only**. The process metrics below
still compare against the prior YEAR alone; blending those is an untested
change and Rule 9 says don't ship the untested half beside the tested one.

## Why it exists (the canonical reversal, 2026-08-09)

Choosing an FA hitter to replace Ezequiel Duran, **three independent lenses all
preferred Caleb Durbin**: rh3 rank (#66 vs #142), production since the ASG
(3.36 vs 2.00 FP/g), and the weekly optimizer. Pegged to their own 2025
baselines the order **reversed**:

| | Durbin | Jarren Duran |
|---|---|---|
| 2025 fp/PA | 0.606 | 0.532 |
| post-ASG fp/PA | **0.747** (+0.142) | 0.489 (−0.043) |
| hard-hit vs 2025 | 26.8 → **20.5** | 46.7 → 42.2 |
| whiff vs 2025 | 13.0 → **16.0** | 29.3 → **28.7** |
| K% vs 2025 | 9.9 → 11.1 | 24.2 → **22.2** |
| xwOBACON YoY | −0.011 | −0.002 |
| luck (xwOBA vs actual) | **+0.037 over** | **−0.022 under** |
| process vote | **1 toward / 5 away** | **3 toward / 2 away** |
| regime | **OVEREXTENDED** | **RECOVERING** |

Durbin was outproducing a process that had **decayed** — his hard-hit rate
collapsed by a third while his output rose. Duran was underproducing a process
that had **held**, with a bounce still owed. Same league, same window, near-
identical "he's hot" narratives, opposite directions.

**Production above a decaying process regresses. Production below an intact
process recovers.** That asymmetry is the whole skill.

## What counts as evidence

Only metrics readable in the window, gated on their own denominators via
`plv_clone.stabilization`: chase (150 OOZ pitches), zone-swing (150 IZ), whiff
(150 swings), SwStr (150 pitches), K% (50 PA), hard-hit (50 BIP).

**HR and ISO are never evidence** — both need ~275 PA, so in any half-season
window a power surge is a *lagging* indicator by construction. A test fails if
either leaks into the evidence set. This is the same trap `/wakeup-board`
routes around, applied to the prior-year question.

Two prior-anchored reads carry extra weight:

- **xwOBACON YoY stability** — the validated hitter-recovery rule (memory
  gotcha #8). STABLE contact quality means prior recoveries are a valid
  template; contact **declining every year** (the Turner pattern) means the
  recovery ceiling sits *below* prior troughs. Strongest RECOVERING-vs-STALLED
  discriminator we have. **The same reading means opposite things by
  direction** — stable contact under an overperformer says the surplus is *not*
  coming from better contact — so the engine glosses it per-regime and the
  report must too.
- **expected-vs-actual wOBA, pegged to the player's OWN luck baseline** — a
  positive **excess** on an above-prior player corroborates OVEREXTENDED; a
  negative excess on a below-prior player is owed bounce.

  *Excess*, not *gap*. The ±0.020 luck threshold is calibrated to the field,
  whose gap centers on zero and mean-reverts — but some hitters' does not,
  because xwOBA is built from exit velocity and launch angle alone and is
  blind to where a ball is hit and who is running. **Jose Altuve beat his
  xwOBA in 10 of 11 full seasons at a PA-weighted +0.030**, so reading his
  2026 +0.030 as "due for negative regression" flagged his normal operating
  level as luck. Validated leave-one-season-out (n=1,583): prior gaps predict
  the current gap at **r=0.334** [0.288, 0.379], slope **0.527** [0.452,
  0.604] — real but regressing, so the baseline is **shrunk** by that slope.
  Shrinking is load-bearing: MAE 0.0154 shrunk vs **0.0164 for the raw career
  gap, identical to ignoring history entirely**.

  Needs 3+ prior seasons and 1,000+ PA; below that it degrades to the field
  zero and says so. **Annotation only — it never changes the regime.**
  Cache: `scripts/xfp/build_hitter_luck_baseline.py` (refresh step 1.68).

## Reading the output

- **The vote counts against the PRIOR YEAR, not against earlier this season.**
  A player can be improving on his own bad first half and still be far below
  the level he has to reach. Both facts are true and only one is the question.
- **A tie resolves pessimistically.** `support == oppose` is not support, and
  0/0 (nothing readable) is a tie — the burden of proof sits with the claim
  that something changed.
- **Direction is set by production, never by the vote.** The vote picks which
  regime *within* a direction; it cannot flip an overperformer into RECOVERING.

## When NOT to use

- **No prior-year MLB baseline** (rookies — Caglianone, Marsee) → the peg
  returns an explicit error rather than guessing. Use `/breakout-sustainability`
  or the archetype level read instead.
- Ranking an open pool with no incumbent → `/hitter-board` or `/all-boards`.
- "Who is waking up" with no specific name in mind → `/wakeup-board`.
- Pitchers → `/sp-decline` and `/sp-form --lens sustainability` are the SP-side
  trajectory lenses; this engine is hitter-only.

## Rule 13

Context/awareness only. Never moves rh3, never re-ranks a model, never
overrides a projection. It reports **which direction a player is travelling
relative to himself** and hands that to the verdict layer — where, when it
contradicts a field-relative ranking, the contradiction is the finding and
must be shown rather than resolved silently.
