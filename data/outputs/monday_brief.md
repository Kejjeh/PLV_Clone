# Monday brief — New York Ligers (BrownU)

_As-of date **2026-08-17** (Monday). Composed offline from artifacts already on disk — no live ESPN, MLB Stats, or Pitcher List calls. Every number below is stamped with the age of the file it came from._

<!-- Brief built: 2026-08-17T10:55:17 — the ONLY wall-clock stamp in this file; the body depends on the calendar date only, so intraday reruns diff to this line alone. -->

## 1. Decisions

### Needs a decision

1. **MOVE AVAILABLE — single move** ADD Tanner Scott / DROP Jhoan Duran for dP(win) +0.0182 (> 2x MC se — a real gap). Verify live rosters (`/roster-verify`) before executing. [weekly_optimizer.json, as-of 2026-08-14, 3 days old (content date) [STALE]]

### Worth knowing

- SP cap TIGHT period 19: 8/10 banked, 2 remaining — sequence the rest of the week before streaming. [matchup_leverage.json, as-of 2026-08-14, 3 days old (content date) [STALE]]
- `matchup_leverage.json` is 3d old, so the cap count above is 3d of starts behind. Run: `python scripts/xfp/run_matchup_leverage.py`
- `weekly_optimizer.json` is 3d old — its plan was built against a 3d-old roster and FA pool; RE-RUN before executing anything above. Run: `python scripts/xfp/run_weekly_optimizer.py`
- PL cache `pl_sp_streamers_latest.json` is STALE — 11d old (rolling, refresh every 2d) (11d old). Refresh in an interactive session (`/triangulate --check-caches`); this brief cannot fetch pitcherlist.com.

## 2. This period — P(win) and cap

- `matchup_leverage.json` — as-of 2026-08-14, 3 days old (content date) [STALE]
- Period **19** vs **Boone's Bad Bullpen** — 228.6 to 157.2, 3d left incl. today
- **P(win) 0.657** — regime **LEADING**
- Regime directive: variance is a LIABILITY — prefer floor (SAFE-tier, low bust%) plays
- SP cap 8/10 banked, 2 remaining (opp 7)
- No `top_moves` in this run (field absent or empty).

## 3. Recommended plan (weekly optimizer)

- `weekly_optimizer.json` — as-of 2026-08-14, 3 days old (content date) [STALE]
- Base P(win) 0.657, regime LEADING, period 19, 10000 sims (seed 7), cap remaining 2
- Recommended sequenced plan:
  1. ADD Tanner Scott (RP) / DROP Jhoan Duran (RP) — dP(win) +0.0182, mc_se 0.0047, title equity +0.0286pp
- Title-equity weight: 1.57pp per win (status **fresh**)

## 4. Delta-P(win) surface (durable counterfactual store)

- `dpwin_history.parquet` — as-of 2026-08-14, 3 days old (content date) [STALE]
- 10649 counterfactual rows over 12 snapshot day(s) (2026-07-29 -> 2026-08-14)
- Latest snapshot 2026-08-14: 326 rows from 2 run(s) [2026-08-14T130350_7, 2026-08-14T132148_7]
- Best-scoring alternative per move_type in the latest snapshot:
  - `add` Ryan Weathers — dP(win) +0.0000
  - `bench_start` Logan Henderson — dP(win) +0.0000
  - `drop` Max Fried — dP(win) +0.0000
  - `sit_hitter` Luis Arraez — dP(win) -0.0412
  - `swap` Tanner Scott — dP(win) +0.0182

## 5. Season outlook (title odds, value of a win)

- `season_sim.json` — as-of 2026-08-14, 3 days old (content date)
- **New York Ligers** — P(playoffs) 1.000, P(title) 0.157 (sim period 19, 5000 sims)
- Sim period 19 matches the live matchup period.
- Value of winning each remaining period (dP(title), pp):
  - period 19: dtitle +1.57pp, dplayoffs +0.00pp (P(win week) 0.771)
  - period 20: dtitle +0.30pp, dplayoffs +0.00pp (P(win week) 0.578)
- Strategy directive from the sim:
  - Playoff odds 100%, title odds 15.7%, modal seed 4 (P(miss) 0%).
  - A win THIS period is worth +1.6pp title equity (vs +0.9pp avg for periods 19-20).
  - SAFE: playoff spot near-locked — bank floor, hoard FAAB/streams for the playoff weeks; a marginal regular-season win buys little. Position the playoff roster (/playoff-team-build, /sp-stash-finder).
  - Variance is roughly title-neutral right now (-0.02pp per +10% sigma) — optimize E[FP].
  - Mean dial: +2 FP/week of true strength = +1.18pp title / +0.00pp playoffs — the scale for valuing any add/trade in equity terms.

## 6. Decision quality (settled verdicts)

- `verdict_scorecard.csv` — as-of 2026-08-17, today (file mtime) (no date column in this artifact, so the age is mtime-based)
- 10 bucket x verdict cells over 795 settled observations

