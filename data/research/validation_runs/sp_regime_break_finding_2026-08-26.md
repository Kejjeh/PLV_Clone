---
signal: sp_regime_break (absence-anchored re-basing)
formula: split a pitcher's season at an inter-start gap >= 25 days (ABSENCE, an objective event) or at a searched changepoint (SEARCHED); post-break FP/start shrunk toward prior-year FP/start with a 5-start pseudo-count; CORROBORATED when post-break K% is within 5pp of prior-year K%
outcome: rest-of-season FP/start
expected_sign: +
theory: rp3 leans on `fp_per_start_to`, a season-to-date aggregate. When a season spans a structural break, that aggregate averages two different pitchers and describes neither; re-anchoring on the post-break segment, corroborated by prior-year level, should beat the contaminated mean.
production_target: research-only
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2017, 2018, 2019, 2021, 2022, 2023]
validation_script: TBD — NOT YET VALIDATED
date: 2026-08-26
verdict: RESEARCH-ONLY
---

# SP regime-break contamination — diagnostic finding, NOT a validated signal

## Status, stated first

**This is a DIAGNOSTIC, not a ranker.** No projection column moves. It has not
been through the Rule 2 bars. The related-but-different signal
`stuff_regime_delta` (short rolling K% window vs season-to-date) was **REJECTED**
earlier the same day — see `stuff_regime_delta_2026-08-26.md`. That rejection
does not cover this mechanism, and this memo does not claim it does.

## What differs from the rejected signal

| | stuff_regime_delta (REJECTED) | sp_regime_break (this) |
|---|---|---|
| trigger | rolling window, every split point | an OBJECTIVE event (>=25-day absence) |
| window | ~5 starts (100 TBF), max 8 | the whole post-break segment |
| comparator | season-to-date | **prior-year established level** |
| confirmation | none | two-source agreement (post-break K% ≈ prior-year K%) |

The rejected version searched blindly and its pooled positive was pseudo-
replication (sign flipped to −0.0488 at one row per pitcher-year). The ABSENCE
variant performs **no search**, so it carries no multiple-testing penalty. The
SEARCHED variant does search and is only reported when prior-year corroborates.

## Canonical cases (2026)

| pitcher | break | pre | post | prior yr | board | adj | Δ |
|---|---|---|---|---|---|---|---|
| Jacob Lopez | ABSENCE 40d, back 7/10 | 2.8 FP / 15.7% K | **14.8 / 29.6%** | 11.2 / 27.7% | 10.6 | 13.4 | **+2.8** |
| Bryce Miller | SEARCHED 7/09 | 21.2 / 34.3% | **4.1 / 15.9%** | 7.1 / 18.9% | 13.2 | 5.2 | **−8.0** |
| José Soriano | SEARCHED 4/28 | 22.4 / 30.6% | **9.2 / 21.6%** | 10.0 / 21.0% | 11.9 | 9.3 | **−2.6** |
| Noah Cameron | SEARCHED 7/11 | 8.8 / 21% | **17.2 / 21%** | 13.5 / 20% | 11.2 | 15.6 | **+4.4** |

Miller is the cautionary one in BOTH directions: a session recommendation earlier
the same day called him a "buy-low" on the strength of the widest ours-vs-PL gap
on the board. That gap was the contaminated season aggregate. His post-break
form is 4.1 FP/start on a 15.9% K%, and his prior-year K% (18.9%) says the
34.3% first half was the anomaly, not the 15.9% second half.

## Scale of the problem

`scripts/xfp/sp_regime_scan.py` flags **49 SPs** with |post-break − board rate|
>= 2.0 FP/start, of which 6 are on the Ligers roster and 11 are free agents.

## Secondary finding — IL feature coverage gap

`data/research/xfp_cache/il_split_features_2018_2026.csv` is a full-population
cache (2,723 pitchers for 2026, including `il_stints_to = 0` rows). Yet **2 of
the 11 absence-break pitchers have ZERO rows for 2026** — Jacob Lopez (40-day
gap) and Andrew Painter (44-day gap). For those pitchers all three rp3 IL
features fall back to defaults.

Note a correction against an earlier reading in-session: `is_on_il_at_split = 0`
for Lopez is **correct** (he is active). The defect is the missing rows, not
that flag. Same failure family as the 2026-07-10 incident where the three IL
features sat dead at a 0.45% join rate for six weeks. **Recommend a
`/model-health` tripwire on IL-cache row coverage per rostered SP.**

