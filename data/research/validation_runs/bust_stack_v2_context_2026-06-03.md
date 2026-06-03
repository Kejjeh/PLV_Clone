---
signal: bust_stack_v2_context
formula: sum of N binary GAME-CONTEXT bust flags at (per-start), each computed using only data strictly before the start's game_date. Candidate components — (1) flag_first_back_long_IL (gap >= 30 days since pitcher's previous start in same season), (2) flag_short_rest (pitcher_days_since_prev_game <= 4), (3) flag_taxed_bullpen (sum of bullpen IP for SP's team in prior 3 days >= 8.0), (4) flag_extreme_prior (prior start pitches >= 110 OR ip < 3.0), (5) flag_day_after_night (SP's team played a game the prior calendar day — proxy for travel/late-night). Weather (wind) skipped — data unavailable.
outcome: per-start actual_FP < 0 (Mode B, bust-rate classifier)
expected_sign: + (higher context_stack -> higher per-start bust rate)
theory: v1 (process-based bust_stack) failed because bust is dominated by within-game noise rather than upstream skill drift. v2 reframes — maybe bust isn't about WHO the pitcher has been, but WHAT THE GAME LOOKS LIKE today. Context features (fatigue, scheduling, rust, taxed pen) might catch a different signal entirely.
production_target: bench-decision flag (Mode B only); Mode A not run
framing: per-start outcome (Mode B)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_bust_stack_v2_context.py
date: 2026-06-03

---

# Pre-registration — bust_stack_v2_context

## Hypothesis (pre-registered)

**H1 (Mode B, primary):** Within the full SP per-start pool (n_prior >= 2), a 4-or-5-component GAME-CONTEXT `bust_stack_v2` predicts per-start bust rate (actual_FP < 0). Stack=3 cohort busts at >= 25% (vs baseline 14%) with chi² p < 0.05.

**H2 (per-component):** Each candidate component produces bust-rate lift >= +2 pp at Bonferroni-corrected p < 0.0125 (4 tests; if 5 components ship, alpha = 0.01).

**H3 (year stability):** Stack=3 sign-positive on >= 5/7 years.

**H4 (independence from boom_stack):** All v2 context components have |r| < 0.15 with all boom_stack components — these are CONTEXT not PROCESS, should be orthogonal by construction.

## Decision tree

| Outcome | Verdict |
|---|---|
| H1 passes (stack=3 bust >= 25%, chi² p<0.05) AND H2 passes for >= 3 components AND >= 5/7 years sign-positive | **SHIP_AS_BENCH_FLAG** |
| H1 directionally passes (monotonic chi² p<0.05) but stack=3 bust < 22% OR <3 components OR <5/7 years | **NEEDS_MORE_DATA** |
| H1 fails (no monotonic separation, chi² p>=0.05) | **DON'T_SHIP** |

## Anti-leakage discipline

- All components computed from data STRICTLY before each start's game_date.
- `flag_first_back_long_IL`: gap between this start and previous start (same pitcher, same season). NaN if first start of season. Threshold 30 days.
- `flag_short_rest`: statcast's `pitcher_days_since_prev_game` <= 4. NaN -> 0.
- `flag_taxed_bullpen`: sum of IP across all non-SP pitchers on the SP's team across game_dates in [game_date-3, game_date-1]. Identified SP team via inning 1 `inning_topbot` mapping. SP of a game = pitchers who threw inning 1 of any game on that date; bullpen = all other pitchers on the team that day. Threshold >= 8.0 IP.
- `flag_extreme_prior`: pitcher's most recent prior start had `pitches >= 110` OR `ip < 3.0`. First start of season -> 0.
- `flag_day_after_night`: SP's team had a game on the prior calendar day. Proxy for the night-game-into-day-game pattern. We can't filter to NIGHT specifically without game-time data, but the prior-day-game flag is a partial proxy.

## Rule 8 / framing match

Mode B only. Same per-start panel as v1 (n ≈ 31,713) for direct comparability.

## Rule 5 sample-size pre-check

- Expected fire rates: first_back_long_IL ~1-2% (small cohort, likely n=300-600), short_rest ~10-15%, taxed_bullpen ~25-35%, extreme_prior ~10-15%, day_after_night ~60-70% (very common — most teams play near-daily).
- Stack=3 cell expected n ~ 31k * (0.015 * 0.13 * 0.30) ≈ 180 starts if independent. Sufficient if effect size lift is sizeable.
- Sample-size honesty: first_back_long_IL cohort is small; we'll report the per-component result honestly even if underpowered.

Verdict for Step 2.5: GO.

## Bonferroni

5 components -> alpha = 0.01 per component. Stack-aggregate alpha = 0.05.

---

# Results

(Populated by `scripts/xfp/validate_bust_stack_v2_context.py` after run.)
