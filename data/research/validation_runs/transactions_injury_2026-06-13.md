# Injury / Transaction data — feasibility + return-curve validation

**Date:** 2026-06-13
**Author:** research (one-off)
**Script:** `scripts/_oneoff/transactions_injury_study.py`
**Cache:** `data/research/xfp_cache/mlb_transactions_2023_2025.csv` (parsed stints),
`data/research/xfp_cache/_il_ramp_sample_2023_2025.csv` (per-stint ramp sample),
`data/research/xfp_cache/_gamelog_cache_il_study.json` (gameLog cache)
**Question:** Can richer IL/transaction data beat ESPN return-date guesses — specifically,
real IL-stint history, stint length by injury type, and a measurable *post-IL-return
performance penalty* (the "ramp") that should discount IL-stash valuation (Snell/Glasnow
pattern)?

---

## 1. Data collection — SUCCESS

The repo **already** caches the MLB Stats API transactions feed via
`build_il_history.py` → `il_transactions_{2023,2024,2025}.json` (typeCode `SC` /
Status-Change, IL placements + activations + transfers, with the free-text injury
description). No new fetch was needed for transactions; this study **parses + validates**
that feed and adds per-start actuals via the pitching `gameLog` endpoint.

**MLB-level pitcher IL events 2023-25** (MiLB affiliates filtered out by team name):

| Event | Count |
|---|---|
| Placements (RHP/LHP) | 2,585 |
| Activations | 2,203 |
| Transfers (10/15→60d) | 501 |
| **Paired place→activate stints** | **1,933** |

Parsed stints cached to `mlb_transactions_2023_2025.csv` with: `pid, name, season,
place_date, activate_date, stint_days, il_days_cat (7/10/15/60), hand, injury_class, paired`.

### Stint length by IL category (paired, days)
| IL cat | n | mean | median | max |
|---|---|---|---|---|
| 7-day | 348 | 64 | 41 | 218 |
| 15-day | 1,095 | 60 | 37 | 234 |
| 60-day | 486 | 156 | 155 | 306 |

The IL *category* is a weak proxy for real layoff — 15-day stints have a 37-day median
and a 234-day max (transfers to 60-day mid-stint). **Actual placement→activation gap is
far more informative than the category label**, which is the first thing ESPN return-date
guesses miss.

### Injury-type coverage — HONEST limitation
The description text carries an injury body-part/diagnosis only **~51%** of the time; the
other half is the bare move ("…placed RHP X on the 15-day injured list."). When present,
we can bucket it, but **exact surgery type is sparse** — "Tommy John surgery" / "UCL repair"
/ "internal brace" appear for only the elbow_ucl_tj class (n=77 stints). What IS reliably
derivable: a coarse `injury_class` (elbow_ucl_tj, elbow_other, shoulder, forearm, lat,
oblique, back, lower_body, finger_blister, strain_unspec, fracture, unspecified).

**Median stint length by injury_class** confirms the buckets are real signal:
elbow_ucl_tj 183d, elbow_other 67d, lat 61d, shoulder 58d, fracture 50d, forearm 42d,
oblique 38d, lower_body 26d, finger_blister 22d. (TJ ≈ full season, as expected.)

---

## 2. Return-curve validation — the actionable finding