## Proposed model change — sequencing matters

1. **Now (no validation needed):** ship the scan as a context-only diagnostic
   and route flagged rows to `/triangulate`. Nothing re-ranks.
2. **Next:** pre-register and validate the ABSENCE variant on its own —
   restricted to pitcher-seasons that actually contain a >=25-day gap (~10-15%
   of the population), one row per pitcher-year to avoid the pseudo-replication
   that killed the rejected signal, full RP3_FEATS baseline on a machine with
   the statcast substrate.
3. **Only if it passes:** integration is a separate Rule 7 request. The likely
   shape is not a new feature but a **re-basing of `fp_per_start_to` and the
   rate terms onto the post-break segment** when an absence break exists and
   prior-year corroborates — a change to how an existing feature is computed,
   which needs its own full-pipeline backtest.

Do NOT skip step 2. The whole reason this memo exists is that a plausible
neighbouring signal failed its test the same day.

---

# BACKTEST RESULTS (2026-08-26, same day) — SEARCHED REJECTED, ABSENCE promising

`scripts/xfp/backtest_sp_regime.py`. **Strictly no lookahead**: at each as-of
point the break is detected using ONLY starts 1..t; prior-year aggregates are
legitimately known at t; the outcome (starts t+1..N) never touches the estimator.
Baseline = season-to-date mean FP/start, which is rp3's dominant term.

| slice | n | MAE base → adj | r base → adj | adj better |
|---|---|---|---|---|
| **TRAIN pooled, ABSENCE** | 197 | 3.44 → **2.80** (−0.63) | .530 → **.680** | 129/197 (65%) |
| **TRAIN pooled, SEARCHED** | 2970 | 3.15 → **3.47 (+0.33)** | .521 → .466 | 1274/2970 (43%) |
| TRAIN one-row, ABSENCE | 23 | 3.67 → 3.62 (−0.05) | .523 → .605 | 14/23 |
| TRAIN one-row, SEARCHED | 241 | 3.13 → **3.38 (+0.25)** | .543 → .497 | 107/241 (44%) |
| **HOLDOUT pooled, ABSENCE** | 82 | 3.39 → **3.17** (−0.22) | .453 → .469 | 39/82 (48%) |
| **HOLDOUT pooled, SEARCHED** | 1417 | 3.08 → **3.41 (+0.33)** | .499 → .400 | 573/1417 (40%) |
| HOLDOUT one-row, SEARCHED | 120 | 3.16 → **3.43 (+0.27)** | .497 → .444 | 45/120 (38%) |

## SEARCHED — REJECTED, and removed from the board

Worse on **every** slice: train and holdout, pooled and one-row-per-season. It
beats simply using the season level in only **38-44%** of cases — worse than a
coin flip. Applying it destroys correlation (holdout .499 → .400).

**Root cause, diagnosed:** `find_searched()` has no magnitude or significance
gate. It returns the max-separation split unconditionally, so it fires on
**80.1%** (1063/1327) of pitcher-seasons. It is not detecting structure; it is
splitting each season at its noisiest point, and prior-year K% corroboration is
too weak a filter to stop it. ABSENCE, with an objective trigger, fires on 19.9%.

`sp_regime_board.py` was patched the same day: SEARCHED breaks are surfaced as
`[SEA unvalidated]` for human review but **never move `adj`**. Ten previously
published adjustments were retracted, including Noah Cameron +4.5, Bryce Miller
−7.3, José Soriano −2.8 and Shota Imanaga −2.1.

Deliberately NOT tuned: adding a magnitude gate to SEARCHED and re-testing on
this holdout would be fitting to the test set. Any such gate needs a fresh
pre-registration and a fresh holdout.

## ABSENCE — promising, still NOT validated

Improves MAE and correlation on both train and holdout, and it is the variant
with the objective trigger and no multiple-testing exposure. But independent-
sample n is thin — **23 train / 9 holdout pitcher-seasons** — and the holdout
win rate is only 48%. The pooled −0.63 MAE gain is inflated by pseudo-
replication; the honest one-row train figure is −0.05.

