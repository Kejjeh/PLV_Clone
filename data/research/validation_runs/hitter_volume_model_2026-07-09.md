---
signal: hitter_volume_model (forward playing-time projector, NEW companion model)
formula: Ridge(StandardScaler) over as-of-split_day volume features -> ros_pa / team_games_remaining
outcome: ros_pa_per_teamgame = ros_pa / team_games_remaining, per (batter, year, split_day) from rolling_hitters_2018_2026.csv; team_games_remaining = distinct team game_pk with game_date > cutoff_date (statcast schedule, batter mapped to modal team-year from hitters_multiyr)
expected_sign: model Spearman > naive persistence Spearman
theory: forward PA volume explains 3-5x more of forward TOTAL fantasy points than the projected rate (R2 0.47-0.69 vs 0.14-0.20, snapshot recon 2026-07-09); nothing in the stack projects volume, and lineup-role features (started_pct_to, lineup_spot_to) are computed but unused
production_target: volume-companion (new) — does NOT touch rh3/rp3/rprs2
framing: in-season -> ros
holdout_years: [2024, 2025]  # their LOO folds must BOTH beat naive
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/xfp_volume_pipeline.py
date: 2026-07-09
verdict: PASS
purpose: single biggest accuracy lever from the forward-error analysis on 25 logged projection snapshots; converts good per-PA rate projections into better RoS TOTAL rankings
---

# Pre-registration — hitter forward-volume model (2026-07-09)

## Target

`ros_pa_per_teamgame` = `ros_pa` (already built in the rolling substrate by
`build_rolling_hitters.py`: statcast PA after the cutoff) divided by
`team_games_remaining` (distinct team `game_pk` after `cutoff_date`, from the
statcast parquet schedule; batter -> team via modal team-year in
`hitters_multiyr_2015_2026.csv`). Rate form so season length / cutoff timing
cancels. NO filter on the target (filtering on `ros_pa` would select on the
outcome); rows with NaN target (2026 in-progress snapshot rows) are excluded
from train/eval and used only for projection.

## Features (all as-of split_day — Rule 8 leakage safety)

1. `pa_per_teamgame_to` = pa_to / team_games_to  (the persistence anchor)
2. `started_pct_to`  (substrate, computed-but-unused by rh3)
3. `lineup_spot_to`  (NaN -> 10.0 + `lineup_spot_missing` flag)
4. `pa_per_started_game_to`  (NaN -> train-year mean)
5. `pa_last21`  (recent volume; NaN -> 0)
6. `prior1_pa_per_g` = prior-year mlb_pa / 162; `prior2_pa_per_g` likewise; NaN -> 0 + `has_prior1` flag
7. `career_stage` = year - first multiyr year (rh3 idiom), clipped 0-20
8. `is_catcher` — static position flag from same-year statcast `fielder_2`
   appearances (>=100 pitches caught). Positional identity, not performance;
   acknowledged as full-year info but time-invariant in practice.
9. IL state: `il_stints_to`, `days_on_il_to`, `is_on_il_at_split` from
   il_split_features_2018_2026.csv (covers hitters; joined merge_asof
   backward on split_day within (batter, year); NaN -> 0)
10. `split_day` (regime / season-phase)

## Filters (as-of only)

pa_to >= 30, team_games_to >= 15, team_games_remaining >= 15, year != 2020.

## Design

Mirror of rh3 LOO idiom: Pipeline(StandardScaler, RidgeCV alphas
logspace(-1,5,80), cv=5), leave-one-year-out over training_years. Spearman is
computed within each (year, split_day) cell with n >= 30, n-weighted to
per-year and pooled aggregates (ranks only make sense within a snapshot).
Baseline = naive persistence: prediction := pa_per_teamgame_to, same rows,
same cells.

## Gates (locked before results)

1. Pooled LOO ΔSpearman (model - naive) >= +0.03
2. Per-year ΔSpearman > 0 in >= 5 of 7 LOO years
3. Holdout: 2024 AND 2025 LOO folds both Δ > 0
4. Report (non-gating): pooled MAE improvement, calibration by predicted
   tercile (mean predicted vs mean actual per tercile)

If gates fail, verdict REJECTED and the output CSV is not to be consumed
downstream. Integration into any ranker is explicitly OUT OF SCOPE for this
run (separate step, separate validation).

---

# RESULTS (appended after the run — design above was locked first)

Run: 2026-07-09, `scripts/xfp/xfp_volume_pipeline.py`, n=61,231 LOO rows.

| year | spear_model | spear_naive | Δ | mae_model | mae_naive | n |
|---|---|---|---|---|---|---|
| 2018 | 0.7805 | 0.7048 | +0.0757 | 0.6242 | 0.7604 | 8,942 |
| 2019 | 0.7411 | 0.6618 | +0.0793 | 0.6658 | 0.7921 | 9,328 |
| 2021 | 0.7511 | 0.6962 | +0.0549 | 0.6750 | 0.7393 | 9,087 |
| 2022 | 0.7040 | 0.6224 | +0.0816 | 0.7042 | 0.8185 | 8,534 |
| 2023 | 0.7334 | 0.6584 | +0.0749 | 0.6989 | 0.7872 | 8,500 |
| 2024 | 0.7063 | 0.6442 | +0.0620 | 0.7231 | 0.7886 | 8,436 |
| 2025 | 0.7613 | 0.6729 | +0.0884 | 0.6889 | 0.7904 | 8,404 |
| POOLED | 0.7401 | 0.6663 | **+0.0737** | 0.6821 | 0.7819 | 61,231 |

- Gate 1: pooled ΔSpearman +0.0737 ≥ +0.03 → **PASS** (2.5× the gate)
- Gate 2: per-year Δ > 0 in **7/7** years (need 5/7) → **PASS**
- Gate 3: holdout 2024 (+0.0620) and 2025 (+0.0884) both > 0 → **PASS**
- MAE: 0.7819 → 0.6821 PA/team-game (−12.8%, every year improves)
- Tercile calibration (pooled LOO): low pred 1.218 / actual 1.196; mid
  2.362 / 2.338; high 3.406 / 3.398 — near-unbiased in all three terciles.
  Naive over-predicts the high tercile (3.721 vs actual 3.398): to-date
  pace ignores forward injury/rest risk; the model's shrinkage is real.

**VERDICT: PASS.** Output shipped to
`data/outputs/xfp_volume_projections.csv`. Consumption notes in
`hitter_volume_model_results_2026-07-09.md`. Integration into rh3 rankings
remains a separate, separately-validated step.
