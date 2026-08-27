---
name: split-check
description: Decide whether a difference between two halves of a player's season is real or ordinary variation. Use whenever someone says a player is "a different hitter/pitcher since" a date, an IL return, a trade, or a role change — or before splitting anyone's line to justify an add/drop. Screens the gap against the empirical within-season noise floor, applying the correct bar for whether the split point was GIVEN by an event or SEARCHED for. Triggers - "is this split real", "he's been different since X", "did the IL stint change him", "should I throw out his first half", "split his stats", "is this a regime change".
---

# split-check

Answers one question: **is this gap outside ordinary within-season variation?**

It does NOT answer "will it continue." That was tested five ways and failed every
time (see `data/research/validation_runs/sp_regime_break_finding_2026-08-26.md`).
Clearing the floor means the difference is real; it does not mean it predicts.

## Why the default answer is "no"

Measured on 26,954 SP splits (1,331 pitcher-seasons) and 243,667 hitter splits
(2,469 hitter-seasons), 2017-2026:

- Over-dispersion vs pure binomial sampling is only **1.114x** (SP) / **1.104x**
  (hitters). **About 89% of apparent in-season change is sampling noise.**
- The |K-BB%| gap between two halves of the SAME pitcher-season has a p90 of
  ~10pp at 100 TBF per side. Most "he's different now" observations sit inside
  that band.

## The two bars — using the wrong one is the classic error

| how you got the split point | bar |
|---|---|
| **GIVEN by an event** (IL stint, trade, role change) | **z > 1.83** |
| **SEARCHED** (you looked for the biggest gap) | **SP z > 2.58 / hitters z > 2.79** |

A searched split is ~100 tests, and the max of 100 draws is not distributed like
one draw. **39% of pitcher-seasons and 50% of hitter-seasons clear the GIVEN bar
at their best split by construction** — the hitter max-split MEDIAN is exactly
1.83. If you went looking for the split, you must use the higher bar.

## Steps

1. **Resolve the player** — `/player-id-resolve` if the name is at all ambiguous.
2. **Establish how the split point was chosen.** Did an event hand it to you, or
   did you find it? This decides the bar and is the whole ballgame. If the user
   says "he's been bad lately" with no event, that is SEARCHED.
3. **Pick the metric.** Use **K-BB%** for pitchers, **K%** for hitters. Never
   split on FP/start or ERA — FP bundles sequencing luck and its largest split is
   usually BABIP (mean predictive gain −1.010 across the sweep, the worst of any
   configuration tested).
4. **Require >= 100 TBF / PA on BOTH sides.** Below that the halves are not
   comparable; report "unmeasurable" rather than a number.
5. **Run it:**

```python
import sys; sys.path.insert(0, "scripts/xfp/lib")
from split_floor import split_floor, floor_for

r = split_floor(k1, bb1, n1, k2, bb2, n2, metric="k_minus_bb")
# -> gap, se, z, threshold, verdict
```

6. **Report** the gap, the z, WHICH bar applies and why, and the verdict. Then say
   plainly that clearing the floor does not imply the change persists.

## Worked calibration (2026 season)

| player | split | gap | z | bar | verdict |
|---|---|---|---|---|---|
| Bryce Miller | searched | 25.2pp | ~4.0 | 2.58 | exceeds |
| Jacob Lopez | 40d IL (given) | 18.5pp | 3.33 | 1.83 | far outside, top 1% |
| José Soriano | searched | 10.0pp | 2.53 | 2.58 | **falls short** |
| Shota Imanaga | searched | 0.9pp | 1.55 | 2.58 | one EIGHTH of the floor |

Soriano is the instructive one: 10pp *looks* enormous and clears the GIVEN bar,
but nothing handed us that split point, so the searched bar applies and he misses.

## Do not

- Do not use this to move a projection. Rule 13 — it is a screen, never a number.
- Do not split on FP or ERA.
- Do not report a verdict without naming which bar you used.
- Do not re-attempt the "re-anchor the projection on the post-break segment" idea.
  It is CLOSED: the best-designed version gained +0.168 on train and lost 1.462 on
  holdout (t = −2.16).
