---
run_id: xwoba_early_read_surface_2026-08-05
status: MEASURED — reference surface, no promotion
family: early_read_confidence
question: >
  Given N < 225 PA of xwOBA, how likely is a hitter's NEXT 225 PA to be above
  league average? Answered as a PA x deviation surface rather than a single
  sample-size threshold.
rule13: display/decision context only — never moves rh3/rp3/rprs2.
---

# The xwOBA early-read surface

## Why this exists

`stabilization.HITTER_MINS['xwoba_ppa'] = (225, PA)` is the point where xwOBA's
forward reliability crosses r=0.50. That is a property of the METRIC. The
question that actually comes up is different and player-specific: *I am looking
at a hitter with 60 PA since the break — can I trust it?*

The answer depends on N **and** on how extreme the reading is. A .500 xwOBA on
40 PA is not the same claim as .360 on 40 PA, and a single PA threshold cannot
express that.

## Method

- Every player-season **2022-2026** with at least N + 225 PA.
- `observed` = xwOBA over the FIRST N PA of the season.
- `forward` = xwOBA over the **NEXT 225 PA**. Strictly disjoint — no overlap.
- "good" = forward xwOBA >= that season's league mean.
- xwOBA per PA = `estimated_woba_using_speedangle` on balls in play,
  `woba_value` otherwise, so K and BB carry their real wOBA weights.
- Sample: 1,520 player-seasons at N=25 down to 849 at N=200.
- **Base rate P(good) = 0.562.** Every number below must be read against this.

Selection note: requiring N+225 PA restricts to players who kept playing, so
this describes REGULARS. It does not cover part-timers or players who lost
their job — which is the population where a bad early read most often ends the
sample entirely.

## Forward correlation of an N-PA read with the next 225 PA

| N PA | pearson r | spearman |
|---|---|---|
| 25 | 0.211 | 0.196 |
| 50 | 0.268 | 0.245 |
| 75 | 0.332 | 0.293 |
| 100 | 0.377 | 0.340 |
| 150 | 0.436 | 0.402 |
| 200 | 0.484 | 0.411 |

Consistent with the 225-PA crossing already in `stabilization.py`.

## P(next 225 PA above league average), by N and by edge

| N PA | below lg | +.000-.030 | +.030-.060 | +.060-.100 | +.100-.150 | +.150+ |
|---|---|---|---|---|---|---|
| 25 | 0.46 | 0.53 | 0.61 | 0.61 | 0.68 | 0.71 |
| 50 | 0.46 | 0.54 | 0.61 | 0.70 | 0.76 | 0.75 |
| 75 | 0.45 | 0.57 | 0.57 | 0.69 | 0.78 | 0.78 |
| 100 | 0.41 | 0.56 | 0.62 | 0.77 | 0.94 | 0.94 |
| 150 | 0.42 | 0.59 | 0.67 | 0.82 | 0.81 | 0.81 |
| 200 | 0.45 | 0.58 | 0.75 | 0.87 | 0.87 | 0.87 |

## The usable form: smallest edge that reaches a confidence target

| PA so far | >=65% | >=70% | >=75% | >=80% |
|---|---|---|---|---|
| 25 | +.035 | +.105 | not reached | not reached |
| 50 | +.015 | +.045 | **+.095** | +.110 |
| 75 | +.030 | +.050 | +.070 | +.100 |
| 100 | +.005 | +.030 | **+.050** | +.060 |
| 150 | +.000 | +.015 | +.045 | +.050 |
| 200 | +.000 | +.005 | +.020 | +.030 |

At a league mean near **.316**, the practical translations are:

- **50 PA** (about one post-ASG window): needs **~.410** for 75% confidence.
- **100 PA**: needs **~.366**.
- **25 PA** (about a week): needs **~.421** for 70%, and **75% is unreachable
  at any edge** — the sample cannot carry it.

## Two findings worth keeping

1. **A below-average early read is the most reliable signal on the board.**
   P(good) sits at 0.41-0.46 at EVERY N. Cold reads inform earlier than hot
   ones do.
2. **The ceiling is modest.** The strongest realistic cell is ~0.78 against a
   0.56 base rate. A great short-window number moves a coin flip to roughly
   3-in-4. It is a real edge and it is not certainty.

## Scope limit — read this before using it

This says when a READING is trustworthy. It does **not** say that acting on
early readings is profitable. The companion study the same day
(`legacy_wakeup_2026-08-04.md`) found that deliberately buying before the box
score fires LOST to simply taking the top decile by trailing FP/game
(-0.103 vs the all-legacy control, -0.403 vs the market's own behaviour).

Use this surface to avoid being fooled by a hot 25 PA. Do not use it as a
licence to front-run the market.

## Applying it to a split

The vs-RHP or vs-LHP LEVEL is just xwOBA on a smaller window, so this surface
applies directly at whatever PA the split leaves. The platoon SPLIT itself
(RHP minus LHP) is a different quantity that needs sample in the thousands and
is **not** covered here.