| bucket | verdict | n | players | mean actual | mean proj | residual | hit rate |
|---|---|---|---|---|---|---|---|
| H | BUY | 249 | 12 | 0.544 | 0.599 | -0.055 | 0.269 |
| H | CAUTION | 32 | 4 | 0.609 | 0.559 | 0.050 | -- |
| H | FADE | 4 | 2 | 0.289 | 0.490 | -0.201 | 1.000 |
| H | MIXED | 255 | 16 | 0.533 | 0.567 | -0.034 | -- |
| RP | BUY | 70 | 4 | 5.385 | 4.723 | -0.190 | 0.071 |
| RP | MIXED | 2 | 1 | 2.555 | -- | -- | -- |
| SP | BUY | 45 | 5 | 10.936 | 11.749 | -0.813 | 0.267 |
| SP | HOLD | 4 | 1 | 12.670 | 10.809 | 1.861 | -- |
| SP | CAUTION | 67 | 7 | 11.945 | 11.134 | 0.811 | -- |
| SP | MIXED | 67 | 8 | 8.732 | 11.439 | -2.708 | -- |

## 7. Model + data health

- `model_scorecard.csv` — as-of 2026-08-17, today (content date)
- Tripwires (data_health + pipeline_staleness): PASS 36
- Drift sentinels (added 2026-07-29):
  - `collision_team_reachability` (all): **PASS** — 41/41 collision team hints reachable from 30 live ESPN codes
  - `collision_smoke` (all): **PASS** — 12/12 canonical resolver cases
  - `fa_join_coverage` (H): **PASS** — 222/222 FA H rows join xfp_rh3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15)
  - `fa_join_coverage` (SP): **PASS** — 218/218 FA SP rows join xfp_rp3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15)
  - `fa_join_coverage` (RP): **PASS** — 296/296 FA RP rows join xfp_rprs2_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15)
- Forward accuracy (all-segment headline rows):
  - `rh3_spearman_rate_7d` = 0.2083 [INFO]
  - `rh3_vs_prior_delta_7d` = 0.0867 [INFO]
  - `rp3_spearman_rate_7d` = 0.4794 [INFO]
  - `rp3_vs_prior_delta_7d` = 0.2136 [INFO]
  - `rprs2_spearman_rate_7d` = 0.1695 [INFO]
  - `rh3_spearman_rate_14d` = 0.2625 [INFO]
  - `rh3_vs_prior_delta_14d` = 0.0994 [INFO]
  - `rp3_spearman_rate_14d` = 0.2834 [INFO]
  - `rp3_vs_prior_delta_14d` = 0.1175 [INFO]
  - `rprs2_spearman_rate_14d` = 0.2306 [INFO]
  - `rh3_spearman_rate_21d` = 0.3041 [INFO]
  - `rh3_vs_prior_delta_21d` = 0.0835 [INFO]
  - `rp3_spearman_rate_21d` = 0.3709 [INFO]
  - `rp3_vs_prior_delta_21d` = 0.1680 [INFO]
  - `rprs2_spearman_rate_21d` = 0.3079 [INFO]
  - `rh3_spearman_rate_28d` = 0.2653 [INFO]
  - `rh3_vs_prior_delta_28d` = 0.0599 [INFO]
  - `rp3_spearman_rate_28d` = 0.3023 [INFO]
  - `rp3_vs_prior_delta_28d` = 0.1827 [INFO]
  - `rprs2_spearman_rate_28d` = 0.3209 [INFO]
- Full rendered scorecard: `model_scorecard.md` — as-of 2026-08-17, today (file mtime)

## 8. Pitcher List cache ages (no scraping here)

- Read-only: this brief does NOT fetch pitcherlist.com. Per `refresh_dashboards.py` step 7 the PL caches need a live agent WebSearch/WebFetch (deliberately not another headless scrape), so refresh them in an interactive session (`/triangulate --check-caches`).
- `pl_sps_top100.json` — fetched 2026-08-10 (7d old) — current: current (latest live Mon edition 2026-08-10 already cached)
- `pl_closers.json` — fetched 2026-08-11 (6d old) — current: current (latest live Tue edition 2026-08-11 already cached)
- `pl_hitters_top150.json` — fetched 2026-08-12 (5d old) — current: current (latest live Wed edition 2026-08-12 already cached)
- `pl_sp_streamers_latest.json` — fetched 2026-08-06 (11d old) — **STALE**: 11d old (rolling, refresh every 2d)

## 9. Provenance

| artifact | status | as-of | age | basis | regenerate with |
|---|---|---|---|---|---|
| `dpwin_history.parquet` | STALE | 2026-08-14 | 3d | content date | `python scripts/xfp/run_matchup_leverage.py  (or run_weekly_optimizer.py — either appends)` |
| `matchup_leverage.json` | STALE | 2026-08-14 | 3d | content date | `python scripts/xfp/run_matchup_leverage.py` |
| `model_scorecard.csv` | ok | 2026-08-17 | 0d | content date | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `model_scorecard.md` | ok | 2026-08-17 | 0d | file mtime | `python scripts/xfp/build_model_scorecard.py  (refresh step 4.97, Mondays only)` |
| `season_sim.json` | ok | 2026-08-14 | 3d | content date | `python scripts/xfp/run_season_sim.py` |
| `verdict_scorecard.csv` | ok | 2026-08-17 | 0d | file mtime | `python scripts/xfp/run_verdict_scorecard.py  (refresh step 4.97b, Mondays only)` |
| `weekly_optimizer.json` | STALE | 2026-08-14 | 3d | content date | `python scripts/xfp/run_weekly_optimizer.py` |
