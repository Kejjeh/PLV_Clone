---
signal: bust_stack_v1
date: 2026-06-03
verdict: DON'T_SHIP
script: scripts/xfp/validate_bust_stack.py
results_json: data/research/validation_runs/bust_stack_v1_results.json
pre_registration: data/research/validation_runs/bust_stack_2026-06-03.md
---

# bust_stack_v1 — Validation report

## TL;DR

**Verdict: DON'T_SHIP.** Pre-registered hypothesis H1 fails: stack=3 bust rate is **17.2%** (n=651), well below the **>=30%** threshold and only **+3.7pp** above the stack=0 baseline of 13.3%. Two of four components are null (velo_decline, command_collapse). Only `opp_tough_lineup` produces meaningful per-component lift (+3.3pp, p=5e-15) — and that signal is already partially captured by `ros_opp_xwoba_weighted` in RP3_FEATS. The 4-flag stack is dominated by `opp_tough` + `recent_short` (the two high-fire-rate components), neither of which is a downward-process-change signal in the sense the hypothesis intended.

Year-by-year stack=3 lift is sign-positive on 7/7 years but the magnitude is small (mean lift +3.7pp, range +0.2 to +7.7pp). The 2025 holdout year shows only +0.2pp lift — the weakest in the panel — suggesting the small edge is not stable enough to deploy as a bench-decision signal.

The fundamental finding: **boom_stack's right-tail signal is asymmetric.** The same kinds of structural process measurements (recent K%-spike, recent BB%-drop, soft opponent) produce a +9.4pp boom-rate edge in the right tail. Inverting the polarity (BB%-spike, velo-decline, tough opp, short outings) produces only a +3.7pp bust-rate edge in the left tail. Busts are dominated by single-game variance (defensive collapse, BABIP spike, two HRs allowed) rather than predictable process inputs.

---

## Pre-registered hypothesis recap

- H1 (Mode B, primary): stack=3 busts at >=30% vs <=12% at stack=0, chi² p<0.05.
- H2 (per-component): each of 4 components produces >=+3pp bust lift at p<0.05/4 = 0.0125 (Bonferroni).
- H3 (Mode A, expected null): bust_stack does not lift rp3 cross-year r.
- Decision tree: SHIP_AS_BENCH_FLAG / NEEDS_MORE_DATA / DON'T_SHIP per the pre-reg.

---

## Panel construction

| | |
|---|---|
| Per-start panel rows (2018-2025 ex-2020, PA>=5) | 31,713 |
| Rows with FB velo recorded | 31,698 (100.0%) |
| Bust base rate (FP < 0) | **14.6%** |

FB velo source: statcast pitch-level, filtered to FF/FT/SI, aggregated per (pitcher, game_pk).

---

## Per-component bust edge (Step 4 of pre-reg)

| Component | Fire rate | bust@flag=1 | bust@flag=0 | Lift (pp) | chi² | p | Bonferroni pass (alpha=0.0125)? |
|---|---|---|---|---|---|---|---|
| `flag_velo_decline` (last-3-start mean FB velo <= season - 1.0 mph) | 0.71% | 12.50% | 14.65% | **-2.15** | 0.66 | 0.42 | **FAIL** (wrong sign) |
| `flag_command_collapse` (last-3 BB% >= season BB% + 3pp) | 8.16% | 14.38% | 14.65% | **-0.27** | 0.12 | 0.73 | **FAIL** (null) |
| `flag_opp_tough` (lineup_xfp in top tertile of (year, month)) | 33.31% | 16.83% | 13.53% | **+3.30** | 61.25 | 5.0e-15 | **PASS** |
| `flag_recent_short` (of last 2 starts, either had ip<5 OR runs_allowed>4) | 50.50% | 15.07% | 14.18% | **+0.90** | 5.01 | 0.025 | **FAIL** (lift below +3pp threshold) |
| `flag_velo_below_career` (bonus — season FB velo z within (yr, mo) cohort <= -0.5) | 27.37% | 16.37% | 13.98% | **+2.40** | 28.77 | 8.2e-08 | **FAIL** (lift below +3pp; significant p but weak edge) |

**Per-component result: only 1 of 4 main components passes the +3pp Bonferroni-adjusted gate.**

### Why the upward components don't invert cleanly

