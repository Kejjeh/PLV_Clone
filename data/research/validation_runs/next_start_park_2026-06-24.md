# Next-start park/opponent adjustment — validation + ship record

**Date:** 2026-06-24
**Status:** SHIPPED as a CONTEXT lens (NOT a projection multiplier — see why)
**Trigger:** "Are we factoring park (Coors) and handedness alright?" — Eury's next start is @ Coors.

## What was tested

Whether a per-start PARK or OPPONENT multiplier improves single-start SP FP prediction.
Data: 2,364 real 2026 SP starts (`boxscore_pitchers` per-start `fp_sp` + `statcast_2026`
game_pk→home_team → venue → multi-year-stable `pf_R`; opponent `bat_index` from
`team_strength_2026`). Baseline = pitcher's prior-start expanding-mean FP (shifted, no
leakage). Calibrate `mult = 1 − k·(factor−1)` on the first 60% of starts by date, test OOS
on the last 40%. Script: `scripts/_oneoff/validate_next_start_park.py`.

## Results

**Q1 — the raw park effect is real (as a population mean):**
SP starts at Coors average **7.67 FP vs 9.99 elsewhere (−2.32 FP/start)**. Lowest-scoring
SP parks: ATH 7.20, WSH 7.55, **COL 7.67**; highest: LAD 12.25, TEX 12.21, SEA 12.08.

**Q2 — but it does not survive once you know the pitcher's baseline:**
corr(actual − baseline FP, park factor): pf_wOBA +0.0045, pf_R +0.0054, pf_HR +0.0367 — all ≈0.
corr with opponent bat_index: **−0.019** (≈0).

**Q3/Q4/Q5 — OOS, no multiplier helps (best k = 0):**

| adjustment | best k (train) | OOS MAE | vs baseline (7.7073) |
|---|---|---|---|
| pf_R (park) | **0.00** | 7.7073 | +0.00% |
| pf_wOBA (park) | 0.50 | 7.7102 | −0.04% (noise) |
| opp bat_index | **0.00** | 7.7073 | +0.00% |

Per-start SP FP is **~75% irreducible noise** (MAE ~7.7 on a ~10 FP mean). The −2.32 Coors
gap is confounded (Rockies' own weak rotation pitches half the Coors games; opponent quality)
and swamped by single-start variance, so a team-season park/opp factor is **not a useful
point predictor**. This extends the earlier finding that park was dropped from rp3 (±0.1 FP).

## Conclusion → what shipped

A park/opp **multiplier on the projection is rejected** (would add noise — same lesson as the
trajectory features). Instead, `next_start_lens` surfaces the next confirmed start as **decision
CONTEXT**: venue, opponent, `park_env` (EXTREME-HITTER = Coors-class / HITTER / NEUTRAL /
PITCHER), and `opp_env` (soft/avg/tough). Columns `next_start_date`/`next_opp`/`next_venue`/
`next_park_env`/`next_opp_env`, registered `next_start` family, **context-only (Rule 13)**.

The honest framing for a decision: an extreme park (Coors) shifts the *expectation* (~−2 FP)
and the *variance* (wider outcomes) — a **cap-bench / high-variance flag** — even though it is
**not** a point-predictable dock you should bake into the rp3 number. Handedness/platoon was
NOT shipped as a multiplier for the same reason (per-start noise + no clean lineup-handedness
data to validate against); it remains displayed via the existing `split_*` lens (context-only).

Engine: `lib/extra_lenses.{park_env, opp_env, next_start_lens}`.
