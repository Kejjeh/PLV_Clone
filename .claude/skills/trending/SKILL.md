---
name: trending
description: Detect which players are physically getting better or worse RIGHT NOW from fast-stabilizing physical signals — bat speed for hitters, fastball velocity for pitchers — 2026-to-date vs prior-year baseline, z-scored, with the contact/results column as confirmation. Default scope = your full roster (split by role) + top FA risers; `--names "A,B,C"` for ad-hoc trend cards. Use when the user asks "who's trending", "who's getting better/worse", "bat speed trend", "velo trend", "is X trending up/down", "physical risers/decliners", "any breakout/decline watch on my roster". DISPLAY/CONTEXT only — never moves an rh3/rp3 projection.
---

# trending — physical getting-better/worse detector

## What this is

A **change detector** (not a forward ranker) built on the one place bat-tracking
beats the box score: **stabilization speed**. Validated 2026-06-16
(`data/research/validation_runs/early_season_bat_speed_2026-06-16.md`):

- **Hitters → 3-axis physical profile** (slice_frontier, 2026-06-16): three
  fast-stabilizing, mutually non-redundant axes, each adding OOS CV R2 over the
  others (box+prior 0.412 → +bat speed 0.495 → +attack angle 0.516 → +fast-swing
  0.536):
  - **bat speed** — how *hard* (stabilizes ~20 swings; raw r +0.60 @3wk predicting
    RoS xwOBACON, partial +0.385 over box+prior).
  - **attack angle** — how well-*shaped* the swing is, scored as movement TOWARD
    the productive band (AA_OPT ≈ 15°). Partial +0.21 over bat speed; stabilizes ~30 sw.
  - **fast-swing %** — *intent* / top-end (≥75 mph swings). Partial +0.17 over bat
    speed; stabilizes ~20 sw.
  Combined into an equal-weight composite z (`z_comp`); the tag lists whichever
  axes (|z|≥1.0) drive the move. This catches swing-re-tool breakouts (Jordan
  Walker via swing-path) and swing-path declines (Wyatt Langford off-band) that
  single-axis bat speed misses. REJECTED slices (don't re-add): premium-velo bat
  speed (redundant w/ overall), swing-grain contact quality (noisy, slow),
  contact-depth/intercept_y (null), binary ideal-AA% (discards magnitude).
- **Pitchers → fastball velocity.** Induced bat speed was REJECTED for pitchers
  (stabilizes too slowly: r≈0.60 only at 200 faced swings; ~zero faithfulness to
  damage). The pitcher analog is FB velo, already validated and in rp3
  (`avg_velo_to` + `delta_velo`).

## Hard rules

1. **Display/context ONLY.** Never use to move an rh3/rp3/Blended xFP projection
   (Rule 13 — lenses are conviction/conflict surfacing, not additive point lift).
   Headline number stays the model's.
2. **Necessary, not sufficient.** A bat-speed/velo rise flags the physical tool
   moving (breakout/decline WATCH), confirmed by the contact/results column as it
   stabilizes. A riser with flat contact = tool up, not yet translating (e.g.,
   Nick Allen +5 mph, flat xwOBACON). Always show the confirmation column.
3. **Role-appropriate metric.** Hitters = 3-axis (bat speed + attack angle +
   fast-swing %); pitchers = FB velo. Do NOT report induced bat speed for pitchers
   (rejected). Do NOT re-add the rejected hitter slices above.
4. **Attack angle is direction-aware.** Score it as movement toward the ~15° band,
   NEVER naive "up = good" — a hitter already at 25° rising further is bad.
5. **All joins by MLBAM id** via `resolve_batter_id` / `resolve_pitcher_id`
   (team + position/role hints) — never name-only (Max Muncy collision).
6. **Roster truth is live.** Tag MINE/FA from a live ESPN call, never session
   memory (`/roster-verify` rule).

## How to run

```bash
# Full board: my roster (hitters by bat speed, pitchers by velo) + top FA risers
python scripts/xfp/run_trending.py

# Ad-hoc trend cards for specific players
python scripts/xfp/run_trending.py --names "Jordan Walker, Dustin May"
```

Engine: `scripts/xfp/lib/trend_signal.py` (`hitter_trend_table()`,
`pitcher_trend_table()`, `tag_hitter()`, `tag_pitcher()`,
`trend_for_mlbam(mlbam, role)`). Other skills (`/slump-or-decline`,
`/breakout-sustainability`) can import `trend_for_mlbam` to add the one-line
physical-trend tag to their cards — bat-speed-down on a slumping hitter =
structural/physical decline = lower recovery ceiling (extends the
xwOBACON-YoY-trajectory rule).

## Reading the output

- `🔺 … (≥+1.5σ)` riser / `🔻 … (≤−1.5σ)` decliner / `• … stable`.
- Confirmation is sign-aware: "confirming" = the outcome moved the same (good/bad)
  way; "diverging" = tool moved but outcome hasn't (Detmers: velo −1.7 but xwOBA-
  allowed still good = watch, not yet confirmed).
- z is vs the population SD of the YoY change (hitters ~1.2 mph, pitchers ~0.8 mph).

## Caveats / scope

- RoS predictive validation is 2 cohorts (2024-25, display-grade); the
  high-powered split-half stabilization carries the weight. 3rd cohort lands when
  2026 completes.
- Best signal is EARLY-season (Apr-May), when the rate stats are still noise; by
  midseason the contact stats have caught up and add their own read.
- IL / small-sample players show "no qualifying 2026 sample" (e.g., Hunter Greene).