**Design (leakage-safe):** each pitcher is his own control. Per paired stint we pull the
pitching `gameLog`, compute BrownU SP FP per start (`K + IP*3.3 − H − 2*ER − BB − HBP`),
and compare the **first 1/2/3 starts strictly AFTER the activation date** to the pitcher's
own **pre-IL baseline** (mean FP over in-season starts *before* the placement; if none,
the prior season's full-year mean). No post-return start ever feeds the baseline.

**Usable sample:** 302 returning-pitcher stints with a clean baseline + ≥1 post start.

### Post-return FP minus own pre-IL baseline (paired)
Baseline level for these pitchers ≈ **9.78 FP/start**.

| Horizon | n | ΔFP vs own baseline | 95% CI | P(below base) |
|---|---|---|---|---|
| **1st start back** | 302 | **−1.42** | [−2.48, −0.37] | 55% |
| starts 1-2 | 270 | −0.93 | [−1.82, −0.03] | 55% |
| starts 1-3 | 245 | −0.66 | [−1.53, +0.21] | 53% |
| starts 4-6 | 223 | −0.49 | [−1.54, +0.56] | 52% |

**The penalty is real, concentrated in start 1 (~−1.4 FP, CI excludes 0), and has
essentially decayed by start 3.** That is the ramp.

### Where the penalty actually lives (the IL-stash population)
The aggregate −1.4 is an average over many short (IL15, lower-body) stints with little
ramp. Splitting reveals the signal is concentrated exactly where stash valuation matters:

**By stint length — 1st start ΔFP:**
| layoff | n | mean | median |
|---|---|---|---|
| ≤20d | 97 | −0.25 | −0.40 |
| 21-45d | 97 | −2.08 | −1.37 |
| 46-90d | 58 | −1.37 | −1.40 |
| **>90d** | 50 | **−2.49** | −2.08 |

**By IL category — 1st start ΔFP:** IL15/7 −1.16 [−2.23,−0.09]; **IL60 −6.51
[−11.80,−1.22]** (n=15). The long-layoff IL60 returns crater hardest on the first start.

**By injury_class (n≥15), 1st start ΔFP:** finger_blister −4.40, back −3.78, forearm −2.72,
elbow_other −2.42, unspecified −1.44, shoulder −0.71, lower_body +0.03. Elbow/forearm
(arm) and back returns ramp worst; pure lower-body returns barely ramp at all.

### Baseline-source nuance (important, keeps us honest)
- **In-season-pre baseline** (cleanest, n=209): start-1 ΔFP **−0.93, CI [−2.15,+0.30]** —
  directionally negative but *not* individually significant; gone by starts 1-3 (−0.22).
- **Prior-season baseline** (n=86, i.e. long layoffs spanning offseason — the true stash
  group): start-1 ΔFP **−2.57, CI [−4.75,−0.39]** — significant and large.

The significant penalty is driven by the **long-layoff / prior-year-baseline / IL60**
subset — precisely the Snell/Glasnow/Cole stash archetype.

### Named canonical cases (start1 → starts1-3 recovery)
- **Gerrit Cole 2024** (elbow, 83d, prior base 17.5): start1 **−9.8** → s1-3 **3.3** (massive dip, recovers)
- **Logan Gilbert 2025** (elbow, 51d, base 17.2): start1 6.5 (−10.7) → s1-3 10.2
- **George Kirby 2025** (shoulder, 56d): start1 −0.5 (−14) → s1-3 12.4
- **Kodai Senga 2025** (lower-body, 28d, base 15.9): start1 −0.1 → s1-3 1.5
- **Shane McClanahan 2023** (back, 16d, base 14.8): start1 0.2 → s1-3 3.3
- **Tyler Glasnow 2025** (shoulder, 72d): start1 18.8 (a counter-example — clean return)
- **Blake Snell 2024**: both returns *positive* (he was bad pre-IL; low baseline)

The variance is high (sd ~9 FP on start 1), so this is a **distributional discount, not a
deterministic one** — apply it as an expectation shift on the first start, not a bench rule.

### Velo — INCONCLUSIVE with current data
Using the rolling panel's `avg_velo_last21` (closest weekly cutoff each side of return):
Δvelo = **+0.17 mph** [−0.01, +0.36], n=160 — i.e. **no detectable velo suppression**.
This is almost certainly a **measurement-resolution artifact**, not evidence of no effect:
`avg_velo_last21` is a 21-day trailing average that blends the rusty first start with later
recovered starts and is only sampled at weekly cutoffs. A proper velo-ramp test needs
**per-game pitch-level Statcast velo** (first-start avg velo vs pre-IL avg velo), which is
out of scope for this pull. **Reported honestly as inconclusive.**

---

## 3. Verdict — WORTH WIRING IN (scoped)

**YES — wire the return-ramp into IL-stash valuation, as a first-start expectation
discount, NOT into the rh3/rp3/rprs2 production rankers (which would need the full
`/validate-feature` 9-rule protocol against the real baseline).**

Recommended, defensible use:
1. **IL-stash / return modeling (`/sp-stash-finder`, `/forced-drop-planner`,
   matchup projection for returning SPs):** discount the **first start back** by an
   injury-/layoff-aware amount:
   - layoff >90d or IL60: **≈ −2.5 FP** on start 1 (arm/back injuries worse);
   - 21-90d: **≈ −1.5 FP**;
   - ≤20d or pure lower-body: **negligible (~0)**.
   Regress the discount to ~0 by start 3.
2. **Stint history is independently useful:** real placement→activation gap (vs the IL
   category label) + the coarse `injury_class` median-stint table give a better *return-date
   prior* than ESPN's single guess — directly addresses the stated goal.

What NOT to claim:
- Do **not** treat this as additive point-forecast lift for the validated rankers without
  the full protocol (per CLAUDE.md feedback #1/#13). It's a **context/return-modeling
  layer**, like the lens stack.
- Do **not** claim a velo-ramp signal from this study — the panel velo can't resolve it.
- Exact **surgery type is NOT reliably in the feed** (~51% have any injury text; TJ/UCL
  only n=77). Don't promise surgery-level granularity.

**Bottom line:** Collection succeeded (1,933 paired MLB pitcher stints 2023-25). The
post-IL first-start ramp penalty is real, ~−1.4 FP on average and **−2.5 to −6.5 FP for the
long-layoff / IL60 / arm-injury stash population**, fully recovered by ~start 3. This is
exactly the signal needed to stop over-valuing a returning stash's *immediate* first start
while still correctly valuing it from start 2-3 onward.
