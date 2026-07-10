---
signal: sp_volume_model (SP forward start-volume projector, NEW companion model)
formula: Ridge(StandardScaler) over as-of-split_day volume features -> ros_gs / team_games_remaining
outcome: ros_gs_per_teamgame = ros_gs / team_games_remaining, per (pitcher, year, split_day) from rolling_pitchers_2018_2026.csv; team_games_remaining = distinct team game_pk with game_date > cutoff_date (statcast schedule, pitcher mapped to team via pitcher_primary_team_2018_2026.csv)
expected_sign: model Spearman > naive persistence Spearman
theory: realized forward starts dominate SP forward-total FP (Spearman 0.79-0.83 vs 0.35-0.40 for the rate projection, forward-error recon 2026-07-09); 8% of non-IL SPs made 0 starts in the next 20 days and 60% of IL-flagged SPs on 6/04 never started within 34 days — nothing in the stack projects SP start volume
production_target: volume-companion (new) — does NOT touch rh3/rp3/rprs2
framing: in-season -> ros
holdout_years: [2024, 2025]  # their LOO folds must BOTH beat naive
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/xfp_sp_volume_pipeline.py
date: 2026-07-09
verdict: PASS
purpose: SP analog of the hitter forward-volume model (PASS 2026-07-09); converts rp3 per-start rate projections into better RoS TOTAL rankings via projected start volume
---

# Pre-registration — SP forward-volume model (2026-07-09)

## Target

`ros_gs_per_teamgame` = `ros_gs` (already built in the rolling substrate:
starts after the cutoff) divided by `team_games_remaining` (distinct team
`game_pk` after `cutoff_date`, from the statcast parquet schedule; pitcher →
team via `pitcher_primary_team_2018_2026.csv`, league-mean fallback for
unmapped team-years). Rate form so season length / cutoff timing cancels.
NO filter on the target; rows with NaN target (2026 in-progress snapshot
rows) are excluded from train/eval and used only for projection.

### Substrate truncation (pre-acknowledged, Rule 8 honesty)

The rolling builder emits a (pitcher, year, split_day) row only when the
pitcher has AT LEAST ONE subsequent start in the data — `ros_gs >= 1` for
100% of rows (verified: min = 1.0, zero-share = 0.0). The zero-future-start
class (the 8%-of-non-IL-SPs finding that motivated this model) is therefore
NOT learnable from this substrate; the model ranks start volume CONDITIONAL
on making at least one more start. The naive baseline faces the identical
truncated universe, so the comparison is fair, but consumers must know that
"projects low" here means "few starts", never "zero starts" — the
zero-start / never-returns risk stays a decision-layer concern.

## Features (all as-of split_day — Rule 8 leakage safety)

1. `gs_per_teamgame_to` = gs_to / team_games_to  (the persistence anchor)
2. `gs_last21`  (starts in the trailing 21 days; NaN -> 0)
3. `fp_per_start_to`  (to-date results quality — rotation-spot retention:
   bad performers get skipped/demoted; good ones keep the every-5th-day slot)
4. `prior1_gs_per_g` = prior-year gs / 162 from sp_multiyr_2015_2025.csv;
   `prior2_gs_per_g` likewise; 2021 looks back to 2019 (skip 2020);
   NaN -> 0 + `has_prior1` flag
5. `career_stage` = year - first sp_multiyr year (rp3 idiom), clipped 0-20
6. IL state (rp3's exact consumption idiom, exact join on
   (pitcher, year, split_day)): `il_stints_to`, `days_on_il_to`,
   `is_on_il_at_split`, `days_since_il_return_imp` (NaN -> max+1, the
   "never returned from IL / never was on IL" sentinel, per rp3)
7. `split_day` (regime / season-phase)

