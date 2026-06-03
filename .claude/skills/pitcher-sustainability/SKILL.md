---
name: pitcher-sustainability
description: Augments rp3 (the validated ROS projection) with a 9-marker Statcast skill decomposition (velo, swstr, CSW, chase, K%, BB%, HardHit%, Barrel%, xwOBA-contact). The headline ROS number is rp3.per_start. The sustainability bucket (LEGIT/IMPROVING/STABLE/MIXED/NOISE/BAD_LUCK/REGRESS) is a CONFIDENCE LAYER on that rp3 number. The most valuable output is the DIVERGENCE SIGNAL — when sustainability decomp and rp3 disagree by >1.5 FP, we get BUY-LOW (rp3 hasn't caught up to a real breakout) or SELL-HIGH (production won't sustain, rp3 already conservative) actionable flags. Use when (a) a pitcher had a monster game or rough stretch and you need to know if rp3's number is going to move, (b) auditing your SP staff for hidden regression risk or buy-low candidates, (c) sizing up FA SPs by validated rp3 PLUS skill confirmation.
---

# pitcher-sustainability

You are running a sustainability decomposition on one or more pitchers. The
skill exists because raw FP/start changes are noisy — a +4 FP/start jump
might be 80% skill (real) or 80% BABIP luck (regressing tomorrow). The
9-marker Statcast checklist + structured output makes the call defensible.

The tool reads `data/research/xfp_cache/sp_multiyr.csv` (Statcast aggregates
per pitcher-year, going back to 2021) and compares 2026 vs the most-recent
prior year. No new API calls needed — runs in <2 seconds even for 30+
pitchers.

---

## When to invoke

- A pitcher had a monster outing and the user wants to know "is this real?"
  (e.g., the Kyle Harrison 31 FP game on 5/20)
- The user is auditing their staff: "which of my SPs is at risk of regression?"
- Sizing up FA SPs whose 2026 form looks attractive — distinguish skill jumps
  from BABIP flukes
- Before making a swap call (e.g., FA Add for X / drop Y), confirm both sides
  of the trade with sustainability bucket
- Trade evaluation: "is the SP they're offering sustainable?"

## When NOT to invoke

- Pitcher has only 2026 data (e.g., a rookie callup) — no baseline to compare,
  tool returns NO_BASELINE. Use rolling 21d trend tools instead.
- Single-start sample size (the tool gates at gs ≥ 3 implicitly via the cache).
- RPs — this tool is SP-focused; RP form analysis needs save/hold context too.
- Mid-season trade deadline projections — sustainability is one input but
  schedule density, ballpark, role changes also matter.

---

## Invocation

Three modes:

```bash
# Mode 1: explicit pitcher list (the most common)
python scripts/xfp/pitcher_sustainability.py \
    --players "Kyle Harrison,Framber Valdez,Will Warren"

# Mode 2: all my healthy SPs (auto-pulls from ESPN roster)
python scripts/xfp/pitcher_sustainability.py --scope my-roster

# Mode 3: all FA SPs with 2026 FP/start ≥ threshold
python scripts/xfp/pitcher_sustainability.py \
    --scope fa-pool --min-2026-fp 12

# Universe for fa-pool sweeps: prefer LeagueState.available_fa_meaningful_sp()
# over available_fa(position="SP") — drops zero-start callup / fringe noise
# (returns a (df, summary) tuple), ~6x speedup. Use available_fa() only when
# you need the full unfiltered SP pool.

# Summary table only (skip per-pitcher detail)
python scripts/xfp/pitcher_sustainability.py --scope my-roster --brief
```

---

## Understanding the buckets (confidence layer on rp3)

| Bucket | Criteria | Implication for rp3 |
|---|---|---|
| **LEGIT** | fp_delta ≥ +2.0 AND ≥7/9 markers materially favorable | rp3 may be **conservative** if recent — BUY-LOW candidate |
| **IMPROVING** | fp_delta ≥ +2.0 AND 5-6/9 markers favorable | rp3 reasonable; small upside vs current value |
| **NOISE** | fp_delta ≥ +2.0 AND ≤3/9 favorable | rp3 should be near prior-year; production won't sustain |
| **STABLE** | abs(fp_delta) < 2.0 | Trust rp3 cleanly; no signal |
| **MIXED** | Doesn't cleanly fit above | Read the markers manually |
| **BAD_LUCK** | fp_delta ≤ -2.0 AND ≥4/9 markers HOLDING | rp3 may catch the bounce; **BUY-LOW** |
| **REGRESS** | fp_delta ≤ -2.0 AND skills declining | rp3 may not yet have penalized; **SELL-HIGH** |

## Divergence signals (the actionable layer)

After computing both rp3 (validated) and sustainability E[ROS] (descriptive),
the tool flags pitchers where they disagree by ≥1.5 FP:

> ⚠ **Threshold under review (2026-06-03):** the rp3 σ rescale ×2.41 widened
> the p25/p75 band on every SP. The 1.5-FP divergence threshold was calibrated
> against the pre-rescale band and may now over-fire BUY-LOW / SELL-HIGH at
> the margin. Treat divergences in the 1.5-2.5 FP range as soft signals
> until recalibrated; ≥3 FP divergences still hold.


| Signal | When | Action |
|---|---|---|
| **BUY-LOW** | Sustainability bullish, rp3 conservative | Add before rp3 refresh catches up |
| **SELL-HIGH** | Sustainability bearish, rp3 still high | Drop / trade while value holds |
| **CONFIRM (bullish)** | Both bullish | High-confidence hold/add |
| **CONFIRM (bearish)** | Both bearish | High-confidence avoid/drop |
| **AGREE** | Within 1.5 FP | Trust rp3 |
| **INVESTIGATE** | Disagree but bucket doesn't suggest direction | Manual review |

