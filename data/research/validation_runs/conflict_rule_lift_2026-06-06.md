# Conflict resolution rule lift test — 2026-06-06

## Method

- Hitter snapshots: 1383  |  SP snapshots: 463
- Source: `shrinkage_h_snap_2026-06-06.parquet` + `shrinkage_sp_snap_2026-06-06.parquet`
- Forward outcome: `target` = mean BrownU FP/g (hitter, next 30d) or FP/start (SP, next 5 starts)
- Tier B lenses (sustainability bucket, xwOBA L21d gap, xwOBACON YoY) are NOT in the parquets;
  we approximate them from the L21/L42/prior/prior2 ladder. These are LOOKALIKE not exact matches.
- Win = rule-applied verdict's predicted FP is closer to `target` than the naive verdict's.

### Proxy mapping per rule
- Rule 1: model FADE = model < prior - 0.2sd; L5 BUY = L21 > L42 + 0.5sd; NOISE = L21 hot but L42~prior
- Rule 2: CAP_FODDER = L21 < prior - 0.4sd; xwOBA intact = |L42 - prior| < 0.2sd
- Rule 3: REAL_DECLINE = L21 < L42 - 0.5sd; RISING xwOBACON = prior > prior2 + 0.15sd
- Rule 4: REGRESS = L21 < L42 - 0.4sd; CAP_FODDER = L21 < prior - 0.4sd; repl-level = model in bottom Q
- Rule 5: hot = L21 > L42 + 0.7sd; capped discipline = |L42 - prior| < 0.2sd; rising = prior > prior2 + 0.15sd

## Rule 1: Model FADE + actuals BUY -> NOISE -> trust model (fade hot streak)

**Verdict: SMALL_N (6) — pooled win rate 16.67%**

### Hitter cases
  - n: 6
  - win_rate: 0.167
  - lift_mae: -0.154
  - regression_amount: -0.009
  - mean_target: 2.594
  - mean_actuals_recent: 2.586
  - mean_model: 2.752

### SP cases
  n=0 — no matching cases

## Rule 2: CAP_FODDER + xwOBA gap intact -> HOLD (process trumps boom-bust)

**Verdict: VALIDATED — pooled win rate 68.75% on n=96**

### Hitter cases
  - n: 72
  - win_rate: 0.667
  - lift_mae: 0.324
  - bounce_amount: 0.723
  - mean_target: 2.131
  - mean_actuals_recent: 1.409
  - mean_prior: 2.185

### SP cases
  - n: 24
  - win_rate: 0.750
  - lift_mae: 2.307
  - bounce_amount: 4.512
  - mean_target: 13.233
  - mean_actuals_recent: 8.722
  - mean_prior: 13.436

## Rule 3: REAL_DECLINE L21d + RISING xwOBACON -> HOLD with sell-high optionality

**Verdict: VALIDATED — pooled win rate 63.08% on n=65**

### Hitter cases
  - n: 46
  - win_rate: 0.674
  - lift_mae: 0.277
  - recovery_amount: 0.869
  - mean_target: 2.435
  - mean_actuals_recent: 1.566
  - mean_baseline: 2.457

### SP cases
  - n: 19
  - win_rate: 0.526
  - lift_mae: 1.091
  - recovery_amount: 4.010
  - mean_target: 13.224
  - mean_actuals_recent: 9.215
  - mean_baseline: 14.325

## Rule 4: REGRESS + CAP_FODDER + replacement-level Blended xFP -> HIGH_CONFIDENCE drop

**Verdict: REJECTED — pooled win rate 36.90% on n=84**

### Hitter cases
  - n: 63
  - win_rate: 0.349
  - lift_mae: -0.026
  - pct_below_prior: 0.444
  - mean_target: 1.752
  - mean_actuals_recent: 0.586
  - mean_model: 1.515
  - mean_prior: 1.643
  - repl_thresh: 1.820

### SP cases
  - n: 21
  - win_rate: 0.429
  - lift_mae: -0.147
  - pct_below_prior: 0.429
  - mean_target: 10.813
  - mean_actuals_recent: 2.127
  - mean_model: 8.543
  - mean_prior: 9.551
  - repl_thresh: 11.025

## Rule 5: Hot streak + capped discipline + RISING xwOBACON -> NARROW BREAKOUT (expect revert)

**Verdict: VALIDATED — pooled win rate 81.82% on n=11**

### Hitter cases
  - n: 9
  - win_rate: 0.778
  - lift_mae: 0.267
  - pct_reverted_below_hot: 0.889
  - pct_stayed_above_prior: 0.444
  - mean_target: 2.864
  - mean_actuals_recent: 3.937
  - mean_prior: 3.054
  - mean_rule_midpoint: 3.500

### SP cases
  - n: 2
  - win_rate: 1.000
  - lift_mae: 2.142
  - pct_reverted_below_hot: 1.000
  - pct_stayed_above_prior: 0.500
  - mean_target: 14.350
  - mean_actuals_recent: 18.000
  - mean_prior: 13.697
  - mean_rule_midpoint: 15.858

## Caveats

1. **Lookalike, not exact.** The protocol's Tier B lenses (sustainability bucket label,
   xwOBA L21d gap, xwOBACON YoY trajectory) are NOT in these parquets. We synthesize
   from L21/L42/prior/prior2 FP rates. A real sus=NOISE/LEGIT label uses Statcast skill
   markers, not FP rate ladders. So these tests bound the protocol's mechanical logic,
   not its actual Tier B signal quality.
2. **Forward target is 30 days, not season-EoY.** The 30d window can under-weight mean
   reversion that plays out over 60+ days.
3. **Small N for Rule 3 + 5** because prior2_avg is missing on 56% of hitter rows (rookies
   + recent debuts). These are the rules most at risk of N=0.
4. **Win metric is MAE-based.** A rule that's directionally right but quantitatively off
   can still 'win' the case; we report mean target vs mean rule-predicted-FP alongside.
5. **Bayes shrinkage as model proxy** under-states Tier A — the real Blended xFP includes
   archetype + PL + multi-feature blend. So 'model FADE' here is conservative.
