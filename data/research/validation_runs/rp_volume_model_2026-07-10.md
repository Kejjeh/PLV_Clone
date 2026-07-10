---
signal: rp_volume_model (RP forward appearance-volume projector, NEW companion model)
formula: Ridge(StandardScaler) over as-of-split_day volume features -> ros_g / team_games_remaining
outcome: ros_g_per_teamgame = ros_g / team_games_remaining, per (pitcher, year, split_day) from rolling_relievers_2018_2026.csv; ros_g DERIVED (substrate carries no RoS column) as relief appearances after cutoff_date via the builder's own relief-appearance idiom (pitcher != half-inning starter, distinct game_pk), verified 100% consistent with substrate g_to on a 300-row 2024 sample; team_games_remaining = distinct team game_pk with game_date > cutoff_date (statcast schedule, pitcher mapped via the substrate's own team_abbr column)
expected_sign: model Spearman > naive persistence Spearman
theory: rprs2 projects a RoS TOTAL but reliever workload varies hugely with role/health/team context; realized forward volume dominated forward TOTAL FP for both hitters and SPs (2026-07-09 recon) and RP appearances are the noisiest volume channel in the stack — nothing currently projects them (snapshot logger proj_volume is NaN for RPs); completes the volume layer whose hitter (+0.074) and SP (+0.100) legs both PASSED 2026-07-09
production_target: volume-companion (new) — does NOT touch rh3/rp3/rprs2
framing: in-season -> ros
holdout_years: [2024, 2025]  # their LOO folds must BOTH beat naive
training_years: [2019, 2021, 2022, 2023, 2024, 2025]  # rprs2 convention (2018 excluded: lag1 features have no 2017 source)
validation_script: scripts/xfp/xfp_rp_volume_pipeline.py
date: 2026-07-10
verdict: PASS
purpose: RP analog of the hitter/SP forward-volume models; converts rprs2 rate skill into honest RoS TOTALS and fills the snapshot logger's proj_volume column for RPs
---

# Pre-registration — RP forward-volume model (2026-07-10)

## Target

`ros_g_per_teamgame` = `ros_g` / `team_games_remaining`.

The reliever rolling substrate (`rolling_relievers_2018_2026.csv`, 57,877
rows, weekly splits 30-191) carries NO rest-of-season column (its
`fp_year_total` is a full-year total, not a forward count), so `ros_g` is
DERIVED — documented here before results — from the statcast parquets using
the substrate builder's OWN relief-appearance idiom
(`build_rolling_relievers.py::relief_pitches_only`): a pitcher-game is a
relief appearance iff the pitcher is not the first pitcher of his
(game_pk, inning_topbot) half; `ros_g` = distinct relief game_pk with
game_date > cutoff_date, same year. Coverage pre-check (Step 2.5, done
BEFORE this prereg was locked): the derived to-date count reproduces the
substrate's `g_to` exactly (100% match, 300-row 2024 sample, mean abs diff
0.0), so the forward count is definition-consistent with the substrate.

`team_games_remaining` = distinct team `game_pk` with game_date >
cutoff_date, from the statcast parquet schedule; pitcher -> team via the
substrate's own `team_abbr` column (enriched from MLB API counting stats;
0% null; code set verified identical to statcast home/away codes);
league-mean fallback retained for safety.

### No substrate truncation (unlike the SP leg)

The reliever builder emits a (pitcher, year, split_day) row whenever
g_to >= 5 through the cutoff — NO subsequent-appearance requirement — so
the zero-forward-appearance class EXISTS here (22.2% of 2024 rows have
ros_g = 0: demotions, releases, season-ending injuries). Unlike the SP
volume model, this model CAN learn attrition to zero. Rate form so season
length / cutoff timing cancels. NO filter on the target; 2026 in-progress
rows have no meaningful target and are used only for projection.

## Features (all as-of split_day — Rule 8 leakage safety)