---

## Understanding the 9 markers

Each marker has a favored direction (+ for K%-like, - for HardHit%-like) and a
"material" threshold (the change must exceed it to count). Marker breakdown:

| Marker | Why it matters | Material if Δ ≥ |
|---|---|---|
| **Velo (mph)** | Pitchers don't fluke 1+ mph year-over-year — pure skill | 0.5 mph |
| **SwStr%** | Swing-and-miss rate — predicts K rate | 1.0 pp |
| **CSW%** | Pitcher List's signature stat — called strikes + whiffs combined | 1.0 pp |
| **Chase%** | Hitters fooled outside zone — pitch design quality | 2.0 pp |
| **K%** | Direct strikeout rate (most predictive single stat) | 2.0 pp |
| **BB%** | Walk rate (less directly improvable but matters) | 1.5 pp |
| **HardHit%** | % of contact at 95+ mph — proxy for damage allowed | 3.0 pp |
| **Barrel%** | % of contact in the "barrel" zone — HR predictor | 1.5 pp |
| **xwOBA-contact** | Expected wOBA when ball is put in play — separates skill from BABIP | 0.020 |

A pitcher with K%, SwStr%, AND xwOBA-contact all favorable simultaneously has
the rare "K-and-soft-contact" combo — the strongest sustainability signal.

---

## Understanding the FP decomposition

The tool splits each FP/start change into:

- **Skill-attributable** = K-rate gain × ~22 BF + xwOBA-contact gain × 20
  (rough: each extra K = +1 FP; .010 xwoba-con improvement ≈ 0.2 FP/start)
- **Luck-attributable** = total fp_delta − skill_attributable

If `luck > 0.5 × fp_delta`, the production gain is dominantly luck-driven and
expect material regression even if the bucket says LEGIT.

---

## Understanding ROS bull/base/bear

Per pitcher, the tool computes:
- **Bull (form sustains)** = current 2026 fp/start
- **Base (halfway regression)** = (2026 + prior) / 2
- **Bear (full revert)** = prior-year fp/start

And weights them per the bucket-based probabilities:

| Bucket | P(bull) | P(base) | P(bear) |
|---|---:|---:|---:|
| LEGIT | 40% | 45% | 15% |
| IMPROVING | 25% | 50% | 25% |
| MIXED | 20% | 40% | 40% |
| NOISE | 10% | 30% | 60% |
| STABLE | 20% | 60% | 20% |
| BAD_LUCK | 40% | 40% | 20% |
| REGRESS | 10% | 30% | 60% |

**E[FP/start] = sum of weighted scenarios.** That's the headline ROS number
the summary table sorts by.

---

## Output interpretation

Per-pitcher block shows:
1. Bucket + n_starts in each year
2. The 9 markers table with ✓ (favorable + material) / · (favorable but not
   material) / ✗ (unfavorable)
3. FP decomposition (skill ≈ X, luck ≈ Y)
4. Bull/base/bear with probabilities and E[ROS FP/start]

Summary table at end sorts by E[ROS FP/start] descending — your best-bet
SP at top.

---

## Anti-patterns this skill exists to prevent

- **Citing `stuff_contact_composite` as an rp3 model feature.** It was
  validated MARGINAL (+0.0021, 7/7 years) on 2026-05-25 — used for
  Signal A alerts in `build_sp_alerts.py` ONLY. Do NOT add the binary
  flag to `RP3_FEATS`. See `/sp-breakout-signal` for the alert use case.
- **Citing `xwoba_contact_to` as an rp3 model feature.** REJECTED
  2026-05-25: algebraically redundant given `xwoba_per_pa_to_sh +
  k_pct_to_sh + bb_pct_to_sh` already in RP3_FEATS (lift = -0.0001).
- **Buying/dropping based on raw FP/start without skill check.** A guy whose
  FP/start jumped 4 might be all luck (NOISE) or all skill (LEGIT) — same
  surface number, opposite verdicts.
- **Treating the bucket as binary.** A LEGIT pitcher with strong bull case is
  not a guarantee — there's still 15% bear case. Use the bull/base/bear
  spread to size the bet.
- **Comparing prior year n=24 to current n=4 as if they're equivalent.** The
  cache reports n_starts; if 2026 sample is < 5, treat the bucket as
  preliminary and downweight your confidence.
- **Running for a rookie with no prior year.** Tool returns NO_BASELINE —
  don't fake a comparison; admit no data.
- **Forgetting BB% counterweight.** Lots of pitchers improve K% via more
  aggressive sequencing but BB% climbs too. Net FP impact can be flat. Check
  K%-BB% gap, not just K%.

---

## Validation patterns

- Run after any "monster game" question to keep recommendations defensible
- Run BEFORE recommending an SP swap (both sides should be classified)
- Run on full SP staff once weekly to catch buy-low / sell-high opportunities
- Cross-reference NOISE-bucket FA SPs with PL: if PL also flags concerns,
  high confidence to avoid
- Cross-reference LEGIT-bucket FA SPs with PL: if PL is bullish too,
  high confidence to add

---

## When NOT to use this skill

- For RPs — out of scope (cached data is SP-focused)
- For year-1 rookies — no baseline, tool will say so
- For point estimates of a single start (use rp3 + opp_factor instead)
- For multi-year career projections (use rp3's rest-of-season directly)
