---
signal: bust_stack_v1
formula: sum of 4 binary downward-process flags at (per-start) — (1) velo_decline_3g (last-3-start mean FB velo - season-mean FB velo <= -1.0 mph), (2) command_collapse (last-3-start BB% - season BB% >= +3 pp), (3) opp_tough_lineup (opp lineup_xfp in TOP tertile within (year, calendar month) slate — soft mirror), (4) recent_short_outings (of last 2 starts, IP < 5.0 OR runs_allowed > 4 fires on either). Bonus 5th component velo_below_career (season FB velo z within (year, month) cohort <= -0.5) tested separately. Range [0, 4].
outcome: per-start actual_FP < 0 (Mode B, bust-rate classifier on all SP starts); ros_fp_per_start (Mode A, integration with rp3 — expected null)
expected_sign: + (higher bust_stack -> higher per-start bust rate)
theory: boom_stack identifies right-tail upward-process windows but leaves a residual ~11% bust rate even at stack=3. The inverse — DOWNWARD process change signals (velo decline, command collapse, tough matchup, short outings) — should isolate the high-EV bench-decision starts that boom_stack misses. Targets bench-the-start decisions for matchup gameplanning.
production_target: rp3 (Mode A integration test, expected null)
framing: per-start outcome (Mode B); in-season -> ros (Mode A)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_bust_stack.py
date: 2026-06-03
verdict: DON'T_SHIP

---

# Pre-registration — bust_stack_v1

## Hypothesis (pre-registered)

**H1 (Mode B, bust-rate classifier — primary):** Within the full SP per-start pool (gs_prior >= 2 to exclude opener / spot starts), per-start bust rate (actual_FP < 0) increases monotonically with `bust_stack`, with `bust_stack >= 3` busting at >= 30% vs `bust_stack == 0` busting at <= 12%. Chi-squared p < 0.05 for the 2x2 (low vs hi) tier separation.

**H2 (per-component bust edge):** Each of the 4 components individually produces bust-rate lift >= +3 pp vs flag=0 at p < 0.05 (per-component chi²). Components that fail this gate are dropped before stack aggregation.

**H3 (Mode A, model integration — expected null):** Adding `bust_stack` to RP3_FEATS does NOT produce a significant cross-year r lift (predicted because (a) RP3_FEATS already contains `delta_k_pct` / `delta_bb_pct` / `ros_opp_xwoba_weighted`, and (b) bust_stack is a left-tail rate flagger, not a conditional-mean improver). We report Mode A as an honesty check, not a ship gate.

## Decision tree

| Outcome | Verdict |
|---|---|
| H1 passes AND H2 passes for >= 3 of 4 components AND stack=3 lift sign-consistent on >= 5 of 7 years | **SHIP_AS_BENCH_FLAG** |
| H1 directionally passes (monotonic chi² p<0.05) but stack=3 bust rate < 25% OR <3 components individually pass H2 OR <5/7 years sign-consistent | **NEEDS_MORE_DATA** (ship-blocked, document for later) |
| H1 fails (no monotonic separation, or chi² p >= 0.05) | **DON'T_SHIP** |

## Anti-leakage discipline

- All components computed using only data STRICTLY before each start's game_date.
- Component 1 (velo_decline_3g): season-mean FB velo and last-3-start mean FB velo are both computed across the pitcher's prior 2026/Year-Y starts at that game_date. <3 prior starts -> flag=0.
- Component 2 (command_collapse): same window as boom_stack's skill_spike but on BB% only.
- Component 3 (opp_tough_lineup): uses the START's OWN `lineup_xfp` value (the actual posted lineup of that game — knowable pre-first-pitch). Tertile within (year, calendar month) cohort, matching boom_stack v1 Mode B framing for direct comparability.
- Component 4 (recent_short_outings): of the pitcher's last 2 prior starts (strictly before this game_date), if EITHER has ip < 5.0 OR runs_allowed > 4, the flag fires. <2 prior starts -> flag=0.
- Bonus component 5 (velo_below_career): season FB velo z-score within (year, calendar month) SP cohort. Excluded from main bust_stack; tested separately.

## Rule 8 / framing match

Mode A run at split_day 30/44/58 convergence. Mode B is per-start, no split_day. Mode B framing matches the boom_stack v1 Mode B framing directly (same per-start panel, same opp tertile cohort definition) for apples-to-apples comparison.

## Rule 5 sample-size pre-check

- Per-start panel 2018-2025 ex-2020: ~31,000 SP starts after PA >= 5 filter.
- Expected per-component fire rates: skill_spike's inverse (~6%), recform's inverse (~13-15% — BB-spike is more common than BB-drop), opp_tough (~33%, by construction), recent_short (~25-30% from prior bust base rate). Stack=3 cohort: rough estimate (.06 * .13 * .33) * 31k = ~80 starts if independent. We'll report actual.
- Stack=4 may be too rare to evaluate (n < 50). We'll fold stack=3 and stack=4 if needed.
- Velo data available for 2018-2025 (statcast game-level).

Verdict for Step 2.5: GO with caveat that stack=4 may be underpowered.

## Bonferroni

Per-component test: 4 components -> alpha = 0.0125. Stack-aggregate test: alpha = 0.05.

---

# Results

(Populated by `scripts/xfp/validate_bust_stack.py` after run.)
