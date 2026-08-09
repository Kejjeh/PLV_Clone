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
- **expected-vs-actual wOBA** (from `/triangulate`) — a positive gap on an
  above-prior player is the OVEREXTENDED tell; a negative gap on a below-prior
  player is owed bounce.

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