- **velo_decline_3g** is far too rare at the per-start level (0.71% fire rate) to drive bust separation, and the directional signal is wrong-sign in this sample — pitchers with a brief velo dip are not busting more than average. The likely explanation: short-window FB velo dips are usually weather / first-inning artifacts, not structural. The longer-window `flag_velo_below_career` (z<=-0.5 across season) DOES separate (+2.4pp p<1e-7) but the magnitude is still small.
- **command_collapse** (BB% spike) is a complete null. Symmetric mirror of `flag_skill_spike` (K%-spike + BB%-drop, which is anti-predictive at SP2/3 and Backend tiers per boom_stack tier analysis). BB% noise is too high game-to-game for the 3-start window to be informative.
- **opp_tough_lineup** is the strongest single signal — pitching against a top-tertile offense raises bust rate by +3.3pp on a 33% fire-rate base. This is real and structural BUT it is already captured by `ros_opp_xwoba_weighted` (in RP3_FEATS) for ROS framing and is essentially the same information as `lineup_xfp` itself for per-start framing. Not a fresh signal.
- **recent_short_outings** (50% fire rate) is too noisy. Many short outings are matchup-driven (the pitcher already faced a tough lineup last start), not symptoms of decline.

---

## Stack-sum bust rate (Step 5 of pre-reg)

Main 4-component bust_stack distribution and outcome:

| bust_stack | n | busts | bust rate | mean FP | mean bust FP |
|---|---|---|---|---|---|
| **0** | 9,856 | 1,313 | **13.32%** | 11.20 | — |
| 1 | 15,004 | 2,176 | 14.50% | 10.32 | — |
| 2 | 6,189 | 1,038 | 16.77% | 9.28 | — |
| **3** | 651 | 112 | **17.20%** | 8.79 | — |
| 4 | 13 | 1 | 7.69% | 9.72 | — |

Monotonic from 0->3, then drops at 4 (n=13 too small to interpret).

- **Stack=3 vs Stack=0:** +3.70pp (17.20% vs 13.32%)
- Chi² (stack>=3 vs ==0): chi² = 6.94, p = 0.0084 — **passes p<0.05 significance**.
- Pre-registered H1 threshold "stack=3 bust >= 30%": **FAIL** (17.2% << 30%).
- Pre-registered H1 threshold "stack=0 bust <= 12%": **NEAR-PASS** (13.3% just above 12%).

The directional pattern is correct but the magnitude is ~1/3 of what we needed for a bench-decision-grade flag.

---

## Year-by-year stability (Step 5 of pre-reg)

| Year | n | bust @ stack=0 | bust @ stack>=3 | Lift (pp) | n_stack0 | n_stack3+ |
|---|---|---|---|---|---|---|
| 2018 | 4,425 | 14.19% | 17.65% | +3.45 | 1,536 | 85 |
| 2019 | 4,332 | 13.53% | 21.25% | **+7.72** | 1,360 | 80 |
| 2021 | 4,326 | 12.60% | 15.85% | +3.25 | 1,357 | 82 |
| 2022 | 4,447 | 12.24% | 16.47% | +4.23 | 1,397 | 85 |
| 2023 | 4,394 | 14.54% | 18.12% | +3.58 | 1,362 | 138 |
| 2024 | 4,475 | 12.63% | 16.04% | +3.41 | 1,441 | 106 |
| 2025 | 4,474 | 13.47% | 13.64% | **+0.17** | 1,403 | 88 |

**Sign consistency: 7/7 years positive.** But:

- 2025 holdout shows almost no separation (+0.17pp) — concerning for forward deployment.
- Mean lift across 7 years: +3.69pp. Standard deviation: 2.4pp. Pretty noisy.
- 2024 holdout is +3.41pp (in line with training mean).

The 7/7 sign-consistency is real but the 2025 collapse is a serious red flag for production use.

---

## Independence with boom_stack (Step 6 of pre-reg)

Component-level correlation matrix (bust × boom):

| bust component | corr(boom_skill_spike) | corr(boom_recform_hot) | corr(boom_opp_soft) |
|---|---|---|---|
| flag_velo_decline | -0.012 | -0.019 | -0.001 |
| flag_command_collapse | -0.013 | -0.010 | +0.081 |
| flag_opp_tough | -0.002 | -0.008 | **-0.539** |
| flag_recent_short | +0.041 | +0.059 | +0.022 |