Verdict: keep as a **diagnostic**. Do not promote to a ranker on this evidence.
A proper run needs the full RP3_FEATS baseline and many more absence seasons
(widening to 2015-2016 and relaxing the >=15 GS cohort would roughly double n).

## Decision consequence recorded

The two drops under consideration when this backtest ran — Imanaga and Soriano —
were **both SEARCHED**. The backtest says their adjusted numbers are not usable.
Imanaga's raw 2026 line shows no decline at all (K% 24.3 vs 20.6 in 2025; August
K% 30%, his second-best month), so that drop is affirmatively wrong. Soriano's
case survives only on evidence independent of this method (August/July K% 17-18%
vs a 21% career norm in both 2024 and 2025).

---

# v2 — A PROPER STRUCTURAL BREAK TEST. RESULT: THE IDEA IS DEAD.

`scripts/xfp/sp_structural_break.py`. Four changes, each targeting one v1 defect:

1. **Test a stabilizing rate, not a noisy composite.** Break tested on **K%**, not
   FP/start. FP bundles K/IP/H/ER/BB and sequencing luck (within-pitcher SD ≈ 9);
   a shift in it is mostly BABIP.
2. **Gate both segments at the stabilization minimum.** A split is admissible only
   when BOTH sides carry ≥ `SP_MINS['k_pct']` = 100 TBF.
3. **Calibrate for the search with a permutation null.** Statistic is sup|z| of a
   two-proportion test over admissible splits. Start order is exchangeable under
   "no break", so the null is built by shuffling — exactly calibrated to the
   search that produced the statistic.
4. **BH-FDR across pitcher-seasons** (q=0.10, M=1339).

## Detector is verified, not assumed

200 sims/scenario, p from 400 permutations:

| scenario | true shift | median p | % p<.05 |
|---|---|---|---|
| NULL (22% flat) | +0pp | 0.531 | **4%** ← correctly calibrated |
| 22 → 26% | +4pp | 0.410 | 12% |
| 20 → 28% | +8pp | 0.079 | 42% |
| **16 → 30% (Lopez-size)** | +14pp | 0.005 | **96%** |
| 15 → 32% | +17pp | 0.002 | 98% |

The detector finds a Lopez-sized break 96% of the time. A null result is a
finding, not a failure.

## A BUG THIS RUN CAUGHT — permutation resolution floor

The first pass reported "0 of 1339 pass FDR" at B=400 permutations. That was an
ARTIFACT: an empirical p from B permutations cannot go below 1/(B+1) = 0.0025,
while BH over M=1339 needs the smallest p ≤ q/M = 7.5e-5. **No test could ever
be rejected regardless of the data.** Re-run at B=200,000 (floor 5e-6).

**Rule to carry forward: always check 1/(B+1) < q/M before believing a null from
a permutation test.**

## Real break rate

| | rate |
|---|---|
| v1 SEARCHED (max FP split, no null) | **80.1%** |
| v2 raw p<0.05 | 6.4% (vs 5% expected by chance) |
| **v2 BH-FDR q=0.10** | **3 / 1339 = 0.22%** |

The three: Andrew Cashner 2018, Kevin Gausman 2017, Adrian Houser 2026.

Of 224 seasons containing a ≥25-day absence, **0** showed an FDR-significant K%
break. An absence does not imply a talent change.

## The decision players, tested properly (2026)

| pitcher | pre K% | post K% | shift | sup_z | p | verdict |
|---|---|---|---|---|---|---|
| Bryce Miller | 34.3 | 15.9 | −18.4 | 4.05 | .016 | raw p<.05 |
| **Jacob Lopez** | 15.8 | 29.9 | **+14.2** | 3.30 | **.044** | raw p<.05 |
| José Soriano | 32.5 | 21.5 | −11.0 | 2.53 | .110 | **NOT A BREAK** |
| Tyler Mahle | 21.1 | 27.1 | +6.0 | 1.36 | .514 | **NOT A BREAK** |
| Noah Cameron | 31.8 | 27.6 | **−4.2** | 0.73 | .619 | **NOT A BREAK** |
| Shota Imanaga | 28.3 | 22.5 | −5.9 | 1.55 | **.783** | **NOT A BREAK** |

Cameron's shift is NEGATIVE — v1's "+4.5, your ace" had the sign backwards.

## Why even the real breaks are unusable

