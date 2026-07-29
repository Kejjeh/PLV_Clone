# Savant rolling xwOBA leaderboards (L50 / L150 / L250 PA) — are they meaningful for FP?

**Date:** 2026-07-28
**Status:** VALIDATED (leakage-safe, 6-season replication). **No model change** (Rule 13).
Hitter increment is a CANDIDATE for `/validate-feature`; SP side is a definitive NO.
**Trigger:** "Savant has rolling xwOBA leaderboards for hitters and pitchers at L50/L150/L250 PA
— are these meaningful for FP?"
**Engines:** `scripts/_oneoff/validate_rolling_xwoba.py` (panel + first pass),
`scripts/_oneoff/validate_rolling_xwoba_matched.py` (matched-sample + production control).
Panels → `.cache/rolling_xwoba_panel_{H,SP}.csv`.

## Why this wasn't already answered

`window_predictive_validity_2026-06-26.md` tested **calendar** windows (L7/L14/L21/L30) and found
**xwOBACON redundant** beyond the FP level. That is *contact quality only*, on a *date* window.
Savant publishes something different: **full xwOBA** (K/BB/HBP included via `woba_value`,
BBE via `estimated_woba_using_speedangle`) on a **PA-denominated** window. Different metric,
different denominator, longer horizon → re-test warranted.

## Method

- **Panel:** 2021–2026, per-PA statcast rows (`woba_denom==1`) in chronological order; per-game
  BrownU FP from `multiyr_boxscore_fp.parquet`.
- **Forward target:** hitters = FP/g over `(t, t+14d]`, ≥4 games; SPs = FP/start over
  `(t, t+21d]`, ≥2 starts. Trailing windows end at `t` inclusive → no overlap.
- **Anchors ≥14d apart** per player-season (forward windows non-overlapping).
- **Matched sample:** all of L50/L150/L250 present, else the long window is silently scored on a
  different (durable, late-season) population. Hitters n=7,657 / 575 players; SPs n=3,452 / 347.
- CIs = **player-cluster bootstrap** (B=600). Controls residualized jointly via lstsq.

## Results

### Marginal r → forward FP (matched sample, same rows for every predictor)

| Predictor | Hitters | SPs |
|---|---|---|
| rolling xwOBA L50 | +0.237 | −0.163 |
| rolling xwOBA L150 | +0.299 | −0.252 |
| rolling xwOBA L250 | +0.314 | −0.288 |
| xwOBA season-to-date | +0.317 | **−0.320** |
| **FP level (shrunk, rh3-proxy)** | **+0.372** | **+0.333** |

Longer window is monotonically better in both buckets — same shape as the 2026-06-26 calendar-window
result, and the same reading: **longer windows estimate the level more precisely; older PAs don't
matter more.** No rolling window beats the plain FP level, and none beats season-to-date xwOBA.

### Incremental over the FP level alone

Both buckets ADD (hitters L150 +0.090 [.068,.115]; SPs L250 −0.066 [−.096,−.032]) — i.e. xwOBA
carries real forward signal that raw FP/g does not, which is exactly why it strips run-scoring context.

### Incremental over PRODUCTION (the decisive test)

**`rh3` and `rp3` already include `xwoba_per_pa_to_sh`** — shrunk season-to-date xwOBA per PA
(`RH3_FEATS` / `RP3_FEATS`; hitter shrink K=300 PA). So the only thing the *rolling leaderboard*
can offer is signal beyond that season number. Control = `[season-to-date xwOBA, shrunk level, PT]`.

| Window | Hitters | SPs |
|---|---|---|
| L50 | **+0.054 [+.028,+.074] ADDS** | +0.003 [−.029,+.036] redundant |
| L150 | **+0.062 [+.035,+.084] ADDS** | −0.008 [−.043,+.027] redundant |
| L250 | **+0.051 [+.030,+.076] ADDS** | −0.004 [−.041,+.033] redundant |

Per-season (L250): hitters +0.036 / **+0.003** / +0.068 / +0.089 / +0.040 / +0.080 (2022 is a null);
SPs +0.003 / −0.003 / −0.022 / −0.015 / +0.021 / −0.025 — **sign flips, centered on zero, 6/6.**

### Practical magnitude (forward FP by rolling-xwOBA quintile, WITHIN level tercile)

| Level tercile | Hitters Q1→Q5 (FP/g) | SPs Q1→Q5 (FP/start) |
|---|---|---|
| low | 1.37 → 1.74 (+0.38) | 9.92 → 7.67 (−2.25) |
| mid | 1.87 → 2.25 (+0.38) | 11.26 → 10.73 (−0.53) |
| high | 2.29 → 2.96 (**+0.67**) | 15.36 → 12.26 (**−3.10**) |

(SP direction is inverted — low xwOBA-against = good. The SP spread is real but it is the *season*
xwOBA doing the work, not the rolling window.)

## Verdict

1. **SPs — NO.** The rolling leaderboard is fully redundant with season-to-date xwOBA-against,
   which `rp3` already ingests. Reading L50/L150/L250 for a starter adds nothing and the short
   windows actively invite the trajectory error already closed by CLAUDE.md #11. **Don't use it.**
2. **Hitters — a real but SMALL increment** (partial r ≈ +0.05–0.06 beyond the season xwOBA in the
   model), replicating 5/6 seasons. Sweet spot **L150**. Enough to justify a `/validate-feature`
   run on `xwoba_L150pa` as an rh3 candidate; **not** enough to move a headline verdict on its own.
3. **Never use L50** as a standalone read — marginal r +0.237 is the weakest of the three and its
   increment is not separable from L150's.
4. Consistent with Rule 13 and with the 2026-06-26 finding: this is a **context/conviction** lens,
   not a point-forecast booster. Headline stays rh3/rp3.

## Caveats

- Control is *un-shrunk* season xwOBA; rh3 uses the K=300-shrunk version, so the true increment
  over production is plausibly a touch smaller than the +0.05–0.06 measured here.
- Population = established regulars (≥15 games / ≥8 starts AND ≥250 PA/BF). Does **not** extend to
  callups, platoons, or post-IL ramps — exactly where a short window might encode a role change.
- 2022 hitters replicate at +0.003. The pooled CI excludes 0, but one season carries no effect.
- Effect sizes throughout are tilts (r ≈ 0.05–0.09), not strong predictors.