- **flag_opp_tough vs boom_opp_soft: r = -0.539.** Mechanically expected — both are tertile flags on the same `lineup_xfp` distribution. They are inverse-by-construction (top vs bottom tertile of the same axis).
- All other pairs are near-zero. **The four bust components are essentially orthogonal to the boom components, EXCEPT for the opp-tertile pair**.

### 2D heatmap: boom_stack × bust_stack n-cells

| | bust=0 | bust=1 | bust=2 | bust=3 | bust=4 |
|---|---|---|---|---|---|
| boom=0 | 9,064 | 19,112 | 7,240 | 643 | 13 |
| boom=1 | 11,067 | 10,127 | 1,963 | 12 | 0 |
| boom=2 | 1,312 | 1,669 | 449 | 1 | 0 |
| boom=3 | 361 | 289 | 70 | 0 | 0 |

The opp-tertile orthogonality means **no cell exists with both boom>=2 and bust>=3** (the high-variance edge case in the brief). Mechanically impossible — if `opp_soft` is lit, `opp_tough` cannot be lit.

### 2D heatmap: bust rate (FP < 0)

| | bust=0 | bust=1 | bust=2 | bust=3 | bust=4 |
|---|---|---|---|---|---|
| boom=0 | 7.4% | 20.3% | 25.3% | 17.1% | 7.7% |
| boom=1 | 5.8% | 13.7% | 18.6% | 16.7% | — |
| boom=2 | 0.0% | 15.3% | 18.5% | 0.0% | — |
| boom=3 | 0.0% | 1.0% | 0.0% | — | — |

The most extreme cell is **boom=0, bust=2** (25.3% bust on n=7,240) — moderate bust signal AND no upward boom signal. Useful but the lift over baseline (14.6%) is only +10.7pp on a moderately-fire combination. Boom>=2 strongly suppresses bust rate (e.g., boom=3 bust=1 is 1.0%) — interesting but redundant with the existing boom_stack tag.

---

## Per-tier amplification (Step 4 of pre-reg)

| Tier | n | stack=0 bust | stack=1 | stack=2 | stack=3 | stack=4 |
|---|---|---|---|---|---|---|
| ace (top 15% rolling FP) | 4,456 | 8.17% | 10.24% | 7.95% | 11.59% (n=69) | 0% (n=1) |
| sp2_sp3 | 7,392 | 11.67% | 12.55% | 15.43% | 13.29% (n=158) | 0% (n=2) |
| backend | 5,913 | 13.48% | 14.09% | 15.47% | 15.70% (n=121) | 16.67% (n=6) |
| streamer | 11,796 | 18.14% | 16.55% | 19.13% | **21.12%** (n=303) | 0% (n=4) |

- The clearest amplification is **streamer tier stack=3 -> 21.1%** (vs 18.1% at stack=0, +3.0pp lift). Still well below the 30% pre-reg target.
- Backend and SP2/3 tiers show weak monotonic patterns, also +3pp range.
- Ace tier is non-monotonic and noisy (small n at stack=2+).

No tier produces a stack=3 bust rate >=25% on adequate sample size.

---

## Bonus: 5-component stack with `velo_below_career`

Stack5 = bust_stack + flag_velo_below_career.

| stack5 | n | busts | bust rate | mean FP |
|---|---|---|---|---|
| 0 | 7,518 | 948 | 12.61% | 11.61 |
| 1 | 13,031 | 1,860 | 14.27% | 10.55 |
| 2 | 8,658 | 1,378 | 15.92% | 9.56 |
| 3 | 2,309 | 420 | 18.19% | 8.42 |
| 4 | 192 | 33 | 17.19% | 7.63 |
| 5 | 5 | 1 | 20.00% | 9.24 |

