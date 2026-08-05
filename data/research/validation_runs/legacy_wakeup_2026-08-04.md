---
run_id: legacy_wakeup_2026-08-04
status: FAIL — family CLOSED
verdict: >
  The screen underperforms every control, including the naive "all legacy
  hitters" baseline (-0.103 FP/game) and badly against what the market
  actually does (-0.403). The bat-speed gate contributes +0.027, i.e.
  nothing. There is no timing arbitrage here.
registered_utc: 2026-08-04
family: legacy_wakeup
question: >
  Among LEGACY hitters whose outcomes lag their own career peak, does a
  league-relative bat-speed LEVEL that is still intact identify forward
  production BEFORE the market reacts?
rule13: decision/acquisition layer — never moves rh3/rp3/rprs2.
---

# Legacy wake-up screen — pre-registration

## Motivation (measured 2026-08-03/04, before this spec was written)

1. **What the market prices.** Over 65 hitter FA-adds this season, the added
   player sat at the **91st percentile of trailing FP/game** and the **87th of
   home runs**, but the **51st of K-avoidance** and the **50th of bat speed**.
   Managers add on the box score; two metrics are priced at a coin flip.
2. **K-avoidance is unpriced because it does not work.** Selecting the top
   decile by K-avoidance returned **−0.031 FP/game vs the pool** forward. Dead
   end; the market is right to ignore it. (This kills the first hypothesis.)
3. **Bat speed is unpriced AND productive** (+0.300 FP/game forward in the same
   exploratory pass), corroborating the registry result that of all process
   metrics only bat speed adds forward-FP signal beyond the FP level itself.
4. **Level, not trajectory.** The in-season bat-speed DELTA family is CLOSED
   (0/6 cells survived BH-FDR, best full integration +0.0035 vs a +0.005 bar).
   This screen therefore uses the LEVEL only.

## Hypothesis (declared before any 2024/2025 result was viewed)

A legacy hitter whose bat-speed level remains high **while his outcomes lag his
own career peak and the box score has not yet spiked** will out-produce (a) all
legacy hitters and (b) the legacy hitters the market would actually add, over
the following 21 days.

## Screen (thresholds LOCKED before running)

Per anchor, trailing 14 days:

| gate | rule |
|---|---|
| universe | ≥6 games AND ≥50 swings with bat speed |
| legacy | ≥2000 career PA in prior seasons |
| outcomes lagging | current-season proxy FP/PA ≤ career-peak FP/PA − 0.02 |
| **tool intact** | league bat-speed percentile ≥ **60** |
| market quiet | trailing FP/game percentile < **75** AND ≤1 HR in window |

## Controls

- **C1 ALL** — every legacy hitter in the universe.
- **C2 MARKET** — legacy hitters in the top decile of trailing FP/game (what
  managers demonstrably add).
- **C3 TOOL-BROKEN** — legacy, outcomes lagging, market quiet, but bat-speed
  percentile < 40. Isolates the bat-speed gate from the rest of the screen.

## Measurement

- Forward **21-day proxy FP/game**, ≥6 games required.
- `PROXY_FP = TB + BB + HBP − K` (R/RBI/SB are absent from Statcast and the
  per-game boxscore store covers 2026 only). Validated against true BrownU FP
  on 2026: **Spearman 0.955** over 5 windows / 1,882 player-windows.
- Anchors spaced **21 days** so no two forward windows overlap.

## Test plan

- **Clean test years: 2024 and 2025.** Never examined at spec time.
- **2026 is CONTAMINATED** — it was used in the exploratory pass that produced
  motivations 1-3 above. Reported separately, never pooled into the headline.
- Bat tracking begins 2024, which is the hard ceiling on history. Three seasons
  exist; two are usable as clean tests. This is a small-n study by construction
  and the verdict must be stated with that limit attached.

## Decision rule (fixed in advance)

- **PASS** requires screen − C1 ≥ **+0.15 FP/game** on the clean years AND the
  same sign against C2 and C3.
- A pass on 2026 alone is NOT a pass.
- Sensitivity sweeps over thresholds are SECONDARY and reported as such; the
  primary is the locked spec above.


---

# RESULT - FAIL, family CLOSED (2026-08-04)

## Clean test: 2024 + 2025, 12 anchors, 171 screen picks

| group | forward 21d FP/game | vs screen |
|---|---|---|
| **screen** | **1.078** | - |
| C1 all legacy | 1.180 | **screen -0.103** |
| C2 market pick (top-decile FP/g) | **1.480** | **screen -0.403** |
| C3 tool-broken (bat speed <40th pct) | 1.050 | screen +0.027 |

Paired by anchor: **3 of 12 positive**, mean -0.103, sd 0.144.
2026 (contaminated, reported separately): -0.139 vs C1, same direction.

Decision rule required **+0.15 vs C1**. Delivered **-0.103**. FAIL.

## What actually happened

1. **The bat-speed gate does nothing here.** Screen vs C3 is **+0.027** --
   filtering to >=60th-percentile bat speed against <40th makes no difference
   once the other gates are applied. The exploratory +0.300 came from bat speed
   as a STANDALONE top-decile selector, which mostly identifies good hitters; it
   does not survive being made CONDITIONAL on suppressed outcomes.
2. **The market-quiet gate is what kills it.** Requiring trailing FP/game below
   the 75th percentile deliberately selects players who are not producing -- and
   recent production is genuinely predictive. The gate meant to buy timing edge
   throws away the signal instead.
3. **The market is not making a mistake.** C2 -- simply taking the top decile by
   trailing FP/game, exactly what managers demonstrably do -- is the BEST group
   at 1.480, beating every construction tried. Chasing the box score works
   because the box score predicts.

## Consequence for the family

`legacy_wakeup` is **CLOSED**. Do not re-attempt a screen whose premise is
"buy before the outcomes fire":

- The premise requires that suppressed outcomes be uninformative. They are not.
- Both unpriced metrics have now been tested and neither pays as a selector:
  K-avoidance -0.031 standalone; bat speed +0.027 conditional.
- **Re-open condition: NONE.** A future attempt needs a genuinely new mechanism,
  not a new threshold on these two.

Sensitivity note: thresholds were locked in advance and deliberately NOT swept
after the fact. A sweep would be a Rule-3 multi-cell exercise requiring BH-FDR,
and with a -0.103 primary there is nothing to rescue.

## What this does NOT say

Bat speed remains the validated forward process metric at the LEVEL (registry:
incremental partial r +0.076 beyond the FP level) and remains genuinely unpriced
by this league (50th percentile at the moment of an add). What fails is using it
to TIME an acquisition ahead of the box score. Reading it as a
decline/intactness CONTEXT lens -- the Teoscar Hernandez read, tool decayed vs
tool intact -- is unaffected and stays Rule 13.
