# sb_target_fix — stolen bases restored to the rh3 training target (2026-07-10)

## The bug

`scripts/xfp/build_rolling_hitters.py` derived SB by matching
`SB_EVENTS = {'stolen_base_2b','stolen_base_3b','stolen_base_home'}` against the
statcast `events` column. Those values **never occur** there — SBs are baserunning
events, not batter-PA outcomes — so for every batter-year in
`rolling_hitters_2018_2026.csv`:

- `sb_to` / `sb_per_pa_to` / `sb_per_pa_last21` were **identically 0.0**
  (verified pre-fix: groupby(year) mean/std/max all 0.0, all 8 years), making the
  production feature `sb_per_pa_to_sh` a constant (Ridge coef exactly 0);
- the training target `ros_full_fp_per_pa` **omitted SB points entirely**:
  window `fp_total = tb+bb+hbp+sb−k` with sb≡0, and the outer-scope season-rate
  allocation was `(mlb_r+mlb_rbi)/mlb_pa` — the counting-stats JSONs already
  carried `mlb_sb`, unused.

BrownU hitter FP = R + TB + RBI + BB + HBP + **SB** − K. Post-2023 the omitted
component is ~0.019 FP/PA league-wide, ~0.05 at p90, up to ~0.13 for elite
stealers (measured directly, see Before/after).

## Since when

- Rolling builder: **broken since inception** — RH1, commit `498ffd5`
  (2026-05-06). The SB term was never live in the rolling target or feature.
- `build_hitters_multiyr.py` had the same events-derivation bug but was
  **already patched in `7a28f46` (2026-05-06, H2)**: `mlb_sb` overrides the
  statcast-events count, `sb_per_pa` is recomputed, and `fp_per_pa_actual`
  includes SB (verified on the current cache: fp_total reproduces
  R+TB+RBI+BB+HBP+SB−K exactly; league sb_per_pa 0.007–0.022 by year, 2023+
  elevated as expected). **No change needed there.**

### Prior/target unit inconsistency (resolved by this fix)

Because the Marcel prior (`prior_fp_per_pa`, built from multiyr
`fp_per_pa_actual`) has included SB since 2026-05-06 while the rolling target
did not, the model carried a systematic wedge that scaled with SB rate.
Measured on eval-filtered train rows (pa_to≥50, ros_pa≥100), gap between the
SB-inclusive season level the prior encodes and the rolling target:

| season SB-rate tercile | mean sb/PA | old target gap | new target gap |
|---|---|---|---|
| low  | 0.002 | −0.001 | +0.001 |
| mid  | 0.010 | −0.013 | −0.003 |
| high | 0.035 | **−0.033** | +0.002 |

The Ridge coefficient on the prior was partially absorbing an *average* SB
discount — right for the median player, systematically wrong at both SB
extremes. Fixing the target resolves the inconsistency.

## The fix (code)

`scripts/xfp/build_rolling_hitters.py` only:

1. **Target**: season-rate allocation extended to SB exactly as R/RBI enter —
   `rrbisb_per_pa = (mlb_r + mlb_rbi + mlb_sb) / mlb_pa` (variable renamed
   `rrbi_rates` → `rrbisb_rates`; unused helper `fp_per_pa_with_rrbi` renamed
   `fp_per_pa_with_rrbisb`). Season rates are legitimately "future" in the
   target — the target IS the future outcome; identical accepted pattern to
   R/RBI. Before/after-cutoff mechanics unchanged: the after-window core
   (TB+BB+HBP−K per PA) still comes from actual post-cutoff statcast events;
   only the R/RBI/SB layer is a season-rate allocation.
2. `fp_total` drops the dead `+ agg['sb']` term (numerically identical — it was
   always 0 — and prevents double-count if a real as-of SB source ever lands).
3. `BUILDER_VERSION` 1 → 2 — invalidates the per-year immutable pickle caches
   (`lib/disk_cache.year_cached_frame` keys on version + dep-file signature;
   without the bump the rebuild would silently reuse cached SB-less years).

