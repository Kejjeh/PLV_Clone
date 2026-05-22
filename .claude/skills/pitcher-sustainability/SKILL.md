---
name: pitcher-sustainability
description: Decompose a pitcher's 2026 vs prior-year FP/start change into skill-attributable (sustainable) vs luck-attributable (regression-prone) using the 9-marker Statcast checklist (velo, swstr, CSW, chase, K%, BB%, HardHit%, Barrel%, xwOBA-contact). Outputs LEGIT / IMPROVING / STABLE / MIXED / NOISE / BAD_LUCK / REGRESS buckets per pitcher plus bull/base/bear expectations for the rest of season. Use when (a) a pitcher had a monster game or rough stretch and you need to know if it's real, (b) auditing your whole SP staff for who's sustainable vs who's regressing, (c) sizing up FA SPs to see if their 2026 form has skill support behind it. Works for any pitcher in sp_multiyr.csv with at least one prior season.
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

# Summary table only (skip per-pitcher detail)
python scripts/xfp/pitcher_sustainability.py --scope my-roster --brief
```

---

## Understanding the buckets

| Bucket | Criteria | Action |
|---|---|---|
| **LEGIT** | fp_delta ≥ +2.0 AND ≥7/9 markers materially favorable | Trust the breakout; hold/add |
| **IMPROVING** | fp_delta ≥ +2.0 AND 5-6/9 markers favorable | Real but expect partial regression |
| **NOISE** | fp_delta ≥ +2.0 AND ≤3/9 favorable | Production up but skills don't support — likely BABIP fluke |
| **STABLE** | abs(fp_delta) < 2.0 | No story to tell; rely on baseline rp3 |
| **MIXED** | Doesn't cleanly fit above | Read the markers manually |
| **BAD_LUCK** | fp_delta ≤ -2.0 AND ≥4/9 markers HOLDING | Buy-low candidate; results regressing up |
| **REGRESS** | fp_delta ≤ -2.0 AND skills declining | Sell-high if you have him; avoid acquiring |

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