NOT available: total-games-pitched (`g_to`) is not in the pitcher rolling
substrate, so the planned gs_to/g_to start-share feature is DROPPED —
documented here before results. Role filtering is handled by the universe
filter below instead (rp3's own idiom), not by ESPN position tags.

## Filters (as-of only)

gs_to >= 2 (rp3's EVAL_GS_MIN modeling-universe filter — this is how rp3
defines "is an SP", caution #1; the substrate already implies gs_to >= 2 on
100% of rows), team_games_to >= 15, team_games_remaining >= 15, year != 2020.
No `ros_gs` filter (that would select on the outcome — note rp3's rate eval
uses ros_gs >= 5, which is legitimate for a RATE target but forbidden here).
marcel_il / prior-only pitchers (no to-date MLB data) have no substrate row
at all, so they are structurally excluded from train/eval AND from the 2026
output — documented; they have no pace anchor and belong to the IL-return
decision layer.

## Design

Mirror of the hitter volume pipeline (`xfp_volume_pipeline.py`): Pipeline(
StandardScaler, RidgeCV alphas logspace(-1,5,80), cv=5), leave-one-year-out
over training_years. Spearman is computed within each (year, split_day) cell
with n >= 30, n-weighted to per-year and pooled aggregates (ranks only make
sense within a snapshot). Baseline = naive persistence: prediction :=
gs_per_teamgame_to, same rows, same cells. Predictions clipped to
[0.0, 0.30] (a strict every-4th-day workhorse tops out ~0.25 GS/team-game).

## Gates (locked before results)

1. Pooled LOO ΔSpearman (model - naive) >= +0.03
2. Per-year ΔSpearman > 0 in >= 5 of 7 LOO years
3. Holdout: 2024 AND 2025 LOO folds both Δ > 0
4. Report (non-gating): pooled MAE improvement, calibration by predicted
   tercile (mean predicted vs mean actual per tercile)

If gates fail, verdict REJECTED and the output CSV is not to be consumed
downstream. Integration into any ranker is explicitly OUT OF SCOPE for this
run (separate step, separate validation). The 10-start weekly cap is a
DECISION layer and is no part of this model.

## Sanity checks (post-fit, non-gating)

- A healthy every-5th-day SP should project ~0.19-0.21 GS/team-game.
- A recent IL activation should project ABOVE its season-long naive pace
  (the naive pace is dragged down by the missed weeks).
- A recent-callup arm (thin gs_to, no prior) should project BELOW a
  full-season workhorse.

---

# RESULTS (appended after the run — design above was locked first)

Run: 2026-07-09, `scripts/xfp/xfp_sp_volume_pipeline.py`, n=26,291 LOO rows.

## Documented deviation: IL join method (implementation fix, not design change)

The prereg's feature section cited "rp3's exact consumption idiom, exact
join on (pitcher, year, split_day)". On the first run that join was found
DEGENERATE: `il_split_features_2018_2026.csv` carries only MONTHLY split
anchors (30/60/90/120 + end-of-season) while the rolling pitcher substrate
is weekly — exact-join match rate is 0.0-0.7% per year, so every IL feature
collapsed to its fillna constant. (rp3's production exact join has the same
property — flagged separately; NOT touched here.) The fix adopts the hitter
volume pipeline's documented idiom for the same file ("file only has
monthly-ish split anchors; asof-backward join"): `merge_asof` backward on
split_day within (pitcher, year) — leakage-safe (past anchors only). Both
runs are reported; gates pass either way, so the fix did not rescue the
verdict:

- Exact join (degenerate IL): pooled Δ +0.1013, 7/7 years, holdout both +.
- Asof join (final):          pooled Δ +0.1001, 7/7 years, holdout both +.

Residual caveat: at projection time the latest IL anchor can be ~2-4 weeks
stale (e.g. day-105 rows read the day-90 anchor), so `is_on_il_at_split` in
the output CSV is "on IL at last monthly anchor", not "on IL today". Its
model weight is tiny (+0.0014); treat the column as context, not live state.

## LOO results (final, asof join)

| year | spear_model | spear_naive | Δ | mae_model | mae_naive | n |
|---|---|---|---|---|---|---|
| 2018 | 0.5010 | 0.3757 | +0.1253 | 0.0438 | 0.0538 | 3,667 |
| 2019 | 0.5026 | 0.4647 | +0.0379 | 0.0439 | 0.0507 | 3,823 |
| 2021 | 0.4875 | 0.3781 | +0.1094 | 0.0444 | 0.0550 | 3,755 |
| 2022 | 0.5216 | 0.3916 | +0.1300 | 0.0411 | 0.0506 | 3,790 |
| 2023 | 0.5848 | 0.4752 | +0.1096 | 0.0411 | 0.0499 | 3,869 |
| 2024 | 0.5224 | 0.4372 | +0.0852 | 0.0439 | 0.0499 | 3,731 |
| 2025 | 0.5157 | 0.4107 | +0.1050 | 0.0434 | 0.0516 | 3,656 |
| POOLED | 0.5197 | 0.4196 | **+0.1001** | 0.0431 | 0.0516 | 26,291 |

- Gate 1: pooled ΔSpearman +0.1001 ≥ +0.03 → **PASS** (3.3× the gate)
- Gate 2: per-year Δ > 0 in **7/7** years (need 5/7) → **PASS**
- Gate 3: holdout 2024 (+0.0852) and 2025 (+0.1050) both > 0 → **PASS**
- MAE: 0.0516 → 0.0431 GS/team-game (−16.5%, every year improves)
- Tercile calibration (pooled LOO): low pred 0.0923 / actual 0.0878; mid
  0.1397 / 0.1424; high 0.1700 / 0.1675 — near-unbiased in all three.
  Naive over-predicts the high tercile badly (0.1870 vs actual 0.1675):
  to-date start pace ignores forward IL/skip risk; realized forward pace of
  even top-tercile SPs is ~0.17 GS/team-game (~1 per 6 team games), which
  also explains why the model's top band (0.176-0.191) sits slightly below
  the naive 0.19-0.21 heuristic — the heuristic is what naive says, the
  model matches what actually happens.

Coefficients (final ridge, alpha=0.1, n=26,291): gs_last21 +0.0193 dominant,
fp_per_start_to +0.0134 (results quality → rotation-spot retention),
split_day +0.0102, gs_per_teamgame_to +0.0070, prior1/prior2_gs_per_g
+0.0048/+0.0042; IL features small (monthly-anchor staleness limits them).

## 2026 sanity checks (all pass)

- Workhorses: Cease 0.1909, C. Sánchez 0.1894, Misiorowski 0.1883 GS/team-game
  (~1 start per 5.2-5.3 team games; implied ~13 RoS starts).
- IL-stint arms now active (il_stints_to ≥ 1, gs_last21 ≥ 3): **90% project
  above their season-long naive pace** — Hunter Brown 0.145 vs naive 0.063,
  Skubal 0.185 vs 0.130, Wheeler 0.187 vs 0.151, Boyd 0.137 vs 0.087.
- Recent callups (gs_to ≤ 6, no prior-year GS): 0.10-0.13, well below the
  workhorse band (Seymour 0.127, Perkins 0.108).

**VERDICT: PASS.** Output shipped to
`data/outputs/xfp_sp_volume_projections.csv` (258 pitchers). Consumption
notes in `sp_volume_model_results_2026-07-09.md`. Integration into any
ranker / the 10-start cap decision layer remains a separate,
separately-validated step.