## Feature verdict: sb_per_pa_to stays DEAD-ZERO (leakage-safe option b)

A true as-of-cutoff SB feature was attempted via statcast runner-id transitions
(`on_1b/on_2b/on_3b` movement between consecutive pitches of the same PA, plus
strikeout-boundary steals; steal-of-home via 3B-runner disappearance + bat_score
increment). Validated against MLB-API season totals (2024):

- per-player-year correlation **r = 0.955** (passes the ≥0.95 bar)
- league total **+59.6% inflated** (5,771 derived vs 3,617 actual) — hard fail
  vs the ±5% bar. Contamination = WP/PB/balk/error/DI advances, per-pitch
  indistinguishable from steals. Best filter stack (drop blocked_ball pitches +
  multi-runner advances + foul-description impossibilities) still **+24.6%**
  (r=0.961), with false positives concentrated on non-stealers (Freeman +20,
  Judge +12) — a *biased*, not just noisy, feature.

Proportionally allocating full-season SB into the to-date windows was ruled out
up front: it leaks future steals into a feature. Per the leakage rule, the
feature ships dead-zero: a constant column is harmless (StandardScaler
zero-variance → transformed column all zeros → coefficient inert; FEATS-as-is
vs FEATS-minus-sb predictions are identical by construction, Δr = 0.0000).

**Registry note:** the validated-signals PASS record for `sb_per_pa_to_sh`
covered a degenerate all-zero column and is superseded by this re-test:
**"dead pending as-of source"**. If a clean as-of SB source ever appears
(e.g. MLB Stats API gameLog backfill for 2018-2025), the feature must pass
/validate-feature from scratch before going live.

## Before / after

Caches regenerated: `rolling_hitters_2018_2026.csv` (90,249 rows, unchanged
row count; `.bak` kept). Multiyr cache untouched (already correct).

**Target level** (new − old, `ros_full_fp_per_pa`, 89,654 target rows, zero
negative deltas; feature columns confirmed still 0.0):

| year | mean | p90 | max |
|---|---|---|---|
| 2018 | +0.0103 | +0.0294 | 1.20* |
| 2019 | +0.0094 | +0.0290 | 0.22 |
| 2021 | +0.0092 | +0.0271 | 0.12 |
| 2022 | +0.0139 | +0.0345 | 0.43 |
| 2023 | +0.0193 | +0.0472 | 0.33 |
| 2024 | +0.0209 | +0.0507 | 1.00* |
| 2025 | +0.0203 | +0.0470 | 0.50 |
| 2026 | +0.0175 | +0.0445 | 0.17 |

\*max outliers are tiny-mlb_pa rows outside the eval filters (same behavior the
R/RBI allocation always had). 2023+ elevation (new SB rules) matches the era
regime diagnostic (era_regime_diagnostic_2026-07-10.md §2).

**Cross-year r**: pre-fix 0.6338 (last night's validation-harness replication of
production RH3_FEATS on the old target, identical train rows, n=36,571;
production bundle from 2026-06-22 logged 0.6287) → post-fix **0.6275**
(mae 0.0861, n=36,571). Δ ≈ −0.006, inside the ±0.01 accept band. Not directly
comparable (the target changed); the small dip is mechanically expected — the
target gained SB variance that no live feature tracks (the SB-inclusive prior
covers part of it). Rule-9 gate re-ran on the cold fit and passes:
Δr(ros_opp_sp_xwoba_weighted) = +0.0138 ≥ +0.005. rh3 cold-fit confirmed via
fit fingerprint (full LOO ran; bundle trained_date 2026-07-10).

**Rank movement** (463 projected hitters, corr(rank-rise, 2026 sb/PA) = +0.30;
mean proj Δ +0.0133 FP/PA, top-SB-decile +0.0165, zero-SB +0.0104):