Backtest of the strictest sensible rule (event-triggered absence AND sup_z ≥ 3.0,
no lookahead): fires on **1 / 10,274** train and **2 / 3,406** holdout decision
points.

**The structural reason:** detection requires 100 TBF *after* the break. By the
time that accumulates, the rest-of-season window is nearly gone. Statistical
detectability and decision usefulness are separated by roughly the length of the
window you would need to act on. This is not a tuning problem and no threshold
fixes it.

## Final disposition

`sp_regime_board.py` now sets **`adj` == rp3 always**. Breaks are ANNOTATION ONLY.
Nothing regime-derived moves any number, in either direction.

**Family CLOSED.** Both the short-window variant (`stuff_regime_delta`, REJECTED)
and the structural-break variant (this) are dead for SP projection. Re-open only
with a detector that needs materially less than 100 TBF post-break to reach
power — which the stabilization curves say does not exist for K%.

---

# v3 — PARAMETER SWEEP: the surface is mapped, and it has no peak

`scripts/xfp/sweep_break_params.py`. 150 cells: metric {K-BB%, K%, FP} x
min_tbf {40,60,80,100,150} x z_gate {1.5..3.5} x trigger {absence, search}.
Evaluated by PREDICTIVE value (MAE vs rest-of-season FP/start), strictly no
lookahead, with the paired t computed at ONE ROW PER PITCHER-SEASON so
pseudo-replication cannot inflate it.

## What each knob actually does (conditional on firing, train)

| axis | value | cells | mean gain | best cell |
|---|---|---|---|---|
| **metric** | **K-BB%** | 32 | **−0.259** | **+0.240** |
| | K% | 21 | −0.300 | +0.012 |
| | **FP/start** | 17 | **−1.010** | −0.593 |
| **trigger** | **absence** | 10 | **−0.158** (3 positive) | +0.240 |
| | **search** | 60 | **−0.503** (0 positive) | −0.099 |

**Every one of the 30 cells with |t| > 2 is NEGATIVE. Zero positive.**
The worst are FP + search: t = −4.57 to **−6.67**. That configuration is v1.

## Ranked lessons, strongest first

1. **Never split on FP/start.** Mean gain −1.010 and the most significant harm in
   the entire sweep. FP bundles sequencing luck; its biggest split is BABIP.
2. **Never use a searched split.** 0 of 60 cells positive. An event must supply
   the split point, or the split point is noise.
3. **K-BB% is the right metric** — better than K% alone, far better than FP.
4. **min_tbf ≈ 100 per side** sits at the peak, matching `SP_MINS['k_pct']`.

## The peak does not replicate

| cell | TRAIN gain (t, seasons) | HOLDOUT gain (t, seasons) |
|---|---|---|
| K-BB%, 100 TBF, z1.5, absence | **+0.240** (t=0.45, n=20) | **−0.141** (t=−0.46, n=9) |
| K-BB%, 40 TBF, z1.5, absence | +0.081 (t=0.18, n=38) | +0.318 (t=0.67, n=17) |
| K% , 40 TBF, z1.5, absence | +0.012 (t=0.02, n=15) | +1.279 (t=1.72, **n=4**) |

The best train cell **flips sign** on holdout. Nothing replicates. Best-case
unconditional gain across all 150 cells was +0.011 MAE on a 3.355 baseline — 0.3%.

## FINAL DISPOSITION — family CLOSED, with a usable practice rule

No parameterisation of "break up a player's stats" produces a replicable forecast
gain. `adj` stays equal to rp3; breaks remain annotation only.

What the sweep DOES license, as practice rather than as a number:

- **Split only on an objective event** (IL absence, role change, trade) — never
  because the numbers look different.
- **Judge the change on K-BB%**, never on FP or ERA.
- **Require ~100 TBF on each side** before the halves are comparable at all.
- **Expect the split to add nothing to the forecast.** It is a story about what
  happened, not evidence about what comes next.

Re-open condition: a trigger that is BOTH objective AND arrives with enough
post-break sample to test — which for SP rate stats does not currently exist.

---

# v4 — WHICH EVENTS? None of them. But the noise floor is the usable answer.

`scripts/xfp/build_sp_event_panel.py` (35,849 appearances incl. relief, with
team-per-game) + `scripts/xfp/analyze_break_events.py`.