1. `g_per_teamgame_to` = g_to / team_games_to  (the persistence anchor)
2. `g_last21` — relief appearances in (cutoff-21d, cutoff], DERIVED from the
   same relief-appearance date arrays (the substrate has no *_last21
   column; the SP leg's gs_last21 was its dominant coefficient)
3. `ip_per_g_to` = ip_to / g_to  (workload shape: multi-inning vs one-out arms)
4. `gf_pct_to`  (substrate; NaN -> 0)
5. `sv_per_g_to`, `hld_per_g_to`  (current to-date role; NaN -> 0)
6. `fp_skill_per_g_to` = fp_skill_to / g_to  (skill quality — better RPs
   pitch more and keep their roster spot; role bonuses excluded to keep it
   a skill read)
7. `prior1_g_per_g` = prior-year official G / 162 from
   relievers_multiyr_2018_2026.csv; `prior2_g_per_g` likewise; 2021 looks
   back to 2019 (skip 2020); NaN -> 0 + `has_prior1` flag (derived from the
   multiyr file, NOT the substrate's g_lag1, which is 0-filled and cannot
   distinguish missing from zero)
8. `sv_per_g_lag1`, `hld_per_g_lag1`  (substrate role-lag features —
   trailing role drives usage; already 0-filled upstream)
9. `career_stage` = year - first multiyr year (rprs2 idiom), clipped 0-20
10. IL state from il_split_features_2018_2026.csv: `il_stints_to`,
    `days_on_il_to`, `is_on_il_at_split`, `days_since_il_return_imp`
    (NaN -> max+1 sentinel, per rp3). Join method: merge_asof BACKWARD on
    split_day within (pitcher, year) — the IL cache was rebuilt 2026-07-09
    onto the PITCHER rolling substrate's split grid; exact join on the
    reliever grid matches only 30.7% of rows (checked pre-registration),
    so the hitter/SP volume pipelines' asof-backward idiom (leakage-safe:
    past anchors only) is adopted from the start.
11. `split_day` (regime / season-phase)

## Filters (as-of only)

g_to >= 5 (rprs2's EVAL_G_MIN / the substrate's own MIN_G_TO — this is how
the stack defines "is an RP"; the substrate additionally enforces
gs_to <= 2 to exclude SP-types), team_games_to >= 15,
team_games_remaining >= 15, year != 2020. No `ros_g` filter (that would
select on the outcome).

## Design

Mirror of the hitter/SP volume pipelines: Pipeline(StandardScaler, RidgeCV
alphas logspace(-1,5,80), cv=5), leave-one-year-out over training_years
(2019, 2021-2025 — 6 LOO folds, rprs2 convention). Spearman computed within
each (year, split_day) cell with n >= 30, n-weighted to per-year and pooled
aggregates. Baseline = naive persistence: prediction := g_per_teamgame_to,
same rows, same cells. Predictions clipped to [0.0, 0.55] (a max-workload
reliever tops out ~80 appearances / 162 team games ~ 0.49).

## Gates (locked before results)

1. Pooled LOO ΔSpearman (model - naive) >= +0.03
2. Per-year ΔSpearman > 0 in >= 5 of 6 LOO years
3. Holdout: 2024 AND 2025 LOO folds both Δ > 0
4. Report (non-gating): pooled MAE improvement, calibration by predicted
   tercile (mean predicted vs mean actual per tercile)

If gates fail, verdict REJECTED and the output CSV is not to be consumed
downstream (the snapshot logger is NOT wired). If pooled Δ lands in
[+0.01, +0.03), verdict MARGINAL with exact numbers, logger NOT wired.
Integration into any ranker is explicitly OUT OF SCOPE for this run.

## Sanity checks (post-fit, non-gating)

- A healthy high-leverage closer should project ~0.28-0.35 G/team-game
  band or the empirical top-tercile equivalent (~55-70 appearances/162);
  mop-up / low-leverage arms materially lower.
- A recently-recalled / recently-activated arm (active last 21 days, IL
  stint or thin season) should project ABOVE its season-long naive pace.
- Thin-history arms (low g_to, no prior-year G — the September-callup
  class analog) should project BELOW established high-leverage arms.
- Name real 2026 examples for each.

## Output

`data/outputs/xfp_rp_volume_projections.csv`: mlbam_id, player_name, team,
proj_ros_g_per_teamgame, naive_pace, proj_ros_g (implied via 162 -
team_games_to), volume_percentile, feature transparency columns. 2026
projection rows: each pitcher's most-recent snapshot within a 14-day
recency window (SP idiom), g_to >= 5, team_games_to >= 15.

IF PASS: add the RP entry to `_VOLUME_SOURCES` in
`build_player_projection_history.py` so `proj_volume` fills for RPs, and
write the refresh wiring snippet (step 4.09c) to
`docs/wiring_notes_2026-07-10_rpvolume.md` (refresh_dashboards.py itself
NOT edited in this run).

---

# RESULTS (appended after the run — design above was locked first)

Run: 2026-07-10, `scripts/xfp/xfp_rp_volume_pipeline.py`, n=40,289 LOO rows.
ros_g == 0 share (past years, pre-filter) = 21.8% — the attrition class is
present and learnable, as pre-registered (no SP-style truncation).