- Top risers: Hyeseong Kim +49, Brice Matthews +43, Chandler Simpson +34
  (22 SB), Troy Johnston +31, Garrett Mitchell +30, TJ Friedl +29,
  Justin Crawford +27 (12 SB), Konnor Griffin +27 (20 SB), Nasim Nuñez +27
  (33 SB), Jake Mangum +24 (18 SB) — burner profiles, as predicted.
- Top fallers (relative — nearly all absolute projections still rose): Alejandro
  Kirk −32, Dansby Swanson −28, Braden Shewmake −28, Michael Conforto −26,
  Salvador Perez −24, Gary Sánchez −23, Paul Goldschmidt −23, Francisco Lindor
  −22, Giancarlo Stanton −20, J.T. Realmuto −19 — station-to-station
  catchers/sluggers.

## Downstream consumers

Verified clean:
- **rp3 / rprs2**: pitcher FP has no SB term; `build_rolling_pitchers.py` /
  `build_sp_multiyr.py` / `build_rolling_relievers.py` contain no SB_EVENTS
  usage at all; `fantasy/pitcher_points.py` uses stolen_base_* only in the
  defensive `_NON_PA` PA-definition set (correct).
- **Hitter volume model** (`xfp_volume_pipeline.py`): zero SB references —
  features are pace/lineup/prior-PA. Unaffected.
- **Seasonality / H2 / xwOBA-residual caches**: target-independent (no reads of
  `ros_full_fp_per_pa` or the rolling CSV target columns).
- NON_PA-only users of stolen_base_* (harmless, correct usage):
  `build_handedness_splits.py`, `build_hitter_lineup.py`,
  `build_batter_rolling_features.py`, `build_team_strength.py`,
  `validate_phase_r3.py`.

Silently reading zeros — **FOLLOW-UP list (not fixed this pass)**:
1. `src/plv_clone/fantasy/hitter_points.py` `_compute_hitter_actuals` (line
   ~340): counts SB from `events` → always 0 → its "actual" hitter FP omits SB.
2. `src/plv_clone/pipelines/build_exports.py` (line ~348): `rolling_sb_pa`
   export → always 0.
3. `scripts/xfp/build_player_profiles_dashboard.py` (line 368): renders an
   `sb_per_pa_to` percentile from the rolling cache → degenerate all-zero
   rating (feature intentionally left dead; the dashboard tile should read
   multiyr `sb_per_pa` or mlb_sb instead).
4. `scripts/xfp/_league_signal_audit.py` (line 157): `events='stolen_base'`
   never matches (also the wrong literal).
5. `scripts/xfp/validate_sprint_speed_lag1.py`: uses `sb_to` / `sb_per_pa_to_sh`
   as outcome/controls — its historical result was computed against zeroed
   controls and should be re-run if it ever mattered.
6. `scripts/xfp/validate_regime_interactions.py` (R1: `sb_x_newrules` =
   `sb_per_pa_to_sh × I[year≥2023]`): the interaction is null-by-construction
   on the zeroed column — today's regime-interaction R1 result is void and
   should be re-run against a real SB signal if one ever ships.
7. Constant-feature mirrors (harmless, coef 0, listed for completeness):
   `RH3_FEATS`/shrink specs in `rh3.py`, `rh3_april.py`, legacy
   `xfp_rh_pipeline.py`, `integrate_rh3_v2_backtest.py`,
   `validate_rh3_breakout_signals.py`.

## Operational notes

- `xfp_rh3_projections.csv` regenerated post-fix (2026-07-10) — tomorrow's
  boards consume the corrected model.
- Snapshot logger (`build_player_projection_history.py`) re-run: **no-op dedup**
  ("panel already has today", 27,381 rows) — today's (2026-07-10) panel rows
  still carry pre-fix hitter projections; tomorrow's refresh self-heals. Flag
  for anyone running forward-calibration retros across this date.
- Coordination guard honored: `era_regime_diagnostic_2026-07-10.md` and
  `regime_interactions_2026-07-10.md` both existed with results before the
  cache regeneration.