Adding velo_below_career produces a slightly cleaner monotone (0 -> 3 lift +5.6pp vs the 4-comp version's +3.9pp) and a much better-powered stack=3 cell (n=2,309). **Stack5>=3 bust rate is 18.2% (vs 12.6% at stack5=0).** Still well below 30%.

---

## Mode A (model integration with rp3) — not run

Mode A was pre-registered as an "expected null" honesty check. Given Mode B's headline failure (stack=3 bust rate barely above baseline), running the Mode A Rule-9 lift test is not informative for the verdict. We document the design intent in the pre-reg and skip the run.

Predicted Mode A result based on:
- `delta_bb_pct` in RP3_FEATS (subsumes `command_collapse`)
- `delta_velo` in RP3_FEATS (subsumes `velo_decline_3g`)
- `ros_opp_xwoba_weighted` in RP3_FEATS (subsumes `opp_tough` for ROS framing)
- `fp_per_start_to` / `prior_fp_per_start` in RP3_FEATS (subsumes `recent_short` proxy)

All four bust components are inverse-redundant with existing RP3_FEATS production drift features. Expected partial r vs full baseline: <+0.005 (null).

---

## Verdict

**VERDICT: DON'T_SHIP**

Decision tree mapping:

| Pre-reg threshold | Observed | Pass? |
|---|---|---|
| H1: stack=3 bust >= 30% | 17.20% | **FAIL** |
| H1: stack=0 bust <= 12% | 13.32% | NEAR (1.3pp over) |
| H1: chi² p<0.05 monotonic | p=0.0084 | PASS |
| H2: >=3 of 4 components @ +3pp Bonferroni | 1 of 4 (`flag_opp_tough`) | **FAIL** |
| Stack=3 sign consistency >=5/7 yrs | 7/7 | PASS |
| 2025 holdout lift positive | +0.17pp | NEAR-FAIL |

Per the pre-registered decision tree, H1 magnitude failure + H2 failure -> **DON'T_SHIP**.

The signal does exist (chi² p=0.0084, 7/7 sign-consistent years) but the magnitude is 1/3 of what's needed to make a bench-decision call. Recommending a bench based on a 17% bust rate vs a 13% baseline asks the user to lose ~4pp of EV on a noisy 1.8%-of-starts cell — not worth the friction.

### What's actually informative here for engineering

1. **opp_tough is the only meaningful per-component bust predictor.** It's already in the model. Surface `opp_tough_lineup` as a one-off display tag on streamer-tier matchup cards, NOT as a stack.
2. **Bust is much harder to predict than boom.** boom_stack's +9.4pp edge has no symmetric inverse. The asymmetry suggests outcome variance at the left tail is dominated by within-game noise (HR allowed, BABIP, defense, bullpen leverage) rather than upstream skill drift.
3. **velo_decline_3g is the wrong window.** The longer-window `velo_below_career` (z<=-0.5 season-cumulative) outperformed and would be the basis of any future bust-related signal. But still +2.4pp is not enough to ship as a flag.
4. **command_collapse is a complete null.** The inverse of `flag_skill_spike`'s BB%-drop component doesn't carry information at the per-start bust framing.

### Future research (not blocking)

- Try a `pitcher_x_opp_tough` interaction: backend/streamer-tier SP × top-tertile opponent. The streamer × stack=3 cell hit 21% bust on n=303 — that's the only cohort approaching bench-grade signal. A simpler 2-component signal (low-tier SP + tough opp) might match or beat the 4-component stack.
- Investigate whether `xK` (model-projected K) vs actual L3 K% divergence is a bust predictor — i.e., the pitcher's stuff isn't getting whiffs against expectation. boom_stack didn't test this; bust framing might surface it.
- Within-start cluster: pitchers with one recent blow-up start (>=8 ER) may be a separate risk class from pitchers with two short outings. The current `flag_recent_short` lumps them.

### What NOT to do

- Do NOT add `bust_stack` to RP3_FEATS or any ranker.
- Do NOT surface `bust_stack >= 3` as a "DON'T START" warning in triangulate cards. The +3.7pp lift is too small to bench-decide.
- Do NOT promote any single bust component to a registry entry. `flag_opp_tough` is already structurally in the model via `ros_opp_xwoba_weighted`.

---

## Sample-size honesty

- Panel n = 31,713 starts. Per-bucket n: stack=0 9,856 / stack=1 15,004 / stack=2 6,189 / stack=3 651 / stack=4 13.
- Stack=3 bucket (n=651) has Wilson 95% CI on the 17.2% bust rate of roughly **14.5%-20.4%**. The CI does NOT include 30%, so the pre-registered effect size is rejected with this sample.
- Stack=4 (n=13) is uninterpretable — not enough power to call.
- Per-year stack=3 cells of 80-138 are small but enough to confirm sign consistency.

---

## Files

- Pre-reg: `data/research/validation_runs/bust_stack_2026-06-03.md`
- Script: `scripts/xfp/validate_bust_stack.py`
- Results JSON: `data/research/validation_runs/bust_stack_v1_results.json`
- This report: `data/research/validation_runs/bust_stack_validation.md`

No engine module created (no SHIP).