## Event base rates (1,331 pitcher-seasons)

IL_SHORT 15-29d **27.0%** · IL_MED 30-59d 16.6% · ROLE_PEN 16.1% ·
ROLE_ROT 15.0% · TRADE **9.5%** · IL_LONG 60d+ 5.1%

## Does the line actually break at the event? (vs matched same-position controls)

Each event matched to 30 random split dates at the SAME fractional season
position for the SAME pitcher, under the same 100-TBF-per-side gate. Paired t at
one row per pitcher-season.

| event | n | seasons | \|dK-BB%\| | control | **excess** | t |
|---|---|---|---|---|---|---|
| IL_SHORT | 244 | 219 | 4.40 | 4.37 | **+0.02** | 0.66 |
| IL_MED | 136 | 134 | 5.05 | 4.91 | **+0.14** | 1.87 |
| ROLE_ROT | 92 | 77 | 4.59 | 4.57 | +0.02 | 0.06 |
| TRADE | 88 | 86 | 3.92 | 3.83 | **+0.09** | 0.99 |
| ROLE_PEN | 87 | 75 | 4.80 | 4.80 | −0.00 | 0.14 |
| IL_LONG | 37 | 37 | 4.04 | 4.11 | **−0.07** | −0.57 |

**No event type moves the line more than a random split at the same time of
year.** Largest excess is IL_MED at +0.14pp (t=1.87, p≈.06, fails even
unadjusted; with 6 events tested BH needs p≈.008). Trade: +0.09pp, t=0.99.
IL_LONG is NEGATIVE.

Well powered, not a null from thinness: IL_SHORT's SE is 0.030pp, so an effect
of 0.09pp would have been detected — that is 2% of the 4.4pp baseline.

**Why IL returns LOOK like breaks:** the raw |dK-BB%| after an IL_MED stint is
5.05pp, which feels enormous. Its matched control is 4.91pp. The apparent break
is explained by *where in the season it happens*, not by the stint.

## THE USABLE OUTPUT — empirical within-season noise floor for K-BB%

|K-BB% difference| between two halves of the SAME pitcher-season, no event
involved. ~2,800 splits per bucket.

| min side TBF | median | mean | **p90** |
|---|---|---|---|
| 25+ | 6.46 | 7.65 | **15.59** |
| 50+ | 5.20 | 6.10 | **12.41** |
| 75+ | 4.50 | 5.41 | **11.25** |
| 100+ | 4.05 | 4.81 | **9.98** |
| 150+ | 3.54 | 4.33 | **9.05** |
| 200+ | 3.38 | 4.05 | **8.37** |
| 300+ | 3.14 | 3.67 | **7.35** |

**Rule: a K-BB% gap must EXCEED the p90 for its smaller side's TBF to be
distinguishable from ordinary within-season variation.**

## Applied to the 2026 decision set

| pitcher | split | pre TBF | post TBF | pre K-BB% | post K-BB% | gap | p90 | verdict |
|---|---|---|---|---|---|---|---|---|
| Bryce Miller | searched | 187 | 189 | 30.5 | 5.3 | **25.2** | 8.8 | **2.9x floor** |
| Jacob Lopez | 40d IL | 257 | 162 | 3.1 | 21.6 | **18.5** | 9.1 | **2.0x floor** |
| José Soriano | searched | 163 | 440 | 20.2 | 10.2 | 10.0 | 9.1 | 1.1x — marginal |
| Tyler Mahle | 29d IL | 249 | 248 | 13.3 | 14.9 | 1.7 | 7.6 | within noise |
| Shota Imanaga | searched | 235 | 357 | 19.1 | 18.2 | **0.9** | 7.6 | within noise |

Imanaga's gap is one EIGHTH of the floor. Independent confirmation, by a
completely different route than the v2 permutation test, that there is nothing
there.

## The reframe this run earns

Events do NOT cause breaks. What an event supplies is a **legitimate place to
look** — a split point that is given rather than chosen, so it pays no search
penalty. The decision is then made entirely by MAGNITUDE against the noise floor.

Practical rule, replacing "which events matter":
1. Use an event only to pick WHERE to split (avoids the search penalty).
2. Judge on **K-BB%**, never FP or ERA.
3. Require **>=100 TBF on both sides**.
4. Act only if the gap **EXCEEDS the p90 for the smaller side**.
5. Even then, expect no forecast gain — v3 showed re-anchoring does not replicate.

