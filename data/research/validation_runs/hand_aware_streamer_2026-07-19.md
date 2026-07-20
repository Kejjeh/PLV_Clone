---
signal: hand_aware_streamer
formula: opp_xwoba_vs_hand_asof = opposing team's season-to-date xwOBA (estimated_woba_using_speedangle fillna woba_value over PA-ending events) accumulated ONLY in PAs against pitchers of the starter's throwing hand, strictly before game date; min 150 team PA vs that hand, else excluded
outcome: fp_proxy of the individual start (per_start_fp_proxy definition — K + 3.3*IP − H − 2*R − BB − HBP, R≈ER proxy, calibrated substrate of sp-breakout-signal)
expected_sign: "-"
theory: lineups are differentially weak/strong vs one pitcher hand beyond their overall strength, so hand-matched opponent xwOBA should predict start FP beyond hand-blind opponent xwOBA
production_target: research-only
framing: in-season per-start (daily streamer/start decision)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_hand_aware_streamer.py
date: 2026-07-19
verdict: REJECTED
---

## Controls (Rule 9 baseline)

Per-start decision-layer candidate (cannot join RP3_FEATS — those are as-of
pitcher aggregates; opponent enters rp3 only via schedule_factor/opp_bat_index,
which are HAND-BLIND). The honest per-start baseline is therefore:

1. `fp_proxy_per_start_to` — the pitcher's own cumulative per-start fp_proxy
   before this start (≥3 prior starts required) = pitcher quality level.
2. `opp_xwoba_overall_asof` — the opposing team's season-to-date xwOBA vs ALL
   hands (≥300 team PA) = the hand-blind opponent strength that opp_bat_index
   already represents in production.

The candidate must add signal BEYOND both. Testing the hand-matched value with
the overall value in the control set is algebraically the delta test
(hand-matched minus overall) — exactly one cell, no sweep (Rule 3 no-op).

## Empirical bounds carried from 2026-07-19 session

- Starters throw 57.3% of IP (2026).
- Starter hand moves the lineup's vs-L PA exposure only 13.4%→65.5%
  (relievers dilute) — but this affects the HITTER-side board. For the
  SP himself the exposure is 100% of his own BF, so no dilution applies
  to this candidate; the bound is noted for scope clarity only.

## Rule 5 / Step 2.5 coverage pre-check

Same-year signal, no lookback. Statcast parquets 2018–2026 local. 2020
excluded (60-game season, as-of samples too thin). 5 training years + 2
holdout years available; ~4,300–4,900 starts/season, thousands qualify
after the ≥3-prior-starts and PA minimums. Clears Rule 2(b) and Rule 5
with wide margin.

## Framing check (Rule 8 analog for per-start)

Convergence-curve analog: partial r computed within season thirds
(Apr–May / Jun–Jul / Aug–Sep) on pooled training years; sign must be
stable. Early-season cells are expected weakest (as-of splits thinnest).

## Priors (pessimistic, pre-declared)

Matchup-feature family is 0-for-3 here (weather REJECTED+CLOSED,
trajectory Δr≈0, Location+ REJECTED). Per-start outcomes are extremely
noisy (sp_floor per-start AUC 0.601 is the calibrated reference).
Expect small or null; the +0.10 partial-r bar (Rule 2a) is a HIGH bar
for any per-start feature and a fail there with a consistent sign may
still merit a Rule-13 context-only note, not promotion.
