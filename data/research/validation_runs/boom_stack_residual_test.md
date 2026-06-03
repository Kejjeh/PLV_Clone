# boom_stack residual test — team-level

Date: 2026-06-03
Author: Claude (measurement-only investigation)
Panel: `data/outputs/predictions_history.csv` — 141 synthetic backfill rows
(84 in 2024, 57 in 2025) + 107 live 2026 rows.

## Hypothesis

At the TEAM-week level, does a roster's aggregate `boom_stack` count predict
the residual (actual − projected) on the synthetic-backfill matchup panel?

Expected sign pattern:
- `n_stack_3_hitters` → POSITIVE
- `n_HIGH_K_SP` → POSITIVE
- `n_anti_predictive_SP` → NEGATIVE

## VERDICT: NEEDS_MORE_DATA — test cannot be executed honestly with current artifacts

The test as specified is **not runnable** from the current data store. Honest
assessment of why, before forcing a contrived regression:

## Why the test cannot be run as specified

### 1. boom_stack is a live tag, not a stored time-series

Both `scripts/xfp/lib/boom_stack.py` (SP) and `scripts/xfp/lib/hitter_boom_stack.py`
(hitter) are LIVE-computation modules. They read:

- `data/research/xfp_cache/statcast_2026.parquet` — current year only
- `data/research/xfp_cache/team_strength_2026.csv` — built fresh each refresh,
  no historical snapshots
- `data/research/xfp_cache/pitcher_schedule_2026.csv` — today's probable
  pitchers; no archive
- `recency_form_gap` from the live rp3 row — no historical per-week store
- Today's confirmed MLB lineup via Stats API — no archive

There is NO stored series of `(player, date, boom_stack)` for 2024 or 2025.
The artifact on disk (`hitter_boom_stack_2026-06-03.json`,
`sp_boom_stack_full_pool_2026-06-03.json`) is a single-day snapshot.

### 2. ratings_master files are year-aggregated, not weekly cumulative

`data/research/hitter_ratings_master.csv` and `sp_ratings_master.csv` are
season-aggregate rows (one row per player-year). They contain no
state-as-of-week-N columns and can't substitute for the per-start /
per-game cumulative-prior windows that boom_stack components require
(skill_spike = last-5-starts K% minus season-to-date K% as of that start).

### 3. Per-week roster history is not stored

`predictions_history.csv` carries only `my_team` / `opp_team` / final
scores, not the roster composition that produced those scores. ESPN
`box_scores(matchup_period=p)` for 2024/2025 still returns rostered
lineups so this layer IS reconstructable, but only by an additional ESPN
API sweep — not from on-disk artifacts.

### 4. The components that ARE reconstructable wouldn't be `boom_stack`

A partial proxy could be built from {`skill_spike`, `opp_soft`,
`park_friendly`} using `statcast_2024.parquet` + `statcast_2025.parquet`
+ `park_factors_2018_2026.csv` + a recomputed weekly `team_strength_recent`
series. But:

- This omits `recform_hot` (no historical rp3 series) and the
  hitter-side `lineup_amp_hitter` (no archived posted lineups).
- The validated boom-rate tables in `boom_stack.py` are calibrated on
  the FULL 4-component stack. A 3-component proxy is a DIFFERENT signal
  with unknown calibration. Running OLS against it does not test the
  validated `boom_stack` hypothesis — it tests a hand-built imitation.
- Rebuilding `team_strength_recent` per week for 2024/2025 (rolling
  team batting indices feeding the soft-tertile cutoff) is the kind of
  load-bearing computation that should go through `/validate-feature`,
  not a one-off measurement script.

### 5. Honesty hook from CLAUDE.md

Rule 1 of the project's anti-patterns: *"Don't drop a feature into
rh3/rp3/rprs2 without `/validate-feature`. Stripped-down backtests
over-claim lift."* The same logic applies in reverse for a residual test
on a stripped-down proxy: a positive result on a non-equivalent stack
would over-claim a marginal effect; a null result would under-state a
real one. Either way the answer would not generalize to the production
`boom_stack` tag.

## What the task's own "Constraints" already flag

The task brief itself notes: *"The synthetic backfill projection used
Bayesian-shrunk season avg, which means it ALREADY incorporates SOME
boom-like signal indirectly... The marginal lift over that should be
small. If it's HUGE, you may be re-discovering signal already in the
prior."*

The Bayesian-shrunk season-to-date average is a strong baseline for
team-week scoring (R/TB/RBI/BB/HBP/SB − K + SP/RP outputs all integrated).
A team's roster boom-tag density is correlated with the prior itself
(better hitters / higher-K SPs accumulate higher season-to-date totals).
A positive residual coefficient would not cleanly attribute to "boom_stack
is a missing signal" vs "the prior is mildly under-shrinking elite-skill
teams." Separating those requires a controlled test the panel size
(N=141) cannot support after splitting by year for CV.

## Power audit (n=141)

Even if a proxy were built:
- 84 (2024) + 57 (2025) rows → ~70 per CV fold.
- ~8 teams × ~17-20 reg-season periods → high within-team correlation;
  effective N is closer to 16 (team-level intercepts).
- Per-coefficient detectable effect at α=0.05, power=0.80 on N_eff≈16
  with 3 predictors: minimum standardized β ≈ 0.7 of residual SD.
- Residual SD on the panel is ~75 FP. Detectable per-coefficient lift
  is thus ~50 FP per team-week — far above the +0.5 FP/player
  "matters" threshold in Step 4.

The panel is statistically under-powered for the per-coefficient
magnitude that would actually move a projection adjustment, even with
a perfect boom_stack reconstruction.

## Recommendation

**DON'T_SHIP — and specifically: do not run a contrived 3-component proxy
to manufacture a verdict.**

To make this hypothesis testable honestly:

1. Store a daily/weekly snapshot of `boom_stack` per player going
   forward (write a Parquet append in `refresh_dashboards.py` step 2.8
   or similar). After 12-16 live weeks of 2026 the panel grows from
   141 → ~250-280 with REAL boom_stack values present at the start of
   each week.
2. THEN: regress residual ~ team-aggregate boom counts, with team
   fixed effects, using the same `/validate-feature` 9-rule protocol
   (pre-registration, Rule 8 framing match, Rule 9 baseline including
   all existing production projection features).
3. The Rule 8 framing match is non-trivial here: the "projection" in
   the live panel is rh3+rp3+rprs2 sums, not Bayesian-shrunk team
   averages. The historical residual is measuring a DIFFERENT projector
   than the live residual would. Don't pool 2024+2025 backfill rows
   with 2026 live rows in the same regression without a year/projector
   dummy.

## Files inspected

- `c:/Users/Joshua/plv_clone/data/outputs/predictions_history.csv`
- `c:/Users/Joshua/plv_clone/scripts/xfp/build_synthetic_calibration_panel.py`
- `c:/Users/Joshua/plv_clone/scripts/xfp/lib/boom_stack.py`
- `c:/Users/Joshua/plv_clone/scripts/xfp/lib/hitter_boom_stack.py`
- `c:/Users/Joshua/plv_clone/data/research/hitter_ratings_master.csv`
- `c:/Users/Joshua/plv_clone/data/research/sp_ratings_master.csv`
- `c:/Users/Joshua/plv_clone/data/research/xfp_cache/` (statcast +
  ancillary feature stores)

No regression was fit. No proxy `boom_stack` was constructed. Reporting
the data-availability blocker is the honest output here.