Steps 1-4 are a screen against fooling yourself. Step 5 is why nothing in this
family may move a projection.

---

# v5 — THE FLOOR IS BINOMIAL. Two bars, and pitchers/hitters invert on walks.

`scripts/xfp/lib/split_floor.py` (+ `build_hitter_event_panel.py`).
26,954 SP splits over 1,331 pitcher-seasons; 243,667 hitter splits over 2,469
hitter-seasons; 2017-2026.

## 1. The floor is a FORMULA, not a table

Express the gap in z units against the sampling SE and the p90 is flat:

| | z p90 |
|---|---|
| across sample size (50 → 300+ TBF) | 1.79 · 1.79 · 1.85 · 1.83 · 1.88 |
| across K-BB% talent quintiles | 1.77 · 1.79 · 1.83 · 1.84 · 1.92 |
| **hitters** | **1.82** |
| **pitchers** | **1.83** |

Raw p90 rises with a pitcher's rate (8.68 → 9.97pp across quintiles) ONLY because
p(1−p) does. **The archetype effect is entirely mechanical.** One constant covers
every player, so this replaces the v4 lookup table with

    threshold = z* · sqrt( V · (1/n1 + 1/n2) ),  V = (p_k + p_bb) − (p_k − p_bb)²

## 2. Almost all apparent in-season change is sampling noise

Observed |z| mean 0.889 vs 0.798 for a pure half-normal → **over-dispersion of
only 1.114x**. About **89% of what looks like a pitcher changing mid-season is
sampling noise**; the true-talent wander component is ~0.49x the sampling SE.

## 3. TWO BARS — confusing them is the easiest way to fool yourself

| how you got the split point | bar | why |
|---|---|---|
| **given by an EVENT** (IL, trade, role) | **1.83** | one test |
| **SEARCHED** (you found the biggest gap) | **SP 2.58 / H 2.79** | ~100 tests; the max of 100 draws is not one draw |

Measured on the max-split statistic itself. **39% of pitcher-seasons and 50% of
hitter-seasons clear the GIVEN bar at their best split by construction.** The
hitter max-split MEDIAN is 1.83 — exactly the single-split p90.

Live demonstration: 6 of 11 Ligers hitters "EXCEED FLOOR" at their most extreme
split — 55%, which is precisely the league-wide rate. Re-judged against the
search-corrected 2.79, **all six are ordinary** (max z = 2.41, Guerrero).

## 4. Pitchers and hitters INVERT on walks

| metric | SP dispersion | Hitter dispersion |
|---|---|---|
| K% | 1.134 | 1.104 |
| K−BB% | 1.114 | 1.104 |
| **BB%** | **1.053** (least real) | **1.139** (MOST real) |

**The walk belongs to the batter.** Pitcher command barely moves within a season
— independently ratifying `stabilization.NEVER_STABILIZES` listing pitcher
`bb_pct`, and CLAUDE.md gotcha #11's "watch STUFF, not walks". Hitter plate
discipline genuinely does move. Neither was assumed; both fall out of the same
estimator applied to both sides.

## 5. The rule STILL fails predictively — final closure

Best-designed rule (EVENT-triggered AND K-BB% AND ≥100 TBF/side AND z>1.83),
no lookahead:

    TRAIN    fired 0.8%   MAE 3.91 → 3.82   gain +0.168   t = +0.25
    HOLDOUT  fired 1.0%   MAE 3.36 → 5.31   gain −1.462   t = **−2.16**

Significantly WORSE on holdout. Five independent attempts have now failed:
short-window delta (REJECTED), searched break (REJECTED), 150-cell sweep (no
replication), event taxonomy (no event exceeds control), and this.

## FINAL DISPOSITION

`split_floor` ships as a **screen**, never a number. Clearing the floor means the
gap is real; it does **not** mean it predicts. Nothing in this family may move
rh3/rp3/rprs2, and `sp_regime_board.adj` stays equal to rp3.

Carry forward, independent of breaks entirely:
- the two-bar distinction (given 1.83 vs searched 2.58/2.79)
- over-dispersion ~1.11x → most in-season movement is noise
- the SP/hitter walk inversion
