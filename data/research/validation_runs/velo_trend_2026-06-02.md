---
signal: velo_trend
formula: mean release_speed of pitcher's primary pitch type over their LAST 3 STARTS strictly before cutoff_date MINUS mean release_speed of same pitch type season-to-date (all starts strictly before cutoff_date). Primary pitch type = most-thrown pitch type season-to-date up to cutoff (typically FF or SI). Velocity is from statcast_YYYY.parquet release_speed column. Strictly framing-respecting — start N can only use starts 1..N-1.
outcome: ros_fp_per_start (rp3 production target, the column already in rolling_pitchers_2018_2026.csv)
expected_sign: positive (recent velo above season mean → arm is still fresh / trending up → higher RoS FP/start; below season mean → fatigue / hidden injury / decline → lower RoS FP/start)
theory: RP3_FEATS already contains avg_velo_to (cumulative season-to-date velo) and delta_velo (last21 minus to). delta_velo is a pitch-mix-agnostic, 21-day-window delta. velo_trend is conceptually orthogonal — it (a) restricts to the PRIMARY pitch type (so mix shifts don't show up as fake velo deltas), and (b) uses a START-COUNT window (last 3 starts) instead of a CALENDAR window (last 21 days). For SPs who pitch every 5 days, 3 starts ≈ 15 days but is robust to IL gaps and 6-man rotation skips. If recent-3-start velo on the bread-and-butter pitch is BELOW the SP's own season norm, that's a behavioral signal that delta_velo (calendar-bound, mix-blended) may dilute or miss.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_velo_trend.py
date: 2026-06-02
verdict: REJECTED
verdict_notes: Pooled cross-year r gain +0.0014 (below +0.005 gate). Sign-consistent only 4/7 years. Holdout 2024-2025 lift -0.0003 (wrong sign). MAE on holdout WORSE by 0.0063 FP/start. Convergence at split_day 30/44/58 all negative — no leakage smell, signal is genuinely redundant with delta_velo + avg_velo_to + shrunken contact metrics. Partial r vs full baseline +0.0474 in-sample but does not generalise cross-year. See velo_trend_validation.md for full report.
---

# Pre-registration body (written BEFORE running any models)

## Why this candidate
- The current rp3 model encodes within-season velocity drift via `delta_velo` (= last21 mean minus season-to-date mean across ALL pitches). That feature passed validation in the 2026-05-12 sweep with +0.0157 r against rp3 v1.
- `delta_velo` has two known dilution mechanisms:
  1. It blends across pitch types. A pitcher who has shifted his slider% up at the expense of his fastball% will register an apparent velo drop, even if his fastball velo is unchanged.
  2. The 21-day calendar window catches at most 4 starts for a healthy SP, but can catch 0 starts for an IL'd pitcher, where the comparison becomes a noisy ratio of two small samples.
- `velo_trend` restricts to the most-thrown pitch type (so mix shifts don't poison it) and uses a start-count window (so IL'd / 6-man-rotation pitchers still get a meaningful 3-start signal).
- These two adjustments make `velo_trend` semantically orthogonal to `delta_velo`. Both could be true (an arm signal that survives mix-shift adjustment) or only `delta_velo` could be (the mix-shift IS most of the signal, and pitch-specific velo doesn't matter for RoS FP/start). The validation will distinguish these.

## Rule 8 framing
- Production use case is in-season → RoS at split rows of split_day = 30, 37, 44, 51, 58 (early-season decisions when waiver/drop calls actually happen).
- Convergence check: re-validate at split_day 30, 44, 58 (closest available match to the requested 30/42/56 — rolling_pitchers cache snaps to 7-day grid). If the lift is materially LARGER at later split_days than earlier, that is a leakage smell because more of the post-cutoff RoS window has been observable.
- All velo computations use ONLY game_dates strictly less than cutoff_date. This is the leakage discipline.

## Rule 9 baseline (the critical one)
- Baseline = the EXACT current RP3_FEATS from `src/plv_clone/models/xfp/rp3.py`, all 24 features. No stripping. No "curated" subset.
- The candidate `velo_trend` is ADDED to that full baseline. Lift = `cross_year_r(baseline + velo_trend) − cross_year_r(baseline alone)`.

## Rule 5 sample-size honesty
- Per-year training cohorts: 2018, 2019, 2021, 2022, 2023 — 5 years × ~1300 rows per split_day × 3 split_days = ~19500 training observations. Well above the n=200 pooled floor.
- Holdout: 2024, 2025 — 2 years × ~1300 × 3 = ~7800 rows. Well above the n=100 floor.
- velo_trend coverage: depends on each pitcher having ≥ 3 prior starts at the cutoff. At split_day=30 this excludes pitchers in their first 2 starts — those rows already exist in baseline so we fill velo_trend with 0 for them (neutral signal). Coverage % will be reported in the script output.

## Rule 3 / Bonferroni
- Single-feature test, no sweep. Bonferroni is a no-op. Decision bar is the +0.005 production gate.

## Decision rule (pre-committed)
- **SHIP** (verdict PASS): partial r vs full baseline ≥ +0.02 (matches the task brief's bar) AND lifts at split_day 30/44/58 are all same-sign AND holdout 2024-2025 lift > 0 AND MAE reduction on holdout ≥ 0.05 FP/start.
- **DON'T SHIP** (verdict REJECTED): partial r < 0 OR wrong sign on holdout OR lifts wildly inconsistent across split_days (leakage smell).
- **NEEDS MORE DATA** (verdict MARGINAL): partial r in (0, +0.02), or directionally right but below sample-size confidence — recommend wait for 2026 season completion before re-test.

## Leakage discipline pre-commitments
1. `velo_trend` at row (pitcher P, year Y, split_day SD) uses ONLY pitches with game_date strictly less than cutoff_date.
2. Primary pitch type is determined from pitches strictly before cutoff_date, not full-season.
3. Pitchers with fewer than 3 prior starts get velo_trend = 0 (neutral). Their baseline features still drive the model.
4. Leave-one-year-out: when predicting year Y, train on the other 4 training years (Y excluded entirely).
5. Holdout (2024, 2025) is NEVER touched during training-year tuning.
