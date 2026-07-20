---
name: pitcher-compare
description: 2-6 pitcher head-to-head with a FIRM verdict — the SP/RP parallel of /hitter-compare. Use for "Bradish vs Rogers vs Sheehan, who do I stream", "which of these two SPs do I keep", "A or B for the long haul", any N-way pitcher choice where the answer must be ONE name. Prose recipe over existing engines (no new joins); full 3-lens synthesis per player stays /triangulate.
---

# pitcher-compare

Codifies the 2026-07-18 Bradish-vs-Rogers-vs-Sheehan session: N pitchers, one
table each, one comparative verdict. PROSE over existing owners — build no
new joins.

## Delta vs /triangulate (read this first)

/triangulate answers "what is this player" (3-lens card, verdict,
confidence). THIS skill answers "which of THESE do I take" — it adds the
head-to-head frame: per-start L1/L3/L5 lines side by side, role truth,
career 2H splits, and a forced single-name verdict. When the user wants the
full lens picture on one player, route to /triangulate; when they name 2-6
pitchers and want a choice, stay here. (Both may run — triangulate rows are
one input below.)

## Recipe (per pitcher, ALL of it — Rule 12: show the full stack)

1. **Guards**: ids via `resolve_pitcher_id` (name_match); role truth via
   `detect_pitcher_role` (lib/pitcher_role — incl. the Jax rule: RP-only
   slots + present in rp3 → decide on gamesStarted). /roster-verify before
   any "yours/FA" claim.
2. **Model row**: `xfp_rp3_projections.csv` (SP) / `xfp_rprs2_projections.csv`
   (RP) by mlbam — per_start/xfp_ros, rank, `data_quality_tag` (marcel_il ⇒
   rank by Stuff+ proj_ros_fp instead, fast-path gotcha #1).
3. **Career 2H split**: `python -X utf8 scripts/xfp/run_second_half_splits.py
   --names "A,B,..."` — pre/post-ASG FP-per-unit deltas (the Peralta +1.27
   vs Soriano-fade lens).
4. **Stuff+ & floor**: sp_stuff_model outputs (Stuff+, proj_ros_fp) +
   sp_floor tier (SAFE/MODERATE/RISKY) — mean lens vs downside lens.
5. **Recent actuals**: lib/boom_bust L8 (SP) / L15 (RP) — avg, trend, boom%,
   bust% (the lens that catches model-behind-reality, Bradish canonical).
6. **PL rank + archetype**: pl_cache (cadence-aware staleness) +
   sp_archetype career panel row (OVERALL, trajectory, T+1).

Render one compact table per pitcher, then a side-by-side line of the
headline numbers.

## Verdict synthesis (the part that makes it a decision)

Apply in order — each rule can END the comparison:

1. **DECLINE-RISK veto** (validated, Framber pattern): STUFF-DECLINE tag or
   ≥2 of {archetype STUFF slope down, K%/SwStr YoY decomp down, comps T+1
   poor} eliminates a pitcher regardless of surface stats.
2. **User veto slot**: a stated matchup/trust veto ("I don't trust X vs
   NYY") eliminates without argument — record it in the verdict text.
3. **Skill-backed vs results-driven peaks**: when recent hot stretches
   conflict, prefer the arm whose peak is process-backed (velo/whiff/K-BB
   moving) over results-only (BABIP/strand luck) — cite /sp-form --lens
   breakout tiers if run.
4. **PL-conviction tiebreak**: near-coin-flips break toward the arm PL
   ranks meaningfully higher THIS week (external conviction, cadence-fresh).
5. Still tied → the better 2H split + safer floor tier.

Verdict block must name ONE pitcher, state which rule decided it, and show
the runner-up's counter-case in one line (Rule 12 — no silent flips later:
if new data changes the answer, say what changed).

## When NOT to use

- One pitcher, full picture → /triangulate. Streamer slate ranking →
  /streamer-precision-board. Whole-staff form audit → /sp-form. Cap math →
  /cap-check.