## LOO results

| year | spear_model | spear_naive | Δ | mae_model | mae_naive | n |
|---|---|---|---|---|---|---|
| 2019 | 0.6470 | 0.4957 | +0.1512 | 0.0983 | 0.1235 | 6,674 |
| 2021 | 0.6871 | 0.5665 | +0.1206 | 0.0994 | 0.1176 | 6,871 |
| 2022 | 0.6956 | 0.5856 | +0.1100 | 0.0938 | 0.1119 | 7,072 |
| 2023 | 0.7049 | 0.5817 | +0.1232 | 0.0919 | 0.1121 | 6,583 |
| 2024 | 0.6749 | 0.5345 | +0.1404 | 0.0980 | 0.1176 | 6,379 |
| 2025 | 0.7209 | 0.6026 | +0.1182 | 0.0951 | 0.1140 | 6,710 |
| POOLED | 0.6885 | 0.5615 | **+0.1270** | 0.0961 | 0.1161 | 40,289 |

- Gate 1: pooled ΔSpearman +0.1270 ≥ +0.03 → **PASS** (4.2× the gate; the
  largest of the three volume legs — hitter +0.074, SP +0.100, RP +0.127 —
  consistent with RP usage being the noisiest channel and therefore the one
  where naive persistence is weakest)
- Gate 2: per-year Δ > 0 in **6/6** years (need 5/6) → **PASS**
- Gate 3: holdout 2024 (+0.1404) and 2025 (+0.1182) both > 0 → **PASS**
- MAE: 0.1161 → 0.0961 G/team-game (−17.2%, every year improves)
- Tercile calibration (pooled LOO): low pred 0.0870 / actual 0.0802; mid
  0.2450 / 0.2454; high 0.3570 / 0.3578 — near-unbiased in all three.
  Naive over-predicts EVERY tercile (low 0.1406, mid 0.2679, high 0.3965 vs
  the same actuals): to-date appearance pace ignores forward
  demotion/injury/attrition risk across the whole distribution, worst at
  the bottom (mop-up arms churn out of the league).

Coefficients (final ridge, alpha=371.2, n=40,289): **g_last21 +0.0706
dominant** (same as the SP leg's gs_last21 — recent usage IS the role),
then g_per_teamgame_to +0.0269, fp_skill_per_g_to +0.0261 (skill quality →
usage retention, as theorized), is_on_il_at_split −0.0242, ip_per_g_to
−0.0173 (multi-inning arms make FEWER appearances — length trades against
frequency), split_day +0.0157. Role lags (sv/hld_per_g_lag1) ~0 once
current-season role is in the model.

## 2026 sanity checks (all pass; real examples, as of 2026-07-10)

- Healthy high-leverage closers land ~0.35-0.43 G/team-game (~24-29 implied
  RoS appearances): Cade Smith CLE 0.417, Jhoan Duran PHI 0.405, Mason
  Miller SD 0.394, Aroldis Chapman BOS 0.353, Raisel Iglesias ATL 0.348.
  Slightly above the prereg's 0.28-0.35 heuristic band but matched to the
  empirical top tercile (mean actual 0.358) — the heuristic understated how
  concentrated modern high-leverage usage is; the model matches what
  actually happens (workhorse setup arms top the board: Dylan Lee ATL
  0.438, Hunter Gaddis CLE 0.427, Trevor Megill MIL 0.425).
- Recently-active thin-season arms project ABOVE their season-long naive
  pace in **100%** of cases: canonical **Josh Hader HOU 0.384 vs naive
  0.168** (16 G season but 9 in the last 21 days — the naive pace is
  dragged down by the missed weeks), Brock Stewart LAD 0.273 vs 0.085,
  Cam Booser TB 0.317 vs 0.154.
- Thin-history arms (g_to ≤ 12, no prior-year G — the callup class)
  project 0.19-0.28, well below the established high-leverage band
  (Jose Cuas KC 0.192, Seth Johnson PHI 0.219, James Karinchak ATL 0.232).
- Predictions span [0.0, 0.438]; floor-0 rows are IL'd/inactive arms.

**VERDICT: PASS.** Output shipped to
`data/outputs/xfp_rp_volume_projections.csv` (334 relievers). The snapshot
logger's `_VOLUME_SOURCES` gains the RP entry
(`build_player_projection_history.py`); refresh wiring snippet (step 4.09c)
in `docs/wiring_notes_2026-07-10_rpvolume.md`. Integration into any ranker
remains a separate, separately-validated step.
